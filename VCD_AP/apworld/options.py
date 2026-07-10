"""Player options. The milestone step controls both granularity and world size;
the goal and its amount define the win condition.
"""

from __future__ import annotations

from dataclasses import dataclass

from Options import (Choice, DeathLink, DefaultOnToggle, NamedRange,
                     OptionSet, PerGameCommonOptions, Range,
                     StartInventoryPool, Toggle)

from .levels import LEVELS


class MilestoneStep(Choice):
    """How finely each level's cleanliness is checked. 5 percent gives 20
    checks per level; 1 percent gives 100 (a very large world, more still
    with above_and_beyond). The 100 percent rung (Employee of the Month)
    exists at every step, and steps finer than 5 keep the 5 percent step's
    ladder ceiling and logic margins, so no check gets closer to a level's
    known maximum than at the 5 percent step."""
    display_name = "Milestone step"
    option_1 = 1
    option_2 = 2
    option_5 = 5
    option_10 = 10
    default = 5


class AboveAndBeyond(Toggle):
    """Extend each level's milestone ladder past 100 percent (levels overfill
    via restorables and bonus points). The ladder tops out a full step under
    the level's known maximum cleanliness, so the last rung stays attainable.
    Off by default."""
    display_name = "Above and beyond"


class Speedrunsanity(Toggle):
    """Add a Speedrun check to every level: punch out at least 95 percent clean
    within the level's par time. Off by default, so seeds carry no speed
    pressure unless asked for."""
    display_name = "Speedrunsanity"


class Toolsanity(DefaultOnToggle):
    """Lock each level's tools and machines behind per-level items: hands
    (carrying), the laser welder, the shovel, the J-HARM lift, the vendor, and
    the incinerator become progression, while the sniffer, broom, and bin
    dispenser become useful unlocks. Every level starts with just the mop and
    the Slosh-O-Matic, and higher cleanliness milestones need the tools that
    can physically reach them. On by default."""
    display_name = "Toolsanity"


class RandomStartingKit(Toggle):
    """With toolsanity on, each level independently rolls its free starting
    pair: mop plus Slosh-O-Matic, or hands plus incinerator (the displaced
    pair becomes that level's items). A hands start is the hard way: debris
    can burn, but blood waits for the mop. On a hands-start level the
    Self-Cleaning Mop counts as the Slosh-O-Matic in logic, since a mop that
    never dirties needs no rinse bucket. Off by default (every level starts
    mop and Slosh-O-Matic)."""
    display_name = "Random starting kit"


class HardStartSqueakyBoots(DefaultOnToggle):
    """With random_starting_kit on, a level that rolls the hands and
    incinerator start also starts with its Squeaky Clean Boots, so the
    janitor tracks no bloody footprints while the mop is still locked. That
    level's boots item is granted up front instead of entering the pool.
    On by default. Does nothing without random_starting_kit."""
    display_name = "Hard start Squeaky Clean Boots"


class TrapPercentage(Range):
    """The share of filler items that become traps: a mess dump near the
    janitor, a spilled bucket, thirty seconds of walking at half or double
    speed, a magnet pull that yanks everything loose nearby toward the
    janitor, or thirty seconds of near-zero gravity. Traps arrive from the
    multiworld while cleaning; they are never required by logic. 0 disables
    traps."""
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


class VCDDeathLink(DeathLink):
    """When you die, everyone who enabled death link dies. Of course, the
    reverse is true too. Either way the whole shift goes down together: every
    janitor in the session dies with the first, and the remains are yours to
    clean up. A death that arrives while no level is loaded is dropped, never
    held. Off by default."""


class TrapLink(Toggle):
    """Link trap activations with every other player who enabled trap link:
    when a trap fires in your game it also fires in theirs, and their linked
    traps arrive here as the closest of this game's traps (one with no close
    equivalent is ignored). Linked traps arrive even with trap_percentage 0.
    Off by default."""
    display_name = "Trap Link"


class LevelPool(OptionSet):
    """The levels the seed plays, keyed by display name. Every level is a valid
    key; the default is all of them. A level left out generates no checks and
    no access item. With randomize_level_pool on, this is the set the random
    draw picks from. The find_bob goal forces the Digsite and the six note
    levels into the pool. The Digsite's gate-locked checks (Open the Digsite
    Gates, Find Bob, the Red Keycard, the Bolter) only exist when the pool
    holds the Digsite and every note level."""
    display_name = "Level pool"
    valid_keys = frozenset(d for _, d, _ in LEVELS)
    # An ordered default keeps the generated template yaml stable.
    default = tuple(d for _, d, _ in LEVELS)


class RandomizeLevelPool(Toggle):
    """Play a random subset of level_pool instead of the whole set. Each seed
    draws the subset size at random, from the smallest set the goal allows
    (goal_amount_levels levels for complete_levels, enough
    collectible-holding levels for collect_collectibles, the Bob chain for
    find_bob) up to the whole pool. Off by default."""
    display_name = "Randomize level pool"


class Goal(Choice):
    """The win condition.

    complete_levels: punch out of `goal_amount_levels` levels.
    find_bob: follow the notes and find Bob in the Digsite (needs the six
    note levels plus the Digsite).
    collect_collectibles: bank `goal_amount_collectibles` collectibles in
    the trunk.
    """
    display_name = "Goal"
    option_complete_levels = 0
    option_find_bob = 1
    option_collect_collectibles = 2
    default = 0


class GoalAmountLevels(NamedRange):
    """How many levels the complete_levels goal needs. It must fit the level
    pool: asking for more levels than the pool holds fails generation. `all`
    is every level. The other goals ignore it."""
    display_name = "Goal amount levels"
    range_start = 1
    range_end = 26
    default = 26
    special_range_names = {"few": 5, "half": 13, "most": 20, "all": 26}


class GoalAmountCollectibles(NamedRange):
    """How many collectibles the collect_collectibles goal needs. It must fit
    the level pool: asking for more collectibles than the pooled levels hold
    fails generation. `all` is every collectible. The other goals ignore
    it."""
    display_name = "Goal amount collectibles"
    range_start = 1
    range_end = 39
    default = 39
    special_range_names = {"few": 5, "half": 20, "most": 30, "all": 39}


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
    toolsanity: Toolsanity
    random_starting_kit: RandomStartingKit
    hard_start_squeaky_boots: HardStartSqueakyBoots
    trap_percentage: TrapPercentage
    useful_percentage: UsefulPercentage
    death_link: VCDDeathLink
    trap_link: TrapLink
    goal: Goal
    goal_amount_levels: GoalAmountLevels
    goal_amount_collectibles: GoalAmountCollectibles
    starting_levels: StartingLevels
