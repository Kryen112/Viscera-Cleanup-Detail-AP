// The Archipelago player controller: home of the dev measurement commands
// for the toolsanity tour. Installed through the game mode's
// PlayerControllerClass; every stock VCPlayerController cast still succeeds.
//
// The commands are standalone-only (a co-op guest or host cannot use them)
// and dev-only: most override state in memory, never the grants file, so a
// level reload returns to the client-driven state. APBobStats is the
// exception; it persists the two storyline stats through the game's own
// save.
class VCPlayerController_Archipelago extends VCPlayerController;

// The game mode, when the commands may run: standalone, in Archipelago mode.
function VCGame_Archipelago DevCommandGame()
{
    if (WorldInfo.NetMode != NM_Standalone)
        return None;
    return VCGame_Archipelago(WorldInfo.Game);
}

exec function APToolLock(string ToolKey)
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevSetToolLock(ToolKey, false, self);
}

exec function APToolUnlock(string ToolKey)
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevSetToolLock(ToolKey, true, self);
}

exec function APToolLockAll()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevSetToolMask(0, self);
}

exec function APToolUnlockAll()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevSetToolMask(class'VCGameReplicationInfo_Archipelago'.const.ToolMaskAll, self);
}

// Drops the dev override and returns to the client-written grants state.
exec function APToolLocksReset()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevClearToolMask(self);
}

exec function APScanReport()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.RunScanReport(self);
}

exec function APCleanBlood()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.CleanAllBloodSplats(self);
}

exec function APCleanMoppable()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.CleanAllMoppableSplats(self);
}

// Clears everything a core kit disposes (moppable splats plus hand-disposable
// mess debris), leaving tool-specific mess, stackables, tools, medkits,
// collectibles, and Bob notes. The cleanliness readout afterwards is the
// level's core-kit ceiling.
exec function APCleanCoreKit()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.CleanAllCoreKitMess(self);
}

// Saves the two Digsite storyline stats through the game's own path, so the
// Bob goal fires without the pedestal run. The gates land first, then Bob.
exec function APBobStats()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevForceBobStats(self);
}

// Spawns the nine Bob note pages at the janitor, for a real pedestal run.
exec function APSpawnBobNotes()
{
    local VCGame_Archipelago Game;

    Game = DevCommandGame();
    if (Game != None)
        Game.DevSpawnBobNotes(self);
}

// Shows every level in the menu and passes the bounce gate for the rest of
// this game session, for the measurement tour. Never writes the grants file.
exec function APLevelsUnlockAll()
{
    SetDevLevelOverride(true,
        "Dev level override active: every level is selectable until the game closes.");
}

exec function APLevelsReset()
{
    SetDevLevelOverride(false,
        "Dev level override cleared: the grants file drives the level list again.");
}

function SetDevLevelOverride(bool bUnlockAll, string Confirmation)
{
    local VCGameViewportClient_Archipelago ViewportClient;

    if (DevCommandGame() == None)
        return;
    ViewportClient = VCGameViewportClient_Archipelago(
        class'Engine'.static.GetEngine().GameViewport);
    if (ViewportClient == None)
        return;
    ViewportClient.bDevUnlockAllLevels = bUnlockAll;
    ClientMessage(Confirmation);
}
