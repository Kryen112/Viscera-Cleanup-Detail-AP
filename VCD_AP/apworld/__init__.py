"""Viscera Cleanup Detail randomizer for Archipelago.

Items, locations, levels, and options live in this directory. There is no
code-generation step; build_apworld.py only packages the world.

v1 shape: level-access unlock items gate each level; per-level checks are a
milestone cleanliness ladder, a punch-out completion, the level's collectibles
and Bob note, and a speedrun when the speedrunsanity option is on. The two
Digsite Bob events additionally need every note level. See V1_PLAN.md and
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

from .collectibles import (BOB_ALTAR_MAP, BOB_NOTE_MAPS, COLLECTIBLES,
                           GATED_COLLECTIBLE_TOKENS)
from .items import (FILLER_NAMES, ITEM_GROUPS, ITEM_NAME_TO_ID,
                    LEVEL_ACCESS_ITEMS, access_item_name)
from .traps import TRAP_NAMES
from .levels import DISPLAY_BY_MAP, LEVELS
from .locations import (BOB_GATED_LOCATIONS, FIND_BOB_LOCATION,
                        LOCATION_GROUPS, LOCATION_MAP, LOCATION_NAME_TO_ID,
                        collectible_name, employee_of_the_month_name,
                        location_enabled, punch_out_name)
from .options import VCDOptions

GAME_NAME = "Viscera Cleanup Detail"
PROGRESSION_ITEM_NAMES: frozenset[str] = frozenset(LEVEL_ACCESS_ITEMS)
TRAP_ITEM_NAMES: frozenset[str] = frozenset(TRAP_NAMES)


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
        """Compare the game mod packaged in this apworld against the install when
        the client connects, and deploy and recompile it if it differs, before the
        game launches. On by default. Set to false to manage the mod yourself with
        the /installmod command."""

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
        start_n = min(int(self.options.starting_levels.value), len(candidates))
        self.started_maps = set(self.random.sample(candidates, start_n))

    def create_item(self, name: str) -> VCDItem:
        if name in PROGRESSION_ITEM_NAMES:
            classification = ItemClassification.progression
        elif name in TRAP_ITEM_NAMES:
            classification = ItemClassification.trap
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
        active_locations = sum(
            len(self._enabled_locations_for(m)) for m in self.pooled_maps)
        filler_slots = active_locations - placed
        trap_slots = filler_slots * int(self.options.trap_percentage.value) // 100
        for _ in range(trap_slots):
            self.multiworld.itempool.append(self.create_item(self.random.choice(TRAP_NAMES)))
        for _ in range(filler_slots - trap_slots):
            self.multiworld.itempool.append(self.create_item(self.get_filler_item_name()))

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

    def set_rules(self) -> None:
        # The Digsite gate needs all nine Bob notes on the pedestal: six live in
        # the note levels (three are Office freebies), and Bob and the Red
        # Keycard sit behind the gate. So those checks need every note level on
        # top of the Digsite access their region already requires. They only
        # exist when the pool holds the whole chain, whose access items are all
        # progression, so they are guaranteed reachable.
        player = self.player
        if self.bob_chain_pooled:
            note_access = tuple(
                access_item_name(DISPLAY_BY_MAP[m]) for m in BOB_NOTE_MAPS)
            for name in BOB_GATED_LOCATIONS:
                self.get_location(name).access_rule = (
                    lambda state, items=note_access: state.has_all(items, player)
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
            "started_maps": sorted(self.started_maps),
            "pooled_maps": list(self.pooled_maps),
        }
