// The janitor pawn under the Archipelago mode. Installed as the game mode's
// DefaultPawnClass. Identical to the stock VCPawn except that on a Squeaky
// Clean Boots level it never lets foot blood build up.
//
// A bloody footprint is a discrete, permanent spawn gated on FootBlood reaching
// one unit at a foot-plant, so a poll that zeroes FootBlood after the fact can
// let a print through between ticks. Refusing the accumulation at its one source
// (AddFootBlood, called from a mess splat's touch) keeps FootBlood at zero, so
// the threshold is never met and no print, blood-step sound, or footstep
// achievement can ever fire. The print spawn is authority-side, so suppressing
// on the host is what counts; the flag rides the replicated GRI for guests.
class VCPawn_Archipelago extends VCPawn;

function AddFootBlood(float Amount, float Max, Vector MessColor)
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(WorldInfo.GRI);
    if (ReplicatedInfo != None && ReplicatedInfo.bSqueakyBoots)
        return;
    super.AddFootBlood(Amount, Max, MessColor);
}
