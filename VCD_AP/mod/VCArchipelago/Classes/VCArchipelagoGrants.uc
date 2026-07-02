// Grants written by the Archipelago client and read by the mod, as a save file
// (Saves\VCArchipelagoGrants.sav) via BasicSaveObject / BasicLoadObject.
//
// Not config: UE3 caches config at startup and exposes no script-callable reload,
// so config cannot deliver a mid-session client write. BasicLoadObject reads from
// disk fresh on every call, which is exactly how the game reads all its own mutable
// state (saves, trophy data, incident reports).
class VCArchipelagoGrants extends Object;

// Comma-separated internal map names the player may enter, e.g. "VC_Hall,VC_Cryo".
var string UnlockedMaps;
