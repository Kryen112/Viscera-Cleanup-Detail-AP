"""Toolsanity: per-level tool and machine lock items and the cleanliness logic
they gate.

The scan table below is transcribed from the mod's APScanReport dev command,
run once per level on an untouched level (raw penalty-point sums straight from
the game's own punchout scoring). Presence tables come from the same scan's
machine counts plus a map-package search for the floor pickups. The core-kit
ceiling for the suspect levels is measured in game with APCleanCoreKit, since a
scan cannot tell how far the core kit reaches on its own.

A scan run before the classifier learned the map-specific splat types leaves
their points in its remainder column, where the band model cannot see whose
mess they are. UNSCANNED_SPLAT_PENALTY names the owner for every such splat
the scan counted, and an import assert holds the two in step.

The logic model is a core-kit ceiling. The core kit (hands, incinerator, mop,
and buckets) cleans a level to 100 percent on its own, so every cleanliness
check up to and including 100 percent (regular rungs and Employee of the Month)
comes with the core kit alone. Over 100 percent, each situational tool the level
has adds a fixed share (OVER_100_PER_TOOL_PERCENT), a conservative floor: the
report and stacking usually reach more, so higher rungs are often obtainable out
of logic, but the full kit always reaches the level's over-100 maximum. The
climb is also capped by the physical ceiling the missing tools leave: a tool's
own measured mess share (welder marks, vendor graffiti, J-HARM barrels) is
unreachable without that tool, so no toolset is ever credited a rung the mess it
cannot clear puts out of reach. A few levels leave a large share of mess the
core kit cannot clear at all (recorded in CORE_KIT_CEILING_PERCENT): the core
kit tops out around that ceiling there, and every check above it waits for all
of the level's EXTRA_CLEAN_TOOLS, one on most of them and two on Uprinsing.
That ceiling is the only guard against a level whose over-100 headroom hides a
tool's share, since the import assert compares against a theoretical maximum a
real shift rarely banks. A tool stored where only
another tool reaches (TOOL_REACH_PREREQUISITES) counts as usable only once
that prerequisite is also held. Physical pickups (collectibles and Bob notes)
need the level's clean kit, because a trophy only banks on a not-fired
punch-out; the Overgrowth pickaxe also needs the shovel to dig it out, and
Athena's Wrath's blue easter egg needs the J-HARM to reach.

The Slosh-O-Matic slot in this model is satisfiable two ways: the machine
unlock itself, or the level's Self-Cleaning Mop (a mop that never dirties needs
no rinse bucket). The rules layer folds either into the unlocked key set before
calling in here; this module only sees tool keys.
"""

from __future__ import annotations

from .levels import LEVELS, MAP_NAMES, MAX_CLEAN_PERCENT_BY_MAP
from .locations import CEILING_STEP_FLOOR

# Tool keys are the client-to-mod contract written into the grants file;
# labels are the player-facing item name suffixes.
TOOL_LABELS: dict[str, str] = {
    "Hands": "Hands",
    "Welder": "Laser Welder",
    "Shovel": "Shovel",
    "Lift": "J-HARM",
    "Vendor": "Vendor",
    "Incinerator": "Incinerator",
    "Sniffer": "Sniffer",
    "Broom": "Broom",
    "Bins": "Bin Dispenser",
    "Mop": "Mop",
    "SloshOMatic": "Slosh-O-Matic",
}

# Item ids are assigned for every tool on every level in a frozen order, so a
# later presence correction can never shift an id; presence only controls
# which items a seed creates.
TOOL_KEY_ORDER: list[str] = list(TOOL_LABELS)

PROGRESSION_TOOL_KEYS: frozenset[str] = frozenset({
    "Hands", "Welder", "Shovel", "Lift", "Vendor", "Incinerator",
    "Mop", "SloshOMatic",
})
USEFUL_TOOL_KEYS: frozenset[str] = frozenset({"Sniffer", "Broom", "Bins"})

# The tools that clear the bulk of a level's mess (mop for blood and scorch,
# hands and incinerator for debris, welder for bullet holes). A started
# level's copies of these are front-loaded so a fresh seed opens with a level
# worth taking deep, rather than only shallow new levels. The Lift, Vendor,
# and Shovel are situational and left to the normal shuffle.
CORE_CLEANING_KEYS: frozenset[str] = frozenset({
    "Hands", "Incinerator", "Welder", "Mop", "SloshOMatic",
})

# The core kit: the tools that clean a level to 100 percent on their own (blood
# and scorch with the mop and buckets, debris with the hands and incinerator).
# Every level has all four. A level's full clean kit is this set plus the
# EXTRA_CLEAN_TOOLS the level needs on top (see below).
CORE_KIT_KEYS: frozenset[str] = frozenset({
    "Hands", "Incinerator", "Mop", "SloshOMatic",
})

# The situational progression tools: everything the core kit does not cover.
# Each one a level has adds a fixed share over 100 percent (see toolset_cap);
# they gate no sub-100 or 100 check, only the over-100 ladder.
SITUATIONAL_TOOL_KEYS: frozenset[str] = PROGRESSION_TOOL_KEYS - CORE_KIT_KEYS

# Percent each situational tool a level has adds over 100. A conservative floor:
# the report and stacking usually reach more, so higher rungs are often
# obtainable out of logic, but the full kit always reaches the level's maximum.
OVER_100_PER_TOOL_PERCENT = 10.0

# The default free pair and the hard-start free pair (the random_starting_kit
# option rolls per level). The displaced pair becomes that level's items.
DEFAULT_FREE_KEYS: frozenset[str] = frozenset({"Mop", "SloshOMatic"})
HARD_START_FREE_KEYS: frozenset[str] = frozenset({"Hands", "Incinerator"})

# Scan sums per map, raw penalty points, then one count:
# (start, mop, welder, hands_disposal, barrels, equipment, vendor, free,
#  remainder, unknown_splats). The free column is machine-use work that no lock
# gates (gravity consoles, incinerator doors standing open). The unknown column
# counts splats the scan's chain does not recognize; their points sit
# unattributed inside the remainder, so UNSCANNED_SPLAT_PENALTY below names the
# tool that owns each one.
_SCAN: dict[str, tuple[float, float, float, float, float, float, float,
                       float, float, int]] = {
    "VC_SplatterStation": (7851.0, 3605.0, 475.0, 3630.0, 75.0, 66.0, 0.0, 0.0, 0.0, 0),
    "VC_RustStation": (7808.0, 4672.5, 0.0, 3050.0, 52.5, 33.0, 0.0, 0.0, 0.0, 0),
    "VC_Section8": (5518.0, 3395.0, 0.0, 2060.0, 30.0, 33.0, 0.0, 0.0, 0.0, 0),
    "VC_ZeroG": (5727.5, 1627.5, 0.0, 3975.0, 75.0, 0.0, 0.0, 50.0, 0.0, 0),
    "VC_MedBay": (23818.5, 15610.0, 1200.0, 6405.0, 7.5, 36.0, 560.0, 0.0, 0.0, 0),
    "VC_Sewer": (21758.5, 15940.0, 925.0, 4630.0, 52.5, 51.0, 160.0, 0.0, 0.0, 0),
    "VC_Caduceus": (22611.0, 12765.0, 3225.0, 6140.0, 15.0, 66.0, 400.0, 0.0, 0.0, 0),
    "VC_Cryo": (24752.5, 15622.5, 1530.0, 7610.0, 15.0, 0.0, 160.0, 0.0, -185.0, 0),
    "VC_Digsite": (20956.5, 10430.0, 2125.0, 7535.0, 7.5, 69.0, 240.0, 0.0, 550.0, 0),
    "VC_Hall": (9828.0, 5665.0, 1100.0, 3000.0, 30.0, 33.0, 0.0, 0.0, 0.0, 0),
    "VC_Greenhouse": (13293.5, 5565.0, 0.0, 7287.5, 15.0, 66.0, 320.0, 0.0, 40.0, 0),
    "VC_Paintenance": (15958.0, 8855.0, 1300.0, 5550.0, 15.0, 33.0, 240.0, 0.0, -35.0, 0),
    "VC_Dark": (13595.5, 8360.0, 1400.0, 3540.0, 22.5, 33.0, 240.0, 0.0, 0.0, 0),
    "VC_ZeroG_New": (25810.5, 11095.0, 2295.0, 12315.0, 22.5, 33.0, 0.0, 50.0, 0.0, 0),
    "VC_Robot": (32915.5, 11562.5, 5610.0, 8395.0, 0.0, 48.0, 560.0, 0.0, 6740.0, 65),
    "VC_Jungle": (11821.5, 5042.5, 1985.0, 4220.0, 75.0, 99.0, 400.0, 0.0, 0.0, 0),
    "VC_IceStation": (7033.5, 3867.5, 0.0, 2765.0, 15.0, 66.0, 320.0, 0.0, 0.0, 0),
    "VC_Incubator": (41951.0, 6697.5, 1690.0, 4325.0, 7.5, 66.0, 320.0, 0.0, 28845.0, 364),
    "VC_Uprinsing": (22385.5, 5277.5, 5370.0, 6595.0, 60.0, 33.0, 320.0, 0.0, 4730.0, 52),
    "VC_Energy_01": (25311.0, 6667.5, 2295.0, 9400.0, 0.0, 51.0, 560.0, 0.0, 6337.5, 0),
    "VC_Darkening": (13590.5, 7420.0, 0.0, 5885.0, 120.0, 33.0, 0.0, 0.0, 132.5, 0),
    "VC_Mantis_01": (17788.5, 10272.5, 0.0, 5940.0, 45.0, 51.0, 0.0, 0.0, 1480.0, 21),
    "VC_Horror_01": (18915.5, 12600.0, 0.0, 7030.0, 0.0, 200.0, 0.0, 0.0, -914.5, 0),
    "VC_Vulcan_01": (23311.5, 6907.5, 3942.0, 14135.0, 30.0, 980.0, 0.0, 0.0, -2683.0, 0),
    "V_Santa01": (13470.0, 8330.0, 0.0, 3884.0, 0.0, 0.0, 0.0, 0.0, 1256.0, 0),
    "sw_temple": (9425.5, 2715.0, 0.0, 4624.0, 0.0, 240.0, 0.0, 0.0, 1846.5, 0),
}

# The splat types the scan's classification chain does not recognize. It sorts
# splats by SplatType and knows blood, scorch, bullet holes, lightning scars,
# and goo jars; every other type falls through into the remainder, where the
# band model cannot see whose mess it is. Each entry names the tool that owns
# the type, the count the scan reported, and the per-splat penalty read from
# the map handler's own InfractionResults defaults. Robot footprints
# (VCSplat_MechFoot) and alien creep (VCSplat_Creep) both extend
# VCSplat_BulletHole, the class the welding laser sweeps, so only the welder
# clears them. Graffiti (VCSplat_Paint) takes the vendor's acid vials and a wet
# mop. A map the scan counts unknown splats on and this table does not name
# fails the import assert below.
UNSCANNED_SPLAT_PENALTY: dict[str, tuple[str, int, float]] = {
    # map: (owning tool key, splat count, penalty each)
    "VC_Robot": ("Welder", 65, 30.0),        # MechFoot, handler bit 8388608
    "VC_Mantis_01": ("Welder", 21, 30.0),    # Creep, handler bit 1048576
    "VC_Incubator": ("Welder", 364, 30.0),   # Creep, handler bit 2097152
    "VC_Uprinsing": ("Vendor", 52, 50.0),    # Paint, handler bit 2097152
}

# Levels holding each optional tool. Hands, Incinerator, Mop, Slosh-O-Matic,
# Sniffer, Broom, and Bin Dispenser exist on every level.
WELDER_MAPS: frozenset[str] = frozenset({
    "VC_SplatterStation", "VC_MedBay", "VC_Sewer", "VC_Caduceus", "VC_Cryo",
    "VC_Digsite", "VC_Hall", "VC_Greenhouse", "VC_Paintenance", "VC_Dark",
    "VC_ZeroG_New", "VC_Robot", "VC_Jungle", "VC_IceStation", "VC_Incubator",
    "VC_Uprinsing", "VC_Energy_01", "VC_Darkening", "VC_Mantis_01",
    "VC_Vulcan_01",
})
SHOVEL_MAPS: frozenset[str] = frozenset({
    "VC_Jungle", "VC_Darkening", "VC_Digsite",
})
LIFT_MAPS: frozenset[str] = frozenset({
    "VC_SplatterStation", "VC_RustStation", "VC_Section8", "VC_MedBay",
    "VC_Caduceus", "VC_Digsite", "VC_Hall", "VC_Greenhouse", "VC_Dark",
    "VC_Robot", "VC_Jungle", "VC_IceStation", "VC_Incubator", "VC_Uprinsing",
    "VC_Energy_01", "VC_Darkening", "VC_Mantis_01", "VC_Horror_01",
    "VC_Vulcan_01",
})
VENDOR_MAPS: frozenset[str] = frozenset({
    "VC_MedBay", "VC_Sewer", "VC_Caduceus", "VC_Cryo", "VC_Digsite",
    "VC_Greenhouse", "VC_Paintenance", "VC_Dark", "VC_ZeroG_New", "VC_Robot",
    "VC_Jungle", "VC_IceStation", "VC_Incubator", "VC_Uprinsing",
    "VC_Energy_01", "VC_Darkening", "VC_Mantis_01", "VC_Horror_01",
    "VC_Vulcan_01",
})

# Played knowledge: a tool stored where only another tool reaches. Holding
# the unlock is not enough there; the tool counts as usable only once its
# prerequisite is also held. Athena's Wrath keeps its laser welder somewhere
# only the J-HARM reaches.
TOOL_REACH_PREREQUISITES: dict[str, dict[str, frozenset[str]]] = {
    "VC_Hall": {"Welder": frozenset({"Lift"})},
}

# Levels the core kit alone cannot clean to 100 percent, with the percent it
# tops out at and the situational tools that clear the rest. Incubation
# Emergency, Core Sample, The Vulcan Affair, and Revolutionary Robotics leave
# welder mess (bullet holes, creep, and robot footprints). Uprinsing leaves
# both graffiti that needs the vendor's acid vials and a welder share larger
# than the graffiti, so it names two tools. The first three ceilings are
# measured with the APCleanCoreKit dev command. The Vulcan ceiling is a
# conservative floor under the arithmetic bound of 98.86 (the known maximum
# 115.90 minus the scanned welder 16.91 and barrel 0.13 shares), pending an
# APCleanCoreKit measurement; the bound proves the core kit cannot reach 100
# there. Played knowledge: Revolutionary Robotics strands the core kit short
# of 100, so it sits with the measured three at a conservative 80, pending its
# own measurement.
#
# The test that sorts a suspect from a safe level is what share of a level's
# over-100 headroom the core kit has to bank to make up the mess it cannot
# reach. Revolutionary Robotics needs 77.7 percent of its headroom (24.67
# points of welder and vendor mess against 31.74 of headroom), which puts it
# with the other suspects; every level below about half its headroom reaches
# 100 with room to spare, Pestilent Penitentiary's 21 creep splats among them
# at 7.9 percent. A level absent here is fully cleaned by the core kit
# (ceiling 100, no extra tools). Refine a ceiling if a rung strands.
#
# A level can need more than one extra tool, and the ceiling then holds until
# every one is in hand: Uprinsing leaves 23.99 percent welder mess on top of
# its 13.04 percent of graffiti, so the vendor alone still has to bank 70
# percent of the level's headroom to reach 100, the same bet Revolutionary
# Robotics loses.
CORE_KIT_CEILING_PERCENT: dict[str, float] = {
    "VC_Incubator": 80.0,
    "VC_Uprinsing": 80.0,
    "VC_Energy_01": 80.0,
    "VC_Vulcan_01": 90.0,
    "VC_Robot": 80.0,
}
EXTRA_CLEAN_TOOLS: dict[str, frozenset[str]] = {
    "VC_Incubator": frozenset({"Welder"}),
    "VC_Uprinsing": frozenset({"Vendor", "Welder"}),
    "VC_Energy_01": frozenset({"Welder"}),
    "VC_Vulcan_01": frozenset({"Welder"}),
    "VC_Robot": frozenset({"Welder"}),
}

# Played knowledge: levels where a toolset without Hands hits a hard ceiling no
# scan can see. House of Horror walls its deeper areas behind carried keys and
# measures 45 percent with mop and buckets alone, incident reports included.
# Penumbra's 40 is a conservative floor under its rung 49 playing out of reach,
# which proves only that the same pair stops short of the 54.60 its scanned mop
# share credits, pending a measurement. No mechanism is recorded there, so
# revise it from play, never from the scan.
NO_HANDS_CEILING_PERCENT: dict[str, float] = {
    "VC_Horror_01": 45.0,
    "VC_Darkening": 40.0,
}

# A hands-and-incinerator start without a mop spreads bloody footprints while
# it works; its opening credit is capped low.
HARD_START_OPENING_CAP_PERCENT = 15.0

# The cleanliness a shift needs to punch out in good standing (not fired). The
# Punch Out and Speedrun checks gate on reaching it. With the one-step slack
# this clears only once the full clean kit is held, matching the game: a
# barely-cleaned shift gets the janitor fired and a fired punch-out never
# counts.
PUNCHOUT_CLEAN_PERCENT = 95


def tool_item_name(display_name: str, tool_key: str) -> str:
    return f"{display_name} - {TOOL_LABELS[tool_key]}"


def tools_present(map_name: str) -> list[str]:
    """The tool keys that exist on the level, in frozen id order."""
    present = []
    for key in TOOL_KEY_ORDER:
        if key == "Welder" and map_name not in WELDER_MAPS:
            continue
        if key == "Shovel" and map_name not in SHOVEL_MAPS:
            continue
        if key == "Lift" and map_name not in LIFT_MAPS:
            continue
        if key == "Vendor" and map_name not in VENDOR_MAPS:
            continue
        present.append(key)
    return present


def free_keys(map_name: str, hard_start_maps: "set[str]") -> frozenset[str]:
    return (HARD_START_FREE_KEYS if map_name in hard_start_maps
            else DEFAULT_FREE_KEYS)


def item_keys(map_name: str, hard_start_maps: "set[str]") -> list[str]:
    """The tool keys a seed creates items for on the level: everything present
    except the level's free pair."""
    free = free_keys(map_name, hard_start_maps)
    return [k for k in tools_present(map_name) if k not in free]


def scan_start_score(map_name: str) -> "float | None":
    """The level's transcribed StartingCleanupScore, for the client's
    cross-check against the live level. None for a map outside the table."""
    row = _SCAN.get(map_name)
    return row[0] if row is not None else None


def core_kit_ceiling(map_name: str) -> float:
    """The percent the core kit alone reaches on the level: 100 unless a
    measured suspect level leaves mess only its extra tool can clear."""
    return CORE_KIT_CEILING_PERCENT.get(map_name, 100.0)


def usable_keys(map_name: str, unlocked: "frozenset[str]") -> frozenset[str]:
    """The unlocked tools the janitor can actually wield on the level: a tool
    stored where only another tool reaches drops out until that prerequisite
    is also unlocked. Prerequisites resolve one level deep: a prerequisite
    with a prerequisite of its own would need a fixpoint here."""
    prerequisites = TOOL_REACH_PREREQUISITES.get(map_name)
    if prerequisites is None:
        return unlocked
    return frozenset(key for key in unlocked
                     if prerequisites.get(key, frozenset()) <= unlocked)


def full_clean_keys(map_name: str) -> frozenset[str]:
    """The tools that clean the level to 100 percent: the core kit, plus the
    extra tools a suspect level needs on top. The free pair counts as held,
    so this set works for either starting kit. Holding it gates every
    cleanliness check up to and including 100 percent; each situational tool the
    level has then adds a share over 100 (see toolset_cap). A suspect level
    stays at its core-kit ceiling until every extra tool is held, so a level
    needing two gives no partial credit for the first."""
    return CORE_KIT_KEYS | EXTRA_CLEAN_TOOLS.get(map_name, frozenset())


class _Bands:
    """Precomputed mess shares for one level, as percents of the starting
    cleanup score. `free` is machine-use work no lock gates; `mop` is the
    blood and scorch the mop and buckets clear; the hands and incinerator
    clear the rest of the mess up to the level's core-kit ceiling.
    `situational` holds each situational tool's own measured share (welder
    marks, vendor graffiti, J-HARM barrels; the shovel has no scanned share),
    unreachable without that tool. A level's unscanned splats are added to
    their owner's share, because the scan columns leave them in the
    remainder."""

    def __init__(self, map_name: str) -> None:
        (start, _mop, _welder, _hands_disposal, _barrels, _equipment,
         _vendor, free, _remainder, _unknown) = _SCAN[map_name]
        self.free = free / start * 100.0
        self.mop = _mop / start * 100.0
        self.situational = {
            "Welder": _welder / start * 100.0,
            "Vendor": _vendor / start * 100.0,
            "Lift": _barrels / start * 100.0,
            "Shovel": 0.0,
        }
        unscanned = UNSCANNED_SPLAT_PENALTY.get(map_name)
        if unscanned is not None:
            owner, count, penalty = unscanned
            self.situational[owner] += count * penalty / start * 100.0


# Every splat the scan could not classify has to be attributed to a tool, or
# its points hide inside the remainder and the band model credits a toolset
# with mess it cannot reach; the import fails loudly instead.
for _map, _, _ in LEVELS:
    *_, _counted = _SCAN[_map]
    _attributed = UNSCANNED_SPLAT_PENALTY.get(_map)
    assert _counted == 0 or _attributed is not None, (
        f"{_map}: the scan counts {_counted} unknown splats and no"
        f" UNSCANNED_SPLAT_PENALTY row owns them")
    assert _counted > 0 or _attributed is None, (
        f"{_map}: UNSCANNED_SPLAT_PENALTY owns splats the scan never counted")
    assert _attributed is None or _attributed[1] == _counted, (
        f"{_map}: UNSCANNED_SPLAT_PENALTY counts {_attributed[1]} splats,"
        f" the scan counted {_counted}")
    assert _attributed is None or _attributed[0] in SITUATIONAL_TOOL_KEYS, (
        f"{_map}: UNSCANNED_SPLAT_PENALTY owner is not a situational tool")
    _extras = EXTRA_CLEAN_TOOLS.get(_map, frozenset())
    assert (_map in CORE_KIT_CEILING_PERCENT) == bool(_extras), (
        f"{_map}: a core-kit ceiling and its extra tools travel together")
    assert _extras <= frozenset(tools_present(_map)) & SITUATIONAL_TOOL_KEYS, (
        f"{_map}: EXTRA_CLEAN_TOOLS names something other than a situational"
        f" tool the level has")

for _table_name, _table in (("CORE_KIT_CEILING_PERCENT", CORE_KIT_CEILING_PERCENT),
                            ("EXTRA_CLEAN_TOOLS", EXTRA_CLEAN_TOOLS),
                            ("UNSCANNED_SPLAT_PENALTY", UNSCANNED_SPLAT_PENALTY),
                            ("NO_HANDS_CEILING_PERCENT", NO_HANDS_CEILING_PERCENT),
                            ("TOOL_REACH_PREREQUISITES", TOOL_REACH_PREREQUISITES)):
    _strays = set(_table) - set(MAP_NAMES)
    assert not _strays, f"{_table_name} names no such level: {sorted(_strays)}"

_BANDS: dict[str, _Bands] = {m: _Bands(m) for m, _, _ in LEVELS}

# A level the suspect table calls core-kit-cleanable must leave at least 100
# percent reachable without its situational tools, or the table is missing a
# row and checks strand; the import fails loudly instead.
for _map, _, _ in LEVELS:
    if _map not in CORE_KIT_CEILING_PERCENT:
        _reachable = (MAX_CLEAN_PERCENT_BY_MAP[_map]
                      - sum(_BANDS[_map].situational.values()))
        assert _reachable >= 100.0, (
            f"{_map}: the scan's situational shares contradict the"
            f" core-kit-cleans-to-100 claim ({_reachable:.2f})")

# A no-hands ceiling only means something below what the mop and buckets reach
# on their own; a row at or above that share is a silent no-op that reads as a
# live constraint. The import fails loudly instead.
for _map, _ceiling in NO_HANDS_CEILING_PERCENT.items():
    _mop_only = _BANDS[_map].free + _BANDS[_map].mop
    assert _ceiling < _mop_only, (
        f"{_map}: a no-hands ceiling of {_ceiling} clamps nothing, the mop"
        f" and buckets reach {_mop_only:.2f} there")


def _slack_step(step: int) -> int:
    """The grid the caps and slack are computed on: never finer than the 5
    percent grid the scan data and the community maxima were validated
    against, so a fine milestone step tightens the rung spacing but never the
    safety margins."""
    return max(step, CEILING_STEP_FLOOR)


def usable_total(map_name: str, step: int) -> int:
    """The level's known maximum floored to the slack grid. The one-step
    slack lives in the rung comparison, not here."""
    grid = _slack_step(step)
    return int(MAX_CLEAN_PERCENT_BY_MAP[map_name] // grid) * grid


def toolset_cap(map_name: str, step: int, unlocked: "frozenset[str]") -> float:
    """The percent the unlocked tool set reaches on the level. The caller folds
    the level's free pair into the unlocked set. The full clean kit reaches 100
    percent (and Employee of the Month and every sub-100 rung with it); each
    situational tool the level has then adds a fixed share over 100, and the
    full kit reaches the level's over-100 maximum. A partial core kit reaches
    only its share of the mess, up to the level's core-kit ceiling. A tool
    stored where only another tool reaches counts only once that prerequisite
    is also unlocked."""
    unlocked = usable_keys(map_name, unlocked)
    if full_clean_keys(map_name) <= unlocked:
        # The slack-step lift keeps every sub-100 rung and the 100 rung in logic
        # at 100 with the clean kit alone; each situational tool the level has
        # adds a fixed share over that, and the full kit reaches the maximum.
        # A missing tool's own measured mess share is out of reach without it,
        # so the climb is also capped by the physical ceiling that remains.
        total = float(usable_total(map_name, step))
        present = frozenset(k for k in tools_present(map_name)
                            if k in SITUATIONAL_TOOL_KEYS)
        held = present & unlocked
        if present <= held:
            return total
        bands = _BANDS[map_name]
        reachable = total - sum(bands.situational[k] for k in present - held)
        # The clean kit reaching 100 (with the slack lift) is the measured
        # claim of the suspect and scan tables, so the deduction never pulls
        # below it: it only trims the over-100 climb.
        floor = 100.0 + float(_slack_step(step))
        return min(total, max(reachable, floor),
                   floor + OVER_100_PER_TOOL_PERCENT * float(len(held)))
    bands = _BANDS[map_name]
    ceiling = core_kit_ceiling(map_name)
    hands = "Hands" in unlocked
    mop = "Mop" in unlocked and "SloshOMatic" in unlocked
    cap = bands.free
    if mop:
        cap += bands.mop
    if hands and "Incinerator" in unlocked:
        # Hands and the incinerator clear the rest of the mess up to the
        # ceiling. Without the mop the credit is capped low: working
        # bare-handed spreads bloody footprints until the mop arrives.
        share = ceiling - bands.free - bands.mop
        if not mop:
            share = min(share, HARD_START_OPENING_CAP_PERCENT)
        cap += max(0.0, share)
    cap = min(cap, ceiling)
    if not hands and map_name in NO_HANDS_CEILING_PERCENT:
        cap = min(cap, NO_HANDS_CEILING_PERCENT[map_name])
    return cap


def rung_in_logic(map_name: str, rung: int, step: int,
                  unlocked: "frozenset[str]") -> bool:
    """A milestone rung is in logic when the toolset's cap clears it by one
    slack-grid step (at least 5 points, so fine steps keep the step-5 margins).
    Every rung uses this: the clean kit clears Employee of the Month at 100 and
    every sub-100 rung, and each situational tool the level has opens more of
    the over-100 ladder, the full kit reaching the top."""
    return rung + _slack_step(step) <= toolset_cap(map_name, step, unlocked)


def free_kit_rungs(map_name: str, step: int,
                   hard_start_maps: "set[str]") -> "list[int]":
    """Every enabled milestone rung a level's free starting kit reaches.
    These are the rungs a player can clear before holding any tools."""
    kit = free_keys(map_name, hard_start_maps)
    return [rung for rung in range(step, 100, step)
            if rung_in_logic(map_name, rung, step, kit)]
