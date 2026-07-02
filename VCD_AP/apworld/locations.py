"""Locations. Per level, the static full set is:
- a Punch Out check (finishing the level, always enabled),
- a milestone ladder at every 5 percent (`Clean 5%` .. `Clean 95%`), each enabled
  only when it is a multiple of the seed's milestone step,
- an Employee of the Month check (the 100 percent rung, enabled for every step),
- a Speedrun check (always enabled).

The full set of names and ids is static (the datapackage is shared across seeds);
a seed enables a subset via the milestone step option. Collectible and Bob-chain
checks are TODO and land with the collectibles module.
"""

from __future__ import annotations

from .levels import LEVELS

LOCATION_ID_BASE = 0x5643_1_0000  # kept well clear of the item id range

MILESTONE_STEP_CHOICES: tuple[int, ...] = (5, 10, 20, 25)
CLEAN_RUNGS: list[int] = list(range(5, 100, 5))  # 5..95; 100 is Employee of the Month

GROUP_PUNCH_OUT = "PunchOut"
GROUP_MILESTONE = "Milestone"
GROUP_EMPLOYEE_OF_THE_MONTH = "EmployeeOfTheMonth"
GROUP_SPEEDRUN = "Speedrun"


def punch_out_name(display: str) -> str:
    return f"{display} - Punch Out"


def milestone_name(display: str, percent: int) -> str:
    return f"{display} - Clean {percent}%"


def employee_of_the_month_name(display: str) -> str:
    return f"{display} - Employee of the Month"


def speedrun_name(display: str) -> str:
    return f"{display} - Speedrun"


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

# Location groups for the client and tracker.
LOCATION_GROUPS: dict[str, list[str]] = {}
for _name, _group in LOCATION_GROUP.items():
    LOCATION_GROUPS.setdefault(_group, []).append(_name)


def milestone_enabled(location_name: str, step: int) -> bool:
    """A milestone or Employee-of-the-Month rung is enabled when its percent is a
    multiple of the seed's step. Punch Out and Speedrun are always enabled."""
    percent = MILESTONE_PERCENT.get(location_name)
    if percent is None:
        return True
    return percent % step == 0
