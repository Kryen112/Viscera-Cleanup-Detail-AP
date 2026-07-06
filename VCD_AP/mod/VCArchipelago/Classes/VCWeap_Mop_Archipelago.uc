// The janitor's mop under the Archipelago mode. Installed by swapping the stock
// mop in the game mode's AddDefaultInventory, the same way the hands are
// swapped. Identical to the stock VCWeap_Mop except that on a Self-Cleaning Mop
// level it keeps its saturation pinned to zero, so the mop never fills, paints
// mess, or drips.
//
// The mop accumulates saturation inline at several points in its fire routine
// with no single source to override, but it recomputes its saturation effects
// right after each of those points, so zeroing here holds the mop clean at the
// moment it would dirty rather than a poll clearing it after the fact. That
// mirrors the boots pawn subclass; the flag rides the replicated GRI, and the
// game mode still runs a poll as a fallback for a map that forces its own mop.
class VCWeap_Mop_Archipelago extends VCWeap_Mop;

simulated function UpdateMopSaturationEffects()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(WorldInfo.GRI);
    if (ReplicatedInfo != None && ReplicatedInfo.bSelfCleaningMop)
        MopSaturation = 0.0;
    super.UpdateMopSaturationEffects();
}
