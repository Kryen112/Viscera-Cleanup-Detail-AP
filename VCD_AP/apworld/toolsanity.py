"""Toolsanity: per-level tool and machine lock items and the band-based
milestone logic they gate.

The scan table below is transcribed from the mod's APScanReport dev command,
run once per level on an untouched level (raw penalty-point sums straight from
the game's own punchout scoring). Presence tables come from the same scan's
machine counts plus a map-package search for the floor pickups. Hand-measured
knowledge fills the two holes a scan cannot see: which remainders belong to
which tool, and the J-HARM's spatial share (a flat reservation).

The logic model is additive bands. Each level's regular milestone ladder is
carved into bands owned by item sets; a toolset's cap is the sum of the bands
it holds, and a rung is in logic when the cap clears it by one full step. The
full kit always caps at the level's usable total (map-specific mess lives in
the unclaimed remainder, so band sums alone would strand the upper ladder on
remainder-heavy levels). Employee of the Month, Speedrun, over-100 rungs, the
punch-out check, collectibles, and Bob notes all require the full kit.
"""

from __future__ import annotations

from .levels import LEVELS, MAX_CLEAN_PERCENT_BY_MAP
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

# The default free pair and the hard-start free pair (the random_starting_kit
# option rolls per level). The displaced pair becomes that level's items.
DEFAULT_FREE_KEYS: frozenset[str] = frozenset({"Mop", "SloshOMatic"})
HARD_START_FREE_KEYS: frozenset[str] = frozenset({"Hands", "Incinerator"})

# Scan sums per map, raw penalty points:
# (start, mop, welder, hands_disposal, barrels, equipment, vendor, free,
#  remainder). The free column is machine-use work that no lock gates
# (gravity consoles, incinerator doors standing open).
_SCAN: dict[str, tuple[float, float, float, float, float, float, float,
                       float, float]] = {
    "VC_SplatterStation": (7851.0, 3605.0, 475.0, 3630.0, 75.0, 66.0, 0.0, 0.0, 0.0),
    "VC_RustStation": (7808.0, 4672.5, 0.0, 3050.0, 52.5, 33.0, 0.0, 0.0, 0.0),
    "VC_Section8": (5518.0, 3395.0, 0.0, 2060.0, 30.0, 33.0, 0.0, 0.0, 0.0),
    "VC_ZeroG": (5727.5, 1627.5, 0.0, 3975.0, 75.0, 0.0, 0.0, 50.0, 0.0),
    "VC_MedBay": (23818.5, 15610.0, 1200.0, 6405.0, 7.5, 36.0, 560.0, 0.0, 0.0),
    "VC_Sewer": (21758.5, 15940.0, 925.0, 4630.0, 52.5, 51.0, 160.0, 0.0, 0.0),
    "VC_Caduceus": (22611.0, 12765.0, 3225.0, 6140.0, 15.0, 66.0, 400.0, 0.0, 0.0),
    "VC_Cryo": (24752.5, 15622.5, 1530.0, 7610.0, 15.0, 0.0, 160.0, 0.0, -185.0),
    "VC_Digsite": (20956.5, 10430.0, 2125.0, 7535.0, 7.5, 69.0, 240.0, 0.0, 550.0),
    "VC_Hall": (9828.0, 5665.0, 1100.0, 3000.0, 30.0, 33.0, 0.0, 0.0, 0.0),
    "VC_Greenhouse": (13293.5, 5565.0, 0.0, 7287.5, 15.0, 66.0, 320.0, 0.0, 40.0),
    "VC_Paintenance": (15958.0, 8855.0, 1300.0, 5550.0, 15.0, 33.0, 240.0, 0.0, -35.0),
    "VC_Dark": (13595.5, 8360.0, 1400.0, 3540.0, 22.5, 33.0, 240.0, 0.0, 0.0),
    "VC_ZeroG_New": (25810.5, 11095.0, 2295.0, 12315.0, 22.5, 33.0, 0.0, 50.0, 0.0),
    "VC_Robot": (32915.5, 11562.5, 5610.0, 8395.0, 0.0, 48.0, 560.0, 0.0, 6740.0),
    "VC_Jungle": (11821.5, 5042.5, 1985.0, 4220.0, 75.0, 99.0, 400.0, 0.0, 0.0),
    "VC_IceStation": (7033.5, 3867.5, 0.0, 2765.0, 15.0, 66.0, 320.0, 0.0, 0.0),
    "VC_Incubator": (41951.0, 6697.5, 1690.0, 4325.0, 7.5, 66.0, 320.0, 0.0, 28845.0),
    "VC_Uprinsing": (22385.5, 5277.5, 5370.0, 6595.0, 60.0, 33.0, 320.0, 0.0, 4730.0),
    "VC_Energy_01": (25311.0, 6667.5, 2295.0, 9400.0, 0.0, 51.0, 560.0, 0.0, 6337.5),
    "VC_Darkening": (13590.5, 7420.0, 0.0, 5885.0, 120.0, 33.0, 0.0, 0.0, 132.5),
    "VC_Mantis_01": (17788.5, 10272.5, 0.0, 5940.0, 45.0, 51.0, 0.0, 0.0, 1480.0),
    "VC_Horror_01": (18915.5, 12600.0, 0.0, 7030.0, 0.0, 200.0, 0.0, 0.0, -914.5),
    "VC_Vulcan_01": (23311.5, 6907.5, 3942.0, 14135.0, 30.0, 980.0, 0.0, 0.0, -2683.0),
    "V_Santa01": (13470.0, 8330.0, 0.0, 3884.0, 0.0, 0.0, 0.0, 0.0, 1256.0),
    "sw_temple": (9425.5, 2715.0, 0.0, 4624.0, 0.0, 240.0, 0.0, 0.0, 1846.5),
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

# Played knowledge: which tool a level's scan remainder belongs to. Uprinsing
# leans on vendor restocking; Incubation Emergency's creep and hive debris are
# welder work. Shovel levels claim their own remainder by default; anything
# else stays unclaimed as safety margin.
_REMAINDER_TOOL: dict[str, str] = {
    "VC_Uprinsing": "Vendor",
    "VC_Incubator": "Welder",
}

# Played knowledge: levels whose deeper areas sit behind carried keys, so any
# toolset without Hands hits a hard ceiling no scan can see. House of
# Horror's measured ceiling is 45 percent with mop and buckets alone,
# incident reports included.
NO_HANDS_CEILING_PERCENT: dict[str, float] = {
    "VC_Horror_01": 45.0,
}

# The flat reservation for the one share no scan can produce: mess only the
# J-HARM reaches. Subtracted from any cap missing Hands plus Lift.
LIFT_RESERVATION_PERCENT = 10.0

# The band value cap for the special tools.
BAND_CAP_PERCENT = 10.0

# A hands-and-incinerator start without a mop spreads bloody footprints while
# it works; its opening credit is capped low.
HARD_START_OPENING_CAP_PERCENT = 15.0


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


def full_kit_keys(map_name: str) -> frozenset[str]:
    """The progression tools of the level's full kit; the free pair counts as
    held, so this set works for either starting kit."""
    return frozenset(k for k in tools_present(map_name)
                     if k in PROGRESSION_TOOL_KEYS)


class _Bands:
    """Precomputed percent shares for one level."""

    def __init__(self, map_name: str) -> None:
        (start, mop, welder, hands_disposal, barrels, equipment, vendor,
         free, remainder) = _SCAN[map_name]
        remainder_percent = remainder / start * 100.0
        attributed = _REMAINDER_TOOL.get(map_name)
        self.free = free / start * 100.0
        self.mop = mop / start * 100.0
        self.welder = min(
            BAND_CAP_PERCENT,
            (welder / start * 100.0)
            + (remainder_percent if attributed == "Welder" else 0.0),
        ) if map_name in WELDER_MAPS else 0.0
        self.vendor = min(
            BAND_CAP_PERCENT,
            (vendor / start * 100.0)
            + (remainder_percent if attributed == "Vendor" else 0.0),
        ) if map_name in VENDOR_MAPS else 0.0
        self.shovel = min(
            BAND_CAP_PERCENT, max(remainder_percent, 0.0),
        ) if map_name in SHOVEL_MAPS and attributed is None else 0.0
        # The hands-and-incinerator clamp: the scanned debris share plus the
        # over-100 headroom (reports, stacking, and restoration are clipboard
        # and hands work), minus any negative remainder (a per-map handler
        # scoring actors differently than the base classification).
        headroom = MAX_CLEAN_PERCENT_BY_MAP[map_name] - 100.0
        self.hands_incinerator_clamp = max(
            0.0,
            (hands_disposal + barrels + equipment) / start * 100.0
            + headroom + min(remainder_percent, 0.0),
        )
        self.lift_reserved = map_name in LIFT_MAPS


_BANDS: dict[str, _Bands] = {m: _Bands(m) for m, _, _ in LEVELS}


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
    """The percent the unlocked tool set reaches on the level. The caller
    folds the level's free pair into the unlocked set."""
    bands = _BANDS[map_name]
    if full_kit_keys(map_name) <= unlocked:
        return float(usable_total(map_name, step))
    hands = "Hands" in unlocked
    mop = "Mop" in unlocked and "SloshOMatic" in unlocked
    cap = bands.free
    if mop:
        cap += bands.mop
    if hands and "Incinerator" in unlocked:
        leftover = (usable_total(map_name, step) - bands.free - bands.mop
                    - bands.welder - bands.vendor - bands.shovel
                    - (LIFT_RESERVATION_PERCENT if bands.lift_reserved else 0.0))
        share = max(0.0, min(leftover, bands.hands_incinerator_clamp))
        if not mop:
            # Working bare-handed spreads bloody footprints; the credit is
            # deliberately low until the mop arrives.
            share = min(share, HARD_START_OPENING_CAP_PERCENT)
        cap += share
    # The welder leaves soot behind as it works, and vendor restock work can
    # end in scrubbing (Uprinsing's graffiti takes acid vials, hands, and a
    # wet mop), so both bands need the mop as well.
    if hands and mop and "Welder" in unlocked:
        cap += bands.welder
    if hands and mop and "Vendor" in unlocked:
        cap += bands.vendor
    if hands and "Shovel" in unlocked:
        cap += bands.shovel
    if bands.lift_reserved and not (hands and "Lift" in unlocked):
        cap -= LIFT_RESERVATION_PERCENT
    if not hands and map_name in NO_HANDS_CEILING_PERCENT:
        cap = min(cap, NO_HANDS_CEILING_PERCENT[map_name])
    return cap


def rung_in_logic(map_name: str, rung: int, step: int,
                  unlocked: "frozenset[str]") -> bool:
    """A regular ladder rung is in logic when the toolset's cap clears it by
    one slack-grid step (at least 5 points, so fine steps keep the step-5
    margins). Rungs at or past 100 use the full-kit rule instead."""
    return rung + _slack_step(step) <= toolset_cap(map_name, step, unlocked)


def free_kit_rungs(map_name: str, step: int,
                   hard_start_maps: "set[str]") -> "list[int]":
    """Every enabled milestone rung a level's free starting kit reaches.
    These are the rungs a player can clear before holding any tools."""
    kit = free_keys(map_name, hard_start_maps)
    return [rung for rung in range(step, 100, step)
            if rung_in_logic(map_name, rung, step, kit)]
