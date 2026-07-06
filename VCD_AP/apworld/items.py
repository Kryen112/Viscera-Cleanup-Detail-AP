"""Items. Progression items are the level-access unlocks plus, under
toolsanity, the per-level tool and machine unlocks (see toolsanity.py for the
tool model). The rest is filler, with an optional share of traps.
"""

from __future__ import annotations

from .levels import LEVELS
from .toolsanity import (PROGRESSION_TOOL_KEYS, TOOL_KEY_ORDER,
                         tool_item_name)
from .traps import TRAP_NAMES, USEFUL_NAMES

# Arbitrary stable base for this game's ids. Item ids and location ids live in
# separate ranges so they never collide.
ITEM_ID_BASE = 0x5643_0000  # "VC" 0000


def access_item_name(display_name: str) -> str:
    return f"{display_name} Access"


LEVEL_ACCESS_ITEMS: list[str] = [access_item_name(d) for _, d, _ in LEVELS]

# Generic filler. VCD has no item economy, so filler is flavor only.
FILLER_NAMES: list[str] = ["Overtime Pay", "Coffee Break"]

# Retired names stay in the ordered list to hold their id slot, so every later
# id keeps its value, but they leave the datapackage and are never created.
RETIRED_NAMES: list[str] = ["Spare Bucket"]

# Toolsanity items: one name per tool per level, in frozen order (levels in
# table order, tools in key order), whether or not the tool exists on the
# level. Ids for absent combinations are never created, but reserving them
# means a presence correction can never shift a later id.
TOOL_ITEMS: list[str] = [
    tool_item_name(_display, _key)
    for _, _display, _ in LEVELS
    for _key in TOOL_KEY_ORDER
]
PROGRESSION_TOOL_ITEMS: frozenset[str] = frozenset(
    tool_item_name(_display, _key)
    for _, _display, _ in LEVELS
    for _key in TOOL_KEY_ORDER if _key in PROGRESSION_TOOL_KEYS
)


def self_cleaning_mop_name(display_name: str) -> str:
    return f"{display_name} - Self-Cleaning Mop"


# One per level in table order: a useful unlock that keeps the level's mop from
# ever dirtying. Always created, independent of toolsanity.
CLEAN_MOP_ITEMS: list[str] = [
    self_cleaning_mop_name(_display) for _, _display, _ in LEVELS
]


def squeaky_boots_name(display_name: str) -> str:
    return f"{display_name} - Squeaky Clean Boots"


# One per level in table order: a useful unlock that keeps the janitor from
# ever tracking bloody footprints on that level. Always created, independent of
# toolsanity.
SQUEAKY_BOOTS_ITEMS: list[str] = [
    squeaky_boots_name(_display) for _, _display, _ in LEVELS
]

# Ids are assigned in list order. The tail below is frozen: a name added later
# appends at the end no matter which group it belongs to, so every existing id
# stays stable even for a seed generated with an older version.
_ID_ORDERED_NAMES: list[str] = LEVEL_ACCESS_ITEMS + FILLER_NAMES + [
    "Spare Bucket",
    "Mess Dump Trap",
    "Bucket Spill Trap",
    "Slowdown Trap",
    "Clean Water Bucket",
    "Empty Bin",
    "Speedup Trap",
] + TOOL_ITEMS + CLEAN_MOP_ITEMS + SQUEAKY_BOOTS_ITEMS
assert sorted(_ID_ORDERED_NAMES) == sorted(
    LEVEL_ACCESS_ITEMS + FILLER_NAMES + RETIRED_NAMES
    + TRAP_NAMES + USEFUL_NAMES + TOOL_ITEMS + CLEAN_MOP_ITEMS
    + SQUEAKY_BOOTS_ITEMS)

ITEM_NAME_TO_ID: dict[str, int] = {}
_next = ITEM_ID_BASE
for _name in _ID_ORDERED_NAMES:
    if _name not in RETIRED_NAMES:
        ITEM_NAME_TO_ID[_name] = _next
    _next += 1

ITEM_GROUPS: dict[str, list[str]] = {
    "Level Access": list(LEVEL_ACCESS_ITEMS),
    "Filler": list(FILLER_NAMES),
    "Traps": list(TRAP_NAMES),
    "Useful": list(USEFUL_NAMES),
    "Tools": list(TOOL_ITEMS),
    "Self-Cleaning Mop": list(CLEAN_MOP_ITEMS),
    "Squeaky Clean Boots": list(SQUEAKY_BOOTS_ITEMS),
}
