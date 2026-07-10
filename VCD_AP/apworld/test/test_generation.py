"""Generation and data-integrity tests.

The option-bearing subclasses inherit WorldTestBase's fill and reachability
tests, so each exercises a full generation. TestData needs no world.
"""

import unittest

from test.general import gen_steps, setup_multiworld

from Options import OptionError
from worlds.AutoWorld import call_all

from .bases import VCDTestBase
from .. import VCDWorld
from ..collectibles import (BOB_NOTE_MAPS, BOB_NOTES, COLLECTIBLE_EXTRA_TOOLS,
                            COLLECTIBLES, GATED_COLLECTIBLE_TOKENS)
from ..items import ITEM_NAME_TO_ID, TOOL_ITEMS, access_item_name
from ..levels import DISPLAY_BY_MAP, LEVELS, MAP_NAMES
from ..locations import (BOB_GATED_LOCATIONS, DIGSITE_GATES_LOCATION,
                         FIND_BOB_LOCATION, LOCATION_MAP,
                         LOCATION_NAME_TO_ID, MILESTONE_PERCENT,
                         collectible_name, employee_of_the_month_name,
                         milestone_enabled, milestone_name, over_100_rungs,
                         punch_out_name, speedrun_name, top_rung)
from ..options import GoalAmountLevels
from ..toolsanity import tool_item_name


class TestDefault(VCDTestBase):
    options = {}

    def test_speedrun_locations_absent_by_default(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for _map, display, _title in LEVELS:
            self.assertNotIn(speedrun_name(display), names)

    def test_bob_gated_checks_need_the_chain_accesses_and_clean_kits(self):
        needed = [access_item_name(DISPLAY_BY_MAP[m])
                  for m in BOB_NOTE_MAPS + ["VC_Digsite"]]
        for m in BOB_NOTE_MAPS + ["VC_Digsite"]:
            needed.extend(self.pickup_kit(m))
        gated = [DIGSITE_GATES_LOCATION, FIND_BOB_LOCATION]
        gated += [collectible_name(DISPLAY_BY_MAP[m], c)
                  for m, t, c in COLLECTIBLES if t in GATED_COLLECTIBLE_TOKENS]
        for name in gated:
            # Any single missing piece (an access item or a clean tool on any
            # chain level) blocks it.
            location = self.multiworld.get_location(name, self.player)
            self.assert_needs_every_item(location.can_reach, needed, name)

    def test_collectibles_need_the_clean_kit(self):
        # Banking a collectible needs a not-fired shift, so it needs the level's
        # clean kit (which includes the hands that grab it); the gate-locked
        # ones the Bob-gated test covers. The Overgrowth pickaxe also needs the
        # shovel to dig it out, and Athena's Wrath's blue easter egg the J-HARM
        # to reach.
        for map_name, token, collectible in COLLECTIBLES:
            if token in GATED_COLLECTIBLE_TOKENS:
                continue
            display = DISPLAY_BY_MAP[map_name]
            extra = tuple(COLLECTIBLE_EXTRA_TOOLS.get(token, frozenset()))
            pickup = self.pickup_kit(map_name, extra)
            location = self.multiworld.get_location(
                collectible_name(display, collectible), self.player)
            self.assert_needs_every_item(
                location.can_reach,
                [access_item_name(display)] + pickup, display)

    def test_blue_easter_egg_waits_for_the_lift(self):
        # Athena's Wrath's blue easter egg sits where only the J-HARM reaches:
        # the clean kit alone leaves it out of logic, the Lift closes it.
        display = "Athena's Wrath"
        location = self.multiworld.get_location(
            collectible_name(display, "Easter Egg Blue"), self.player)
        kit = [access_item_name(display)] + self.pickup_kit("VC_Hall")
        self.assertFalse(location.can_reach(self.state_with(kit)))
        self.assertTrue(location.can_reach(self.state_with(
            kit + [tool_item_name(display, "Lift")])))

    def test_pickup_rule_pulls_a_required_tool_prerequisite_in(self):
        # A pickup that required Athena's Wrath's welder would need the J-HARM
        # that reaches it too.
        needed, _groups = self.world._pickup_requirements(
            "VC_Hall", ("Welder",))
        self.assertIn(tool_item_name("Athena's Wrath", "Lift"), needed)

    def test_tool_items_follow_presence_and_skip_the_free_pair(self):
        pool = self.created_item_names()
        self.assertIn(tool_item_name("Overgrowth", "Shovel"), pool)
        self.assertNotIn(tool_item_name("Splatter Station", "Shovel"), pool)
        self.assertIn(tool_item_name("Splatter Station", "Lift"), pool)
        self.assertNotIn(tool_item_name("Cryogenesis", "Lift"), pool)
        self.assertIn(tool_item_name("Cryogenesis", "Hands"), pool)
        # The default free pair is never itemized.
        self.assertNotIn(tool_item_name("Cryogenesis", "Mop"), pool)
        self.assertNotIn(tool_item_name("Cryogenesis", "SloshOMatic"), pool)

    def test_tool_item_classifications(self):
        from BaseClasses import ItemClassification
        for key in ("Hands", "Incinerator", "Welder", "Lift", "Vendor"):
            item = self.world.create_item(tool_item_name("Overgrowth", key))
            self.assertEqual(item.classification,
                             ItemClassification.progression, key)
        for key in ("Sniffer", "Broom", "Bins"):
            item = self.world.create_item(tool_item_name("Overgrowth", key))
            self.assertEqual(item.classification,
                             ItemClassification.useful, key)

    def test_self_cleaning_mop_is_useful_one_per_pooled_level(self):
        from BaseClasses import ItemClassification
        from ..items import self_cleaning_mop_name
        item = self.world.create_item(self_cleaning_mop_name("Overgrowth"))
        self.assertEqual(item.classification, ItemClassification.useful)
        pool = self.created_item_names()
        for map_name in self.world.pooled_maps:
            self.assertEqual(
                pool.count(self_cleaning_mop_name(DISPLAY_BY_MAP[map_name])), 1,
                map_name)

    def test_self_cleaning_mop_never_gates_a_location(self):
        # Under the default kit the Slosh-O-Matic is free, so the mop has
        # nothing to stand in for and no location's rule references it.
        from ..items import self_cleaning_mop_name
        access = [access_item_name("Waste Disposal")]
        kit = self.pickup_kit("VC_Sewer")
        location = self.multiworld.get_location(
            employee_of_the_month_name("Waste Disposal"), self.player)
        # The clean kit alone reaches it; the mop item is not part of the kit.
        self.assertNotIn(self_cleaning_mop_name("Waste Disposal"), kit)
        self.assertTrue(location.can_reach(self.state_with(access + kit)))

    def test_squeaky_boots_is_useful_one_per_pooled_level(self):
        from BaseClasses import ItemClassification
        from ..items import squeaky_boots_name
        item = self.world.create_item(squeaky_boots_name("Overgrowth"))
        self.assertEqual(item.classification, ItemClassification.useful)
        pool = self.created_item_names()
        for map_name in self.world.pooled_maps:
            self.assertEqual(
                pool.count(squeaky_boots_name(DISPLAY_BY_MAP[map_name])), 1,
                map_name)

    def test_squeaky_boots_never_gates_a_location(self):
        # A useful item is never required, so no location's rule references it.
        from ..items import squeaky_boots_name
        access = [access_item_name("Waste Disposal")]
        kit = self.pickup_kit("VC_Sewer")
        location = self.multiworld.get_location(
            employee_of_the_month_name("Waste Disposal"), self.player)
        # The clean kit alone reaches it; the boots item is not part of the kit.
        self.assertNotIn(squeaky_boots_name("Waste Disposal"), kit)
        self.assertTrue(location.can_reach(self.state_with(access + kit)))

    def test_low_rungs_open_with_access_high_rungs_need_the_kit(self):
        # Waste Disposal is 73 percent moppable, so mid rungs open with the
        # starting kit but the top of the ladder waits for the core kit.
        access = [access_item_name("Waste Disposal")]
        kit = self.pickup_kit("VC_Sewer")
        low = self.multiworld.get_location(
            milestone_name("Waste Disposal", 45), self.player)
        high = self.multiworld.get_location(
            milestone_name("Waste Disposal", 95), self.player)
        self.assertTrue(low.can_reach(self.state_with(access)))
        self.assertFalse(high.can_reach(self.state_with(access)))
        self.assertTrue(high.can_reach(self.state_with(access + kit)))

    def test_employee_of_the_month_needs_the_clean_kit(self):
        access = [access_item_name("Waste Disposal")]
        kit = self.pickup_kit("VC_Sewer")
        location = self.multiworld.get_location(
            employee_of_the_month_name("Waste Disposal"), self.player)
        self.assert_needs_every_item(location.can_reach, access + kit,
                                     "Employee of the Month")

    def test_punch_out_needs_the_clean_kit_not_hands_alone(self):
        # A not-fired shift needs the core kit; hands alone leaves the level
        # too dirty to clock off, so the punch-out check waits for the kit.
        access = [access_item_name("Waste Disposal")]
        hands = [tool_item_name("Waste Disposal", "Hands")]
        kit = self.pickup_kit("VC_Sewer")
        punch = self.multiworld.get_location(
            punch_out_name("Waste Disposal"), self.player)
        self.assertFalse(punch.can_reach(self.state_with(access + hands)))
        self.assertTrue(punch.can_reach(self.state_with(access + kit)))


class TestSpeedrunsanity(VCDTestBase):
    options = {"speedrunsanity": True}

    def test_speedrun_locations_exist(self):
        for _map, display, _title in LEVELS:
            self.assert_location_exists(speedrun_name(display))


class TestAboveAndBeyond(VCDTestBase):
    options = {"above_and_beyond": True, "milestone_step": 10}

    def test_over_100_rungs_exist_on_the_step_up_to_the_top(self):
        # Athena's Wrath at step 10 tops at 140.
        for percent in (110, 120, 130, 140):
            self.assert_location_exists(milestone_name("Athena's Wrath", percent))
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn(milestone_name("Athena's Wrath", 150), names)
        # Off-step rungs stay out even though the datapackage holds them.
        self.assertNotIn(milestone_name("Athena's Wrath", 105), names)
        # Gravity Drive has no over-100 rung at step 10.
        self.assertNotIn(milestone_name("Gravity Drive", 110), names)


class TestNoOver100ByDefault(VCDTestBase):
    options = {}

    def test_over_100_rungs_absent(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertNotIn(milestone_name("Athena's Wrath", 105), names)
        self.assertNotIn(milestone_name("Zilla Pagoda", 200), names)


class TestTrapPercentage(VCDTestBase):
    options = {"trap_percentage": 50, "useful_percentage": 0}

    def test_half_the_filler_is_traps_and_classified_trap(self):
        from BaseClasses import ItemClassification
        from ..traps import TRAP_NAMES
        pool_traps = [item for item in self.multiworld.itempool
                      if item.name in TRAP_NAMES]
        filler = [item for item in self.multiworld.itempool
                  if item.name not in TRAP_NAMES
                  and item.classification == ItemClassification.filler]
        self.assertGreater(len(pool_traps), 0)
        # Half the filler slots, rounded down.
        self.assertEqual(len(pool_traps), (len(pool_traps) + len(filler)) // 2)
        for item in pool_traps:
            self.assertEqual(item.classification, ItemClassification.trap, item.name)

    def test_traps_never_progression(self):
        from BaseClasses import ItemClassification
        from ..traps import TRAP_NAMES
        for name in TRAP_NAMES:
            item = self.world.create_item(name)
            self.assertEqual(item.classification, ItemClassification.trap)


class TestLinkOptions(VCDTestBase):
    options = {"death_link": True, "trap_link": True}

    def test_slot_data_reports_both_links_on(self):
        slot_data = self.world.fill_slot_data()
        self.assertIs(slot_data["death_link"], True)
        self.assertIs(slot_data["trap_link"], True)


class TestLinkOptionsDefaultOff(VCDTestBase):
    options = {}

    def test_slot_data_reports_both_links_off(self):
        slot_data = self.world.fill_slot_data()
        self.assertIs(slot_data["death_link"], False)
        self.assertIs(slot_data["trap_link"], False)


class TestUsefulPercentage(VCDTestBase):
    options = {"trap_percentage": 0, "useful_percentage": 50}

    def test_half_the_filler_is_useful_and_classified_useful(self):
        from BaseClasses import ItemClassification
        from ..traps import USEFUL_NAMES
        pool_useful = [item for item in self.multiworld.itempool
                       if item.name in USEFUL_NAMES]
        filler = [item for item in self.multiworld.itempool
                  if item.name not in USEFUL_NAMES
                  and item.classification == ItemClassification.filler]
        self.assertGreater(len(pool_useful), 0)
        # Half the filler slots, rounded down.
        self.assertEqual(len(pool_useful), (len(pool_useful) + len(filler)) // 2)
        for item in pool_useful:
            self.assertEqual(item.classification, ItemClassification.useful, item.name)

    def test_useful_items_never_progression(self):
        from BaseClasses import ItemClassification
        from ..traps import USEFUL_NAMES
        for name in USEFUL_NAMES:
            item = self.world.create_item(name)
            self.assertEqual(item.classification, ItemClassification.useful)


class TestTrapAndUsefulSharesCapAtTheFiller(VCDTestBase):
    options = {"trap_percentage": 60, "useful_percentage": 60}

    def test_traps_take_their_share_first(self):
        from BaseClasses import ItemClassification
        from ..traps import TRAP_NAMES, USEFUL_NAMES
        pool_traps = sum(1 for item in self.multiworld.itempool
                         if item.name in TRAP_NAMES)
        pool_useful = sum(1 for item in self.multiworld.itempool
                          if item.name in USEFUL_NAMES)
        plain_filler = sum(1 for item in self.multiworld.itempool
                           if item.name not in TRAP_NAMES
                           and item.name not in USEFUL_NAMES
                           and item.classification == ItemClassification.filler)
        filler_slots = pool_traps + pool_useful + plain_filler
        self.assertEqual(pool_traps, filler_slots * 60 // 100)
        # The useful share is capped at what the traps left over.
        self.assertEqual(pool_useful, filler_slots - pool_traps)
        self.assertEqual(plain_filler, 0)


class TestDefaultShares(VCDTestBase):
    options = {}

    def test_defaults_are_five_percent_traps_and_fifteen_percent_useful(self):
        from BaseClasses import ItemClassification
        from ..traps import TRAP_NAMES, USEFUL_NAMES
        pool_traps = sum(1 for item in self.multiworld.itempool
                         if item.name in TRAP_NAMES)
        pool_useful = sum(1 for item in self.multiworld.itempool
                          if item.name in USEFUL_NAMES)
        plain_filler = sum(1 for item in self.multiworld.itempool
                           if item.name not in TRAP_NAMES
                           and item.name not in USEFUL_NAMES
                           and item.classification == ItemClassification.filler)
        filler_slots = pool_traps + pool_useful + plain_filler
        self.assertEqual(pool_traps, filler_slots * 5 // 100)
        self.assertEqual(pool_useful, filler_slots * 15 // 100)


class TestZeroPercentagesDisableTrapsAndUseful(VCDTestBase):
    options = {"trap_percentage": 0, "useful_percentage": 0}

    def test_pool_has_no_traps_or_useful_items(self):
        from ..traps import TRAP_NAMES, USEFUL_NAMES
        for item in self.multiworld.itempool:
            self.assertNotIn(item.name, TRAP_NAMES)
            self.assertNotIn(item.name, USEFUL_NAMES)


class TestToolsanityOff(VCDTestBase):
    options = {"toolsanity": False}

    def test_no_tool_items(self):
        self.assertTrue(set(self.created_item_names()).isdisjoint(TOOL_ITEMS))

    def test_collectibles_need_only_their_level(self):
        for map_name, token, collectible in COLLECTIBLES:
            if token in GATED_COLLECTIBLE_TOKENS:
                continue
            display = DISPLAY_BY_MAP[map_name]
            location = self.multiworld.get_location(
                collectible_name(display, collectible), self.player)
            self.assertTrue(
                location.can_reach(self.state_with([access_item_name(display)])))


class TestStartingKeystoneEarly(VCDTestBase):
    # A single high-mop starting level (Waste Disposal, 73 percent moppable)
    # deterministically has many tool-free rungs, so the placement always runs.
    options = {"starting_levels": 1, "goal": "complete_levels",
               "goal_amount_levels": 1, "level_pool": {"Waste Disposal"}}

    def test_started_level_keystone_is_placed_in_its_own_early_rung(self):
        from ..toolsanity import free_kit_rungs, tool_item_name
        (started,) = self.world.started_maps
        self.assertEqual(started, "VC_Sewer")
        key = self.world._starting_keystone(started)
        rungs = free_kit_rungs(started, self.world._step(),
                               self.world.hard_start_maps)
        self.assertIsNotNone(key)
        self.assertGreaterEqual(len(rungs), 2)
        display = DISPLAY_BY_MAP[started]
        # The keystone is locked into the highest rung the free kit reaches,
        # leaving the low rungs for the fill.
        location = self.multiworld.get_location(
            milestone_name(display, rungs[-1]), self.player)
        self.assertEqual(location.item.name, tool_item_name(display, key))
        self.assertTrue(location.locked)
        self.assertTrue(location.can_reach(self.state_with(
            [access_item_name(DISPLAY_BY_MAP[m])
             for m in self.world.started_maps])))


class TestRandomStartingKit(VCDTestBase):
    options = {"random_starting_kit": True}

    def test_hard_start_levels_swap_their_item_pairs(self):
        pool = self.created_item_names()
        for map_name, display, _title in LEVELS:
            if map_name in self.world.hard_start_maps:
                self.assertIn(tool_item_name(display, "Mop"), pool)
                self.assertIn(tool_item_name(display, "SloshOMatic"), pool)
                self.assertNotIn(tool_item_name(display, "Hands"), pool)
                self.assertNotIn(tool_item_name(display, "Incinerator"), pool)
            else:
                self.assertNotIn(tool_item_name(display, "Mop"), pool)
                self.assertIn(tool_item_name(display, "Hands"), pool)

    def test_slot_data_reports_the_rolls(self):
        self.assertEqual(self.world.fill_slot_data()["hard_start_maps"],
                         sorted(self.world.hard_start_maps))

    def test_hard_start_levels_start_with_their_boots(self):
        # hard_start_squeaky_boots is on by default: a hard-start level's
        # Squeaky Clean Boots start granted instead of entering the pool.
        from ..items import squeaky_boots_name
        pooled = [item.name for item in self.multiworld.itempool]
        precollected = [item.name for item in
                        self.multiworld.precollected_items[self.player]]
        for map_name in self.world.pooled_maps:
            name = squeaky_boots_name(DISPLAY_BY_MAP[map_name])
            if map_name in self.world.hard_start_maps:
                self.assertIn(name, precollected, map_name)
                self.assertNotIn(name, pooled, map_name)
            else:
                self.assertNotIn(name, precollected, map_name)
                self.assertEqual(pooled.count(name), 1, map_name)

    def test_clean_mop_classifies_progression_only_on_hard_start_levels(self):
        from BaseClasses import ItemClassification
        from ..items import self_cleaning_mop_name
        for map_name in self.world.pooled_maps:
            item = self.world.create_item(
                self_cleaning_mop_name(DISPLAY_BY_MAP[map_name]))
            expected = (ItemClassification.progression
                        if map_name in self.world.hard_start_maps
                        else ItemClassification.useful)
            self.assertEqual(item.classification, expected, map_name)

    def test_clean_mop_stands_in_for_the_slosh_o_matic(self):
        # On a hard-start level the Slosh-O-Matic is itemized, and the level's
        # Self-Cleaning Mop satisfies its slot: a mop that never dirties needs
        # no rinse bucket. Either item clears the punch-out; neither leaves it
        # out of reach.
        from ..items import self_cleaning_mop_name
        if not self.world.hard_start_maps:
            self.skipTest("no hard-start roll this seed")
        map_name = sorted(self.world.hard_start_maps)[0]
        display = DISPLAY_BY_MAP[map_name]
        needed, groups = self.world._pickup_requirements(map_name)
        self.assertIn((tool_item_name(display, "SloshOMatic"),
                       self_cleaning_mop_name(display)), groups)
        base = [access_item_name(display)] + list(needed)
        punch = self.multiworld.get_location(
            punch_out_name(display), self.player)
        self.assertFalse(punch.can_reach(self.state_with(base)))
        self.assertTrue(punch.can_reach(self.state_with(
            base + [tool_item_name(display, "SloshOMatic")])))
        self.assertTrue(punch.can_reach(self.state_with(
            base + [self_cleaning_mop_name(display)])))


def tracker_regeneration(test: VCDTestBase, slot_data: dict) -> VCDWorld:
    """A second generation the way the Universal Tracker runs one: default
    options (no yaml on hand), a different random seed, and the played
    seed's slot_data passed through."""
    multiworld = setup_multiworld(VCDWorld, steps=(),
                                  seed=test.multiworld.seed + 1)
    multiworld.re_gen_passthrough = {
        VCDWorld.game: VCDWorld.interpret_slot_data(slot_data)}
    for step in gen_steps:
        call_all(multiworld, step)
    return multiworld.worlds[1]


class TestTrackerRegeneration(VCDTestBase):
    # A played seed with rolled state a regeneration cannot reroll by luck
    # alone: random kits, a non-default step, the over-100 ladder, and the
    # find_bob pool.
    options = {"random_starting_kit": True, "milestone_step": 2,
               "above_and_beyond": True, "goal": "find_bob",
               "level_pool": {"Unearthly Excavation"}}

    def test_regeneration_replays_the_played_seed(self):
        regenerated = tracker_regeneration(self, self.world.fill_slot_data())
        self.assertEqual(regenerated.pooled_maps, self.world.pooled_maps)
        self.assertEqual(regenerated.started_maps, self.world.started_maps)
        self.assertEqual(regenerated.hard_start_maps,
                         self.world.hard_start_maps)
        self.assertEqual(regenerated.progression_clean_mop_items,
                         self.world.progression_clean_mop_items)
        self.assertEqual(regenerated._step(), self.world._step())
        self.assertEqual(regenerated.options.goal.current_key, "find_bob")
        self.assertTrue(regenerated.options.above_and_beyond)
        self.assertTrue(regenerated.options.toolsanity)
        self.assertEqual(
            {loc.name for loc in
             regenerated.multiworld.get_locations(regenerated.player)},
            {loc.name for loc in
             self.multiworld.get_locations(self.player)})
        self.assertEqual(
            sorted(item.name for item in
                   regenerated.multiworld.precollected_items[
                       regenerated.player]),
            sorted(item.name for item in
                   self.multiworld.precollected_items[self.player]))

    def test_slot_data_without_the_boots_key_still_restores(self):
        # Slot data written before the hard_start_squeaky_boots key existed
        # leaves the option as parsed (the default here) and restores the
        # rolled state the same way.
        slot_data = dict(self.world.fill_slot_data())
        del slot_data["hard_start_squeaky_boots"]
        regenerated = tracker_regeneration(self, slot_data)
        self.assertEqual(regenerated.hard_start_maps,
                         self.world.hard_start_maps)
        self.assertTrue(regenerated.options.hard_start_squeaky_boots)
        self.assertEqual(
            sorted(item.name for item in
                   regenerated.multiworld.precollected_items[
                       regenerated.player]),
            sorted(item.name for item in
                   self.multiworld.precollected_items[self.player]))


class TestTrackerRegenerationCollectibleAmount(VCDTestBase):
    options = {"goal": "collect_collectibles", "goal_amount_collectibles": 7}

    def test_restore_routes_the_amount_to_the_collectible_knob(self):
        # Slot data carries one goal_amount; the restore path must hand it
        # to the knob the goal reads, not the level knob.
        regenerated = tracker_regeneration(self, self.world.fill_slot_data())
        self.assertEqual(
            int(regenerated.options.goal_amount_collectibles.value), 7)
        self.assertEqual(regenerated._goal_amount(), 7)


class TestHardStartBootsOff(VCDTestBase):
    options = {"random_starting_kit": True,
               "hard_start_squeaky_boots": False}

    def test_every_boots_item_stays_in_the_pool(self):
        from ..items import squeaky_boots_name
        pooled = [item.name for item in self.multiworld.itempool]
        precollected = [item.name for item in
                        self.multiworld.precollected_items[self.player]]
        for map_name in self.world.pooled_maps:
            name = squeaky_boots_name(DISPLAY_BY_MAP[map_name])
            self.assertNotIn(name, precollected, map_name)
            self.assertEqual(pooled.count(name), 1, map_name)


class TestStep1(VCDTestBase):
    # A small pool keeps the fill fast; step 1 on the full 26 levels holds
    # thousands of checks and works the same way.
    options = {"milestone_step": 1, "above_and_beyond": True,
               "level_pool": {"Athena's Wrath", "Cryogenesis",
                              "Waste Disposal"},
               "goal_amount_levels": 3}

    def test_fine_rungs_exist_and_the_ceiling_stays_on_the_5_grid(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn(milestone_name("Athena's Wrath", 7), names)
        self.assertIn(milestone_name("Athena's Wrath", 101), names)
        # Athena's Wrath peaks at 154.04: the ladder tops at 145, same as
        # step 5, so the community-measured maximum is never trusted tighter.
        self.assertIn(milestone_name("Athena's Wrath", 145), names)
        self.assertNotIn(milestone_name("Athena's Wrath", 146), names)


class TestStep2(VCDTestBase):
    options = {"milestone_step": 2,
               "level_pool": {"Athena's Wrath", "Cryogenesis",
                              "Waste Disposal"},
               "goal_amount_levels": 3}

    def test_even_rungs_only(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn(milestone_name("Cryogenesis", 4), names)
        self.assertNotIn(milestone_name("Cryogenesis", 5), names)


class TestStep10HardStartOpener(VCDTestBase):
    # Generation itself must never fail on the hard-start roll: at step 10 no
    # hard-start level clears a rung with its opening kit, so an all-hard roll
    # would otherwise abort the seed.
    options = {"milestone_step": 10, "random_starting_kit": True,
               "level_pool": {"Athena's Wrath", "Cryogenesis"},
               "goal_amount_levels": 2}

    def test_all_hard_roll_softens_one_level(self):
        from ..toolsanity import free_kit_rungs
        world = self.world
        forced = {"VC_Hall", "VC_Cryo"}
        world.hard_start_maps = set(forced)
        # With both levels hard-started nothing opens at step 10.
        self.assertEqual([m for m in forced
                          if free_kit_rungs(m, 10, world.hard_start_maps)], [])
        world._ensure_openable_start(["VC_Hall", "VC_Cryo"])
        self.assertEqual(len(world.hard_start_maps), 1)
        softened = forced - world.hard_start_maps
        self.assertTrue(free_kit_rungs(softened.pop(), 10,
                                       world.hard_start_maps))

    def test_openable_roll_is_left_alone(self):
        world = self.world
        world.hard_start_maps = {"VC_Hall"}
        world._ensure_openable_start(["VC_Hall", "VC_Cryo"])
        self.assertEqual(world.hard_start_maps, {"VC_Hall"})


class TestFewStartingLevels(VCDTestBase):
    options = {"starting_levels": 3}


class TestFindBobGoal(VCDTestBase):
    options = {"goal": "find_bob"}

    def test_completion_requires_the_note_levels(self):
        needed = [access_item_name(DISPLAY_BY_MAP[m])
                  for m in BOB_NOTE_MAPS + ["VC_Digsite"]]
        for m in BOB_NOTE_MAPS + ["VC_Digsite"]:
            needed.extend(self.pickup_kit(m))
        self.assert_needs_every_item(
            self.multiworld.completion_condition[self.player], needed,
            "find_bob")


class TestCollectiblesGoal(VCDTestBase):
    options = {"goal": "collect_collectibles", "goal_amount_collectibles": 3}

    def test_completion_counts_reachable_collectibles(self):
        # Cryogenesis and Gravity Drive hold two collectibles each; the two
        # levels together clear the three-collectible bar. Collectibles need
        # their level's hands on top of its access.
        cryo = ([access_item_name("Cryogenesis")]
                + self.pickup_kit("VC_Cryo"))
        both_kits = (cryo + [access_item_name("Gravity Drive")]
                     + self.pickup_kit("VC_ZeroG_New"))
        self.assertFalse(self.multiworld.completion_condition[self.player](
            self.state_with(cryo)))
        self.assertTrue(self.multiworld.completion_condition[self.player](
            self.state_with(both_kits)))


class TestCollectiblesGoalFullAmount(VCDTestBase):
    # 39 is the collectible cap, so it survives the clamp and must still fill.
    options = {"goal": "collect_collectibles", "goal_amount_collectibles": 39}

    def test_amount_kept(self):
        self.assertEqual(
            int(self.world.options.goal_amount_collectibles.value), 39)

    def test_slot_data_carries_the_collectible_amount(self):
        # Slot data resolves the per-goal knobs into the one amount the
        # goal reads, so the client keeps a single goal_amount key.
        self.assertEqual(self.world.fill_slot_data()["goal_amount"], 39)


class TestLevelPool(VCDTestBase):
    options = {"level_pool": {"Splatter Station", "Cryogenesis", "Gravity Drive"},
               "goal_amount_levels": 3}

    def test_only_pooled_levels_have_locations(self):
        maps = {LOCATION_MAP[loc.name]
                for loc in self.multiworld.get_locations(self.player)}
        self.assertEqual(maps, {"VC_SplatterStation", "VC_Cryo", "VC_ZeroG_New"})

    def test_only_pooled_access_items_exist(self):
        pool = (list(self.multiworld.itempool)
                + self.multiworld.precollected_items[self.player])
        access = [item.name for item in pool if item.name.endswith(" Access")]
        self.assertCountEqual(access, ["Splatter Station Access",
                                       "Cryogenesis Access",
                                       "Gravity Drive Access"])

    def test_slot_data_reports_the_pool(self):
        self.assertEqual(self.world.fill_slot_data()["pooled_maps"],
                         ["VC_SplatterStation", "VC_Cryo", "VC_ZeroG_New"])


class TestLevelPoolDigsiteWithoutNotes(VCDTestBase):
    # The Digsite without every note level: the gate can never open, so the
    # gate-locked checks stay out while the open-area drops stay in.
    options = {"level_pool": {"Unearthly Excavation", "Splatter Station"},
               "goal_amount_levels": 2}

    def test_gated_checks_absent_open_area_drops_present(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for gated in BOB_GATED_LOCATIONS:
            self.assertNotIn(gated, names)
        self.assertIn(collectible_name("Unearthly Excavation", "Bolter"),
                      BOB_GATED_LOCATIONS)
        self.assertIn(collectible_name("Unearthly Excavation", "Red Keycard"),
                      BOB_GATED_LOCATIONS)
        self.assert_location_exists(
            collectible_name("Unearthly Excavation", "Saber"))


class TestFindBobGoalForcesPool(VCDTestBase):
    options = {"level_pool": {"Splatter Station"}, "goal": "find_bob"}

    def test_chain_levels_forced_into_the_pool(self):
        for map_name in BOB_NOTE_MAPS + ["VC_Digsite"]:
            self.assertIn(map_name, self.world.pooled_maps)
        self.assert_location_exists(FIND_BOB_LOCATION)


class TestCollectiblesGoalPooled(VCDTestBase):
    # Cryogenesis and Gravity Drive hold two collectibles each, so four fit.
    options = {"goal": "collect_collectibles", "goal_amount_collectibles": 4,
               "level_pool": {"Cryogenesis", "Gravity Drive"}}

    def test_completion_needs_both_pooled_levels(self):
        cryo = ([access_item_name("Cryogenesis")]
                + self.pickup_kit("VC_Cryo"))
        both_kits = (cryo + [access_item_name("Gravity Drive")]
                     + self.pickup_kit("VC_ZeroG_New"))
        self.assertFalse(self.multiworld.completion_condition[self.player](
            self.state_with(cryo)))
        self.assertTrue(self.multiworld.completion_condition[self.player](
            self.state_with(both_kits)))


class TestPoolOptionErrors(unittest.TestCase):
    @staticmethod
    def _generate(options: dict) -> None:
        probe_class = type("Probe", (VCDTestBase,), {"options": options})
        probe_class("setUp").setUp()

    def test_level_goal_over_pool_raises(self):
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station", "Cryogenesis"},
                            "goal": "complete_levels",
                            "goal_amount_levels": 3})

    def test_level_goal_amount_caps_at_the_level_count(self):
        # 39 collectibles exist but only 26 levels; the level knob's own
        # range rejects an amount past the level count.
        with self.assertRaises(Exception):
            GoalAmountLevels.from_any(39)

    def test_default_goal_amount_over_small_pool_raises(self):
        # The default amount is every level; a two-level pool cannot carry it.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station", "Cryogenesis"}})

    def test_collectible_goal_over_pooled_collectibles_raises(self):
        # The two pooled levels hold four collectibles between them.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Cryogenesis", "Gravity Drive"},
                            "goal": "collect_collectibles",
                            "goal_amount_collectibles": 5})

    def test_collectible_goal_without_collectible_levels_raises(self):
        # Splatter Station holds no collectibles at all.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station"},
                            "goal": "collect_collectibles",
                            "goal_amount_collectibles": 1})

    def test_randomized_pool_cannot_rescue_an_impossible_goal(self):
        # The draw only picks from the candidates, so a candidate set without
        # collectibles still fails the collectible goal.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station"},
                            "randomize_level_pool": True,
                            "goal": "collect_collectibles",
                            "goal_amount_collectibles": 1})

    def test_empty_pool_raises(self):
        with self.assertRaises(OptionError):
            self._generate({"level_pool": set(), "goal_amount_levels": 1})


class TestRandomizedPoolLevelGoal(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "complete_levels",
               "goal_amount_levels": 4}

    def test_pool_is_large_enough_for_the_goal(self):
        self.assertGreaterEqual(len(self.world.pooled_maps), 4)
        self.assertTrue(set(self.world.pooled_maps).issubset(MAP_NAMES))

    def test_option_value_reflects_the_drawn_pool(self):
        self.assertEqual({DISPLAY_BY_MAP[m] for m in self.world.pooled_maps},
                         self.world.options.level_pool.value)


class TestRandomizedPoolCollectiblesGoal(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "collect_collectibles",
               "goal_amount_collectibles": 5}

    def test_pool_carries_enough_collectibles(self):
        pooled = set(self.world.pooled_maps)
        chain_present = pooled.issuperset(BOB_NOTE_MAPS + ["VC_Digsite"])
        countable = sum(1 for m, t, _ in COLLECTIBLES if m in pooled
                        and (chain_present or t not in GATED_COLLECTIBLE_TOKENS))
        self.assertGreaterEqual(countable, 5)


class TestRandomizedPoolAllCollectibles(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "collect_collectibles",
               "goal_amount_collectibles": 39}

    def test_the_gate_chain_is_forced_in(self):
        # 39 needs the gate-locked drops, so the whole chain joins.
        pooled = set(self.world.pooled_maps)
        self.assertTrue(pooled.issuperset(BOB_NOTE_MAPS + ["VC_Digsite"]))


class TestRandomizedPoolFindBob(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "find_bob"}

    def test_pool_holds_the_bob_chain(self):
        for map_name in BOB_NOTE_MAPS + ["VC_Digsite"]:
            self.assertIn(map_name, self.world.pooled_maps)
        self.assert_location_exists(FIND_BOB_LOCATION)


class TestRandomizedPoolFromCandidates(VCDTestBase):
    options = {"randomize_level_pool": True,
               "level_pool": {"Splatter Station", "Cryogenesis", "Gravity Drive",
                              "Frostbite", "Penumbra"},
               "goal": "complete_levels", "goal_amount_levels": 2}

    def test_pool_stays_inside_the_candidates_and_fits_the_goal(self):
        candidates = {"VC_SplatterStation", "VC_Cryo", "VC_ZeroG_New",
                      "VC_IceStation", "VC_Darkening"}
        self.assertTrue(set(self.world.pooled_maps).issubset(candidates))
        self.assertGreaterEqual(len(self.world.pooled_maps), 2)


class TestCompleteFew(VCDTestBase):
    options = {"goal": "complete_levels", "goal_amount_levels": 5,
               "milestone_step": 10}


class TestToolsanityBands(unittest.TestCase):
    def test_mop_only_caps(self):
        from ..toolsanity import DEFAULT_FREE_KEYS, rung_in_logic
        kit = frozenset(DEFAULT_FREE_KEYS)
        # Waste Disposal is 73 percent moppable with mop and buckets alone.
        self.assertTrue(rung_in_logic("VC_Sewer", 65, 5, kit))
        self.assertFalse(rung_in_logic("VC_Sewer", 70, 5, kit))
        # Incubation Emergency is 16 percent moppable: the first rung clears,
        # but the ladder stalls low until hands and the incinerator arrive.
        self.assertTrue(rung_in_logic("VC_Incubator", 5, 5, kit))
        self.assertFalse(rung_in_logic("VC_Incubator", 15, 5, kit))

    def test_no_hands_ceiling_on_key_gated_levels(self):
        from ..toolsanity import DEFAULT_FREE_KEYS, rung_in_logic, toolset_cap
        kit = frozenset(DEFAULT_FREE_KEYS)
        # House of Horror walls its deeper areas behind carried keys: without
        # hands the measured ceiling is 45 percent, under the 66 the mop share
        # alone would otherwise credit.
        self.assertEqual(toolset_cap("VC_Horror_01", 5, kit), 45.0)
        self.assertTrue(rung_in_logic("VC_Horror_01", 40, 5, kit))
        self.assertFalse(rung_in_logic("VC_Horror_01", 45, 5, kit))
        # With hands and the incinerator the whole core kit is held, so the
        # level reaches its over-100 maximum.
        self.assertTrue(rung_in_logic(
            "VC_Horror_01", 45, 5, kit | {"Hands", "Incinerator"}))
        # A map absent from the ceiling table with mop only is exactly its
        # scanned mop share.
        self.assertAlmostEqual(toolset_cap("VC_Sewer", 5, kit),
                               15940.0 / 21758.5 * 100.0)

    def test_fine_steps_keep_the_five_point_slack(self):
        from ..toolsanity import DEFAULT_FREE_KEYS, rung_in_logic
        kit = frozenset(DEFAULT_FREE_KEYS)
        # At step 1 the slack stays 5 points, so the mop-only ladder on Waste
        # Disposal (73.26 percent) tops out at rung 68, not 72.
        self.assertTrue(rung_in_logic("VC_Sewer", 68, 1, kit))
        self.assertFalse(rung_in_logic("VC_Sewer", 69, 1, kit))

    def _situational_present(self, map_name):
        from ..toolsanity import SITUATIONAL_TOOL_KEYS, tools_present
        return frozenset(k for k in tools_present(map_name)
                         if k in SITUATIONAL_TOOL_KEYS)

    def test_core_kit_reaches_100_and_the_full_kit_reaches_the_max(self):
        from ..toolsanity import CORE_KIT_KEYS, toolset_cap, usable_total
        # A normal level: the core kit reaches 100 (with the slack lift, so EotM
        # and every sub-100 rung clear) but not the over-100 maximum on its own.
        core = toolset_cap("VC_Sewer", 5, CORE_KIT_KEYS)
        total = float(usable_total("VC_Sewer", 5))
        self.assertGreaterEqual(core, 100.0)
        self.assertLess(core, total)
        # Holding every situational tool the level has reaches the maximum.
        present = self._situational_present("VC_Sewer")
        self.assertEqual(toolset_cap("VC_Sewer", 5, CORE_KIT_KEYS | present),
                         total)

    def test_each_situational_tool_adds_over_100(self):
        from ..toolsanity import CORE_KIT_KEYS, toolset_cap, usable_total
        # Athena's Wrath has room over 100: one situational tool credits a share
        # over 100, and holding all of them reaches the maximum. The Lift is the
        # one usable on its own there (the welder waits for it).
        present = self._situational_present("VC_Hall")
        self.assertGreaterEqual(len(present), 2)
        core = toolset_cap("VC_Hall", 5, CORE_KIT_KEYS)
        one = toolset_cap("VC_Hall", 5, CORE_KIT_KEYS | {"Lift"})
        self.assertGreater(one, core)
        self.assertEqual(
            toolset_cap("VC_Hall", 5, CORE_KIT_KEYS | set(present)),
            float(usable_total("VC_Hall", 5)))

    def test_suspect_level_needs_its_extra_tool(self):
        from ..toolsanity import CORE_KIT_KEYS, toolset_cap, usable_total
        # Incubation Emergency's core kit tops out at its 80 percent ceiling;
        # only the welder lifts it to 100 and opens the over-100 ladder.
        self.assertEqual(toolset_cap("VC_Incubator", 5, CORE_KIT_KEYS), 80.0)
        self.assertGreaterEqual(
            toolset_cap("VC_Incubator", 5, CORE_KIT_KEYS | {"Welder"}), 100.0)
        # Uprinsing leans on the vendor instead.
        self.assertEqual(toolset_cap("VC_Uprinsing", 5, CORE_KIT_KEYS), 80.0)
        self.assertGreaterEqual(
            toolset_cap("VC_Uprinsing", 5, CORE_KIT_KEYS | {"Vendor"}), 100.0)
        # The full kit reaches each suspect's maximum.
        for m in ("VC_Incubator", "VC_Uprinsing"):
            present = self._situational_present(m)
            self.assertEqual(toolset_cap(m, 5, CORE_KIT_KEYS | present),
                             float(usable_total(m, 5)))

    def test_a_tool_stored_behind_another_waits_for_its_prerequisite(self):
        from ..toolsanity import CORE_KIT_KEYS, toolset_cap, usable_total
        # Athena's Wrath keeps its laser welder where only the J-HARM reaches:
        # the welder unlock alone credits nothing over the core kit, and the
        # pair together reaches the level's maximum.
        core = toolset_cap("VC_Hall", 5, CORE_KIT_KEYS)
        self.assertEqual(
            toolset_cap("VC_Hall", 5, CORE_KIT_KEYS | {"Welder"}), core)
        self.assertGreater(
            toolset_cap("VC_Hall", 5, CORE_KIT_KEYS | {"Welder", "Lift"}),
            toolset_cap("VC_Hall", 5, CORE_KIT_KEYS | {"Lift"}))
        self.assertEqual(
            toolset_cap("VC_Hall", 5, CORE_KIT_KEYS | {"Welder", "Lift"}),
            float(usable_total("VC_Hall", 5)))

    def test_situational_tool_does_not_help_where_unneeded(self):
        from ..toolsanity import toolset_cap
        # A partial core kit on a normal level gains nothing from the J-HARM: it
        # cleans only mess the core kit already reaches.
        partial = frozenset({"Mop", "SloshOMatic"})
        self.assertEqual(toolset_cap("VC_Sewer", 5, partial),
                         toolset_cap("VC_Sewer", 5, partial | {"Lift"}))

    def test_missing_tool_share_caps_the_over_100_climb(self):
        from ..toolsanity import CORE_KIT_KEYS, rung_in_logic, toolset_cap
        # Revolutionary Robotics: the welder's own mess is 5610 of a 32915.5
        # start (17.04 points), so without it the physical ceiling is the
        # 131.74 maximum minus that share (114.70). Lift and Vendor alone must
        # never put rungs 115 or 120 in logic.
        kit = CORE_KIT_KEYS | {"Lift", "Vendor"}
        self.assertAlmostEqual(toolset_cap("VC_Robot", 5, kit),
                               130.0 - 5610.0 / 32915.5 * 100.0)
        self.assertTrue(rung_in_logic("VC_Robot", 105, 5, kit))
        self.assertFalse(rung_in_logic("VC_Robot", 115, 5, kit))
        self.assertFalse(rung_in_logic("VC_Robot", 120, 5, kit))
        # The welder itself reopens the top of the ladder.
        self.assertTrue(rung_in_logic("VC_Robot", 120, 5, kit | {"Welder"}))

    def test_deduction_never_pulls_the_clean_kit_below_100(self):
        from ..toolsanity import CORE_KIT_KEYS, rung_in_logic, toolset_cap
        # Uprinsing's welder share (23.99) subtracted from its usable total
        # would land under 110, but the suspect row measured that the vendor
        # closes the level to 100: the clean kit keeps 100 plus the slack
        # step, even at coarse steps.
        kit = CORE_KIT_KEYS | {"Vendor"}
        self.assertEqual(toolset_cap("VC_Uprinsing", 10, kit), 110.0)
        self.assertTrue(rung_in_logic("VC_Uprinsing", 100, 10, kit))

    def test_vulcan_waits_for_the_welder(self):
        from ..toolsanity import CORE_KIT_KEYS, toolset_cap, usable_total
        # The Vulcan Affair's welder share (16.91 points against a 115.90
        # maximum) proves the core kit cannot reach 100; the conservative 90
        # ceiling holds the 95-and-up checks (punch-out, Employee of the
        # Month, speedrun) until the welder arrives.
        self.assertEqual(toolset_cap("VC_Vulcan_01", 5, CORE_KIT_KEYS), 90.0)
        self.assertGreaterEqual(
            toolset_cap("VC_Vulcan_01", 5, CORE_KIT_KEYS | {"Welder"}), 100.0)
        present = self._situational_present("VC_Vulcan_01")
        self.assertEqual(
            toolset_cap("VC_Vulcan_01", 5, CORE_KIT_KEYS | present),
            float(usable_total("VC_Vulcan_01", 5)))


class TestData(unittest.TestCase):
    def test_ids_unique_and_disjoint(self):
        item_ids = set(ITEM_NAME_TO_ID.values())
        loc_ids = set(LOCATION_NAME_TO_ID.values())
        self.assertEqual(len(item_ids), len(ITEM_NAME_TO_ID))
        self.assertEqual(len(loc_ids), len(LOCATION_NAME_TO_ID))
        self.assertTrue(item_ids.isdisjoint(loc_ids))

    def test_level_count(self):
        self.assertEqual(len(LEVELS), 26)
        self.assertEqual(len(MAP_NAMES), len(set(MAP_NAMES)))

    def test_each_level_has_the_full_static_set(self):
        # Punch Out + 99 clean rungs + Employee of the Month + Speedrun = 102,
        # plus the level's collectibles, its Bob note, and the Digsite events.
        for _map, display, _title in LEVELS:
            expected = 102 + len(over_100_rungs(_map))
            expected += sum(1 for m, _t, _c in COLLECTIBLES if m == _map)
            expected += sum(1 for m, _t in BOB_NOTES if m == _map)
            if _map == "VC_Digsite":
                expected += 2
            count = sum(1 for m in LOCATION_MAP.values() if m == _map)
            self.assertEqual(count, expected, display)

    def test_top_rung_floors_to_step_then_backs_off_one(self):
        # Athena's Wrath peaks at 154.04 percent. Steps finer than 5 keep the
        # 5-grid ceiling, so the maxima are never trusted more tightly.
        self.assertEqual(top_rung("VC_Hall", 5), 145)
        self.assertEqual(top_rung("VC_Hall", 10), 140)
        self.assertEqual(top_rung("VC_Hall", 2), 145)
        self.assertEqual(top_rung("VC_Hall", 1), 145)
        # Gravity Drive peaks at 113.78: the ceiling is 105 on the fine grid.
        self.assertEqual(top_rung("VC_ZeroG_New", 5), 105)
        self.assertEqual(top_rung("VC_ZeroG_New", 10), 100)
        self.assertCountEqual(over_100_rungs("VC_ZeroG_New"),
                              [101, 102, 103, 104, 105])

    def test_collectible_tokens_unique(self):
        tokens = ([t for _m, t, _c in COLLECTIBLES] + [t for _m, t in BOB_NOTES])
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertEqual(len(COLLECTIBLES), 39)

    def test_step_choices_match_the_option(self):
        from ..locations import MILESTONE_STEP_CHOICES
        from ..options import MilestoneStep
        self.assertEqual(sorted(MILESTONE_STEP_CHOICES),
                         sorted(MilestoneStep.options.values()))

    def test_milestone_step_gating(self):
        # Punch Out (not a milestone) is always enabled.
        self.assertTrue(milestone_enabled(punch_out_name(LEVELS[0][1]), 10))
        # A milestone rung is enabled only when its percent is a multiple of step.
        enabled_10 = [n for n in MILESTONE_PERCENT if milestone_enabled(n, 10)]
        self.assertTrue(all(MILESTONE_PERCENT[n] % 10 == 0 for n in enabled_10))
        # The datapackage holds every whole-percent rung; step 1 enables all.
        self.assertTrue(all(milestone_enabled(n, 1) for n in MILESTONE_PERCENT))
        self.assertTrue(any(MILESTONE_PERCENT[n] % 5 != 0
                            for n in MILESTONE_PERCENT))


if __name__ == "__main__":
    unittest.main()
