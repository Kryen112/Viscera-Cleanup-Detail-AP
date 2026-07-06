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

// Toolsanity: per-map unlocked tool keys, formatted like the milestones file,
// e.g. "VC_Hall:Hands Welder,VC_Cryo:". A map listed with no keys has every
// tool locked; a map absent from the string has toolsanity off (everything
// unlocked), which keeps older clients and toolsanity-off seeds on stock
// behavior. Keys: Hands Welder Shovel Lift Vendor Incinerator Sniffer Broom
// Bins Mop SloshOMatic (see VCGameReplicationInfo_Archipelago.ToolBitForKey).
var string UnlockedTools;

// Toolsanity: per-map tool keys the level HAS, same format as UnlockedTools.
// The unlocked string is a subset of this; the HUD panel colors a present
// tool green when also unlocked and dim when not. Empty means toolsanity off.
var string PresentTools;

// Comma-separated internal map names where the janitor holds the Self-Cleaning
// Mop, so that level's mop never dirties. A map absent means the mop dirties
// normally there (absent means off, like UnlockedMaps).
var string SelfCleaningMaps;

// Comma-separated internal map names where the janitor holds the Squeaky Clean
// Boots, so that level's janitor never tracks bloody footprints. A map absent
// means the janitor tracks prints normally there (absent means off).
var string SqueakyBootsMaps;
