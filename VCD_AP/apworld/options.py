"""Player options. The milestone step controls both granularity and world size;
the goal and its amount define the win condition.
"""

from __future__ import annotations

from dataclasses import dataclass

from Options import (Choice, NamedRange, OptionSet, PerGameCommonOptions,
                     Range, StartInventoryPool, Toggle)

from .levels import LEVELS


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


class AboveAndBeyond(Toggle):
    """Extend each level's milestone ladder past 100 percent (levels overfill
    via restorables and bonus points). The ladder tops out a full step under
    the level's known maximum cleanliness, so the last rung stays attainable.
    Off by default."""
    display_name = "Above and beyond"


class Speedrunsanity(Toggle):
    """Add a Speedrun check to every level: punch out at least 95 percent clean
    within 75 percent of the level's par time. Off by default, so seeds carry no
    speed pressure unless asked for."""
    display_name = "Speedrunsanity"


class TrapPercentage(Range):
    """The share of filler items that become traps: a mess dump near the
    janitor, a spilled bucket, or thirty seconds of slow walking. Traps arrive
    from the multiworld while cleaning; they are never required by logic. 0
    disables traps."""
    display_name = "Trap percentage"
    range_start = 0
    range_end = 100
    default = 5


class UsefulPercentage(Range):
    """The share of filler items that become useful supplies: a bucket of
    clean water or an empty bin dropped next to the janitor. Supplies arrive
    from the multiworld while cleaning; they are never required by logic. When
    trap_percentage and useful_percentage together pass 100, traps take their
    share first. 0 disables supplies."""
    display_name = "Useful percentage"
    range_start = 0
    range_end = 100
    default = 15


class LevelPool(OptionSet):
    """The levels the seed plays, keyed by display name. Every level is a valid
    key; the default is all of them. A level left out generates no checks and
    no access item. With randomize_level_pool on, this is the set the random
    draw picks from. The find_bob goal forces the Digsite and the six note
    levels into the pool. The Digsite's gate-locked checks (Open the Digsite
    Gates, Find Bob, the Red Keycard) only exist when the pool holds the
    Digsite and every note level."""
    display_name = "Level pool"
    valid_keys = frozenset(d for _, d, _ in LEVELS)
    # An ordered default keeps the generated template yaml stable.
    default = tuple(d for _, d, _ in LEVELS)


class RandomizeLevelPool(Toggle):
    """Play a random subset of level_pool instead of the whole set. Each seed
    draws the subset size at random, from the smallest set the goal allows
    (goal_amount levels for the level goals, enough collectible-holding levels
    for collect_collectibles, the Bob chain for find_bob) up to the whole
    pool. Off by default."""
    display_name = "Randomize level pool"


class Goal(Choice):
    """The win condition.

    complete_levels: punch out of `goal_amount` levels.
    employee_of_the_month: reach 100 percent on `goal_amount` levels.
    find_bob: follow the notes and find Bob in the Digsite (needs the six
    note levels plus the Digsite).
    collect_collectibles: bank `goal_amount` collectibles in the trunk.
    """
    display_name = "Goal"
    option_complete_levels = 0
    option_employee_of_the_month = 1
    option_find_bob = 2
    option_collect_collectibles = 3
    default = 0


class GoalAmount(NamedRange):
    """How many levels (or collectibles) the goal needs. It must fit the level
    pool: asking for more levels than the pool holds, or more collectibles than
    the pooled levels hold, fails generation. `all` is every level. Ignored by
    find_bob."""
    display_name = "Goal amount"
    range_start = 1
    range_end = 39
    default = 26
    special_range_names = {"few": 5, "half": 13, "most": 20, "all": 26,
                           "all_collectibles": 39}


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
    level_pool: LevelPool
    randomize_level_pool: RandomizeLevelPool
    milestone_step: MilestoneStep
    above_and_beyond: AboveAndBeyond
    speedrunsanity: Speedrunsanity
    trap_percentage: TrapPercentage
    useful_percentage: UsefulPercentage
    goal: Goal
    goal_amount: GoalAmount
    starting_levels: StartingLevels
