"""Items. For v1 the only progression items are level-access unlocks, one per
playable level. Everything else is filler. No tool-gating, no traps in v1.
"""

from __future__ import annotations

from .levels import LEVELS

# Arbitrary stable base for this game's ids. Item ids and location ids live in
# separate ranges so they never collide.
ITEM_ID_BASE = 0x5643_0000  # "VC" 0000


def access_item_name(display_name: str) -> str:
    return f"{display_name} Access"


LEVEL_ACCESS_ITEMS: list[str] = [access_item_name(d) for _, d, _ in LEVELS]

# Generic filler. VCD has no item economy, so filler is flavor only.
FILLER_NAMES: list[str] = ["Overtime Pay", "Coffee Break", "Spare Bucket"]

ITEM_NAME_TO_ID: dict[str, int] = {}
_next = ITEM_ID_BASE
for _name in LEVEL_ACCESS_ITEMS + FILLER_NAMES:
    ITEM_NAME_TO_ID[_name] = _next
    _next += 1

ITEM_GROUPS: dict[str, list[str]] = {
    "Level Access": list(LEVEL_ACCESS_ITEMS),
    "Filler": list(FILLER_NAMES),
}
