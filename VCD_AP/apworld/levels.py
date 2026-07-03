"""The playable level table, transcribed from the game's `VCProviders*.ini`.

Each entry is `(map_name, display_name, title)`:
- `map_name` is the authoritative key. It is the `MapName` the menu launches and
  the `Stats_<map_name>` key in `GlobalStatsData.sav`. Never guess it; it comes
  from the provider files.
- `display_name` is the player-facing name used in item and location strings,
  confirmed against the `FriendlyName` entries in the game's
  `Localization\\INT\\VCProviders*.int` files (including the game's own
  "Uprinsing" spelling).
- `title` is the Switch-game title the map ships under (base game is `Viscera`).

Hand-maintained source of truth. There is no generator.
"""

from __future__ import annotations

# (map_name, display_name, title)
LEVELS: list[tuple[str, str, str]] = [
    ("VC_SplatterStation", "Splatter Station", "Viscera"),
    ("VC_RustStation", "Rust-Station East", "Viscera"),
    ("VC_Section8", "Section 8", "Viscera"),
    ("VC_ZeroG", "Zero-G Therapy", "Viscera"),
    ("VC_MedBay", "Evil Science", "Viscera"),
    ("VC_Sewer", "Waste Disposal", "Viscera"),
    ("VC_Caduceus", "Caduceus", "Viscera"),
    ("VC_Cryo", "Cryogenesis", "Viscera"),
    ("VC_Digsite", "Unearthly Excavation", "Viscera"),
    ("VC_Hall", "Athena's Wrath", "Viscera"),
    ("VC_Greenhouse", "Hydroponic Hell", "Viscera"),
    ("VC_Paintenance", "Paintenance Tunnels", "Viscera"),
    ("VC_Dark", "Unrefinery", "Viscera"),
    ("VC_ZeroG_New", "Gravity Drive", "Viscera"),
    ("VC_Robot", "Revolutionary Robotics", "Viscera"),
    ("VC_Jungle", "Overgrowth", "Viscera"),
    ("VC_IceStation", "Frostbite", "Viscera"),
    ("VC_Incubator", "Incubation Emergency", "Viscera"),
    ("VC_Uprinsing", "Uprinsing", "Viscera"),
    ("VC_Energy_01", "Core Sample", "Viscera"),
    ("VC_Darkening", "Penumbra", "Viscera"),
    ("VC_Mantis_01", "Pestilent Penitentiary", "Viscera"),
    ("VC_Horror_01", "House of Horror", "Horror"),
    ("VC_Vulcan_01", "The Vulcan Affair", "Vulcan"),
    ("V_Santa01", "Santa's Workshop", "Santa"),
    ("sw_temple", "Zilla Pagoda", "Shadow"),
]

MAP_NAMES: list[str] = [m for m, _, _ in LEVELS]
DISPLAY_BY_MAP: dict[str, str] = {m: d for m, d, _ in LEVELS}
MAP_BY_DISPLAY: dict[str, str] = {d: m for m, d, _ in LEVELS}
TITLE_BY_MAP: dict[str, str] = {m: t for m, _, t in LEVELS}

# The Bob storyline data (note levels, the Digsite altar, collectible tables)
# lives in collectibles.py.

# The highest cleanliness percentage each level can reach, from community
# measurements. Evil Science has several stacking-dependent values; the
# conservative 122.85 is the one used. These feed the above_and_beyond
# milestone ladder, whose top rung stays at least a full step under the
# maximum, so small measurement error cannot strand a check.
MAX_CLEAN_PERCENT_BY_MAP: dict[str, float] = {
    "VC_SplatterStation": 158.84,
    "VC_RustStation": 149.39,
    "VC_Section8": 160.64,
    "VC_ZeroG": 144.80,
    "VC_MedBay": 122.85,
    "VC_Sewer": 122.74,
    "VC_Caduceus": 127.95,
    "VC_Cryo": 136.42,
    "VC_Digsite": 161.08,
    "VC_Hall": 154.04,
    "VC_Greenhouse": 141.60,
    "VC_Paintenance": 129.33,
    "VC_Dark": 135.14,
    "VC_ZeroG_New": 113.78,
    "VC_Robot": 131.74,
    "VC_Jungle": 165.20,
    "VC_IceStation": 174.96,
    "VC_Incubator": 117.67,
    "VC_Uprinsing": 134.57,
    "VC_Energy_01": 142.61,
    "VC_Darkening": 178.96,
    "VC_Mantis_01": 148.25,
    "VC_Horror_01": 161.82,
    "VC_Vulcan_01": 115.90,
    "V_Santa01": 172.18,
    "sw_temple": 209.24,
}
