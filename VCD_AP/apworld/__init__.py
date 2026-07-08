"""Viscera Cleanup Detail randomizer for Archipelago.

Items, locations, levels, and options live in this directory. There is no
code-generation step; build_apworld.py only packages the world.

v1 shape: level-access unlock items gate each level; per-level checks are a
milestone cleanliness ladder, a punch-out completion, the level's collectibles
and Bob note, and a speedrun when the speedrunsanity option is on. The two
Digsite Bob events additionally need every note level. Under toolsanity (on
by default) each level's tools and machines are per-level items too, and the
milestone ladder follows the band logic in toolsanity.py. See V1_PLAN.md and
CLAUDE.md.
"""

from __future__ import annotations

from typing import ClassVar, Union

import settings
from BaseClasses import Item, ItemClassification, Location, Region
from Options import OptionError
from worlds.AutoWorld import World
from worlds.LauncherComponents import (Component, Type, components,
                                       launch_subprocess)

from .collectibles import (BOB_ALTAR_MAP, BOB_NOTE_MAPS, COLLECTIBLE_EXTRA_TOOLS,
                           COLLECTIBLES, GATED_COLLECTIBLE_TOKENS)
from .items import (CLEAN_MOP_ITEMS, FILLER_NAMES, ITEM_GROUPS,
                    ITEM_NAME_TO_ID, LEVEL_ACCESS_ITEMS,
                    PROGRESSION_TOOL_ITEMS, SQUEAKY_BOOTS_ITEMS, TOOL_ITEMS,
                    access_item_name, self_cleaning_mop_name,
                    squeaky_boots_name)
from .traps import TRAP_NAMES, USEFUL_NAMES
from .levels import DISPLAY_BY_MAP, LEVELS
from .locations import (BOB_GATED_LOCATIONS, FIND_BOB_LOCATION,
                        LOCATION_GROUPS, LOCATION_MAP, LOCATION_NAME_TO_ID,
                        MILESTONE_PERCENT, bob_note_name, collectible_name,
                        employee_of_the_month_name, location_enabled,
                        milestone_name, punch_out_name, speedrun_name)
from .options import VCDOptions
from .toolsanity import (CORE_CLEANING_KEYS, PROGRESSION_TOOL_KEYS,
                         PUNCHOUT_CLEAN_PERCENT, free_keys, free_kit_rungs,
                         full_clean_keys, item_keys, rung_in_logic,
                         tool_item_name)

GAME_NAME = "Viscera Cleanup Detail"
PROGRESSION_ITEM_NAMES: frozenset[str] = frozenset(
    LEVEL_ACCESS_ITEMS) | PROGRESSION_TOOL_ITEMS
TRAP_ITEM_NAMES: frozenset[str] = frozenset(TRAP_NAMES)
# The quality-of-life tool unlocks, the per-level Self-Cleaning Mop, and the
# per-level Squeaky Clean Boots classify useful like the supply drops: never
# progression, never in logic.
USEFUL_ITEM_NAMES: frozenset[str] = (
    frozenset(USEFUL_NAMES)
    | (frozenset(TOOL_ITEMS) - PROGRESSION_TOOL_ITEMS)
    | frozenset(CLEAN_MOP_ITEMS)
    | frozenset(SQUEAKY_BOOTS_ITEMS))


def _launch_client() -> None:
    from .client import launch
    launch_subprocess(launch, name="VCDClient")


components.append(Component("Viscera Cleanup Detail Client", func=_launch_client,
                            component_type=Type.CLIENT))


class VCDSettings(settings.Group):
    # Client settings, stored in host.yaml under viscera_cleanup_detail_options.
    class InstallFolder(settings.UserFolderPath):
        """Viscera Cleanup Detail install folder: the root holding Binaries (with
        Win32/UDK.exe) and UDKGame. The client reads and writes game state here and
        launches the game. Blank by default; the client offers a folder picker on
        first connect and saves the choice here. Use forward slashes."""
        description = "Viscera Cleanup Detail install folder"
        required = False

    class AutoLaunchGame(settings.Bool):
        """Launch UDK.exe automatically when the client connects to a seed (once per
        client session). On by default. Set to false to launch it yourself or with
        the /play command."""

    class IsolateSaves(settings.Bool):
        """Keep each Archipelago seed's Office, job saves, and collectibles in their
        own save set, apart from your career saves, swapped in when the client
        connects. On by default. Bring your career saves back with the client's
        /restore command."""

    class AutoInstallMod(settings.Bool):
        """Compare the precompiled mod packaged in this apworld against the install
        when the client connects, and copy it in if it differs, before the game
        launches. On by default. Set to false to manage the mod yourself with the
        /installmod command."""

    install_folder: InstallFolder = InstallFolder("")
    auto_launch_game: Union[AutoLaunchGame, bool] = True
    isolate_saves: Union[IsolateSaves, bool] = True
    auto_install_mod: Union[AutoInstallMod, bool] = True


class VCDItem(Item):
    game = GAME_NAME


class VCDLocation(Location):
    game = GAME_NAME


class VCDWorld(World):
    """Viscera Cleanup Detail: clean levels, unlock more levels."""

    game = GAME_NAME
    options_dataclass = VCDOptions
    options: VCDOptions
    settings: ClassVar[VCDSettings]

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    started_maps: ClassVar[set[str]]
    pooled_maps: ClassVar[list[str]]
    bob_chain_pooled: ClassVar[bool]
    hard_start_maps: ClassVar[set[str]]

    @staticmethod
    def _countable_collectibles(maps: set[str]) -> int:
        """How many collectible checks the given levels carry. The gate-locked
        ones count only when the whole Bob chain is present."""
        chain_present = maps.issuperset(BOB_NOTE_MAPS + [BOB_ALTAR_MAP])
        return sum(1 for m, t, _ in COLLECTIBLES if m in maps
                   and (chain_present or t not in GATED_COLLECTIBLE_TOKENS))

    def _random_pool(self, candidates: list[str], goal: str,
                     amount: int) -> list[str]:
        """A random subset of the candidate levels that still carries the goal.
        The size is drawn from the smallest set the goal allows up to the whole
        candidate set; the goal's must-have levels are forced in."""
        chain = set(BOB_NOTE_MAPS) | {BOB_ALTAR_MAP}
        forced: set[str] = set()
        if goal == "find_bob":
            forced |= chain
        if goal == "collect_collectibles":
            open_area = sum(1 for m, t, _ in COLLECTIBLES if m in candidates
                            and t not in GATED_COLLECTIBLE_TOKENS)
            if amount > open_area:
                # Only the gate-locked collectibles close the gap, and counting
                # them needs the whole Bob chain.
                forced |= chain
        minimum = max(len(forced), 1)
        if goal in ("complete_levels", "employee_of_the_month"):
            minimum = max(minimum, amount)
        size = self.random.randint(minimum, len(candidates))
        loose = [m for m in candidates if m not in forced]
        pool = forced | set(self.random.sample(loose, size - len(forced)))
        if goal == "collect_collectibles":
            carriers = [m for m in loose if m not in pool
                        and any(cm == m and t not in GATED_COLLECTIBLE_TOKENS
                                for cm, t, _ in COLLECTIBLES)]
            self.random.shuffle(carriers)
            # Exhausting the carriers puts every open-area collectible level in
            # the pool, and the only gated collectible sits on a chain map, so
            # the count reaches the candidate cap and the pop cannot underrun.
            while self._countable_collectibles(pool) < amount:
                pool.add(carriers.pop())
        return [m for m in candidates if m in pool]

    def generate_early(self) -> None:
        goal = self.options.goal.current_key
        amount = int(self.options.goal_amount.value)
        if goal == "find_bob":
            # The goal needs the note levels and the Digsite; force them in.
            self.options.level_pool.value |= {
                DISPLAY_BY_MAP[m] for m in BOB_NOTE_MAPS + [BOB_ALTAR_MAP]}
        chosen = self.options.level_pool.value
        candidates = [m for m, d, _ in LEVELS if d in chosen]
        if not candidates:
            raise OptionError(f"{self.player_name}: level_pool holds no levels.")
        # The goal cannot need more than the pool can hold: levels for the level
        # goals, collectibles the pooled levels carry for the collectible goal.
        cap = (self._countable_collectibles(set(candidates))
               if goal == "collect_collectibles" else len(candidates))
        if goal != "find_bob" and amount > cap:
            raise OptionError(
                f"{self.player_name}: goal_amount {amount} needs more than "
                f"the level pool holds ({cap}).")
        if self.options.randomize_level_pool:
            candidates = self._random_pool(candidates, goal, amount)
            # The spoiler shows the drawn pool, not just the candidate set.
            self.options.level_pool.value = {
                DISPLAY_BY_MAP[m] for m in candidates}
        self.pooled_maps = candidates
        pooled = set(candidates)
        self.bob_chain_pooled = pooled.issuperset(BOB_NOTE_MAPS + [BOB_ALTAR_MAP])
        # Toolsanity starting kits: by default every level starts mop and
        # Slosh-O-Matic; the random_starting_kit option rolls each level
        # independently, and a hard-start level opens hands and incinerator
        # instead.
        self.hard_start_maps = set()
        if self.options.toolsanity and self.options.random_starting_kit:
            self.hard_start_maps = {
                m for m in candidates if self.random.random() < 0.5}
        start_n = min(int(self.options.starting_levels.value), len(candidates))
        self.started_maps = self._draw_started_maps(candidates, start_n)

    def _starting_keystone(self, map_name: str) -> "str | None":
        """The one keystone cleaning tool to hand a started level up front: the
        most impactful core tool the level itemizes. None when the level's
        free kit already covers the core (nothing worth front-loading)."""
        available = set(item_keys(map_name, self.hard_start_maps))
        for key in ("Hands", "Mop", "Incinerator", "Welder", "SloshOMatic"):
            if key in available and key in CORE_CLEANING_KEYS:
                return key
        return None

    def _draw_started_maps(self, candidates: "list[str]",
                           start_n: int) -> "set[str]":
        """The starting levels. Under toolsanity a seed must open with at
        least one reachable check, so one started level is always drawn from
        those whose starting kit alone clears some milestone rung (a level
        like Incubation Emergency has too little moppable mess to clear even
        the first rung with slack); the rest draw freely."""
        if not self.options.toolsanity:
            return set(self.random.sample(candidates, start_n))
        step = self._step()
        open_maps = [
            m for m in candidates
            if free_kit_rungs(m, step, self.hard_start_maps)
        ]
        if not open_maps:
            raise OptionError(
                f"{self.player_name}: no pooled level offers a reachable "
                f"milestone with its starting kit alone. Lower milestone_step "
                f"or widen level_pool.")
        first = self.random.choice(open_maps)
        rest = [m for m in candidates if m != first]
        return {first} | set(self.random.sample(rest, start_n - 1))

    def create_item(self, name: str) -> VCDItem:
        if name in PROGRESSION_ITEM_NAMES:
            classification = ItemClassification.progression
        elif name in TRAP_ITEM_NAMES:
            classification = ItemClassification.trap
        elif name in USEFUL_ITEM_NAMES:
            classification = ItemClassification.useful
        else:
            classification = ItemClassification.filler
        return VCDItem(name, classification, self.item_name_to_id[name], self.player)

    def get_filler_item_name(self) -> str:
        return self.random.choice(FILLER_NAMES)

    def _step(self) -> int:
        return int(self.options.milestone_step.value)

    def _enabled_locations_for(self, map_name: str) -> list[str]:
        step = self._step()
        speedrunsanity = bool(self.options.speedrunsanity)
        above_and_beyond = bool(self.options.above_and_beyond)
        return [
            name for name, loc_map in LOCATION_MAP.items()
            if loc_map == map_name
            and location_enabled(name, step, speedrunsanity, above_and_beyond)
            and (self.bob_chain_pooled or name not in BOB_GATED_LOCATIONS)
        ]

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        for map_name, display, _title in LEVELS:
            if map_name not in self.pooled_maps:
                continue
            region = Region(map_name, self.player, self.multiworld)
            self.multiworld.regions.append(region)
            access = access_item_name(display)
            menu.connect(
                region,
                rule=lambda state, a=access: state.has(a, self.player),
            )
            for loc_name in self._enabled_locations_for(map_name):
                loc_id = LOCATION_NAME_TO_ID[loc_name]
                region.locations.append(VCDLocation(self.player, loc_name, loc_id, region))

    def create_items(self) -> None:
        placed = 0
        for map_name, display, _title in LEVELS:
            if map_name not in self.pooled_maps:
                continue
            item = self.create_item(access_item_name(display))
            if map_name in self.started_maps:
                self.multiworld.push_precollected(item)
            else:
                self.multiworld.itempool.append(item)
                placed += 1
            if self.options.toolsanity:
                for key in item_keys(map_name, self.hard_start_maps):
                    self.multiworld.itempool.append(
                        self.create_item(tool_item_name(display, key)))
                    placed += 1
            # The Self-Cleaning Mop and the Squeaky Clean Boots are always
            # created, one of each per pooled level, independent of toolsanity.
            self.multiworld.itempool.append(
                self.create_item(self_cleaning_mop_name(display)))
            placed += 1
            self.multiworld.itempool.append(
                self.create_item(squeaky_boots_name(display)))
            placed += 1
        active_locations = sum(
            len(self._enabled_locations_for(m)) for m in self.pooled_maps)
        filler_slots = active_locations - placed
        if filler_slots < 0:
            raise OptionError(
                f"{self.player_name}: the item pool ({placed} items) outgrows "
                f"the location pool ({active_locations} checks). Lower "
                f"milestone_step, add levels, or turn toolsanity off.")
        trap_slots = filler_slots * int(self.options.trap_percentage.value) // 100
        # Traps take their share first; supplies cap at the remaining slots.
        useful_slots = min(
            filler_slots * int(self.options.useful_percentage.value) // 100,
            filler_slots - trap_slots)
        for _ in range(trap_slots):
            self.multiworld.itempool.append(self.create_item(self.random.choice(TRAP_NAMES)))
        for _ in range(useful_slots):
            self.multiworld.itempool.append(self.create_item(self.random.choice(USEFUL_NAMES)))
        for _ in range(filler_slots - trap_slots - useful_slots):
            self.multiworld.itempool.append(self.create_item(self.get_filler_item_name()))

    def pre_fill(self) -> None:
        # Front-load each started level's keystone tool by locking it into one
        # of that level's tool-free rungs, so a seed opens with a level worth
        # taking deep instead of only shallow new levels. Only levels with at
        # least two tool-free rungs qualify, and the keystone takes the
        # highest of them, so the low rungs stay free for the fill to bootstrap
        # progression (reserving a level's sole early slot starves tight
        # pools). Levels with fewer tool-free rungs are simply left alone.
        if not self.options.toolsanity:
            return
        step = self._step()
        for map_name in self.started_maps:
            key = self._starting_keystone(map_name)
            if key is None:
                continue
            rungs = free_kit_rungs(map_name, step, self.hard_start_maps)
            if len(rungs) < 2:
                continue
            display = DISPLAY_BY_MAP[map_name]
            location = self.get_location(milestone_name(display, rungs[-1]))
            if location.item is not None:
                continue
            item_name = tool_item_name(display, key)
            item = next((i for i in self.multiworld.itempool
                         if i.player == self.player and i.name == item_name),
                        None)
            if item is None:
                continue
            self.multiworld.itempool.remove(item)
            location.place_locked_item(item)

    def _goal_locations(self) -> tuple[list[str], int]:
        """The locations whose reachability defines victory, and how many are
        needed."""
        goal = self.options.goal.current_key
        amount = int(self.options.goal_amount.value)
        pooled = set(self.pooled_maps)
        if goal == "employee_of_the_month":
            return [employee_of_the_month_name(d)
                    for m, d, _ in LEVELS if m in pooled], amount
        if goal == "find_bob":
            # Find Bob's own access rule carries the note levels plus the Digsite.
            return [FIND_BOB_LOCATION], 1
        if goal == "collect_collectibles":
            return [collectible_name(DISPLAY_BY_MAP[m], c)
                    for m, t, c in COLLECTIBLES if m in pooled
                    and (self.bob_chain_pooled
                         or t not in GATED_COLLECTIBLE_TOKENS)], amount
        return [punch_out_name(d) for m, d, _ in LEVELS if m in pooled], amount

    def _tool_state_pairs(self, map_name: str) -> "tuple[tuple[str, str], ...]":
        """(tool key, item name) for the level's progression tool items; the
        free pair is not itemized and folds in as always held, and the
        quality-of-life unlocks never gate a band, so the hot rung predicate
        skips them."""
        display = DISPLAY_BY_MAP[map_name]
        return tuple((k, tool_item_name(display, k))
                     for k in item_keys(map_name, self.hard_start_maps)
                     if k in PROGRESSION_TOOL_KEYS)

    def _pickup_items(self, map_name: str,
                      extra_keys: "tuple[str, ...]" = ()) -> "tuple[str, ...]":
        """The item names gating a physical pickup on the level. A trophy only
        banks on a punch-out in good standing (a fired shift clears the trunk),
        so a pickup needs the level's full clean kit, the same tools the
        punch-out check needs, which includes the Hands that grab it. Any extra
        pickup tool (the Overgrowth pickaxe is dug out with the shovel) is added
        on top. The free pair drops out."""
        display = DISPLAY_BY_MAP[map_name]
        free = free_keys(map_name, self.hard_start_maps)
        keys = set(full_clean_keys(map_name)) | set(extra_keys)
        return tuple(tool_item_name(display, k)
                     for k in sorted(keys) if k not in free)

    def _full_clean_items(self, map_name: str) -> "tuple[str, ...]":
        """The tool items that clean the level to 100 percent: the full clean
        kit (core kit plus any suspect level's extra tool) minus the free pair.
        These gate every cleanliness check at or above 100 percent."""
        display = DISPLAY_BY_MAP[map_name]
        free = free_keys(map_name, self.hard_start_maps)
        return tuple(tool_item_name(display, k)
                     for k in sorted(full_clean_keys(map_name))
                     if k not in free)

    def _pickup_rule(self, map_name: str,
                     extra_keys: "tuple[str, ...]" = ()):
        """A physical pickup's access rule: the level's full clean kit (so the
        punch-out that banks the trophy is not fired), plus any extra pickup
        tool, must be held (the free pair counts as held)."""
        player = self.player
        items = self._pickup_items(map_name, tuple(extra_keys))

        def rule(state, needed=items) -> bool:
            return state.has_all(needed, player)

        return rule

    def _rung_rule(self, map_name: str, rung: int, step: int):
        """A regular ladder rung's access rule: the held toolset's band cap
        must clear the rung (toolsanity.py owns the arithmetic)."""
        player = self.player
        base = free_keys(map_name, self.hard_start_maps)
        pairs = self._tool_state_pairs(map_name)

        def rule(state, m=map_name, r=rung, s=step, kit=base,
                 tool_pairs=pairs) -> bool:
            unlocked = set(kit)
            for key, item in tool_pairs:
                if state.has(item, player):
                    unlocked.add(key)
            return rung_in_logic(m, r, s, frozenset(unlocked))

        return rule

    def set_rules(self) -> None:
        player = self.player
        toolsanity = bool(self.options.toolsanity)
        step = self._step()

        # Toolsanity gates each check on the tools that reach it. Cleanliness
        # checks (every milestone rung, Employee of the Month at 100, and the
        # over-100 ladder) follow the band cap: the core kit reaches 100 (the
        # report and stacking then reach the over-100 maximum), so a situational
        # tool a level does not need for 100 gates none of them. The Punch Out
        # and Speedrun checks need a not-fired shift, and physical pickups
        # (collectibles, Bob notes) need the same clean kit (a trophy only banks
        # on a not-fired punch-out) plus any extra pickup tool.
        if toolsanity:
            token_by_collectible = {
                collectible_name(DISPLAY_BY_MAP[m], c): t
                for m, t, c in COLLECTIBLES}
            for map_name in self.pooled_maps:
                display = DISPLAY_BY_MAP[map_name]
                punch_or_speedrun = {punch_out_name(display),
                                     speedrun_name(display)}
                note_name = bob_note_name(display)
                for name in self._enabled_locations_for(map_name):
                    if name in BOB_GATED_LOCATIONS:
                        continue
                    percent = MILESTONE_PERCENT.get(name)
                    if percent is not None:
                        rule = self._rung_rule(map_name, percent, step)
                    elif name in punch_or_speedrun:
                        rule = self._rung_rule(
                            map_name, PUNCHOUT_CLEAN_PERCENT, step)
                    elif name == note_name:
                        rule = self._pickup_rule(map_name)
                    else:
                        token = token_by_collectible.get(name)
                        extra = tuple(COLLECTIBLE_EXTRA_TOOLS.get(
                            token, frozenset()))
                        rule = self._pickup_rule(map_name, extra)
                    self.get_location(name).access_rule = rule

        # The Digsite gate needs all nine Bob notes on the pedestal: six live in
        # the note levels (three are Office freebies), and Bob and the Red
        # Keycard sit behind the gate. So those checks need every note level on
        # top of the Digsite access their region already requires; under
        # toolsanity they also need each note level's clean kit, because a note
        # only banks on a not-fired punch-out on its own level. They only exist
        # when the pool holds the whole chain, whose access items are all
        # progression, so they are guaranteed reachable.
        if self.bob_chain_pooled:
            required = [access_item_name(DISPLAY_BY_MAP[m])
                        for m in BOB_NOTE_MAPS]
            if toolsanity:
                for m in list(BOB_NOTE_MAPS) + [BOB_ALTAR_MAP]:
                    required.extend(self._pickup_items(m))
            for name in BOB_GATED_LOCATIONS:
                self.get_location(name).access_rule = (
                    lambda state, items=tuple(required):
                        state.has_all(items, player)
                )

        locations, need = self._goal_locations()
        self.multiworld.completion_condition[player] = (
            lambda state, locs=locations, n=need:
                sum(state.can_reach_location(loc, player) for loc in locs) >= n
        )

    def fill_slot_data(self) -> dict:
        # The mod and client learn the seed's shape only through slot_data.
        return {
            "goal": self.options.goal.current_key,
            "goal_amount": int(self.options.goal_amount.value),
            "milestone_step": self._step(),
            "above_and_beyond": bool(self.options.above_and_beyond),
            "speedrunsanity": bool(self.options.speedrunsanity),
            "toolsanity": bool(self.options.toolsanity),
            "hard_start_maps": sorted(self.hard_start_maps),
            "started_maps": sorted(self.started_maps),
            "pooled_maps": list(self.pooled_maps),
        }
