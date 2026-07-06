// Output of the APScanReport dev command, written with SaveConfig to
// UDKGame\Config\UDKVCArchipelago.ini. One line per scanned map: the starting
// score, the per-category penalty sums the toolsanity logic table is built
// from, and the machine presence counts. Dev tooling only; players never run
// the scan.
class VCArchipelagoScanResults extends Object
    config(VCArchipelago);

var config array<string> ScanLines;
