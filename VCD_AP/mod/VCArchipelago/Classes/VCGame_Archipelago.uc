// The Archipelago game mode entry point.
//
// A VCGame subclass selected through a VCUIDataProvider_GameInfo entry whose
// GameClass is this class, so a level launches with
// ?Game=VCArchipelago.VCGame_Archipelago and this runs in place of VCGame. It
// watches the level's cleanliness, publishes state for the Archipelago client
// (see VCArchipelagoState), and mirrors the live value into the replicated GRI
// for the on-screen readout (see VCHUD_Archipelago).
//
// Cleanliness is the game's own value: 1 - FinalPenalty / StartingCleanupScore,
// where the punchout handler's ProcessMapState recomputes FinalPenalty. Every
// per-map handler extends VCPunchoutHandler_General, which owns those fields.
//
// Level access is gated two ways: the curated menu (VCGameViewportClient_Archipelago
// hides locked levels from the list) is the front door, and EnforceLevelGate here
// refuses a locked level that is reached some other way.
//
// Punch-out is event-driven: PunchoutFromGame below wraps the game's own flow
// and publishes the verdict (punched out, fired, speedrun) exactly once.
//
// TODO: detect collectibles as checks; make detection event-driven where the
// game gives an event; throttle the mess scan (calling ProcessMapState every
// second is a full scan).
class VCGame_Archipelago extends VCGame;

// The published state object. Not named "State": that is a reserved UnrealScript
// keyword (the state-machine feature).
var VCArchipelagoState APState;

// Highest cleanliness rung already published for the current map, and the last
// published percent. Reset per map because a fresh GameInfo spawns per level.
var int HighestReportedRung;
var int LastPublishedPercent;

// Scans in a row that saw no percent movement. The cleanliness probe is a full
// mess scan, so after enough idle scans it backs off to a slower cadence and
// snaps back to per-second the moment the percent moves again.
var int UnchangedScans;
var bool bScanBackedOff;

// Janitors under a timed speed effect, with the base speeds to restore.
// Same-level references only; the GameInfo and these arrays die with the
// level. The game itself never writes GroundSpeed after defaults, so a
// scale-and-restore cannot be clobbered.
var array<VCPawn> SpeedAffectedJanitors;
var array<float> SpeedAffectedBaseSpeeds;

// The GRI effect type of the running speed effect; TimedEffectNone when the
// speeds are at base.
var byte ActiveSpeedEffectType;

// Seconds a speed effect lasts; the HUD countdown shares this value through
// the replicated GRI slot.
const SpeedEffectDurationSeconds = 30.0;

// Reused load target for the trap queue file, so the 5 second poll does not
// pile up garbage objects between collections.
var VCArchipelagoTraps TrapQueueFile;

event InitGame(string Options, out string ErrorMessage)
{
    super.InitGame(Options, ErrorMessage);
    APState = new(self) class'VCArchipelagoState';
    // A config object starts from the last values written to the ini, which belong
    // to the previous level. Clear the per-level fields so this level rebuilds its
    // own rungs from its own cleanliness instead of inheriting the last level's.
    APState.APMilestones = "";
    APState.APCleanPct = 0;
    APState.APPunchedOut = 0;
    APState.APFired = 0;
    APState.APSpeedrun = 0;
    APState.APTrunkFinds = "";
    APState.APDigsiteGates = 0;
    APState.APFoundBob = 0;
    StampSeedTag();
    HighestReportedRung = 0;
    LastPublishedPercent = -1;
    UnchangedScans = 0;
    bScanBackedOff = false;
    SetTimer(1.0, true, 'PublishCleanliness');
    SetTimer(5.0, true, 'PollTraps');
    EnforceLevelGate();
}

// Reads the client-written unlocked set (Saves\VCArchipelagoGrants.sav, fresh via
// BasicLoadObject) and, if this level is not unlocked, returns the player to the
// Office. The Office and menu maps are always allowed. The client is the only
// writer of the grants file; the mod only reads it.
//
// This only ever runs in Archipelago mode: the class is instantiated only for a
// level launched as ?Game=VCArchipelago.VCGame_Archipelago. Cleanup and Speedrun
// use their own GameInfo, so normal play (including workshop maps) is untouched;
// workshop maps are refused only inside an Archipelago run, where they are never
// granted.
function EnforceLevelGate()
{
    local VCMapInfo MapInfo;
    local string mapName;

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.bIsOfficeLevel)
        return;

    mapName = WorldInfo.GetMapName(true);
    if (IsMapUnlocked(mapName))
    {
        `log("VCAP GATE map="$mapName$" allowed=true");
        return;
    }

    `log("VCAP GATE map="$mapName$" allowed=false locked; returning to Office");
    // Let the level finish loading before travelling out.
    SetTimer(1.0, false, 'BounceLockedLevel');
}

function bool IsMapUnlocked(string MapName)
{
    local VCArchipelagoGrants Grants;
    local string unlocked;

    Grants = new class'VCArchipelagoGrants';
    if (!class'Engine'.static.BasicLoadObject(Grants, "..\\..\\Saves\\VCArchipelagoGrants.sav", true, 1))
        return false;
    unlocked = Grants.UnlockedMaps;
    return unlocked != "" && InStr(","$unlocked$",", ","$MapName$",") != -1;
}

function BounceLockedLevel()
{
    local VCGameViewportClient ViewportClient;

    // Stop our timers so they do not fire against a level being torn down.
    ClearTimer('PublishCleanliness');
    ClearTimer('PollTraps');

    // The trophy handler is persistent (it lives on the viewport client and
    // survives travel) and holds a reference to this level's punchout handler.
    // The normal punch-out flow clears that; our abrupt travel does not, so the
    // old world would leak and garbage collection aborts (appError). Break the
    // reference here. The next level re-sets it on load.
    ViewportClient = VCGameViewportClient(class'Engine'.static.GetEngine().GameViewport);
    if (ViewportClient != None && ViewportClient.TrophyHandler != None)
        ViewportClient.TrophyHandler.PunchoutHandler = None;

    ConsoleCommand("open VC_JanitorOffice");
}

// Copies the connected seed's tag from the client-written traps file into the
// published state, so the client can tell this seed's state from another
// seed's leftovers. With no traps file the tag empties, which the client also
// ignores.
function StampSeedTag()
{
    if (TrapQueueFile == None)
        TrapQueueFile = new class'VCArchipelagoTraps';
    if (class'Engine'.static.BasicLoadObject(TrapQueueFile, "..\\..\\Saves\\VCArchipelagoTraps.sav", true, 1))
        APState.APSeedTag = TrapQueueFile.SeedTag;
    else
        APState.APSeedTag = "";
}

// Saves the published state, mirroring the fields that persist across levels
// into class defaults first: a new'd config object copies the class default
// object, and an instance SaveConfig never updates it.
function SaveAPState()
{
    class'VCArchipelagoState'.default.APSeq = APState.APSeq;
    class'VCArchipelagoState'.default.APTrapSeed = APState.APTrapSeed;
    class'VCArchipelagoState'.default.APTrapsApplied = APState.APTrapsApplied;
    APState.SaveConfig();
}

// Applies entries from the client-written queue (traps and useful supply
// drops), one per poll so a burst spaces itself out. The queue file is read
// fresh every time (config-style objects cache at startup; BasicLoadObject does
// not). The applied counter lives in the config state, never in memory alone,
// so a relaunch cannot replay entries.
function PollTraps()
{
    local VCMapInfo MapInfo;
    local array<string> Entries;
    local int I, EntryIndex;
    local string QueueType;

    // Queue entries only fire in a cleanable gameplay level.
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo == None || MapInfo.bIsOfficeLevel || APState == None)
        return;

    if (TrapQueueFile == None)
        TrapQueueFile = new class'VCArchipelagoTraps';
    if (!class'Engine'.static.BasicLoadObject(TrapQueueFile, "..\\..\\Saves\\VCArchipelagoTraps.sav", true, 1))
        return;

    // A client that connected mid-level rewrites the traps file. Adopt its tag
    // only when the level started without one: an already-stamped level keeps
    // its own seed, so switching seeds mid-level cannot cross-credit checks.
    if (APState.APSeedTag == "" && TrapQueueFile.SeedTag != "")
        APState.APSeedTag = TrapQueueFile.SeedTag;

    // A different seed's counter means this queue was never applied here. Start
    // it at the client's baseline: everything the player already held when the
    // session connected counts as applied, so no backlog is dumped.
    if (TrapQueueFile.SeedTag != APState.APTrapSeed)
    {
        APState.APTrapSeed = TrapQueueFile.SeedTag;
        APState.APTrapsApplied = int(TrapQueueFile.BaselineIndex);
        SaveAPState();
        return;
    }

    // The baseline can rise after the seed is latched (a reconnect, or the
    // client refining an early write). Raising the counter first means the
    // freshly baselined backlog can never apply.
    if (int(TrapQueueFile.BaselineIndex) > APState.APTrapsApplied)
    {
        APState.APTrapsApplied = int(TrapQueueFile.BaselineIndex);
        SaveAPState();
    }

    ParseStringIntoArray(TrapQueueFile.TrapQueue, Entries, ",", true);
    for (I = 0; I < Entries.Length; I++)
    {
        EntryIndex = int(Left(Entries[I], InStr(Entries[I], ":")));
        if (EntryIndex <= APState.APTrapsApplied)
            continue;
        QueueType = Mid(Entries[I], InStr(Entries[I], ":") + 1);
        ApplyQueueEntry(QueueType);
        APState.APTrapsApplied = EntryIndex;
        SaveAPState();
        return;
    }
}

function ApplyQueueEntry(string QueueType)
{
    `log("VCAP QUEUE type="$QueueType);
    if (QueueType ~= "MessDump")
    {
        SpawnMessDump();
    }
    else if (QueueType ~= "BucketSpill")
    {
        // A level with no bucket in play still owes a setback.
        if (!SpillNearestBucket())
            SpawnMessDump();
    }
    else if (QueueType ~= "Slowdown")
    {
        ScaleJanitorSpeeds(0.5,
            class'VCGameReplicationInfo_Archipelago'.const.TimedEffectSlowdown);
    }
    else if (QueueType ~= "Speedup")
    {
        ScaleJanitorSpeeds(2.0,
            class'VCGameReplicationInfo_Archipelago'.const.TimedEffectSpeedup);
    }
    else if (QueueType ~= "CleanBucket")
    {
        SpawnSupplyNearJanitor(class'VCBucket');
    }
    else if (QueueType ~= "EmptyBin")
    {
        SpawnSupplyNearJanitor(class'VCBin');
    }
}

// Sprays blood splats on the floor around the janitor. Splats spawn the same
// way the game's own footprints and mop drips do (a plain Spawn on a downward
// trace), and the live scan counts every VCSplat, so cleanliness drops
// legitimately and mopping recovers it.
function SpawnMessDump()
{
    local VCPawn Janitor;
    local Vector Start, HitLocation, HitNormal, Offset;
    local Actor Floor;
    local Rotator SplatRotation;
    local int I;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
        break;
    if (Janitor == None)
        return;

    for (I = 0; I < 10; I++)
    {
        Offset = VRand() * RandRange(48.0, 224.0);
        Offset.Z = 0.0;
        Start = Janitor.Location + Offset + vect(0, 0, 32);
        // World-geometry-only trace, straight down.
        Floor = Trace(HitLocation, HitNormal, Start - vect(0, 0, 512), Start, false);
        if (Floor == None || IsSplatForbiddenAt(HitLocation))
            continue;
        SplatRotation = Rotator(-HitNormal);
        SplatRotation.Roll = Rand(65536);
        Spawn(class'VCSplat_BloodyMop',,, HitLocation + HitNormal * 6.0, SplatRotation,, true);
    }
}

// Mirrors the game's own splat-placement checks: no splats in water or inside
// a designated no-splat volume.
function bool IsSplatForbiddenAt(Vector Point)
{
    local PhysicsVolume Volume;

    foreach WorldInfo.AllActors(class'PhysicsVolume', Volume)
    {
        if ((Volume.bWaterVolume || VCNoSplatVolume(Volume) != None)
            && Volume.ContainsPoint(Point))
        {
            return true;
        }
    }
    return false;
}

// Tips over the non-empty bucket nearest the janitor, using the bucket's own
// Spill (it empties the bucket and sprays saturation-scaled splats itself).
function bool SpillNearestBucket()
{
    local VCPawn Janitor;
    local VCBucket Bucket, Nearest;
    local float Distance, NearestDistance;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
        break;
    if (Janitor == None)
        return false;

    foreach DynamicActors(class'VCBucket', Bucket)
    {
        if (Bucket.bEmpty)
            continue;
        Distance = VSize(Bucket.Location - Janitor.Location);
        if (Nearest == None || Distance < NearestDistance)
        {
            Nearest = Bucket;
            NearestDistance = Distance;
        }
    }
    if (Nearest == None)
        return false;
    Nearest.Spill();
    return true;
}

// Scales every janitor's ground speed off its stored base for the effect
// duration and registers the countdown the HUD draws. Slowdown and speedup
// share one clock: a new effect rescales from the base speeds and replaces
// whichever is active, so multipliers never stack.
function ScaleJanitorSpeeds(float Multiplier, byte EffectType)
{
    local VCPawn Janitor;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local int Index;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        Index = SpeedAffectedJanitors.Find(Janitor);
        if (Index == -1)
        {
            SpeedAffectedJanitors.AddItem(Janitor);
            SpeedAffectedBaseSpeeds.AddItem(Janitor.GroundSpeed);
            Index = SpeedAffectedJanitors.Length - 1;
        }
        Janitor.GroundSpeed = SpeedAffectedBaseSpeeds[Index] * Multiplier;
    }
    SetTimer(SpeedEffectDurationSeconds, false, 'RestoreJanitorSpeeds');
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None)
    {
        if (ActiveSpeedEffectType != EffectType
            && ActiveSpeedEffectType
                != class'VCGameReplicationInfo_Archipelago'.const.TimedEffectNone)
        {
            ReplicatedInfo.ClearTimedEffect(ActiveSpeedEffectType);
        }
        ReplicatedInfo.StartTimedEffect(EffectType, SpeedEffectDurationSeconds);
    }
    ActiveSpeedEffectType = EffectType;
}

function RestoreJanitorSpeeds()
{
    local int I;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    for (I = 0; I < SpeedAffectedJanitors.Length; I++)
    {
        if (SpeedAffectedJanitors[I] != None)
            SpeedAffectedJanitors[I].GroundSpeed = SpeedAffectedBaseSpeeds[I];
    }
    SpeedAffectedJanitors.Length = 0;
    SpeedAffectedBaseSpeeds.Length = 0;
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None
        && ActiveSpeedEffectType
            != class'VCGameReplicationInfo_Archipelago'.const.TimedEffectNone)
    {
        ReplicatedInfo.ClearTimedEffect(ActiveSpeedEffectType);
    }
    ActiveSpeedEffectType = class'VCGameReplicationInfo_Archipelago'.const.TimedEffectNone;
}

// Drops a supply item on the floor near the janitor. A plain spawn is exactly
// what the game's own dispensers vend: a fresh VCBucket is full of clean water
// and a fresh VCBin is empty, and both score as misplaced equipment if left
// out, same as a vended one.
function SpawnSupplyNearJanitor(class<VCDebris> SupplyClass)
{
    local VCPawn Janitor;
    local Vector Start, HitLocation, HitNormal, Offset;
    local Actor Floor;
    local int I;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
        break;
    if (Janitor == None)
        return;

    for (I = 0; I < 10; I++)
    {
        Offset = VRand() * RandRange(64.0, 160.0);
        Offset.Z = 0.0;
        Start = Janitor.Location + Offset + vect(0, 0, 32);
        // World-geometry-only trace, straight down.
        Floor = Trace(HitLocation, HitNormal, Start - vect(0, 0, 512), Start, false);
        if (Floor == None)
            continue;
        if (Spawn(SupplyClass,,, HitLocation + vect(0, 0, 24)) != None)
            return;
    }
    // No clear floor spot took the spawn; drop it from above the janitor.
    Spawn(SupplyClass,,, Janitor.Location + vect(0, 0, 96));
}

// The game's single legitimate punch-out path: the punch machine and the level
// time limit both land here, and the flow inside super arms the PunchoutDelay
// travel timer only when a punch-out actually proceeds. So the timer turning
// active across the super call marks exactly one real punch-out, after
// CalculateResults has filled JobStatus and before the level travels away.
function PunchoutFromGame(VCPunchMachine PunchoutMachine)
{
    local VCPunchoutHandler_General Handler;
    local bool bWasPunchingOut;

    bWasPunchingOut = IsTimerActive('PunchoutDelay');
    super.PunchoutFromGame(PunchoutMachine);
    if (bWasPunchingOut || !IsTimerActive('PunchoutDelay'))
        return;

    // Catch the final cleanliness rungs, then stop our timers: the level is on
    // its way out, and the handler's results are final now.
    PublishCleanliness();
    ClearTimer('PublishCleanliness');
    ClearTimer('PollTraps');

    Handler = VCPunchoutHandler_General(PunchoutHandler);
    if (Handler == None || APState == None)
        return;

    APState.APMap = WorldInfo.GetMapName(true);
    APState.APPunchedOut = 1;
    if (Handler.JobStatus.bStatus)
        APState.APFired = 1;
    else
    {
        // Trophies only bank on a punch-out in good standing (a fired one runs
        // ClearTrophies), so the trunk scan mirrors that.
        APState.APTrunkFinds = CollectTrunkFinds();
    }
    // The game's own speedrun standard, evaluated here because Archipelago is
    // its own mode: status bit 1 or 2 (at least 95 percent clean) inside 75
    // percent of the map's par time, dilated for player count.
    if ((Handler.JobStatus.StatusCode & 3) != 0
        && Handler.CleanupTimeLimitGamePar > 0.0
        && Handler.CleanupTimeDilated <= 0.75 * Handler.CleanupTimeLimitGamePar)
    {
        APState.APSpeedrun = 1;
    }
    APState.APSeq = APState.APSeq + 1;
    SaveAPState();
    `log("VCAP PUNCHOUT map="$APState.APMap$" fired="$APState.APFired$" speedrun="$APState.APSpeedrun);
}

// Tokens for everything in the janitor's trunk that maps to a check: a
// collectible's class name, or a Bob note's archetype name. Both are unique
// across the whole game, so the client resolves each token to its home level's
// location no matter where it was banked.
function string CollectTrunkFinds()
{
    local VCGameViewportClient ViewportClient;
    local array<VCDebris> TrunkItems;
    local string Token, Finds;
    local int I;

    Finds = "";
    ViewportClient = VCGameViewportClient(class'Engine'.static.GetEngine().GameViewport);
    if (ViewportClient == None || ViewportClient.TrophyHandler == None)
        return Finds;
    TrunkItems = ViewportClient.TrophyHandler.GetTrunkActors();
    for (I = 0; I < TrunkItems.Length; I++)
    {
        if (TrunkItems[I] == None)
            continue;
        Token = "";
        if (InStr(string(TrunkItems[I].Class.Name), "VCSpecialDrop") == 0)
            Token = string(TrunkItems[I].Class.Name);
        else if (TrunkItems[I].ObjectArchetype != None
            && InStr(string(TrunkItems[I].ObjectArchetype.Name), "Note_Bob_") == 0)
        {
            Token = string(TrunkItems[I].ObjectArchetype.Name);
        }
        if (Token == "" || InStr(","$Finds$",", ","$Token$",") != -1)
            continue;
        if (Finds == "")
            Finds = Token;
        else
            Finds = Finds $ "," $ Token;
    }
    return Finds;
}

// The game routes every global stat save through here (VCStatsData.SaveData
// calls the GameInfo). The two Bob events fire from the Digsite Kismet.
function GlobalStatChanged(string KeyName, string NewValue)
{
    local bool bTruthy;

    super.GlobalStatChanged(KeyName, NewValue);
    if (APState == None)
        return;
    bTruthy = NewValue == "1" || NewValue ~= "true";
    if (!bTruthy)
        return;
    if (KeyName ~= "bOpenedDigsiteGates" && APState.APDigsiteGates == 0)
    {
        APState.APDigsiteGates = 1;
        APState.APMap = WorldInfo.GetMapName(true);
        APState.APSeq = APState.APSeq + 1;
        SaveAPState();
        `log("VCAP BOB event=DigsiteGates");
    }
    else if (KeyName ~= "bFoundBob" && APState.APFoundBob == 0)
    {
        APState.APFoundBob = 1;
        APState.APMap = WorldInfo.GetMapName(true);
        APState.APSeq = APState.APSeq + 1;
        SaveAPState();
        `log("VCAP BOB event=FoundBob");
    }
}

function PublishCleanliness()
{
    local VCPunchoutHandler_General Handler;
    local VCMapInfo MapInfo;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local float clean;
    local int percent, rung;
    local bool changed;

    // Never probe the Office or menu maps; they are not cleanable levels.
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.bIsOfficeLevel)
        return;

    Handler = VCPunchoutHandler_General(PunchoutHandler);
    if (Handler == None || Handler.StartingCleanupScore <= 0.0 || APState == None)
        return;

    Handler.ProcessMapState(self, None);
    clean = 1.0 - (Handler.FinalPenalty / Handler.StartingCleanupScore);
    percent = int(clean * 100.0);

    // Hundredths for the on-screen readout, floored so the display never
    // overstates cleanliness. Rides the GRI so co-op guests see it too.
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None)
    {
        ReplicatedInfo.CleanlinessHundredths = FFloor(clean * 10000.0);
        ReplicatedInfo.bCleanlinessSampled = true;
    }

    changed = false;
    if (percent != LastPublishedPercent)
    {
        LastPublishedPercent = percent;
        APState.APCleanPct = percent;
        APState.APMap = WorldInfo.GetMapName(true);
        changed = true;
        UnchangedScans = 0;
    }
    else
    {
        UnchangedScans += 1;
    }

    // Publish each newly crossed five percent rung, so a jump does not skip one.
    rung = (percent / 5) * 5;
    while (HighestReportedRung < rung)
    {
        HighestReportedRung += 5;
        if (APState.APMilestones == "")
            APState.APMilestones = string(HighestReportedRung);
        else
            APState.APMilestones = APState.APMilestones $ "," $ string(HighestReportedRung);
        changed = true;
    }

    if (changed)
    {
        APState.APSeq = APState.APSeq + 1;
        SaveAPState();
    }

    // Back off to a five second cadence after thirty idle scans; return to
    // per-second the moment the percent moves. Rung publication is unaffected
    // beyond the added latency, and the punch-out hook runs its own final scan.
    if (!bScanBackedOff && UnchangedScans >= 30)
    {
        bScanBackedOff = true;
        SetTimer(5.0, true, 'PublishCleanliness');
    }
    else if (bScanBackedOff && UnchangedScans == 0)
    {
        bScanBackedOff = false;
        SetTimer(1.0, true, 'PublishCleanliness');
    }
}

defaultproperties
{
    HUDType=Class'VCArchipelago.VCHUD_Archipelago'
    GameReplicationInfoClass=Class'VCArchipelago.VCGameReplicationInfo_Archipelago'
}
