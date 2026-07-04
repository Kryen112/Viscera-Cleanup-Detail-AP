"""Items. The only progression items are level-access unlocks, one per playable
level. The rest is filler, with an optional share of traps. No tool-gating.
"""

from __future__ import annotations

from .levels import LEVELS
from .traps import TRAP_NAMES, USEFUL_NAMES

# Arbitrary stable base for this game's ids. Item ids and location ids live in
# separate ranges so they never collide.
ITEM_ID_BASE = 0x5643_0000  # "VC" 0000


def access_item_name(display_name: str) -> str:
    return f"{display_name} Access"


LEVEL_ACCESS_ITEMS: list[str] = [access_item_name(d) for _, d, _ in LEVELS]

# Generic filler. VCD has no item economy, so filler is flavor only.
FILLER_NAMES: list[str] = ["Overtime Pay", "Coffee Break", "Spare Bucket"]

# Ids are assigned in list order. The tail below is frozen: a name added later
# appends at the end no matter which group it belongs to, so every existing id
# stays stable even for a seed generated with an older version.
_ID_ORDERED_NAMES: list[str] = LEVEL_ACCESS_ITEMS + FILLER_NAMES + [
    "Mess Dump Trap",
    "Bucket Spill Trap",
    "Slowdown Trap",
    "Clean Water Bucket",
    "Empty Bin",
    "Speedup Trap",
]
assert sorted(_ID_ORDERED_NAMES) == sorted(
    LEVEL_ACCESS_ITEMS + FILLER_NAMES + TRAP_NAMES + USEFUL_NAMES)

ITEM_NAME_TO_ID: dict[str, int] = {}
_next = ITEM_ID_BASE
for _name in _ID_ORDERED_NAMES:
    ITEM_NAME_TO_ID[_name] = _next
    _next += 1

ITEM_GROUPS: dict[str, list[str]] = {
    "Level Access": list(LEVEL_ACCESS_ITEMS),
    "Filler": list(FILLER_NAMES),
    "Traps": list(TRAP_NAMES),
    "Useful": list(USEFUL_NAMES),
}
