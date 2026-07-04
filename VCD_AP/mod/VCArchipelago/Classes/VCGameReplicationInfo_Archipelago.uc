// Replicated Archipelago state, one instance per level, spawned by the game
// mode through GameReplicationInfoClass.
//
// The cleanliness readout must reach co-op guests, who have no GameInfo, so
// the host writes the value here each probe scan and the engine replicates
// it. Every stock VCGameReplicationInfo cast still succeeds against this
// subclass.
class VCGameReplicationInfo_Archipelago extends VCGameReplicationInfo;

// Live cleanliness in hundredths of a percent, floored, negative when the
// level is dirtier than it started. Unsampled until the first probe scan, so
// the HUD stays blank in the Office and the menus.
var int CleanlinessHundredths;
var bool bCleanlinessSampled;

replication
{
    if (bNetDirty)
        CleanlinessHundredths, bCleanlinessSampled;
}
