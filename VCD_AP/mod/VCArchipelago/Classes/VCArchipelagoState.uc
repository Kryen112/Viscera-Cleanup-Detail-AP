// State the mod publishes to the Archipelago client.
//
// Written with SaveConfig on change to UDKGame\Config\UDKVCArchipelago.ini; the
// client polls that file. APSeq increments on every write so the client detects
// updates. The mod writes the full state, not deltas, so a client reconnect
// recovers from the file alone.
class VCArchipelagoState extends Object
    config(VCArchipelago);

// Monotonic write counter. Bumped on every SaveConfig.
var config int APSeq;

// The seed this state belongs to, copied from the client-written traps file at
// level start. The client ignores state stamped for another seed (or not
// stamped at all), so a new seed can never replay a previous seed's leftovers.
var config string APSeedTag;

// The map currently being cleaned, and its live cleanliness percent (0 to 100+).
var config string APMap;
var config int APCleanPct;

// The level's own StartingCleanupScore, published once per shift and cleared
// on level start. The client cross-checks it against the shipped scan table
// and warns when a measured constant no longer matches the live level.
var config int APStartScore;

// Comma-separated cleanliness rungs reached in the current map, e.g. "5,10,15".
// TODO: widen to the full per-seed checked set (collectibles, Bob) once those
// checks are detected, so the file is the whole reconnect-safe state and not
// just the current level's cleanliness.
var config string APMilestones;

// Punch-out result for the current map, all cleared on level start. APPunchedOut
// becomes 1 on a legitimate punch-out; APFired mirrors the game's fired verdict;
// APSpeedrun becomes 1 when the run also met the Speedrun check: at least 95
// percent clean and under the map's par time (dilated for player count).
var config int APPunchedOut;
var config int APFired;
var config int APSpeedrun;

// Comma-separated tokens for what banked in the trunk at a punch-out in good
// standing: collectible class names (VCSpecialDrop_*) and Bob note archetype
// names (Note_Bob_*). Cleared on level start like the other punch-out fields.
var config string APTrunkFinds;

// Bob storyline events for the current map, set live when the game saves the
// matching global stat (the Digsite Kismet fires both). Cleared on level start.
var config int APDigsiteGates;
var config int APFoundBob;

// Trap bookkeeping, persistent across levels (not cleared on level start). The
// seed the applied counter belongs to, and the highest received-item index whose
// trap has been applied. Both survive a game relaunch through the config file,
// so a trap is never applied twice.
var config string APTrapSeed;
var config int APTrapsApplied;

// "MapName:states", the gravity volumes a zero gravity trap flipped with the
// captured pre-trap enabled flags ("0,1" in capture order). Persistent, so a
// save that baked the flip mid-trap (an autosave, then a quit or crash) gets
// undone: the next load of the named map restores the carried states. Lifted
// by a level save that confirms the volumes with no trap in play, by the
// punch-out flow, or by the load that consumes it. Empty when nothing is
// pending.
var config string APGravityRestoreMap;
