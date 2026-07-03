// The Archipelago game mode entry point.
//
// A VCGame subclass selected through a VCUIDataProvider_GameInfo entry whose
// GameClass is this class, so a level launches with
// ?Game=VCArchipelago.VCGame_Archipelago and this runs in place of VCGame. It
// watches the level's cleanliness and publishes state for the Archipelago client
// (see VCArchipelagoState).
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
    HighestReportedRung = 0;
    LastPublishedPercent = -1;
    SetTimer(1.0, true, 'PublishCleanliness');
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

    // Stop our timer so it does not fire against a level being torn down.
    ClearTimer('PublishCleanliness');

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

    // Catch the final cleanliness rungs, then stop the timer: the level is on
    // its way out, and the handler's results are final now.
    PublishCleanliness();
    ClearTimer('PublishCleanliness');

    Handler = VCPunchoutHandler_General(PunchoutHandler);
    if (Handler == None || APState == None)
        return;

    APState.APMap = WorldInfo.GetMapName(true);
    APState.APPunchedOut = 1;
    if (Handler.JobStatus.bStatus)
        APState.APFired = 1;
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
    APState.SaveConfig();
    `log("VCAP PUNCHOUT map="$APState.APMap$" fired="$APState.APFired$" speedrun="$APState.APSpeedrun);
}

function PublishCleanliness()
{
    local VCPunchoutHandler_General Handler;
    local VCMapInfo MapInfo;
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

    changed = false;
    if (percent != LastPublishedPercent)
    {
        LastPublishedPercent = percent;
        APState.APCleanPct = percent;
        APState.APMap = WorldInfo.GetMapName(true);
        changed = true;
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
        APState.SaveConfig();
    }
}

defaultproperties
{
}
