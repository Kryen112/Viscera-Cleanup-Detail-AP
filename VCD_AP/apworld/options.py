"""Player options. The milestone step controls both granularity and world size;
the goal and its amount define the win condition.
"""

from __future__ import annotations

from dataclasses import dataclass

from Options import (Choice, NamedRange, PerGameCommonOptions,
                     StartInventoryPool, Toggle)


class MilestoneStep(Choice):
    """How finely each level's cleanliness is checked. 5 percent gives 20 checks
    per level (a large, filler-heavy world); 25 percent gives 4. The 100 percent
    rung (Employee of the Month) exists at every step."""
    display_name = "Milestone step"
    option_5 = 5
    option_10 = 10
    option_20 = 20
    option_25 = 25
    default = 5


class Speedrunsanity(Toggle):
    """Add a Speedrun check to every level: punch out at least 95 percent clean
    within 75 percent of the level's par time. Off by default, so seeds carry no
    speed pressure unless asked for."""
    display_name = "Speedrunsanity"


class Goal(Choice):
    """The win condition.

    complete_levels: punch out of `goal_amount` levels.
    employee_of_the_month: reach 100 percent on `goal_amount` levels.
    find_bob: complete the Bob storyline (needs the note levels plus the Digsite).
    collect_collectibles: return `goal_amount` collectibles.

    find_bob and collect_collectibles depend on the collectibles module, which is
    not in this skeleton yet, so they currently resolve to a conservative
    level-completion requirement. Do not ship them until that lands.
    """
    display_name = "Goal"
    option_complete_levels = 0
    option_employee_of_the_month = 1
    option_find_bob = 2
    option_collect_collectibles = 3
    default = 0


class GoalAmount(NamedRange):
    """How many levels (or collectibles) the goal needs. `all` is every pooled
    level. Ignored by find_bob."""
    display_name = "Goal amount"
    range_start = 1
    range_end = 26
    default = 26
    special_range_names = {"few": 5, "half": 13, "most": 20, "all": 26}


class StartingLevels(NamedRange):
    """How many levels are unlocked at the start of the seed."""
    display_name = "Starting levels"
    range_start = 1
    range_end = 10
    default = 1
    special_range_names = {"one": 1, "few": 3}


@dataclass
class VCDOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    milestone_step: MilestoneStep
    speedrunsanity: Speedrunsanity
    goal: Goal
    goal_amount: GoalAmount
    starting_levels: StartingLevels
