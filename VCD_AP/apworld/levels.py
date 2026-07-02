"""The playable level table, transcribed from the game's `VCProviders*.ini`.

Each entry is `(map_name, display_name, title)`:
- `map_name` is the authoritative key. It is the `MapName` the menu launches and
  the `Stats_<map_name>` key in `GlobalStatsData.sav`. Never guess it; it comes
  from the provider files.
- `display_name` is the player-facing name used in item and location strings.
  Most are confirmed; the three marked TODO use the internal shorthand and must
  be confirmed against the game's `.int` localization before release.
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
    ("VC_Dark", "Penumbra", "Viscera"),
    ("VC_ZeroG_New", "Gravity Drive", "Viscera"),
    ("VC_Robot", "Revolutionary Robotics", "Viscera"),
    ("VC_Jungle", "Overgrowth", "Viscera"),
    ("VC_IceStation", "Frostbite", "Viscera"),
    ("VC_Incubator", "Incubation Emergency", "Viscera"),
    ("VC_Uprinsing", "Uprising", "Viscera"),
    ("VC_Energy_01", "Energy", "Viscera"),          # TODO confirm display name vs .int
    ("VC_Darkening", "Darkening", "Viscera"),        # TODO confirm display name vs .int
    ("VC_Mantis_01", "Mantis", "Viscera"),           # TODO confirm display name vs .int
    ("VC_Horror_01", "House of Horror", "Horror"),
    ("VC_Vulcan_01", "The Vulcan Affair", "Vulcan"),
    ("V_Santa01", "Santa's Rampage", "Santa"),
    ("sw_temple", "Shadow Warrior", "Shadow"),
]

MAP_NAMES: list[str] = [m for m, _, _ in LEVELS]
DISPLAY_BY_MAP: dict[str, str] = {m: d for m, d, _ in LEVELS}
MAP_BY_DISPLAY: dict[str, str] = {d: m for m, d, _ in LEVELS}
TITLE_BY_MAP: dict[str, str] = {m: t for m, _, t in LEVELS}

# The Digsite is the altar level for the Bob storyline (bFoundBob). The nine
# note-bearing levels are not yet mapped to their map names; that comes with the
# collectibles module. Until then goals that need Bob use a conservative
# over-approximation (see __init__).
BOB_ALTAR_MAP = "VC_Digsite"
