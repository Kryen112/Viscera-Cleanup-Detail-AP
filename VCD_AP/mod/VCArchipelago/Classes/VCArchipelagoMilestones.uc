// Remaining milestones written by the Archipelago client and read by the mod,
// as a save file (Saves\VCArchipelagoMilestones.sav) via BasicSaveObject /
// BasicLoadObject. It drives the HUD's next-milestone indicator.
//
// Not config: UE3 caches config at startup and exposes no script-callable
// reload, so config cannot deliver a mid-session client write. BasicLoadObject
// reads from disk fresh on every call.
class VCArchipelagoMilestones extends Object;

// The connected seed; another seed's leftovers never drive the indicator.
var string SeedTag;

// Per-level percents whose milestone check the server has not confirmed yet,
// ascending, e.g. "VC_Hall:85 90 95 100,VC_Cryo:". A map listed with no
// percents has every milestone confirmed checked; a map absent from the list
// has no data in this seed, which the HUD shows as unknown.
var string RemainingByMap;
