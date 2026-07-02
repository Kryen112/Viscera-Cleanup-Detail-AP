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
// TODO: widen to the full per-seed checked set (punch-out, speedrun, collectibles,
// Bob) once those checks are detected, so the file is the whole reconnect-safe
// state and not just the current level's cleanliness.
var config string APMilestones;
