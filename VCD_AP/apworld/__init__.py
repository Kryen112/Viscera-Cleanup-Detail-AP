"""Viscera Cleanup Detail randomizer for Archipelago.

Items, locations, levels, and options live in this directory. There is no
code-generation step; build_apworld.py only packages the world.

v1 shape: level-access unlock items gate each level; per-level checks are a
milestone cleanliness ladder plus a punch-out completion, and a speedrun when
the speedrunsanity option is on. Collectible and Bob-chain checks are TODO. See
V1_PLAN.md and CLAUDE.md.
"""

from __future__ import annotations

from typing import ClassVar, Union

import settings
from BaseClasses import Item, ItemClassification, Location, Region
from worlds.AutoWorld import World
from worlds.LauncherComponents import (Component, Type, components,
                                       launch_subprocess)

from .items import (FILLER_NAMES, ITEM_GROUPS, ITEM_NAME_TO_ID,
                    LEVEL_ACCESS_ITEMS, access_item_name)
from .traps import TRAP_NAMES
from .levels import LEVELS, MAP_NAMES
from .locations import (LOCATION_GROUPS, LOCATION_MAP, LOCATION_NAME_TO_ID,
                        employee_of_the_month_name, location_enabled,
                        punch_out_name)
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

    install_folder: InstallFolder = InstallFolder("")
    auto_launch_game: Union[AutoLaunchGame, bool] = True
    isolate_saves: Union[IsolateSaves, bool] = True


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

    def generate_early(self) -> None:
        pooled = list(MAP_NAMES)
        start_n = min(int(self.options.starting_levels.value), len(pooled))
        self.started_maps = set(self.random.sample(pooled, start_n))
        # Cannot need more levels than exist in the pool.
        if int(self.options.goal_amount.value) > len(pooled):
            self.options.goal_amount.value = len(pooled)

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
        return [
            name for name, loc_map in LOCATION_MAP.items()
            if loc_map == map_name and location_enabled(name, step, speedrunsanity)
        ]

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        for map_name, display, _title in LEVELS:
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
            item = self.create_item(access_item_name(display))
            if map_name in self.started_maps:
                self.multiworld.push_precollected(item)
            else:
                self.multiworld.itempool.append(item)
                placed += 1
        active_locations = sum(len(self._enabled_locations_for(m)) for m in MAP_NAMES)
        filler_slots = active_locations - placed
        trap_slots = filler_slots * int(self.options.trap_percentage.value) // 100
        for _ in range(trap_slots):
            self.multiworld.itempool.append(self.create_item(self.random.choice(TRAP_NAMES)))
        for _ in range(filler_slots - trap_slots):
            self.multiworld.itempool.append(self.create_item(self.get_filler_item_name()))

    def _goal_locations(self) -> tuple[list[str], int]:
        """The locations whose reachability defines victory, and how many are
        needed. Reaching any of a level's checks means owning that level's access
        item, so these counts are really 'access to N levels'."""
        goal = self.options.goal.current_key
        amount = int(self.options.goal_amount.value)
        if goal == "employee_of_the_month":
            return [employee_of_the_month_name(d) for _, d, _ in LEVELS], amount
        punch_outs = [punch_out_name(d) for _, d, _ in LEVELS]
        if goal == "find_bob":
            # TODO: gate on the nine Bob-note levels plus the Digsite once the
            # collectibles module exists. Conservative for now: every level.
            return punch_outs, len(punch_outs)
        # complete_levels, and (TODO) collect_collectibles until collectibles land.
        return punch_outs, amount

    def set_rules(self) -> None:
        locations, need = self._goal_locations()
        player = self.player
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
            "speedrunsanity": bool(self.options.speedrunsanity),
            "started_maps": sorted(self.started_maps),
            "pooled_maps": list(MAP_NAMES),
        }
