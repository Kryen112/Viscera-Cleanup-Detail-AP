"""Locations. Per level, the static full set is:
- a Punch Out check (finishing the level, always enabled),
- a milestone ladder at every 1 percent (`Clean 1%` .. `Clean 99%`), each
  enabled only when it is a multiple of the seed's milestone step,
- an Employee of the Month check (the 100 percent rung, enabled for every step),
- an over-100 ladder enabled by the above_and_beyond option, whose ceiling is
  computed on the 5 percent grid (a full 5-grid step under the level's known
  maximum, or coarser for coarser steps), so a fine step never trusts the
  community-measured maxima more than the 5 percent step does,
- a Speedrun check (enabled by the speedrunsanity option),
- the level's collectibles and Bob note, where it has them (always enabled),
- and on the Digsite, the two Bob events (gates opened, Bob found).

The full set of names and ids is static (the datapackage is shared across seeds);
a seed enables a subset via the milestone step, speedrunsanity, and
above_and_beyond options.
"""

from __future__ import annotations

from .collectibles import (BOB_ALTAR_MAP, BOB_NOTES, COLLECTIBLES,
                           GATED_COLLECTIBLE_TOKENS)
from .levels import DISPLAY_BY_MAP, LEVELS, MAX_CLEAN_PERCENT_BY_MAP

LOCATION_ID_BASE = 0x5643_1_0000  # kept well clear of the item id range

MILESTONE_STEP_CHOICES: tuple[int, ...] = (1, 2, 5, 10)
CLEAN_RUNGS: list[int] = list(range(5, 100, 5))  # the original 5-grid ladder
# The fine 1-grid rungs, kept separate so every original id stays frozen.
FINE_CLEAN_RUNGS: list[int] = [p for p in range(1, 100) if p % 5 != 0]

# The known maxima are community measurements, so ceilings never trust them
# on a grid finer than the 5 percent step they were validated against.
CEILING_STEP_FLOOR = 5


def top_rung(map_name: str, step: int) -> int:
    """The highest above_and_beyond rung a level generates at a step: the
    level's known maximum floored to the step, minus one more step, so a small
    measurement error cannot strand the top check. Steps finer than 5 keep the
    5-grid ceiling. At or below 100 the level gets no over-100 rungs."""
    ceiling_step = max(step, CEILING_STEP_FLOOR)
    return (int(MAX_CLEAN_PERCENT_BY_MAP[map_name] // ceiling_step)
            * ceiling_step - ceiling_step)


def over_100_rungs(map_name: str) -> list[int]:
    """Every over-100 rung the datapackage holds for a level (the finest
    step): the original 5-grid rungs first, then the finer fill, mirroring
    the frozen id order."""
    return _over_100_original(map_name) + _over_100_fine(map_name)


def _over_100_original(map_name: str) -> list[int]:
    return list(range(105, top_rung(map_name, 5) + 1, 5))


def _over_100_fine(map_name: str) -> list[int]:
    return [p for p in range(101, top_rung(map_name, 1) + 1) if p % 5 != 0]


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
for _map, _display, _title in LEVELS:
    for _p in _over_100_original(_map):
        _add(milestone_name(_display, _p), _map, GROUP_MILESTONE, _p)

# The fine 1-grid rungs (steps 1 and 2) appended after everything the 5-grid
# datapackage held, so every earlier id keeps its frozen value.
for _map, _display, _title in LEVELS:
    for _p in FINE_CLEAN_RUNGS:
        _add(milestone_name(_display, _p), _map, GROUP_MILESTONE, _p)
for _map, _display, _title in LEVELS:
    for _p in _over_100_fine(_map):
        _add(milestone_name(_display, _p), _map, GROUP_MILESTONE, _p)

COLLECTIBLE_LOCATION_NAMES: list[str] = [
    collectible_name(DISPLAY_BY_MAP[_m], _c) for _m, _t, _c in COLLECTIBLES
]

# Every check behind the Digsite gates: the two Bob events plus the gate-locked
# collectibles. They share the all-note-levels access rule and only exist when
# the level pool holds the Digsite and every note level.
BOB_GATED_LOCATIONS: list[str] = (
    [DIGSITE_GATES_LOCATION, FIND_BOB_LOCATION]
    + [collectible_name(DISPLAY_BY_MAP[_m], _c)
       for _m, _t, _c in COLLECTIBLES if _t in GATED_COLLECTIBLE_TOKENS]
)

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


def location_enabled(location_name: str, step: int, speedrunsanity: bool,
                     above_and_beyond: bool) -> bool:
    """Whether a seed with the given options creates this location. Speedrun
    checks exist only under speedrunsanity; over-100 rungs only under
    above_and_beyond, on the step, up to the level's top rung at that step; the
    rest follows the milestone step."""
    if LOCATION_GROUP[location_name] == GROUP_SPEEDRUN:
        return speedrunsanity
    percent = MILESTONE_PERCENT.get(location_name)
    if percent is not None and percent > 100:
        return (above_and_beyond and percent % step == 0
                and percent <= top_rung(LOCATION_MAP[location_name], step))
    return milestone_enabled(location_name, step)
