// The spawn queue the client writes and the mod reads fresh with BasicLoadObject
// (Saves\VCArchipelagoTraps.sav). It carries every received item with an
// in-level effect, traps and useful supply drops alike. The client is the only
// writer.
//
// SeedTag names the connected seed so a stale file from another seed is never
// replayed. BaselineIndex is how many items the player already held when the
// session connected; entries at or below it count as already applied. TrapQueue
// is the full ordered queue as comma-separated "index:Type" entries with 1-based
// indexes into the framework's received-item list, so a reconnect rebuilds the
// identical queue and each entry still applies exactly once.
class VCArchipelagoTraps extends Object;

var string SeedTag;
var string BaselineIndex;
var string TrapQueue;
