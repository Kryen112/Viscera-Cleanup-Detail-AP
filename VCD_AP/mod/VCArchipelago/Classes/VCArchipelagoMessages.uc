// The toast feed the client writes and the HUD reads fresh with BasicLoadObject
// (Saves\VCArchipelagoMessages.sav). The client is the only writer.
//
// SessionTag names one client session on one seed; the HUD resets its shown
// counter when the tag changes, so a fresh session replays its own feed from
// the top and another seed's leftovers never show. Messages holds newline-joined
// entries, each "index:segments" with a 1-based index that only rises within a
// session; segments are tab-joined, each six hex characters RRGGBB then text.
class VCArchipelagoMessages extends Object;

var string SessionTag;
var string Messages;
