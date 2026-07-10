// The Archipelago game mode entry point.
//
// A VCGame subclass selected through a VCUIDataProvider_GameInfo entry whose
// GameClass is this class, so a level launches with
// ?Game=VCArchipelago.VCGame_Archipelago and this runs in place of VCGame. It
// watches the level's cleanliness, publishes state for the Archipelago client
// (see VCArchipelagoState), and mirrors the live value and the level's next
// remaining milestone into the replicated GRI for the on-screen readout
// (see VCHUD_Archipelago).
//
// Cleanliness is the game's own value: 1 - FinalPenalty / StartingCleanupScore,
// where the punchout handler's ProcessMapState recomputes FinalPenalty. Every
// per-map handler extends VCPunchoutHandler_General, which owns those fields.
// Two Digsite adjustments ride on top: the crate stacking zones widen to the
// crate archetypes the level spawns, and the published value credits partial
// sand pit fill gradually (see PublishCleanliness).
//
// Level access is gated two ways: the curated menu (VCGameViewportClient_Archipelago
// hides locked levels from the list) is the front door, and EnforceLevelGate here
// refuses a locked level that is reached some other way.
//
// Toolsanity locks tools and machines per level: EnforceToolLocks publishes
// the unlocked set to the GRI each second, holds locked machines disabled,
// and sweeps locked tools out of inventories. The carry-lock hands subclass
// and the PRI machine gate read the GRI mask, so co-op guests enforce the
// same locks.
//
// Punch-out is event-driven: PunchoutFromGame below wraps the game's own flow
// and publishes the verdict (punched out, fired, speedrun) exactly once.
//
// The mess scan is event-driven: the GRI's mess counters signal every splat
// and debris change (NotifyMessChanged), which runs a debounced immediate
// scan, and a 1s floor timer catches scoring changes that add or remove no
// actor (a barrel uprighted, a medpack restored, an incinerator door closed).
class VCGame_Archipelago extends VCGame;

// The published state object. Not named "State": that is a reserved UnrealScript
// keyword (the state-machine feature).
var VCArchipelagoState APState;

// Highest cleanliness rung already published for the current map, and the last
// published percent. Reset per map because a fresh GameInfo spawns per level.
var int HighestReportedRung;
var int LastPublishedPercent;

// Set when the level is on its way out (punch-out or bounce), so a queued
// burst scan cannot run against a torn-down level.
var bool bCleanlinessProbeStopped;

// A splat or debris change coalesces into one scan after this delay, so a
// burst (a spill, a mess-dump trap, a mop sweep clearing several splats)
// folds into a single scan instead of one per actor.
const CleanlinessBurstDelaySeconds = 0.2;

// Janitors under a timed speed effect, with the base speeds to restore.
// Same-level references only; the GameInfo and these arrays die with the
// level. The game itself never writes GroundSpeed after defaults, so a
// scale-and-restore cannot be clobbered.
var array<VCPawn> SpeedAffectedJanitors;
var array<float> SpeedAffectedBaseSpeeds;

// The GRI effect type of the running speed effect; TimedEffectNone when the
// speeds are at base. The multiplier is kept alongside so a janitor spawning
// mid effect can be scaled to match.
var byte ActiveSpeedEffectType;
var float ActiveSpeedMultiplier;

// Seconds a timed trap effect lasts (speed and gravity alike); the HUD
// countdown shares this value through the replicated GRI slot.
const TimedEffectDurationSeconds = 30.0;

// Zero gravity trap state: what to put back when the effect ends. The two
// volume arrays pair index for index. The active flag guards the restore
// paths and keeps a second trap from capturing trap state as the baseline.
var bool bZeroGravityActive;
var float ZeroGravitySavedWorldGravityZ;
var array<VCLowGravityVolume> ZeroGravityVolumes;
var array<byte> ZeroGravityVolumeWasEnabled;

// The world gravity a zero gravity trap applies outside the gravity levels.
// Mildly negative, never zero or positive: everything still settles, so a
// missed restore self-recovers and a jumping janitor always lands.
const ZeroGravityWorldGravityZ = -60.0;

// The gravity console is watched while the trap holds the volumes: a player
// toggle mid-trap ends the effect instead of being reverted by the restore.
// The cancel waits one extra watch tick so a staggered Kismet cycle finishes.
const GravityConsoleWatchInterval = 0.25;
var int GravityToggleTicksSeen;

// A pending defensive gravity restore rechecks at this interval until the
// game's own save-state load has finished (bMatchHasBegun), because the
// volumes' saved flip applies during that load.
const PendingGravityRestorePollInterval = 0.5;

// The save hooks lift the pending marker only when no trap runs and none
// ended within this grace, because a stepped save spans ticks and its volume
// snapshot may predate a restore by a moment.
const GravityMarkerSaveGraceSeconds = 10.0;
var float LastZeroGravityEndSeconds;

// The magnet trap's reach and pull speeds. The pull sets rigid-body velocity
// instead of adding an impulse, so every piece moves at a bounded speed no
// matter its mass. The speed grows with distance (scaled, then clamped) so far
// pieces arrive on the janitor about as fast as near ones. Pieces closer than
// the dead zone are already at the janitor's feet and stay put.
const MagnetizeRadius         = 1024.0;
const MagnetizeDeadZone       = 64.0;
const MagnetizePullSpeedScale = 1.25;
const MagnetizeMinPullSpeed   = 340.0;
const MagnetizeMaxPullSpeed   = 1000.0;
const MagnetizeLiftSpeed      = 190.0;

// Reused load target for the trap queue file, so the 5 second poll does not
// pile up garbage objects between collections.
var VCArchipelagoTraps TrapQueueFile;

// Reused load target for the client-written milestones file.
var VCArchipelagoMilestones MilestoneFile;

// Reused load target for the client-written link-event file, and its death
// link flag: whether any one janitor's death takes the whole crew with it.
var VCArchipelagoLinks LinksFile;
var bool bDeathLinkOn;

// Latched while a link kill runs (an inbound death or the crew sweep), so
// the deaths it causes never count as organic and never sweep again.
var bool bLinkDeathSweep;

// Reused load target for the client-written grants file (toolsanity reads).
var VCArchipelagoGrants GrantsFile;

// Toolsanity: the last applied unlocked-tools mask, to catch a mid-level
// unlock transition (the sniffer is the one tool granted in place; the rest
// re-enable machines or floor pickups that already exist in the level).
var int AppliedToolsMask;

// Dev override for the measurement tour: while active it replaces the
// grants-driven mask. In-memory only, so a level reload drops it.
var bool bDevToolMaskActive;
var int DevToolMask;

// Toolsanity: the tools the level HAS, for the HUD unlock panel. Constant per
// level, so it is read once from the grants file and cached (0 means no
// toolsanity data, which the panel shows as all-available).
var bool bPresentToolsMaskRead;
var int PresentToolsMaskCache;

// Self-Cleaning Mop: whether the current level's mop never dirties. The client
// only ever adds a level to the grant list, so this is monotonic: the poll
// re-reads the grants file while it is still off, then leaves it latched, so a
// grant received while already in the level takes effect without a reload. A
// short poll pins every mop's saturation to zero, faster than the tool-lock pass
// so a furious mopper cannot reach the paint threshold between ticks.
var bool bSelfCleaningMap;
const SelfCleaningMopPollInterval = 0.25;

// Squeaky Clean Boots: whether the current level's janitor never tracks bloody
// footprints. Monotonic and re-read the same way as the self-cleaning flag. The
// same short poll pins every janitor's foot blood to zero, so it never reaches
// the one-unit threshold a footstep needs to stamp a print.
var bool bSqueakyBootsMap;
const SqueakyBootsPollInterval = 0.25;

// Original machine tuning cached at first lock, restored on unlock, because
// mappers tune these per instance and a blanket default would clobber that.
struct BinDispensorLockInfo
{
    var VCBinDispensor Dispensor;
    var bool bFrontDisabled;
    var bool bBackDisabled;
};
var array<BinDispensorLockInfo> BinDispensorLocks;

struct BucketDispensorLockInfo
{
    var VCBucketDispensor Dispensor;
    var bool bFrontDisabled;
    var bool bBackDisabled;
};
var array<BucketDispensorLockInfo> BucketDispensorLocks;

struct IncineratorLockInfo
{
    var VCIncinerator Incinerator;
    var float BurnRateScale;
};
var array<IncineratorLockInfo> IncineratorLocks;

struct DisposalVolumeLockInfo
{
    var VCDisposalVolume Volume;
    var float DisposalRate;
    var bool bInstantDisposal;
};
var array<DisposalVolumeLockInfo> DisposalVolumeLocks;

// Shark pools whose sharks are despawned while the incinerator group is
// locked, so they can be respawned on unlock. The sharks eat within a
// fraction of a second, too fast to intercept by clearing targets on a poll.
var array<VCSharkDisposalVolume> SharkVolumesDespawned;

event InitGame(string Options, out string ErrorMessage)
{
    super.InitGame(Options, ErrorMessage);
    APState = new(self) class'VCArchipelagoState';
    // A config object starts from the last values written to the ini, which belong
    // to the previous level. Clear the per-level fields so this level rebuilds its
    // own rungs from its own cleanliness instead of inheriting the last level's.
    APState.APMilestones = "";
    APState.APCleanPct = 0;
    APState.APStartScore = 0;
    APState.APPunchedOut = 0;
    APState.APFired = 0;
    APState.APSpeedrun = 0;
    APState.APTrunkFinds = "";
    APState.APDigsiteGates = 0;
    APState.APFoundBob = 0;
    StampSeedTag();
    // Link entries pending at level start predate the level and are dropped,
    // never applied, so a death from minutes ago cannot fire on load.
    BaselineLinksQueue();
    HighestReportedRung = 0;
    LastPublishedPercent = -1;
    bCleanlinessProbeStopped = false;
    bPresentToolsMaskRead = false;
    bSelfCleaningMap = false;
    bSqueakyBootsMap = false;
    AppliedToolsMask = class'VCGameReplicationInfo_Archipelago'.const.ToolMaskAll;
    SetTimer(1.0, true, 'PublishCleanliness');
    SetTimer(5.0, true, 'PollTraps');
    SetTimer(5.0, true, 'PollLinks');
    SetTimer(1.0, true, 'PollMilestones');
    SetTimer(1.0, true, 'EnforceToolLocks');
    SetTimer(SelfCleaningMopPollInterval, true, 'PollSelfCleaningMop');
    SetTimer(SqueakyBootsPollInterval, true, 'PollSqueakyBoots');
    // A pending marker for this map means a zero gravity trap flipped its
    // volumes and no save has confirmed them since; put the captured states
    // back once the save-state load finishes.
    if (APState.APGravityRestoreMap != ""
        && PendingGravityRestoreMap() ~= WorldInfo.GetMapName(true))
    {
        SetTimer(PendingGravityRestorePollInterval, true,
                 'ApplyPendingGravityRestore');
    }
    EnforceLevelGate();
}

// The GRI exists by now (the base spawns it before this) and no janitor has
// spawned yet, so publishing the boots and mop flags here means the pawn and
// mop subclasses suppress from the very first step, with no first-poll gap.
event PostBeginPlay()
{
    super.PostBeginPlay();
    PublishSqueakyBootsFlag();
    PublishSelfCleaningMopFlag();
    PublishToolMasks(CurrentToolsMask());
}

// Grants the stock default inventory, then swaps the stock hands for the
// carry-lock subclass and strips whatever the level's toolsanity state locks.
// Runs server-side on every spawn and respawn, so co-op guests and deaths are
// covered without extra plumbing.
function AddDefaultInventory(Pawn PlayerPawn)
{
    super.AddDefaultInventory(PlayerPawn);
    SwapInHandsSubclass(PlayerPawn);
    SwapInMopSubclass(PlayerPawn);
    if (VCPawn(PlayerPawn) != None)
        ApplyPawnInventoryLocks(VCPawn(PlayerPawn), CurrentToolsMask());
}

// Runs on every spawn after the engine resets GroundSpeed to the class
// default (which happens after the inventory grant), so a mid-effect scale
// applied any earlier would be wiped; it lands here instead.
function SetPlayerDefaults(Pawn PlayerPawn)
{
    super.SetPlayerDefaults(PlayerPawn);
    ScaleOneJanitor(VCPawn(PlayerPawn));
}

function SwapInHandsSubclass(Pawn PlayerPawn)
{
    local VCWeap_Hands Candidate, StockHands;
    local bool bWasActive;

    if (PlayerPawn == None || PlayerPawn.InvManager == None)
        return;
    // Only the exact stock class is swapped: a map that overrides the hands
    // slot with its own weapon keeps it, and a swapped pawn is left alone.
    foreach PlayerPawn.InvManager.InventoryActors(class'VCWeap_Hands', Candidate)
    {
        if (Candidate.Class == class'VCWeap_Hands')
        {
            StockHands = Candidate;
            break;
        }
    }
    if (StockHands == None)
        return;
    bWasActive = (PlayerPawn.Weapon == StockHands);
    PlayerPawn.InvManager.RemoveFromInventory(StockHands);
    StockHands.Destroy();
    PlayerPawn.CreateInventory(class'VCWeap_Hands_Archipelago', !bWasActive);
}

// Swaps the stock mop for the Self-Cleaning Mop subclass, so a self-cleaning
// level holds saturation at zero at its source. Mirrors SwapInHandsSubclass:
// only the exact stock class is swapped, so a map with its own mop keeps it,
// and the subclass behaves exactly like the stock mop unless the level's
// self-cleaning flag is set.
function SwapInMopSubclass(Pawn PlayerPawn)
{
    local VCWeap_Mop Candidate, StockMop;
    local bool bWasActive;

    if (PlayerPawn == None || PlayerPawn.InvManager == None)
        return;
    foreach PlayerPawn.InvManager.InventoryActors(class'VCWeap_Mop', Candidate)
    {
        if (Candidate.Class == class'VCWeap_Mop')
        {
            StockMop = Candidate;
            break;
        }
    }
    if (StockMop == None)
        return;
    bWasActive = (PlayerPawn.Weapon == StockMop);
    PlayerPawn.InvManager.RemoveFromInventory(StockMop);
    StockMop.Destroy();
    PlayerPawn.CreateInventory(class'VCWeap_Mop_Archipelago', !bWasActive);
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

// The dev level override lives on the viewport client because that object
// persists across level travel; the GameInfo dies with each level. It only
// takes effect standalone, so a flag left on cannot leak into a co-op
// session started without a relaunch.
function bool IsDevLevelOverrideActive()
{
    local VCGameViewportClient_Archipelago ViewportClient;

    if (WorldInfo.NetMode != NM_Standalone)
        return false;
    ViewportClient = VCGameViewportClient_Archipelago(
        class'Engine'.static.GetEngine().GameViewport);
    return ViewportClient != None && ViewportClient.bDevUnlockAllLevels;
}

function bool IsMapUnlocked(string MapName)
{
    local VCArchipelagoGrants Grants;
    local string unlocked;

    if (IsDevLevelOverrideActive())
        return true;
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
    bCleanlinessProbeStopped = true;
    ClearTimer('PublishCleanliness');
    ClearTimer('PublishCleanlinessBurst');
    ClearTimer('PollTraps');
    ClearTimer('PollLinks');
    ClearTimer('PollMilestones');
    ClearTimer('EnforceToolLocks');
    ClearTimer('PollSelfCleaningMop');
    ClearTimer('PollSqueakyBoots');
    RestoreGravity();

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
    class'VCArchipelagoState'.default.APDeathCount = APState.APDeathCount;
    class'VCArchipelagoState'.default.APLastSpawn = APState.APLastSpawn;
    class'VCArchipelagoState'.default.APLinkSession = APState.APLinkSession;
    class'VCArchipelagoState'.default.APLinksApplied = APState.APLinksApplied;
    class'VCArchipelagoState'.default.APGravityRestoreMap = APState.APGravityRestoreMap;
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
        // The marker feeds the client's TrapLink bounce. Item-queue spawns
        // only: a linked trap from the link queue must never re-broadcast.
        APState.APLastSpawn = string(EntryIndex) $ ":" $ QueueType;
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
    else if (QueueType ~= "Magnetize")
    {
        Magnetize();
    }
    else if (QueueType ~= "ZeroGravity")
    {
        StartZeroGravity();
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

// Loads the client-written link-event file once per poll, into the reused
// target, and mirrors its death link flag. False when the file is absent.
function bool LoadLinksFile()
{
    if (APState == None)
        return false;
    if (LinksFile == None)
        LinksFile = new class'VCArchipelagoLinks';
    if (!class'Engine'.static.BasicLoadObject(LinksFile, "..\\..\\Saves\\VCArchipelagoLinks.sav", true, 1))
    {
        bDeathLinkOn = false;
        return false;
    }
    bDeathLinkOn = LinksFile.DeathLinkOn == "1";
    return true;
}

// Consumes every pending link entry without applying it: the applied counter
// jumps to the newest index in the file. Runs at level start, on a session
// tag change, and on every poll outside a cleanable level, so an entry only
// ever applies when it arrives while a cleanable level is live.
function BaselineLinksQueue()
{
    local array<string> Entries;
    local int I, EntryIndex, Highest;

    if (!LoadLinksFile())
        return;
    ParseStringIntoArray(LinksFile.Entries, Entries, ",", true);
    Highest = 0;
    for (I = 0; I < Entries.Length; I++)
    {
        EntryIndex = int(Left(Entries[I], InStr(Entries[I], ":")));
        if (EntryIndex > Highest)
            Highest = EntryIndex;
    }
    if (LinksFile.SessionTag != APState.APLinkSession
        || Highest > APState.APLinksApplied)
    {
        APState.APLinkSession = LinksFile.SessionTag;
        APState.APLinksApplied = Highest;
        SaveAPState();
    }
}

// Applies entries from the client-written link-event queue (inbound deaths
// and linked traps), one per poll like the item queue. A new session tag or
// a poll outside a cleanable level baselines instead: those entries are
// dropped, never held, so a stale death cannot fire on a later level load.
function PollLinks()
{
    local VCMapInfo MapInfo;
    local array<string> Entries;
    local int I, EntryIndex;

    if (!LoadLinksFile())
        return;
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (LinksFile.SessionTag != APState.APLinkSession
        || MapInfo == None || MapInfo.bIsOfficeLevel)
    {
        BaselineLinksQueue();
        return;
    }
    ParseStringIntoArray(LinksFile.Entries, Entries, ",", true);
    for (I = 0; I < Entries.Length; I++)
    {
        EntryIndex = int(Left(Entries[I], InStr(Entries[I], ":")));
        if (EntryIndex <= APState.APLinksApplied)
            continue;
        ApplyLinkEntry(Mid(Entries[I], InStr(Entries[I], ":") + 1));
        APState.APLinksApplied = EntryIndex;
        SaveAPState();
        return;
    }
}

function ApplyLinkEntry(string EntryType)
{
    `log("VCAP LINK type="$EntryType);
    if (EntryType ~= "Death")
        KillAllJanitors(None);
    else
        ApplyQueueEntry(EntryType);
}

// Kills every living janitor, barring the one whose death triggered a sweep.
// The latch keeps the deaths this causes from counting as organic or
// sweeping again, so a link kill can never echo back out or cascade.
function KillAllJanitors(Pawn AlreadyDead)
{
    local VCPawn Janitor;
    local array<VCPawn> Janitors;
    local int I;
    local class<DamageType> LinkDamageType;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        if (Janitor.Health > 0 && Janitor != AlreadyDead)
            Janitors.AddItem(Janitor);
    }
    if (Janitors.Length == 0)
        return;
    // The game's own gib damage type; enough damage to put any janitor down.
    LinkDamageType = class<DamageType>(DynamicLoadObject(
        "VisceraGameContent.VCDmgType_Dynamite", class'Core.Class'));
    bLinkDeathSweep = true;
    for (I = 0; I < Janitors.Length; I++)
    {
        Janitors[I].TakeDamage(1000, None, Janitors[I].Location,
            vect(0, 0, 0), LinkDamageType);
    }
    bLinkDeathSweep = false;
}

// Counts every organic janitor death for the client's DeathLink bounce and,
// with death link on, takes the rest of the crew down with it. Deaths a link
// kill causes are latched out above, so they neither count nor sweep.
function Killed(Controller Killer, Controller KilledPlayer, Pawn KilledPawn, class<DamageType> DamageType)
{
    local VCMapInfo MapInfo;

    super.Killed(Killer, KilledPlayer, KilledPawn, DamageType);
    if (bLinkDeathSweep || APState == None)
        return;
    if (KilledPlayer == None || !KilledPlayer.bIsPlayer)
        return;
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo == None || MapInfo.bIsOfficeLevel)
        return;
    APState.APDeathCount = APState.APDeathCount + 1;
    SaveAPState();
    `log("VCAP DEATH count="$APState.APDeathCount);
    if (bDeathLinkOn)
        KillAllJanitors(KilledPawn);
}

// Mirrors the next milestone from the client-written milestones file into the
// replicated GRI for the HUD, so co-op guests see it too. Server-confirmed
// data only: the file lists, per level, the percents whose check the server
// has not confirmed, so the indicator never runs ahead of the server.
function PollMilestones()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local bool bFileCurrent;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo == None)
        return;
    bFileCurrent = LoadMilestoneFile();
    ReplicatedInfo.NextMilestonePercent = ReadNextMilestonePercent(bFileCurrent);
    ReplicatedInfo.bSpeedrunOutstanding = ReadSpeedrunOutstanding(bFileCurrent);
}

// Loads the client-written milestones file once per poll, into the reused
// target. False without trustworthy same-seed data (no connected seed, no
// file, another seed's file).
function bool LoadMilestoneFile()
{
    if (APState == None || APState.APSeedTag == "")
        return false;
    if (MilestoneFile == None)
        MilestoneFile = new class'VCArchipelagoMilestones';
    return class'Engine'.static.BasicLoadObject(MilestoneFile,
        "..\\..\\Saves\\VCArchipelagoMilestones.sav", true, 1)
        && MilestoneFile.SeedTag == APState.APSeedTag;
}

// Whether the current map's Speedrun check is still outstanding, from the
// already-loaded milestones file. False without trustworthy same-seed data,
// so the HUD timer stays hidden until the client confirms the seed.
function bool ReadSpeedrunOutstanding(bool bFileCurrent)
{
    if (!bFileCurrent)
        return false;
    return InStr("," $ MilestoneFile.SpeedrunOutstandingMaps $ ",",
        "," $ WorldInfo.GetMapName(true) $ ",") != -1;
}

// The lowest percent the server still misses for the current map, from the
// already-loaded milestones file: Unknown without trustworthy same-seed data
// (or a map absent from it), Cleared when the map is listed with nothing
// remaining.
function int ReadNextMilestonePercent(bool bFileCurrent)
{
    local array<string> MapEntries, PercentTexts;
    local string Remaining;
    local int I, J, ColonAt, Percent, Lowest;

    if (!bFileCurrent)
        return class'VCGameReplicationInfo_Archipelago'.const.NextMilestoneUnknown;

    ParseStringIntoArray(MilestoneFile.RemainingByMap, MapEntries, ",", true);
    for (I = 0; I < MapEntries.Length; I++)
    {
        ColonAt = InStr(MapEntries[I], ":");
        if (ColonAt == -1 || Left(MapEntries[I], ColonAt) != WorldInfo.GetMapName(true))
            continue;
        Remaining = Mid(MapEntries[I], ColonAt + 1);
        ParseStringIntoArray(Remaining, PercentTexts, " ", true);
        Lowest = class'VCGameReplicationInfo_Archipelago'.const.NextMilestoneCleared;
        for (J = 0; J < PercentTexts.Length; J++)
        {
            Percent = int(PercentTexts[J]);
            if (Percent > 0 && (Lowest <= 0 || Percent < Lowest))
                Lowest = Percent;
        }
        return Lowest;
    }
    return class'VCGameReplicationInfo_Archipelago'.const.NextMilestoneUnknown;
}

// Toolsanity: the effective unlocked-tools mask for the current level. The
// Office is the hub and is never locked; the dev override wins over the
// client-written grants during the measurement tour.
function int CurrentToolsMask()
{
    local VCMapInfo MapInfo;

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.bIsOfficeLevel)
        return class'VCGameReplicationInfo_Archipelago'.const.ToolMaskAll;
    if (bDevToolMaskActive)
        return DevToolMask;
    return ReadUnlockedToolsMask(WorldInfo.GetMapName(true));
}

// Reads the level's unlocked tool keys from the client-written grants file. A
// map absent from the string (or no file, or an old client) has toolsanity
// off, so everything stays unlocked and stock behavior is the default.
function int ReadUnlockedToolsMask(string MapName)
{
    local array<string> MapEntries, ToolKeys;
    local int I, J, ColonAt, Mask;

    if (GrantsFile == None)
        GrantsFile = new class'VCArchipelagoGrants';
    if (!class'Engine'.static.BasicLoadObject(GrantsFile, "..\\..\\Saves\\VCArchipelagoGrants.sav", true, 1)
        || GrantsFile.UnlockedTools == "")
    {
        return class'VCGameReplicationInfo_Archipelago'.const.ToolMaskAll;
    }
    ParseStringIntoArray(GrantsFile.UnlockedTools, MapEntries, ",", true);
    for (I = 0; I < MapEntries.Length; I++)
    {
        ColonAt = InStr(MapEntries[I], ":");
        if (ColonAt == -1 || Left(MapEntries[I], ColonAt) != MapName)
            continue;
        Mask = 0;
        ParseStringIntoArray(Mid(MapEntries[I], ColonAt + 1), ToolKeys, " ", true);
        for (J = 0; J < ToolKeys.Length; J++)
        {
            Mask = Mask
                | class'VCGameReplicationInfo_Archipelago'.static.ToolBitForKey(ToolKeys[J]);
        }
        return Mask;
    }
    return class'VCGameReplicationInfo_Archipelago'.const.ToolMaskAll;
}

// Reads the level's present tool keys (the superset the HUD panel colors).
// Returns 0 when the map has no toolsanity data (no file, old client, or a
// toolsanity-off seed), which the panel shows as an all-available fallback.
function int ReadPresentToolsMask(string MapName)
{
    local array<string> MapEntries, ToolKeys;
    local int I, J, ColonAt, Mask;

    if (GrantsFile == None)
        GrantsFile = new class'VCArchipelagoGrants';
    if (!class'Engine'.static.BasicLoadObject(GrantsFile, "..\\..\\Saves\\VCArchipelagoGrants.sav", true, 1)
        || GrantsFile.PresentTools == "")
    {
        return 0;
    }
    ParseStringIntoArray(GrantsFile.PresentTools, MapEntries, ",", true);
    for (I = 0; I < MapEntries.Length; I++)
    {
        ColonAt = InStr(MapEntries[I], ":");
        if (ColonAt == -1 || Left(MapEntries[I], ColonAt) != MapName)
            continue;
        ParseStringIntoArray(Mid(MapEntries[I], ColonAt + 1), ToolKeys, " ", true);
        for (J = 0; J < ToolKeys.Length; J++)
        {
            Mask = Mask
                | class'VCGameReplicationInfo_Archipelago'.static.ToolBitForKey(ToolKeys[J]);
        }
        return Mask;
    }
    return 0;
}

// Reads whether the current level's mop never dirties, from the client-written
// grants file. A map absent from the list dirties normally (absent means off).
function bool IsSelfCleaningMap(string MapName)
{
    if (GrantsFile == None)
        GrantsFile = new class'VCArchipelagoGrants';
    if (!class'Engine'.static.BasicLoadObject(GrantsFile, "..\\..\\Saves\\VCArchipelagoGrants.sav", true, 1)
        || GrantsFile.SelfCleaningMaps == "")
    {
        return false;
    }
    return InStr("," $ GrantsFile.SelfCleaningMaps $ ",", "," $ MapName $ ",") != -1;
}

// Reads the level's self-cleaning state and publishes it to the GRI, so the mop
// weapon subclass sees it. Called from PostBeginPlay before any mop spawns and
// again each poll, so a grant received while in the level takes effect without a
// reload. Re-reads the grants file only while still off; once on it stays on,
// because the client never revokes a level's grant.
function PublishSelfCleaningMopFlag()
{
    local VCMapInfo MapInfo;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.bIsOfficeLevel)
        return;
    if (!bSelfCleaningMap)
        bSelfCleaningMap = IsSelfCleaningMap(WorldInfo.GetMapName(true));
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None && ReplicatedInfo.bSelfCleaningMop != bSelfCleaningMap)
        ReplicatedInfo.bSelfCleaningMop = bSelfCleaningMap;
}

// Keeps the mop clean on a Self-Cleaning Mop level, so it never fills, paints
// mess, drips, or needs a bucket rinse. The primary stop is the mop weapon
// subclass (VCWeap_Mop_Archipelago), which pins saturation to zero while the
// replicated flag is set. This poll keeps the flag published and, as a fallback
// for a map that forces its own mop past the swap, zeroes any mop's saturation.
function PollSelfCleaningMop()
{
    local VCPawn Janitor;
    local VCWeap_Mop Mop;

    PublishSelfCleaningMopFlag();
    if (!bSelfCleaningMap)
        return;
    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        if (Janitor.InvManager == None)
            continue;
        foreach Janitor.InvManager.InventoryActors(class'VCWeap_Mop', Mop)
        {
            if (Mop.MopSaturation != 0.0)
            {
                Mop.MopSaturation = 0.0;
                Mop.UpdateMopSaturationEffects();
            }
        }
    }
}

// Reads whether the current level's janitor never tracks bloody footprints,
// from the client-written grants file. A map absent from the list tracks
// prints normally (absent means off).
function bool IsSqueakyBootsMap(string MapName)
{
    if (GrantsFile == None)
        GrantsFile = new class'VCArchipelagoGrants';
    if (!class'Engine'.static.BasicLoadObject(GrantsFile, "..\\..\\Saves\\VCArchipelagoGrants.sav", true, 1)
        || GrantsFile.SqueakyBootsMaps == "")
    {
        return false;
    }
    return InStr("," $ GrantsFile.SqueakyBootsMaps $ ",", "," $ MapName $ ",") != -1;
}

// Reads the level's boots state and publishes it to the GRI, so the pawn
// subclass sees it. Called from PostBeginPlay before any janitor spawns, so foot
// blood is refused from the first step, and again each poll, so a grant received
// while in the level takes effect without a reload. Re-reads the grants file
// only while still off; once on it stays on, because the client never revokes a
// level's grant.
function PublishSqueakyBootsFlag()
{
    local VCMapInfo MapInfo;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.bIsOfficeLevel)
        return;
    if (!bSqueakyBootsMap)
        bSqueakyBootsMap = IsSqueakyBootsMap(WorldInfo.GetMapName(true));
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None && ReplicatedInfo.bSqueakyBoots != bSqueakyBootsMap)
        ReplicatedInfo.bSqueakyBoots = bSqueakyBootsMap;
}

// Suppresses bloody footprints on a Squeaky Clean Boots level. The primary stop
// is the pawn subclass (VCPawn_Archipelago), which refuses foot-blood
// accumulation while the replicated boots flag is set, so FootBlood never
// reaches the one-unit print threshold (this also kills the blood-step sound
// and the footstep achievement, all gated on the same threshold). This poll
// keeps the flag published and, as a fallback for maps that force their own
// pawn class past DefaultPawnClass, zeroes any foot blood a janitor carries.
function PollSqueakyBoots()
{
    local VCPawn Janitor;

    PublishSqueakyBootsFlag();
    if (!bSqueakyBootsMap)
        return;
    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        if (Janitor.FootBlood != 0.0)
        {
            Janitor.FootBlood = 0.0;
            Janitor.UpdateFootBloodEffects();
        }
    }
}

// The per-second lock pass: publishes the mask to the GRI for the weapon and
// PRI checks, holds every locked machine in its disabled state (kismet or a
// map script may fight a value, so it is reasserted), and sweeps inventories
// for tools that slipped in outside AddDefaultInventory (floor pickups, the
// stock GiveTools cheat).
function EnforceToolLocks()
{
    local int Mask;

    Mask = CurrentToolsMask();
    PublishToolMasks(Mask);
    // The steady all-unlocked state (stock behavior, toolsanity off) has
    // nothing to enforce or restore; skip the actor sweeps.
    if (Mask == class'VCGameReplicationInfo_Archipelago'.const.ToolMaskAll
        && AppliedToolsMask == Mask
        && BinDispensorLocks.Length == 0
        && BucketDispensorLocks.Length == 0
        && IncineratorLocks.Length == 0
        && DisposalVolumeLocks.Length == 0
        && SharkVolumesDespawned.Length == 0)
    {
        return;
    }
    ApplyMachineLocks(Mask);
    ApplyInventoryLocks(Mask);
    if ((Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolSniffer) != 0
        && (AppliedToolsMask & class'VCGameReplicationInfo_Archipelago'.const.ToolSniffer) == 0)
    {
        GrantSniffers();
    }
    if ((Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolMop) != 0
        && (AppliedToolsMask & class'VCGameReplicationInfo_Archipelago'.const.ToolMop) == 0)
    {
        GrantMops();
    }
    AppliedToolsMask = Mask;
}

// Publishes the unlocked and present tool masks to the GRI, from every
// enforcement pass and once from PostBeginPlay before any janitor spawns, so
// the carry-lock hands never see the all-unlocked default at level start.
function PublishToolMasks(int Mask)
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo == None)
        return;
    if (ReplicatedInfo.UnlockedToolsMask != Mask)
        ReplicatedInfo.UnlockedToolsMask = Mask;
    // Present tools are constant per level; read once and publish for the HUD.
    if (!bPresentToolsMaskRead)
    {
        PresentToolsMaskCache = ReadPresentToolsMask(WorldInfo.GetMapName(true));
        bPresentToolsMaskRead = true;
    }
    if (ReplicatedInfo.PresentToolsMask != PresentToolsMaskCache)
        ReplicatedInfo.PresentToolsMask = PresentToolsMaskCache;
}

function ApplyMachineLocks(int Mask)
{
    local VCBucketDispensor BucketDispensor;
    local VCBinDispensor BinDispensor;
    local VCIncinerator Incinerator;
    local VCDisposalVolume Volume;
    local VCWoodChipper Chipper;
    local VCSharkDisposalVolume SharkVolume;
    local array<VCShark> DoomedSharks;
    local array<VCDebris> Contents;
    local int CacheIndex, I;
    local bool bLocked;

    // The Slosh-O-Matic locks only under the hard-start option; the default
    // starting kit keeps it unlocked for the whole seed.
    bLocked = (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolSloshOMatic) == 0;
    foreach AllActors(class'VCBucketDispensor', BucketDispensor)
    {
        CacheIndex = BucketDispensorLocks.Find('Dispensor', BucketDispensor);
        if (bLocked)
        {
            if (CacheIndex == -1)
            {
                CacheIndex = BucketDispensorLocks.Length;
                BucketDispensorLocks.Length = CacheIndex + 1;
                BucketDispensorLocks[CacheIndex].Dispensor = BucketDispensor;
                BucketDispensorLocks[CacheIndex].bFrontDisabled = BucketDispensor.bDisableFront;
                BucketDispensorLocks[CacheIndex].bBackDisabled = BucketDispensor.bDisableBack;
            }
            BucketDispensor.bDisableFront = true;
            BucketDispensor.bDisableBack = true;
        }
        else if (CacheIndex != -1)
        {
            BucketDispensor.bDisableFront = BucketDispensorLocks[CacheIndex].bFrontDisabled;
            BucketDispensor.bDisableBack = BucketDispensorLocks[CacheIndex].bBackDisabled;
            BucketDispensorLocks.Remove(CacheIndex, 1);
        }
    }

    // Bin dispensers vend the carryable bins.
    bLocked = (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolBins) == 0;
    foreach AllActors(class'VCBinDispensor', BinDispensor)
    {
        CacheIndex = BinDispensorLocks.Find('Dispensor', BinDispensor);
        if (bLocked)
        {
            if (CacheIndex == -1)
            {
                CacheIndex = BinDispensorLocks.Length;
                BinDispensorLocks.Length = CacheIndex + 1;
                BinDispensorLocks[CacheIndex].Dispensor = BinDispensor;
                BinDispensorLocks[CacheIndex].bFrontDisabled = BinDispensor.bDisableFront;
                BinDispensorLocks[CacheIndex].bBackDisabled = BinDispensor.bDisableBack;
            }
            BinDispensor.bDisableFront = true;
            BinDispensor.bDisableBack = true;
        }
        else if (CacheIndex != -1)
        {
            BinDispensor.bDisableFront = BinDispensorLocks[CacheIndex].bFrontDisabled;
            BinDispensor.bDisableBack = BinDispensorLocks[CacheIndex].bBackDisabled;
            BinDispensorLocks.Remove(CacheIndex, 1);
        }
    }

    // The incinerator group is one lock: incinerators (fireplaces are
    // subclasses), disposal volumes, the woodchipper, and the shark pool.
    bLocked = (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolIncinerator) == 0;
    foreach AllActors(class'VCIncinerator', Incinerator)
    {
        CacheIndex = IncineratorLocks.Find('Incinerator', Incinerator);
        if (bLocked)
        {
            if (CacheIndex == -1)
            {
                CacheIndex = IncineratorLocks.Length;
                IncineratorLocks.Length = CacheIndex + 1;
                IncineratorLocks[CacheIndex].Incinerator = Incinerator;
                IncineratorLocks[CacheIndex].BurnRateScale = Incinerator.BurnRateScale;
            }
            Incinerator.BurnRateScale = 0.0;
            // A cold incinerator still hides its contents from the mess scan,
            // so anything stuffed inside is unregistered; the burn timer
            // prunes the entries within seconds and the mess counts again.
            Contents.Length = 0;
            Incinerator.GetContents(Contents);
            for (I = 0; I < Contents.Length; I++)
            {
                if (Contents[I] != None)
                    Incinerator.RemoveObject(Contents[I]);
            }
        }
        else if (CacheIndex != -1)
        {
            Incinerator.BurnRateScale = IncineratorLocks[CacheIndex].BurnRateScale;
            IncineratorLocks.Remove(CacheIndex, 1);
        }
    }
    foreach AllActors(class'VCDisposalVolume', Volume)
    {
        CacheIndex = DisposalVolumeLocks.Find('Volume', Volume);
        if (bLocked)
        {
            if (CacheIndex == -1)
            {
                CacheIndex = DisposalVolumeLocks.Length;
                DisposalVolumeLocks.Length = CacheIndex + 1;
                DisposalVolumeLocks[CacheIndex].Volume = Volume;
                DisposalVolumeLocks[CacheIndex].DisposalRate = Volume.DisposalRate;
                DisposalVolumeLocks[CacheIndex].bInstantDisposal = Volume.bInstantDisposal;
            }
            Volume.DisposalRate = 0.0;
            Volume.bInstantDisposal = false;
        }
        else if (CacheIndex != -1)
        {
            Volume.DisposalRate = DisposalVolumeLocks[CacheIndex].DisposalRate;
            Volume.bInstantDisposal = DisposalVolumeLocks[CacheIndex].bInstantDisposal;
            DisposalVolumeLocks.Remove(CacheIndex, 1);
        }
    }
    // The woodchipper's consume ignores its own in-flag: it destroys an object
    // once that object's consume timer reaches four seconds near the intake.
    // Removing the entry does not stop it, so pin every entry's timer to zero
    // each pass; a one-second pass keeps it well under the four-second mark.
    if (bLocked)
    {
        foreach AllActors(class'VCWoodChipper', Chipper)
        {
            for (I = 0; I < Chipper.DebrisObjects.Length; I++)
                Chipper.DebrisObjects[I].ConsumeTime = 0.0;
        }
    }

    // The shark pool eats what swims in within a fraction of a second, too
    // fast to intercept by clearing targets on a poll, so despawn the sharks
    // while locked and respawn them on unlock. The pool spawns its sharks once
    // and never maintains a count, so a cleared list stays cleared.
    foreach AllActors(class'VCSharkDisposalVolume', SharkVolume)
    {
        CacheIndex = SharkVolumesDespawned.Find(SharkVolume);
        if (bLocked)
        {
            if (CacheIndex == -1)
            {
                // Clear the pool's lists before destroying, so a shark's
                // UnTouch firing synchronously during Destroy never reads a
                // half-cleared Sharks array.
                DoomedSharks = SharkVolume.Sharks;
                SharkVolume.Sharks.Length = 0;
                SharkVolume.PendingTargets.Length = 0;
                for (I = 0; I < DoomedSharks.Length; I++)
                {
                    if (DoomedSharks[I] != None)
                        DoomedSharks[I].Destroy();
                }
                SharkVolumesDespawned.AddItem(SharkVolume);
            }
        }
        else if (CacheIndex != -1)
        {
            SharkVolume.SpawnSharks();
            SharkVolumesDespawned.Remove(CacheIndex, 1);
        }
    }
}

function ApplyInventoryLocks(int Mask)
{
    local VCPawn Janitor;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
        ApplyPawnInventoryLocks(Janitor, Mask);
}

function ApplyPawnInventoryLocks(VCPawn Janitor, int Mask)
{
    local VCWeapon Weapon;
    local array<VCWeapon> LockedWeapons;
    local int I;

    if (Janitor == None || Janitor.InvManager == None)
        return;
    foreach Janitor.InvManager.InventoryActors(class'VCWeapon', Weapon)
    {
        if (VCWeap_Mop(Weapon) != None
            && (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolMop) == 0)
        {
            LockedWeapons.AddItem(Weapon);
        }
        else if (VCWeap_Mucktector(Weapon) != None
            && (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolSniffer) == 0)
        {
            LockedWeapons.AddItem(Weapon);
        }
        else if (VCWeap_WeldingLaser(Weapon) != None
            && (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolWelder) == 0)
        {
            LockedWeapons.AddItem(Weapon);
        }
        else if (VCWeap_Shovel(Weapon) != None
            && (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolShovel) == 0)
        {
            LockedWeapons.AddItem(Weapon);
        }
        else if (VCWeap_BroomBase(Weapon) != None
            && (Mask & class'VCGameReplicationInfo_Archipelago'.const.ToolBroom) == 0)
        {
            LockedWeapons.AddItem(Weapon);
        }
    }
    for (I = 0; I < LockedWeapons.Length; I++)
        RemoveLockedWeapon(Janitor, LockedWeapons[I]);
}

// Returns the locked tool to the world as its floor pickup unless a world
// copy already exists (so the map's welder can still be racked once unlocked,
// and respawns never pile up duplicates); tools with no pickup form, like the
// sniffer, are simply removed.
function RemoveLockedWeapon(VCPawn Janitor, VCWeapon LockedWeapon)
{
    local Actor ExistingDrop;
    local bool bDropExists;

    if (LockedWeapon.ItemDropClass != None)
    {
        foreach AllActors(LockedWeapon.ItemDropClass, ExistingDrop)
        {
            bDropExists = true;
            break;
        }
        if (!bDropExists)
        {
            LockedWeapon.DropFrom(Janitor.Location, vect(0, 0, 0));
            return;
        }
    }
    if (Janitor.InvManager != None)
        Janitor.InvManager.RemoveFromInventory(LockedWeapon);
    LockedWeapon.Destroy();
}

// Grants the mop to every janitor missing one, on a mid-level unlock under
// the hard start. Granted active (the mop arriving is the moment the level
// opens up), which also releases anything the hands are holding.
function GrantMops()
{
    local VCPawn Janitor;
    local VCMapInfo MapInfo;
    local class<VCWeapon> MopClass;
    local VCWeap_Mop Existing;
    local bool bHasMop;

    MopClass = class'VCWeap_Mop';
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.LevelInventory.Length > 0)
    {
        // A blank slot means the map deliberately gives no mop; a non-mop
        // override keeps the map's own arrangement.
        if (MapInfo.LevelInventory[0] == None
            || !ClassIsChildOf(MapInfo.LevelInventory[0], class'VCWeap_Mop'))
        {
            return;
        }
        MopClass = MapInfo.LevelInventory[0];
    }
    // Grant the self-cleaning subclass wherever the stock mop would be created,
    // matching the default-inventory swap, so a mid-level mop grant on a
    // self-cleaning level is held clean at its source too. A map's own mop
    // subclass is kept as-is.
    if (MopClass == class'VCWeap_Mop')
        MopClass = class'VCWeap_Mop_Archipelago';
    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        if (Janitor.InvManager == None)
            continue;
        bHasMop = false;
        foreach Janitor.InvManager.InventoryActors(class'VCWeap_Mop', Existing)
        {
            bHasMop = true;
            break;
        }
        if (!bHasMop)
            Janitor.CreateInventory(MopClass);
    }
}

// Grants the sniffer to every janitor missing one, on a mid-level unlock. The
// other tools re-enable things that already exist in the level; the sniffer
// and the mop are default inventory, so they are the grants done in place.
function GrantSniffers()
{
    local VCPawn Janitor;
    local VCMapInfo MapInfo;
    local class<VCWeapon> SnifferClass;
    local VCWeap_Mucktector Existing;
    local bool bHasSniffer;

    if (bDisableSniffer)
        return;
    SnifferClass = class'VCWeap_Mucktector';
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.LevelInventory.Length > 2)
    {
        // A blank slot means the map deliberately gives no sniffer; a non-
        // sniffer override keeps the map's own arrangement. A sniffer
        // subclass is the map's own and is granted as-is, like GrantMops.
        if (MapInfo.LevelInventory[2] == None
            || !ClassIsChildOf(MapInfo.LevelInventory[2], class'VCWeap_Mucktector'))
        {
            return;
        }
        SnifferClass = MapInfo.LevelInventory[2];
    }
    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        if (Janitor.InvManager == None)
            continue;
        bHasSniffer = false;
        foreach Janitor.InvManager.InventoryActors(class'VCWeap_Mucktector', Existing)
        {
            bHasSniffer = true;
            break;
        }
        if (!bHasSniffer)
            Janitor.CreateInventory(SnifferClass, true);
    }
}

// Dev override of one tool's lock, from the measurement tour commands. The
// override starts from the current effective mask, so single locks compose
// with the grants-driven state.
function DevSetToolLock(string ToolKey, bool bUnlock, PlayerController Requester)
{
    local int ToolBit;

    ToolBit = class'VCGameReplicationInfo_Archipelago'.static.ToolBitForKey(ToolKey);
    if (ToolBit == 0)
    {
        Requester.ClientMessage("Unknown tool key '"$ToolKey
            $"'. Keys: Hands Welder Shovel Lift Vendor Incinerator Sniffer Broom Bins Mop SloshOMatic.");
        return;
    }
    if (!bDevToolMaskActive)
    {
        DevToolMask = CurrentToolsMask();
        bDevToolMaskActive = true;
    }
    if (bUnlock)
        DevToolMask = DevToolMask | ToolBit;
    else
        DevToolMask = DevToolMask & ~ToolBit;
    EnforceToolLocks();
    Requester.ClientMessage("Dev tool override active. Unlocked: "
        $class'VCGameReplicationInfo_Archipelago'.static.DescribeToolMask(DevToolMask));
}

function DevSetToolMask(int Mask, PlayerController Requester)
{
    bDevToolMaskActive = true;
    DevToolMask = Mask;
    EnforceToolLocks();
    Requester.ClientMessage("Dev tool override active. Unlocked: "
        $class'VCGameReplicationInfo_Archipelago'.static.DescribeToolMask(DevToolMask));
}

function DevClearToolMask(PlayerController Requester)
{
    bDevToolMaskActive = false;
    EnforceToolLocks();
    Requester.ClientMessage("Dev tool override cleared. Unlocked: "
        $class'VCGameReplicationInfo_Archipelago'.static.DescribeToolMask(CurrentToolsMask()));
}

// Dev shortcut for the Bob goal: saves the two Digsite storyline stats
// through the game's own path (VCStatsData.SaveData), so the
// GlobalStatChanged hook publishes them exactly as the map Kismet does.
// The gates save first: the stats file rejects a Bob find while the gates
// flag is unset. Cleanable levels only, so the state stamps a map the
// client recognizes. The stats persist in GlobalStatsData.sav; without the
// client's save isolation running, the real career file keeps them.
function DevForceBobStats(PlayerController Requester)
{
    local VCMapInfo MapInfo;
    local VCStatsData StatsData;

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo == None || MapInfo.bIsOfficeLevel)
    {
        Requester.ClientMessage("APBobStats: no cleanable level is loaded.");
        return;
    }
    StatsData = VCStatsData(class'VisceraGame.VCStatsData'.static.LoadAllData());
    if (StatsData == None)
    {
        Requester.ClientMessage("APBobStats: global stats data failed to load.");
        return;
    }
    StatsData.SaveData("bOpenedDigsiteGates", "True");
    StatsData.SaveData("bFoundBob", "True");
    // Read back through the stats file, so the message reports what actually
    // stuck rather than what was asked.
    Requester.ClientMessage("APBobStats: bOpenedDigsiteGates="
        $StatsData.GetData("bOpenedDigsiteGates")
        $" bFoundBob="$StatsData.GetData("bFoundBob"));
}

// Dev shortcut for the pedestal: spawns the nine Bob note pages in a ring
// around the requesting janitor, from the game's own archetypes, so the
// Digsite gates Kismet can run without touring the note levels. The pages
// count as mess while they sit out, same as placed ones.
function DevSpawnBobNotes(PlayerController Requester)
{
    local VCMapInfo MapInfo;
    local array<string> PagePaths;
    local VCDebris_Note PageArchetype;
    local Rotator RingDirection;
    local Vector Spot;
    local int I, SpawnedCount;

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo == None || MapInfo.bIsOfficeLevel)
    {
        Requester.ClientMessage("APSpawnBobNotes: no cleanable level is loaded.");
        return;
    }
    if (Requester.Pawn == None)
    {
        Requester.ClientMessage("APSpawnBobNotes: no janitor to spawn at.");
        return;
    }
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Caduceus01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Cryo01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Greenhouse01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Medbay01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Robot01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Sewer01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Office01");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Office02");
    PagePaths.AddItem("GP_Notes_Arch.Bob.Arc_Page_Bob_Office03");
    for (I = 0; I < PagePaths.Length; I++)
    {
        PageArchetype = VCDebris_Note(DynamicLoadObject(
            PagePaths[I], class'VCDebris_Note'));
        if (PageArchetype == None)
            continue;
        RingDirection.Yaw = (I * 65536) / PagePaths.Length;
        // Waist height, so each page flutters down clear of the floor mesh.
        Spot = Requester.Pawn.Location
            + Vector(RingDirection) * 100.0 + vect(0, 0, 32);
        if (Spawn(PageArchetype.Class,,, Spot,, PageArchetype, true) != None)
            SpawnedCount++;
    }
    Requester.ClientMessage("APSpawnBobNotes: spawned "$SpawnedCount
        $" of "$PagePaths.Length$" Bob note pages.");
}

// The measurement scan: walks every mess item the way the punchout handler's
// starting pass does, sums the penalty per toolsanity category, and reports
// the machine presence counts. The result drives the apworld's per-level
// logic table; run it on arrival, before cleaning anything.
function RunScanReport(PlayerController Requester)
{
    local VCPunchoutHandler_General Handler;
    local VCMapInfo MapInfo;
    local VCDebris Debris;
    local VCSplat Splat;
    local VCIncinerator Incinerator;
    local VCMedpackBox MedpackBox;
    local VCLowGravityVolume GravityVolume;
    local VCBucketDispensor BucketDispensor;
    local VCBinDispensor BinDispensor;
    local VCDisposalVolume DisposalVolume;
    local VCWoodChipper Chipper;
    local VCSharkDisposalVolume SharkVolume;
    local VCSupplyMachine SupplyMachine;
    local VCScissorLift Lift;
    local VCPunchMachine PunchMachine;
    local float MopPenalty, WelderPenalty, HandsDisposalPenalty, BarrelPenalty;
    local float EquipmentPenalty, VendorPenalty, GravityPenalty, DoorPenalty;
    local float Total, Remainder;
    local int MopCount, WelderCount, HandsDisposalCount, BarrelCount;
    local int EquipmentCount, VendorCount, UnknownSplatCount, WelderPickupCount;
    local int SloshCount, BinMachineCount, IncineratorCount, FireplaceCount;
    local int DisposalCount, ChipperCount, SharkPoolCount, SupplyCount;
    local int LiftCount, PunchClockCount;
    local string MapName, ReportLine;
    local string DebrisId;

    Handler = VCPunchoutHandler_General(PunchoutHandler);
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (Handler == None || Handler.StartingCleanupScore <= 0.0
        || MapInfo == None || MapInfo.bIsOfficeLevel)
    {
        Requester.ClientMessage("APScanReport: no cleanable level is loaded.");
        return;
    }

    // Mirrors ProcessStartingMapState's classification chain exactly, so the
    // sums line up with StartingCleanupScore.
    foreach AllActors(class'VCDebris', Debris)
    {
        if (Debris.bShutdown)
            continue;
        DebrisId = string(Debris.Id);
        if (VCBucket(Debris) != None)
        {
            EquipmentPenalty += Handler.GetPenaltyFor(Debris, 512);
            EquipmentCount++;
        }
        else if (VCBin(Debris) != None)
        {
            EquipmentPenalty += Handler.GetPenaltyFor(Debris, 1024);
            EquipmentCount++;
        }
        else if (InStr(DebrisId, "Barrel",, true) != -1)
        {
            if (!Debris.IsUpright())
            {
                BarrelPenalty += Handler.GetPenaltyFor(Debris, 256);
                BarrelCount++;
            }
        }
        else if (VCDebris_BurntRubbish(Debris) != None)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 64);
            HandsDisposalCount++;
        }
        else if (VCDebris_ShellCasing(Debris) != None)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 4);
            HandsDisposalCount++;
        }
        else if (InStr(DebrisId, "BodyBag",, true) != -1)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 128);
            HandsDisposalCount++;
        }
        else if (InStr(DebrisId, "GooJar",, true) != -1)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 16384);
            HandsDisposalCount++;
        }
        else if (InStr(DebrisId, "GlassShard",, true) != -1)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 32768);
            HandsDisposalCount++;
        }
        else if (VCItemDrop_WeldingLaser(Debris) != None)
        {
            WelderPickupCount++;
        }
        else if (Debris.CountAsMess() && Debris.SplatClass != None)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 2);
            HandsDisposalCount++;
        }
        else if (Debris.CountAsMess() && Debris.SplatClass == None)
        {
            HandsDisposalPenalty += Handler.GetPenaltyFor(Debris, 8);
            HandsDisposalCount++;
        }
    }
    foreach AllActors(class'VCSplat', Splat)
    {
        if (Splat.bHidden && Splat.Physics == PHYS_None)
            continue;
        if (Splat.IsA('VCSplat_GooJar'))
        {
            MopPenalty += Handler.GetPenaltyFor(Splat, 16384);
            MopCount++;
        }
        else if (Splat.SplatType == 1)
        {
            MopPenalty += Handler.GetPenaltyFor(Splat, 1);
            MopCount++;
        }
        else if (Splat.SplatType == 2)
        {
            MopPenalty += Handler.GetPenaltyFor(Splat, 32);
            MopCount++;
        }
        else if (Splat.SplatType == 4)
        {
            WelderPenalty += Handler.GetPenaltyFor(Splat, 16);
            WelderCount++;
        }
        else if (Splat.SplatType == 8)
        {
            WelderPenalty += Handler.GetPenaltyFor(Splat, 131072);
            WelderCount++;
        }
        else
        {
            // Map-specific splat types score through per-map handler bits and
            // land in the remainder; the count flags them for manual review.
            UnknownSplatCount++;
        }
    }
    foreach AllActors(class'VCMedpackBox', MedpackBox)
    {
        if (!MedpackBox.CheckRestored())
        {
            VendorPenalty += Handler.GetPenaltyFor(MedpackBox, 2048);
            VendorCount++;
        }
    }
    foreach AllActors(class'VCIncinerator', Incinerator)
    {
        IncineratorCount++;
        if (Incinerator.IsA('VCIncinerator_FirePlace')
            || Incinerator.IsA('VCIncinerator_FirePlace_Horror'))
        {
            FireplaceCount++;
        }
        // Doors standing open at level start cost their penalty until closed;
        // door use is denied while the incinerator is locked, so this share
        // belongs to the incinerator item.
        if (Incinerator.Doors.Length >= 2
            && (int(Incinerator.Doors[0].State) == 1 || int(Incinerator.Doors[0].State) == 2
                || int(Incinerator.Doors[1].State) == 1 || int(Incinerator.Doors[1].State) == 2))
        {
            DoorPenalty += Handler.GetPenaltyFor(Incinerator, 4096);
        }
    }
    foreach AllActors(class'VCLowGravityVolume', GravityVolume)
    {
        if (GravityVolume.bEnabled && MapInfo.GravityVolumes.Length > 0
            && MapInfo.GravityVolumes.Find(GravityVolume) != -1)
        {
            // The gravity console is a machine UI, always usable, so this
            // share is free; scored once per level like the starting pass.
            GravityPenalty += Handler.GetPenaltyFor(GravityVolume, 8192);
            break;
        }
    }

    foreach AllActors(class'VCBucketDispensor', BucketDispensor)
        SloshCount++;
    foreach AllActors(class'VCBinDispensor', BinDispensor)
        BinMachineCount++;
    foreach AllActors(class'VCDisposalVolume', DisposalVolume)
        DisposalCount++;
    foreach AllActors(class'VCWoodChipper', Chipper)
        ChipperCount++;
    foreach AllActors(class'VCSharkDisposalVolume', SharkVolume)
        SharkPoolCount++;
    foreach AllActors(class'VCSupplyMachine', SupplyMachine)
        SupplyCount++;
    foreach AllActors(class'VCScissorLift', Lift)
        LiftCount++;
    foreach AllActors(class'VCPunchMachine', PunchMachine)
        PunchClockCount++;

    Total = Handler.StartingCleanupScore;
    Remainder = Total - MopPenalty - WelderPenalty - HandsDisposalPenalty
        - BarrelPenalty - EquipmentPenalty - VendorPenalty - GravityPenalty
        - DoorPenalty;
    MapName = WorldInfo.GetMapName(true);
    ReportLine = "Map="$MapName
        $"|Start="$Total
        $"|Mop="$MopPenalty$"/"$MopCount
        $"|Welder="$WelderPenalty$"/"$WelderCount
        $"|HandsDisposal="$HandsDisposalPenalty$"/"$HandsDisposalCount
        $"|Barrels="$BarrelPenalty$"/"$BarrelCount
        $"|Equipment="$EquipmentPenalty$"/"$EquipmentCount
        $"|Vendor="$VendorPenalty$"/"$VendorCount
        $"|Gravity="$GravityPenalty
        $"|IncineratorDoors="$DoorPenalty
        $"|Remainder="$Remainder
        $"|UnknownSplats="$UnknownSplatCount
        $"|WelderPickups="$WelderPickupCount
        $"|Machines=Slosh:"$SloshCount$" Bins:"$BinMachineCount
        $" Incinerator:"$IncineratorCount$" Fireplace:"$FireplaceCount
        $" Disposal:"$DisposalCount$" Chipper:"$ChipperCount
        $" SharkPool:"$SharkPoolCount$" Vendor:"$SupplyCount
        $" Lift:"$LiftCount$" PunchClock:"$PunchClockCount;
    WriteScanLine(MapName, ReportLine);
    `log("VCAP SCAN "$ReportLine);
    Requester.ClientMessage("Scan written for "$MapName$". Mop-only share: "
        $int((MopPenalty / Total) * 100.0)$" percent of "$int(Total)
        $" points; remainder "$int(Remainder)$" points"
        $", unknown splats "$UnknownSplatCount$".");
}

// Updates or appends the map's line in the scan results config object. The
// class defaults mirror keeps repeat scans in one session consistent, because
// an instance SaveConfig never updates the class default object.
function WriteScanLine(string MapName, string ReportLine)
{
    local VCArchipelagoScanResults Results;
    local string LinePrefix;
    local int I;
    local bool bReplaced;

    Results = new class'VCArchipelagoScanResults';
    LinePrefix = "Map="$MapName$"|";
    for (I = 0; I < Results.ScanLines.Length; I++)
    {
        if (Left(Results.ScanLines[I], Len(LinePrefix)) == LinePrefix)
        {
            Results.ScanLines[I] = ReportLine;
            bReplaced = true;
            break;
        }
    }
    if (!bReplaced)
        Results.ScanLines.AddItem(ReportLine);
    class'VCArchipelagoScanResults'.default.ScanLines = Results.ScanLines;
    Results.SaveConfig();
}

// Removes every blood splat, and only blood: the same category the mop
// clears first, through the same Die path the game's own mess cheat uses, so
// the score updates with no other side effects. Measurement aid for
// eyeballing the blood share in place.
function CleanAllBloodSplats(PlayerController Requester)
{
    local VCSplat Splat;
    local int Removed;

    foreach AllActors(class'VCSplat', Splat)
    {
        if (Splat.bHidden && Splat.Physics == PHYS_None)
            continue;
        if (Splat.SplatType != 1 || Splat.IsA('VCSplat_GooJar'))
            continue;
        Splat.Die();
        Removed++;
    }
    Requester.ClientMessage("Removed "$Removed$" blood splats.");
}

// Removes everything the scan's mop band counts: blood, scorch, and goo
// splats. Verifies the mop-only share in place; the live percent afterwards
// should match the scan's mop number.
function CleanAllMoppableSplats(PlayerController Requester)
{
    local VCSplat Splat;
    local int Removed;

    foreach AllActors(class'VCSplat', Splat)
    {
        if (Splat.bHidden && Splat.Physics == PHYS_None)
            continue;
        if (Splat.SplatType != 1 && Splat.SplatType != 2
            && !Splat.IsA('VCSplat_GooJar'))
        {
            continue;
        }
        Splat.Die();
        Removed++;
    }
    Requester.ClientMessage("Removed "$Removed$" moppable splats.");
}

// Clears the mess a core kit (mop, buckets, hands, incinerator) disposes: the
// moppable splats plus the hand-disposable mess debris (bodies, body parts,
// gore, trash, gibs), mirroring the scan's Mop and HandsDisposal categories so
// the cleanliness readout afterwards is the level's core-kit ceiling. Uses the
// scan's own discriminators, not the base-debris default flags (a bare VCDebris
// is a gib, so bMustStackUpright and bIsCollectible default true and would wrong
// a gib for a stackable or a collectible). Kept out: welder and vendor marks
// (bullet-hole and lightning splats the mop does not own), barrels (by Id),
// buckets and bins, dropped welders, medkits (a plain Actor, never in this
// loop), and the check items (collectibles are VCSpecialDrop classes, Bob
// notes carry an Arc_Page_Bob archetype, and neither counts as mess anyway).
// Anything else the game counts as mess is cleared. Measurement aid; never
// wired to gameplay.
function CleanAllCoreKitMess(PlayerController Requester)
{
    local VCPunchoutHandler_General Handler;
    local VCMapInfo MapInfo;
    local VCSplat Splat;
    local VCDebris Debris;
    local string DebrisId;
    local int Removed;

    Handler = VCPunchoutHandler_General(PunchoutHandler);
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (Handler == None || Handler.StartingCleanupScore <= 0.0
        || MapInfo == None || MapInfo.bIsOfficeLevel)
    {
        Requester.ClientMessage("APCleanCoreKit: no cleanable level is loaded.");
        return;
    }

    foreach AllActors(class'VCSplat', Splat)
    {
        if (Splat.bHidden && Splat.Physics == PHYS_None)
            continue;
        if (Splat.SplatType != 1 && Splat.SplatType != 2
            && !Splat.IsA('VCSplat_GooJar'))
        {
            continue;
        }
        Splat.Die();
        Removed++;
    }
    foreach AllActors(class'VCDebris', Debris)
    {
        // CountAsMess is the game's own mess flag, so tools and other non-mess
        // debris never qualify. The skips below keep the mess a core kit cannot
        // dispose or should not destroy, matching the scan's classification.
        if (Debris.bShutdown || !Debris.CountAsMess())
            continue;
        if (VCBucket(Debris) != None || VCBin(Debris) != None)
            continue;
        if (VCItemDrop_WeldingLaser(Debris) != None)
            continue;
        DebrisId = string(Debris.Id);
        if (InStr(DebrisId, "Barrel",, true) != -1)
            continue;
        if (InStr(string(Debris.Class.Name), "VCSpecialDrop") == 0)
            continue;
        if (Debris.ObjectArchetype != None
            && InStr(string(Debris.ObjectArchetype.Name), "Arc_Page_Bob") == 0)
        {
            continue;
        }
        Debris.Die();
        Removed++;
    }
    Requester.ClientMessage("APCleanCoreKit: cleared "$Removed$" core-kit mess"
        $" actors. Read the cleanliness readout for the core-kit ceiling. Welder"
        $" and vendor marks, barrels, buckets, bins, collectibles, and Bob notes"
        $" stay; any other loose prop the game counts as mess is cleared too.");
}

// Picks a random living janitor as a trap or supply anchor, so in co-op the
// entries spread across the crew instead of always landing on the host.
function VCPawn PickRandomJanitor()
{
    local VCPawn Janitor;
    local array<VCPawn> Janitors;

    foreach WorldInfo.AllPawns(class'VCPawn', Janitor)
    {
        if (Janitor.Health > 0)
            Janitors.AddItem(Janitor);
    }
    if (Janitors.Length == 0)
        return None;
    return Janitors[Rand(Janitors.Length)];
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

    Janitor = PickRandomJanitor();
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

    Janitor = PickRandomJanitor();
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

// Yanks every loose debris piece within reach toward the janitor in one kick,
// via the piece's own SpawnKick. Held, shut-down, and contained pieces are
// skipped; a container's contents ride along with the container's pull.
function Magnetize()
{
    local VCPawn Janitor;
    local VCDebris Debris;
    local Vector Pull;
    local float Distance;

    Janitor = PickRandomJanitor();
    if (Janitor == None)
        return;

    foreach DynamicActors(class'VCDebris', Debris)
    {
        if (Debris.bHeld || Debris.bShutdown || Debris.MyContainer != None
            || Pawn(Debris.NetConstrainer) != None)
        {
            continue;
        }
        Distance = VSize(Janitor.Location - Debris.Location);
        if (Distance > MagnetizeRadius || Distance < MagnetizeDeadZone)
            continue;
        Pull = Normal(Janitor.Location - Debris.Location)
            * FClamp(Distance * MagnetizePullSpeedScale,
                MagnetizeMinPullSpeed, MagnetizeMaxPullSpeed);
        Pull.Z += MagnetizeLiftSpeed;
        Debris.SpawnKick(Pull,, true);
    }
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
    ActiveSpeedMultiplier = Multiplier;
    SetTimer(TimedEffectDurationSeconds, false, 'RestoreJanitorSpeeds');
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None)
    {
        if (ActiveSpeedEffectType != EffectType
            && ActiveSpeedEffectType
                != class'VCGameReplicationInfo_Archipelago'.const.TimedEffectNone)
        {
            ReplicatedInfo.ClearTimedEffect(ActiveSpeedEffectType);
        }
        ReplicatedInfo.StartTimedEffect(EffectType, TimedEffectDurationSeconds);
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
    ActiveSpeedMultiplier = 1.0;
}

// A janitor who spawns or respawns mid speed effect gets the running
// multiplier too, so the replicated countdown matches what every pawn feels
// and a death never shakes off a slowdown.
function ScaleOneJanitor(VCPawn Janitor)
{
    local int Index;

    if (Janitor == None || ActiveSpeedEffectType
        == class'VCGameReplicationInfo_Archipelago'.const.TimedEffectNone)
    {
        return;
    }
    Index = SpeedAffectedJanitors.Find(Janitor);
    if (Index == -1)
    {
        SpeedAffectedJanitors.AddItem(Janitor);
        SpeedAffectedBaseSpeeds.AddItem(Janitor.GroundSpeed);
        Index = SpeedAffectedJanitors.Length - 1;
    }
    Janitor.GroundSpeed = SpeedAffectedBaseSpeeds[Index] * ActiveSpeedMultiplier;
}

// Drops the level into low gravity for the effect duration. The two gravity
// levels use their own placed volumes (the same switch the map Kismet drives),
// which replicate and wake debris themselves; on a level still in its starting
// zero-g that flip changes nothing and the entry is spent as a no-op.
// Everywhere else the replicated world gravity value drives pawn falling
// physics and the rigid body scene together, so one write covers co-op guests
// too. A second trap while one runs restarts the clock from the same captured
// baseline.
function StartZeroGravity()
{
    local VCMapInfo MapInfo;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local VCLowGravityVolume Volume;
    local int I;

    if (!bZeroGravityActive)
    {
        MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
        ZeroGravityVolumes.Length = 0;
        ZeroGravityVolumeWasEnabled.Length = 0;
        if (MapInfo != None)
        {
            for (I = 0; I < MapInfo.GravityVolumes.Length; I++)
            {
                Volume = MapInfo.GravityVolumes[I];
                if (Volume == None)
                    continue;
                ZeroGravityVolumes.AddItem(Volume);
                ZeroGravityVolumeWasEnabled.AddItem(Volume.bEnabled ? 1 : 0);
            }
        }
        ZeroGravitySavedWorldGravityZ = WorldInfo.WorldGravityZ;
    }
    if (ZeroGravityVolumes.Length > 0)
    {
        for (I = 0; I < ZeroGravityVolumes.Length; I++)
            ZeroGravityVolumes[I].SetEnabled(true);
        // Only a level save persists the flip, so a persistent marker carries
        // the captured pre-trap states; a load of this map restores them when
        // no save has confirmed the volumes since (a crash, or a save that
        // fired mid-trap).
        if (APState != None)
        {
            APState.APGravityRestoreMap = WorldInfo.GetMapName(true) $ ":"
                $ EncodeZeroGravityVolumeStates();
            SaveAPState();
        }
        GravityToggleTicksSeen = 0;
        SetTimer(GravityConsoleWatchInterval, true, 'WatchGravityConsole');
    }
    else
    {
        WorldInfo.WorldGravityZ = ZeroGravityWorldGravityZ;
        WakeAllDebris();
    }
    bZeroGravityActive = true;
    SetTimer(TimedEffectDurationSeconds, false, 'RestoreGravity');
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None)
    {
        ReplicatedInfo.StartTimedEffect(
            class'VCGameReplicationInfo_Archipelago'.const.TimedEffectZeroGravity,
            TimedEffectDurationSeconds);
    }
}

// Puts gravity back to the captured pre-trap state. The volume flip would
// persist into the level save, so the teardown paths call this too; the
// guard makes those calls free when no effect runs. Debris wakes again on
// the world path so pieces asleep mid-float notice the restore and drop.
function RestoreGravity()
{
    local int I;

    if (!bZeroGravityActive)
        return;
    if (ZeroGravityVolumes.Length > 0)
    {
        // A console toggle that landed inside the last watch interval ends
        // the effect the way the watch would: the player's choice stands and
        // the capture is not re-applied over it.
        for (I = 0; I < ZeroGravityVolumes.Length; I++)
        {
            if (ZeroGravityVolumes[I] != None && !ZeroGravityVolumes[I].bEnabled)
            {
                EndZeroGravity();
                return;
            }
        }
        for (I = 0; I < ZeroGravityVolumes.Length; I++)
        {
            if (ZeroGravityVolumes[I] != None)
                ZeroGravityVolumes[I].SetEnabled(ZeroGravityVolumeWasEnabled[I] == 1);
        }
    }
    else
    {
        WorldInfo.WorldGravityZ = ZeroGravitySavedWorldGravityZ;
        WakeAllDebris();
    }
    EndZeroGravity();
}

// The gravity console is the trap's escape hatch: a toggle during the effect
// is the janitor fixing gravity, so the effect ends and no restore overrides
// the choice. The cancel waits one extra tick after the first flipped volume,
// so a Kismet cycle that staggers the flips finishes before the effect ends.
// Only the volume path arms this watch; the world gravity levels have no
// console.
function WatchGravityConsole()
{
    local int I;
    local bool bToggleSeen;

    if (!bZeroGravityActive || ZeroGravityVolumes.Length == 0)
    {
        ClearTimer('WatchGravityConsole');
        return;
    }
    for (I = 0; I < ZeroGravityVolumes.Length; I++)
    {
        if (ZeroGravityVolumes[I] != None && !ZeroGravityVolumes[I].bEnabled)
        {
            bToggleSeen = true;
            break;
        }
    }
    if (!bToggleSeen)
    {
        GravityToggleTicksSeen = 0;
        return;
    }
    GravityToggleTicksSeen++;
    if (GravityToggleTicksSeen >= 2)
        EndZeroGravity();
}

// Shared trap teardown: stops the clocks, drops the captured baseline, and
// clears the HUD countdown. Gravity itself is the caller's business:
// RestoreGravity re-applies the capture first, the console watch leaves the
// player's choice standing. The pending marker deliberately survives: only a
// level save persists volume state, so the save hooks lift it once a save
// confirms the volumes with no trap in play.
function EndZeroGravity()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    ClearTimer('RestoreGravity');
    ClearTimer('WatchGravityConsole');
    ZeroGravityVolumes.Length = 0;
    ZeroGravityVolumeWasEnabled.Length = 0;
    bZeroGravityActive = false;
    GravityToggleTicksSeen = 0;
    LastZeroGravityEndSeconds = WorldInfo.TimeSeconds;
    ReplicatedInfo = VCGameReplicationInfo_Archipelago(GameReplicationInfo);
    if (ReplicatedInfo != None)
    {
        ReplicatedInfo.ClearTimedEffect(
            class'VCGameReplicationInfo_Archipelago'.const.TimedEffectZeroGravity);
    }
}

// The captured pre-trap volume states, paired index for index with the
// capture order, as the "0,1" tail of the pending marker.
function string EncodeZeroGravityVolumeStates()
{
    local string Encoded;
    local int I;

    for (I = 0; I < ZeroGravityVolumeWasEnabled.Length; I++)
    {
        if (I > 0)
            Encoded $= ",";
        Encoded $= string(int(ZeroGravityVolumeWasEnabled[I]));
    }
    return Encoded;
}

// The map a pending marker belongs to: the marker is "MapName:states", or a
// bare map name written by an older build.
function string PendingGravityRestoreMap()
{
    local int ColonAt;

    if (APState == None)
        return "";
    ColonAt = InStr(APState.APGravityRestoreMap, ":");
    if (ColonAt == -1)
        return APState.APGravityRestoreMap;
    return Left(APState.APGravityRestoreMap, ColonAt);
}

// Lifts the marker when it belongs to this map. Punch-out calls this (the
// shift is over and its save runs after the restore); the save hooks call it
// through LiftGravityMarkerIfSafe.
function ClearPendingGravityRestoreMarker()
{
    if (APState != None && APState.APGravityRestoreMap != ""
        && PendingGravityRestoreMap() ~= WorldInfo.GetMapName(true))
    {
        APState.APGravityRestoreMap = "";
        SaveAPState();
    }
}

// A save is the only thing that persists volume state, so it is also the only
// safe point to lift the marker: no trap running, and none that just ended (a
// stepped save spans ticks, so its volume snapshot may predate the restore by
// a moment).
function LiftGravityMarkerIfSafe()
{
    if (bZeroGravityActive
        || WorldInfo.TimeSeconds - LastZeroGravityEndSeconds
            < GravityMarkerSaveGraceSeconds)
    {
        return;
    }
    ClearPendingGravityRestoreMarker();
}

function savegamestate(optional string SaveFileName)
{
    super.savegamestate(SaveFileName);
    LiftGravityMarkerIfSafe();
}

// A stepped save serializes across later ticks, so the lift is deferred past
// the save's whole span; a crash mid-save leaves the marker standing, which
// is the conservative side.
function StepAutosave(optional string SaveFileName)
{
    super.StepAutosave(SaveFileName);
    SetTimer(GravityMarkerSaveGraceSeconds, false, 'LiftGravityMarkerIfSafe');
}

// Runs only while a pending marker names this map: waits for the game's own
// save-state load to finish (the volumes' saved flip applies during it), then
// restores the captured pre-trap volume states the marker carries. A bare
// marker from an older build falls back to the level default, zero gravity
// on, which both gravity levels ship with.
function ApplyPendingGravityRestore()
{
    local VCMapInfo MapInfo;
    local array<string> StateTexts;
    local int I, StateIndex, ColonAt;
    local string States;

    if (GameReplicationInfo == None || !GameReplicationInfo.bMatchHasBegun)
        return;
    ClearTimer('ApplyPendingGravityRestore');
    if (APState == None)
        return;
    // A trap that started meanwhile owns the volumes and the marker again;
    // its own restore or the console watch settles both.
    if (bZeroGravityActive)
        return;
    ColonAt = InStr(APState.APGravityRestoreMap, ":");
    if (ColonAt != -1)
    {
        States = Mid(APState.APGravityRestoreMap, ColonAt + 1);
        ParseStringIntoArray(States, StateTexts, ",", true);
    }
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None)
    {
        StateIndex = 0;
        for (I = 0; I < MapInfo.GravityVolumes.Length; I++)
        {
            if (MapInfo.GravityVolumes[I] == None)
                continue;
            if (StateIndex < StateTexts.Length)
            {
                MapInfo.GravityVolumes[I].SetEnabled(
                    StateTexts[StateIndex] == "1");
            }
            else
            {
                MapInfo.GravityVolumes[I].SetEnabled(true);
            }
            StateIndex++;
        }
    }
    if (APState.APGravityRestoreMap != "")
    {
        APState.APGravityRestoreMap = "";
        SaveAPState();
    }
}

// Wakes every loose debris rigid body, the same pass the gravity volumes' own
// switch runs, so sleeping pieces notice a world gravity change.
function WakeAllDebris()
{
    local VCDebris Debris;

    foreach DynamicActors(class'VCDebris', Debris)
    {
        if (Debris.Mesh != None)
            Debris.Mesh.WakeRigidBody();
    }
}

// Quitting a work level does not save it (only the periodic autosave and the
// punch-out flow do), so this restore is best effort for the dying world; a
// flip a mid-trap autosave already persisted stays covered by the pending
// marker, which survives this teardown on purpose.
event GameEnding()
{
    RestoreGravity();
    super.GameEnding();
}

// Drops a supply item on the floor near the janitor. A plain spawn is exactly
// what the game's own dispensers vend: a fresh VCBucket is full of clean water
// and a fresh VCBin is empty, and both score as misplaced equipment if left
// out, same as a vended one.
function SpawnSupplyNearJanitor(class<VCDebris> SupplyClass)
{
    local VCPawn Janitor;
    local Vector Start, HitLocation, HitNormal, Offset, Spot, SupplyExtent;
    local Actor Floor;
    local int I;

    Janitor = PickRandomJanitor();
    if (Janitor == None)
        return;

    // Half-size box around the bin, the larger of the two supplies; a spot
    // with this much clearance takes either one without clipping anything.
    SupplyExtent = vect(22, 22, 26);

    for (I = 0; I < 16; I++)
    {
        Offset = VRand() * RandRange(64.0, 160.0);
        Offset.Z = 0.0;
        Start = Janitor.Location + Offset + vect(0, 0, 32);
        // A candidate the janitor has no clear line to sits behind a wall.
        if (!FastTrace(Start, Janitor.Location + vect(0, 0, 32)))
            continue;
        // Swept-box trace straight down, against actors too, so the spot
        // rests on top of furniture instead of inside it. HitLocation is the
        // box center at contact, so the box bottom touches the surface.
        Floor = Trace(HitLocation, HitNormal, Start - vect(0, 0, 512), Start,
            true, SupplyExtent);
        if (Floor == None)
            continue;
        Spot = HitLocation + vect(0, 0, 2);
        // Engine encroachment test: a shallow overlap gets nudged clear and a
        // wedged spot is rejected, so nothing spawns inside a wall.
        if (!FindSpot(SupplyExtent, Spot))
            continue;
        if (Spawn(SupplyClass,,, Spot) != None)
            return;
    }
    // No clear spot took the spawn; drop it from above the janitor, whose own
    // footprint is proven open.
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

    // Catch the final cleanliness rungs, then stop the probe and trap timers:
    // the level is on its way out, and the handler's results are final now.
    // The milestone poll keeps running so the indicator can still flip once
    // the server confirms the final rungs before the travel.
    // Gravity goes back before the final rung capture, so a trap-flipped
    // volume's transient penalty never bakes into the published rungs. The
    // shift's own results keep it: leaving gravity off costs points, the
    // game's rule either way. The shift is over, so this map's pending
    // marker lifts with it (the punch-out flow saves after the restore).
    RestoreGravity();
    ClearPendingGravityRestoreMarker();
    PublishCleanliness();
    bCleanlinessProbeStopped = true;
    ClearTimer('PublishCleanliness');
    ClearTimer('PublishCleanlinessBurst');
    ClearTimer('PollTraps');
    ClearTimer('PollLinks');

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
    // The Speedrun check: clean enough to not be fired (status bit 1 or 2, at
    // least 95 percent clean) and under the map's par time, dilated for player
    // count. The par is the target, not the game's stricter 75-percent
    // achievement bar.
    if ((Handler.JobStatus.StatusCode & 3) != 0
        && Handler.CleanupTimeLimitGamePar > 0.0
        && Handler.CleanupTimeDilated <= Handler.CleanupTimeLimitGamePar)
    {
        APState.APSpeedrun = 1;
    }
    APState.APSeq = APState.APSeq + 1;
    SaveAPState();
    `log("VCAP PUNCHOUT map="$APState.APMap$" fired="$APState.APFired$" speedrun="$APState.APSpeedrun);
}

// Tokens for everything in the janitor's trunk that maps to a check: a
// collectible's class name, or a Bob page's archetype name (Arc_Page_Bob*,
// the shared GP_Notes_Arch names). Both are unique across the whole game, so
// the client resolves each token to its home level's location no matter where
// it was banked; tokens with no location (the Office pages) it ignores.
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
            && InStr(string(TrunkItems[I].ObjectArchetype.Name), "Arc_Page_Bob") == 0)
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

// The Digsite crate stacking zones list only the Type1 crate archetypes while
// the level spawns Type2, Type4, and Type5 crates, so vanilla awards stacked
// crates nothing there. Every other level's crate zones list the full crate
// family. Widen each crate zone to the crate archetypes present in the level;
// barrel zones and special sorting zones keep their own lists.
function WidenDigsiteCrateStackingZones()
{
    local VCDebris Debris;
    local VCStackingVolume Zone;
    local array<Actor> PresentCrateArchetypes;
    local Actor DebrisArchetype;
    local int I;
    local bool bCrateZone;

    if (!(WorldInfo.GetMapName(true) ~= "VC_Digsite"))
        return;

    foreach AllActors(class'VCDebris', Debris)
    {
        DebrisArchetype = Actor(Debris.ObjectArchetype);
        if (DebrisArchetype == None
            || InStr(string(DebrisArchetype.Name), "ARCH_VC_Crate_Type") != 0
            || PresentCrateArchetypes.Find(DebrisArchetype) != -1)
        {
            continue;
        }
        PresentCrateArchetypes.AddItem(DebrisArchetype);
    }
    if (PresentCrateArchetypes.Length == 0)
        return;

    foreach AllActors(class'VCStackingVolume', Zone)
    {
        bCrateZone = false;
        for (I = 0; I < Zone.ValidArchetypes.Length; I++)
        {
            if (Zone.ValidArchetypes[I] != None
                && InStr(string(Zone.ValidArchetypes[I].Name), "ARCH_VC_Crate_Type") == 0)
            {
                bCrateZone = true;
                break;
            }
        }
        if (!bCrateZone)
            continue;
        for (I = 0; I < PresentCrateArchetypes.Length; I++)
        {
            if (Zone.ValidArchetypes.Find(PresentCrateArchetypes[I]) == -1)
                Zone.ValidArchetypes.AddItem(PresentCrateArchetypes[I]);
        }
    }
}

function PublishCleanliness()
{
    local VCPunchoutHandler_General Handler;
    local VCMapInfo MapInfo;
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local VCSandTrap SandTrap;
    local float LivePenalty, SandFilledSum, SandFillMaxSum;
    local float clean;
    local int percent;
    local bool changed;

    // Never probe the Office or menu maps; they are not cleanable levels.
    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo != None && MapInfo.bIsOfficeLevel)
        return;

    Handler = VCPunchoutHandler_General(PunchoutHandler);
    if (Handler == None || Handler.StartingCleanupScore <= 0.0 || APState == None)
        return;

    // Every poll: idempotent, and it catches crates a factory spawns after
    // the first pass.
    WidenDigsiteCrateStackingZones();

    Handler.ProcessMapState(self, None);
    LivePenalty = Handler.FinalPenalty;

    // The Digsite handler scores the sand pits as one flat infraction while
    // any pit is uncovered, so vanilla credits nothing until every pit is
    // full. Credit the filled share gradually so each shovel of sand moves
    // the readout; the value meets the game's own score the moment the last
    // pit tops off. Only the Digsite places sand traps; on any other map the
    // sums stay zero and nothing changes.
    if ((Handler.BitCode & class'VCPunchoutHandler_Digsite'.const.RESULT_SandTrap) != 0)
    {
        foreach AllActors(class'VCSandTrap', SandTrap)
        {
            SandFilledSum += SandTrap.SandFilledAmount;
            SandFillMaxSum += SandTrap.SandFillMax;
        }
        if (SandFillMaxSum > 0.0)
        {
            LivePenalty -= Handler.GetPenaltyFor(None,
                class'VCPunchoutHandler_Digsite'.const.RESULT_SandTrap)
                * FClamp(SandFilledSum / SandFillMaxSum, 0.0, 1.0);
        }
    }

    clean = 1.0 - (LivePenalty / Handler.StartingCleanupScore);
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
    }

    // The level's starting score publishes once per shift, so the client can
    // cross-check it against the shipped scan table and warn loudly when a
    // measured constant no longer matches the live level.
    if (APState.APStartScore == 0)
    {
        APState.APStartScore = int(Handler.StartingCleanupScore);
        changed = true;
    }

    // Publish every newly crossed whole percent, so a jump does not skip
    // one; the client filters the list to the seed's enabled rungs.
    while (HighestReportedRung < percent)
    {
        HighestReportedRung += 1;
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
}

// Called by the GRI when a splat or debris is created or removed. Coalesces a
// burst of changes into one scan through a one-shot timer, so a spill or a
// mop sweep folds into a single scan. Ignored once the level is on its way
// out, so a queued burst cannot rescan a torn-down level.
function NotifyMessChanged()
{
    if (bCleanlinessProbeStopped)
        return;
    if (!IsTimerActive('PublishCleanlinessBurst'))
        SetTimer(CleanlinessBurstDelaySeconds, false, 'PublishCleanlinessBurst');
}

function PublishCleanlinessBurst()
{
    PublishCleanliness();
}

defaultproperties
{
    HUDType=Class'VCArchipelago.VCHUD_Archipelago'
    GameReplicationInfoClass=Class'VCArchipelago.VCGameReplicationInfo_Archipelago'
    PlayerControllerClass=Class'VCArchipelago.VCPlayerController_Archipelago'
    PlayerReplicationInfoClass=Class'VCArchipelago.VCPlayerReplicationInfo_Archipelago'
    // The stock janitor pawn, subclassed only to suppress bloody footprints on
    // a Squeaky Clean Boots level.
    DefaultPawnClass=Class'VCArchipelago.VCPawn_Archipelago'
}
