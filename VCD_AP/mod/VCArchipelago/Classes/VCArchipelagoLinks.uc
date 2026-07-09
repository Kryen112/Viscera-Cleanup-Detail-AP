// The link-event queue the client writes and the mod reads fresh with
// BasicLoadObject (Saves\VCArchipelagoLinks.sav): deaths and traps that
// arrive over the DeathLink and TrapLink bounce channels rather than as
// received items. The client is the only writer.
//
// SessionTag is the connected seed plus a per-connect nonce; a tag change
// baselines the applied counter to the newest entry, so another session's
// leftovers never apply. DeathLinkOn is "1" when the slot plays with death
// link, which makes any one janitor's death take the whole crew down.
// Entries is comma-joined "index:Type" with a 1-based index that only rises
// within a session; Type is a trap type token or "Death".
class VCArchipelagoLinks extends Object;

var string SessionTag;
var string DeathLinkOn;
var string Entries;
