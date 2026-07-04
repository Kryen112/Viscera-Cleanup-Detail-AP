// The HUD's toast bookkeeping, persisted so toasts never replay. Its own config
// class (own ini section), so its SaveConfig can never clobber the fields the
// GameInfo's VCArchipelagoState instance owns.
//
// ShownSessionTag is the feed session whose entries have been shown;
// ShownIndex is the highest entry index already displayed. A per-level new of
// a config object copies the class defaults, which read the ini once at game
// launch, so the HUD mirrors both fields into the defaults before SaveConfig
// (an instance SaveConfig never updates them itself).
class VCArchipelagoMessageState extends Object
    config(VCArchipelago);

var config string ShownSessionTag;
var config int ShownIndex;
