// The viewport client for Archipelago play.
//
// Adds two behaviors over the stock client, both on a slow timer. First, it
// hides every level not in the client-written unlocked set by flipping
// bHideFromMenu on the map data providers. The level-select menu rebuilds from
// those providers and shows a map only when bHideFromMenu is false, so the
// list holds exactly the unlocked levels, updated live. Second, it heals the
// Start Work menu's saved launch map: the menu launches its config-saved
// LastSelectedMap, not the highlighted list entry, so a value carried over
// from stock play (or from a list built before the first curation pass) sends
// every launch to a level the gate refuses. The heal keeps that saved map
// inside the unlocked set.
//
// It lives here because this is the one object that both persists and ticks in the
// FrontEnd where the menu reads the providers. Flipping the flag earlier (from the
// GameInfo, or during datastore registration) does not survive: the providers are
// re-created or reload their config before the menu reads them.
//
// Swapped in through GameViewportClientClassName. With no grants file the list
// and the saved launch map are left untouched, so normal play outside a
// session is unaffected. The heal is this class's one durable write into the
// stock preferences: a grants file lingering past an unclean exit keeps
// steering the saved map until the client's disconnect restore removes it.
class VCGameViewportClient_Archipelago extends VCGameViewportClient;

// Dev override for the measurement tour: shows every level and passes the
// bounce gate, set by the APLevelsUnlockAll dev command. An instance var
// works because this object persists across level travel; a relaunch returns
// to the grants-driven state and the grants file keeps its single writer
// (the client).
var bool bDevUnlockAllLevels;

// Seconds between curation passes, and the running accumulator.
const CurationInterval = 0.5;
var float SecondsSinceCuration;

// Logs the first few passes only, so the log is not spammed at the tick rate.
var int CurationLogBudget;

event Tick(float DeltaTime)
{
    super.Tick(DeltaTime);

    SecondsSinceCuration += DeltaTime;
    if (SecondsSinceCuration < CurationInterval)
        return;
    SecondsSinceCuration = 0.0;
    CurateMapProviders();
}

// Reads the unlocked set fresh from Saves\VCArchipelagoGrants.sav and flips
// bHideFromMenu on every map provider to match it. With no grants file, leaves
// every provider visible.
function CurateMapProviders()
{
    local DataStoreClient DSClient;
    local UDKUIDataStore_MenuItems ResourceDataStore;
    local array<UDKUIResourceDataProvider> Providers;
    local VCUIDataProvider_MapInfo MapProvider;
    local VCArchipelagoGrants Grants;
    local string unlocked;
    local int i, shown, hidden;
    local bool bUnlockAll;

    // Standalone only, so a flag left on never leaks into a co-op session
    // started without a relaunch.
    bUnlockAll = bDevUnlockAllLevels
        && class'WorldInfo'.static.GetWorldInfo() != None
        && class'WorldInfo'.static.GetWorldInfo().NetMode == NM_Standalone;
    if (!bUnlockAll)
    {
        Grants = new class'VCArchipelagoGrants';
        if (!class'Engine'.static.BasicLoadObject(Grants, "..\\..\\Saves\\VCArchipelagoGrants.sav", true, 1))
            return;
        unlocked = Grants.UnlockedMaps;
    }

    DSClient = class'Engine.UIInteraction'.static.GetDataStoreClient();
    if (DSClient == None)
        return;
    ResourceDataStore = UDKUIDataStore_MenuItems(DSClient.FindDataStore('VCGameResources'));
    if (ResourceDataStore == None)
        return;

    ResourceDataStore.GetAllResourceDataProviders(class'VisceraGame.VCUIDataProvider_MapInfo', Providers);
    for (i = 0; i < Providers.Length; i++)
    {
        MapProvider = VCUIDataProvider_MapInfo(Providers[i]);
        if (MapProvider == None)
            continue;
        if (bUnlockAll || InStr(","$unlocked$",", ","$MapProvider.MapName$",") != -1)
        {
            MapProvider.bHideFromMenu = false;
            // An empty ValidTitles passes the menu's title filter, so a granted
            // DLC map lists under whatever title is active. In-memory only;
            // nothing saves the providers back to config.
            MapProvider.ValidTitles.Length = 0;
            shown++;
        }
        else
        {
            MapProvider.bHideFromMenu = true;
            hidden++;
        }
    }

    if (!bUnlockAll)
        HealMenuLaunchSelection(unlocked);

    if (CurationLogBudget > 0)
    {
        CurationLogBudget--;
        if (bUnlockAll)
            `log("VCAP VP CURATE shown="$shown$" hidden="$hidden$" unlocked=<dev-override>");
        else
            `log("VCAP VP CURATE shown="$shown$" hidden="$hidden$" unlocked="$unlocked);
    }
}

// The Start Work menu launches the map named by VCUI_GameMenu's config-saved
// LastSelectedMap, not the highlighted list entry, and only rewrites it when
// the dropdown selection changes. A saved map outside the unlocked set sends
// every launch into the level gate's bounce, so whenever the saved map is not
// unlocked (or is empty), point it at the first unlocked level. A freshly
// opened menu copies the class default and reconciles its selection to it, so
// the caption, the preview, and the launch all land on that level. A live menu
// instance keeps its own copy, so a selection made from a stale list still
// launches through the gate; the next menu open starts healed.
// StaticSaveConfig flushes the whole section from class defaults, so an ini
// value a live instance saved mid-session can revert to a boot-time value;
// the instance is unaffected and re-saves on its next selection change.
function HealMenuLaunchSelection(string UnlockedMaps)
{
    local array<string> UnlockedList;
    local string SavedMap;

    SavedMap = class'VisceraUI.VCUI_GameMenu'.default.LastSelectedMap;
    if (SavedMap != "" && InStr(","$UnlockedMaps$",", ","$SavedMap$",") != -1)
        return;
    ParseStringIntoArray(UnlockedMaps, UnlockedList, ",", true);
    if (UnlockedList.Length == 0)
        return;
    class'VisceraUI.VCUI_GameMenu'.default.LastSelectedMap = UnlockedList[0];
    class'VisceraUI.VCUI_GameMenu'.static.StaticSaveConfig();
    `log("VCAP VP HEAL LastSelectedMap="$UnlockedList[0]);
}

defaultproperties
{
    CurationLogBudget=3
}
