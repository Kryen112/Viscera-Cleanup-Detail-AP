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
// TODO: detect punch-out, speedrun, and collectibles as checks; make detection
// event-driven where the game gives an event; throttle the mess scan (calling
// ProcessMapState every tick is a full scan); enforce level gating (refuse to
// start a level not in the client-written unlocked set).
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
    HighestReportedRung = 0;
    LastPublishedPercent = -1;
    SetTimer(1.0, true, 'PublishCleanliness');
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
