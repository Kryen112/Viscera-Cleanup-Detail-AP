// The viewport client for Archipelago play.
//
// Adds one behavior over the stock client: on a slow timer it hides every level
// not in the client-written unlocked set by flipping bHideFromMenu on the map data
// providers. The level-select menu rebuilds from those providers and shows a map
// only when bHideFromMenu is false, so the list holds exactly the unlocked levels,
// updated live.
//
// It lives here because this is the one object that both persists and ticks in the
// FrontEnd where the menu reads the providers. Flipping the flag earlier (from the
// GameInfo, or during datastore registration) does not survive: the providers are
// re-created or reload their config before the menu reads them.
//
// Swapped in through GameViewportClientClassName. With no grants file the list is
// left untouched, so normal play outside a session is unaffected.
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

    if (CurationLogBudget > 0)
    {
        CurationLogBudget--;
        if (bUnlockAll)
            `log("VCAP VP CURATE shown="$shown$" hidden="$hidden$" unlocked=<dev-override>");
        else
            `log("VCAP VP CURATE shown="$shown$" hidden="$hidden$" unlocked="$unlocked);
    }
}

defaultproperties
{
    CurationLogBudget=3
}
