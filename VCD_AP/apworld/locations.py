"""Locations. Per level, the static full set is:
- a Punch Out check (finishing the level, always enabled),
- a milestone ladder at every 5 percent (`Clean 5%` .. `Clean 95%`), each enabled
  only when it is a multiple of the seed's milestone step,
- an Employee of the Month check (the 100 percent rung, enabled for every step),
- a Speedrun check (enabled by the speedrunsanity option),
- the level's collectibles and Bob note, where it has them (always enabled),
- and on the Digsite, the two Bob events (gates opened, Bob found).

The full set of names and ids is static (the datapackage is shared across seeds);
a seed enables a subset via the milestone step and speedrunsanity options.
"""

from __future__ import annotations

from .collectibles import BOB_ALTAR_MAP, BOB_NOTES, COLLECTIBLES
from .levels import DISPLAY_BY_MAP, LEVELS

LOCATION_ID_BASE = 0x5643_1_0000  # kept well clear of the item id range

MILESTONE_STEP_CHOICES: tuple[int, ...] = (5, 10, 20, 25)
CLEAN_RUNGS: list[int] = list(range(5, 100, 5))  # 5..95; 100 is Employee of the Month

GROUP_PUNCH_OUT = "PunchOut"
GROUP_MILESTONE = "Milestone"
GROUP_EMPLOYEE_OF_THE_MONTH = "EmployeeOfTheMonth"
GROUP_SPEEDRUN = "Speedrun"
GROUP_COLLECTIBLE = "Collectible"
GROUP_BOB_NOTE = "BobNote"
GROUP_BOB_EVENT = "BobEvent"


def punch_out_name(display: str) -> str:
    return f"{display} - Punch Out"


def milestone_name(display: str, percent: int) -> str:
    return f"{display} - Clean {percent}%"


def employee_of_the_month_name(display: str) -> str:
    return f"{display} - Employee of the Month"


def speedrun_name(display: str) -> str:
    return f"{display} - Speedrun"


def collectible_name(display: str, collectible: str) -> str:
    return f"{display} - {collectible}"


def bob_note_name(display: str) -> str:
    return f"{display} - Bob Note"


DIGSITE_GATES_LOCATION = f"{DISPLAY_BY_MAP[BOB_ALTAR_MAP]} - Open the Digsite Gates"
FIND_BOB_LOCATION = f"{DISPLAY_BY_MAP[BOB_ALTAR_MAP]} - Find Bob"


LOCATION_NAME_TO_ID: dict[str, int] = {}
LOCATION_MAP: dict[str, str] = {}          # location name -> level map_name
LOCATION_GROUP: dict[str, str] = {}        # location name -> group
MILESTONE_PERCENT: dict[str, int] = {}     # milestone/EotM location -> percent

_next = LOCATION_ID_BASE


def _add(name: str, map_name: str, group: str, percent: "int | None" = None) -> None:
    global _next
    LOCATION_NAME_TO_ID[name] = _next
    LOCATION_MAP[name] = map_name
    LOCATION_GROUP[name] = group
    if percent is not None:
        MILESTONE_PERCENT[name] = percent
    _next += 1


for _map, _display, _title in LEVELS:
    _add(punch_out_name(_display), _map, GROUP_PUNCH_OUT)
    for _p in CLEAN_RUNGS:
        _add(milestone_name(_display, _p), _map, GROUP_MILESTONE, _p)
    _add(employee_of_the_month_name(_display), _map, GROUP_EMPLOYEE_OF_THE_MONTH, 100)
    _add(speedrun_name(_display), _map, GROUP_SPEEDRUN)

# Appended after the per-level ladder so earlier ids stay stable.
for _map, _token, _collectible in COLLECTIBLES:
    _add(collectible_name(DISPLAY_BY_MAP[_map], _collectible), _map, GROUP_COLLECTIBLE)
for _map, _token in BOB_NOTES:
    _add(bob_note_name(DISPLAY_BY_MAP[_map]), _map, GROUP_BOB_NOTE)
_add(DIGSITE_GATES_LOCATION, BOB_ALTAR_MAP, GROUP_BOB_EVENT)
_add(FIND_BOB_LOCATION, BOB_ALTAR_MAP, GROUP_BOB_EVENT)

COLLECTIBLE_LOCATION_NAMES: list[str] = [
    collectible_name(DISPLAY_BY_MAP[_m], _c) for _m, _t, _c in COLLECTIBLES
]

# Location groups for the client and tracker.
LOCATION_GROUPS: dict[str, list[str]] = {}
for _name, _group in LOCATION_GROUP.items():
    LOCATION_GROUPS.setdefault(_group, []).append(_name)


def milestone_enabled(location_name: str, step: int) -> bool:
    """A milestone or Employee-of-the-Month rung is enabled when its percent is a
    multiple of the seed's step. Non-milestone checks are always enabled."""
    percent = MILESTONE_PERCENT.get(location_name)
    if percent is None:
        return True
    return percent % step == 0


def location_enabled(location_name: str, step: int, speedrunsanity: bool) -> bool:
    """Whether a seed with the given options creates this location. Speedrun
    checks exist only under speedrunsanity; the rest follows the milestone step."""
    if LOCATION_GROUP[location_name] == GROUP_SPEEDRUN:
        return speedrunsanity
    return milestone_enabled(location_name, step)
