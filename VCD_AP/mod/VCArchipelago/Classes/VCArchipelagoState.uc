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

// The map currently being cleaned, and its live cleanliness percent (0 to 100+).
var config string APMap;
var config int APCleanPct;

// Comma-separated cleanliness rungs reached in the current map, e.g. "5,10,15".
// TODO: widen to the full per-seed checked set (collectibles, Bob) once those
// checks are detected, so the file is the whole reconnect-safe state and not
// just the current level's cleanliness.
var config string APMilestones;

// Punch-out result for the current map, all cleared on level start. APPunchedOut
// becomes 1 on a legitimate punch-out; APFired mirrors the game's fired verdict;
// APSpeedrun becomes 1 when the run also met the game's own speedrun standard
// (at least 95 percent clean, inside 75 percent of the map's par time).
var config int APPunchedOut;
var config int APFired;
var config int APSpeedrun;
