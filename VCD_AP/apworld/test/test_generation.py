"""Generation and data-integrity tests.

The option-bearing subclasses inherit WorldTestBase's fill and reachability
tests, so each exercises a full generation. TestData needs no world.
"""

import unittest

from Options import OptionError

from .bases import VCDTestBase
from ..collectibles import (BOB_NOTE_MAPS, BOB_NOTES, COLLECTIBLES,
                            GATED_COLLECTIBLE_TOKENS)
from ..items import ITEM_NAME_TO_ID, TOOL_ITEMS, access_item_name
from ..levels import DISPLAY_BY_MAP, LEVELS, MAP_NAMES
from ..locations import (BOB_GATED_LOCATIONS, DIGSITE_GATES_LOCATION,
                         FIND_BOB_LOCATION, LOCATION_MAP,
                         LOCATION_NAME_TO_ID, MILESTONE_PERCENT,
                         collectible_name, employee_of_the_month_name,
                         milestone_enabled, milestone_name, over_100_rungs,
                         punch_out_name, speedrun_name, top_rung)
from ..toolsanity import tool_item_name


class TestDefault(VCDTestBase):
    options = {}

    def test_speedrun_locations_absent_by_default(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for _map, display, _title in LEVELS:
            self.assertNotIn(speedrun_name(display), names)

    def test_bob_gated_checks_need_the_chain_accesses_and_full_kits(self):
        needed = [access_item_name(DISPLAY_BY_MAP[m])
                  for m in BOB_NOTE_MAPS + ["VC_Digsite"]]
        for m in BOB_NOTE_MAPS + ["VC_Digsite"]:
            needed.extend(self.world._full_kit_items(m))
        gated = [DIGSITE_GATES_LOCATION, FIND_BOB_LOCATION]
        gated += [collectible_name(DISPLAY_BY_MAP[m], c)
                  for m, t, c in COLLECTIBLES if t in GATED_COLLECTIBLE_TOKENS]
        for name in gated:
            # Any single missing piece (the last is a Digsite tool) blocks it.
            self.assertFalse(
                self.multiworld.get_location(name, self.player).can_reach(
                    self.state_with(needed[:-1])), name)
            self.assertTrue(
                self.multiworld.get_location(name, self.player).can_reach(
                    self.state_with(needed)), name)

    def test_collectibles_need_their_level_and_its_full_kit(self):
        # Except the gate-locked ones, which the Bob-gated test covers.
        for map_name, token, collectible in COLLECTIBLES:
            if token in GATED_COLLECTIBLE_TOKENS:
                continue
            display = DISPLAY_BY_MAP[map_name]
            kit = list(self.world._full_kit_items(map_name))
            location = self.multiworld.get_location(
                collectible_name(display, collectible), self.player)
            self.assertFalse(
                location.can_reach(self.state_with(
                    [access_item_name(display)] + kit[:-1])), display)
            self.assertTrue(
                location.can_reach(self.state_with(
                    [access_item_name(display)] + kit)), display)

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
        # A useful item is never required, so no location's rule references it.
        from ..items import self_cleaning_mop_name
        access = [access_item_name("Waste Disposal")]
        kit = list(self.world._full_kit_items("VC_Sewer"))
        location = self.multiworld.get_location(
            employee_of_the_month_name("Waste Disposal"), self.player)
        # The full kit alone reaches it; the mop item is not part of the kit.
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
        kit = list(self.world._full_kit_items("VC_Sewer"))
        location = self.multiworld.get_location(
            employee_of_the_month_name("Waste Disposal"), self.player)
        # The full kit alone reaches it; the boots item is not part of the kit.
        self.assertNotIn(squeaky_boots_name("Waste Disposal"), kit)
        self.assertTrue(location.can_reach(self.state_with(access + kit)))

    def test_low_rungs_open_with_access_high_rungs_need_the_kit(self):
        # Waste Disposal is 73 percent moppable, so mid rungs open with the
        # starting kit but the top of the ladder waits for the tools.
        access = [access_item_name("Waste Disposal")]
        kit = list(self.world._full_kit_items("VC_Sewer"))
        low = self.multiworld.get_location(
            milestone_name("Waste Disposal", 45), self.player)
        high = self.multiworld.get_location(
            milestone_name("Waste Disposal", 95), self.player)
        self.assertTrue(low.can_reach(self.state_with(access)))
        self.assertFalse(high.can_reach(self.state_with(access)))
        self.assertTrue(high.can_reach(self.state_with(access + kit)))

    def test_employee_of_the_month_needs_the_full_kit(self):
        access = [access_item_name("Waste Disposal")]
        kit = list(self.world._full_kit_items("VC_Sewer"))
        location = self.multiworld.get_location(
            employee_of_the_month_name("Waste Disposal"), self.player)
        self.assertFalse(location.can_reach(self.state_with(access + kit[:-1])))
        self.assertTrue(location.can_reach(self.state_with(access + kit)))


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
               "goal_amount": 1, "level_pool": {"Waste Disposal"}}

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


class TestStep1(VCDTestBase):
    # A small pool keeps the fill fast; step 1 on the full 26 levels holds
    # thousands of checks and works the same way.
    options = {"milestone_step": 1, "above_and_beyond": True,
               "level_pool": {"Athena's Wrath", "Cryogenesis",
                              "Waste Disposal"},
               "goal_amount": 3}

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
               "goal_amount": 3}

    def test_even_rungs_only(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn(milestone_name("Cryogenesis", 4), names)
        self.assertNotIn(milestone_name("Cryogenesis", 5), names)


class TestFewStartingLevels(VCDTestBase):
    options = {"starting_levels": 3}


class TestEmployeeGoal(VCDTestBase):
    options = {"goal": "employee_of_the_month", "goal_amount": 5}


class TestFindBobGoal(VCDTestBase):
    options = {"goal": "find_bob"}

    def test_completion_requires_the_note_levels(self):
        needed = [access_item_name(DISPLAY_BY_MAP[m])
                  for m in BOB_NOTE_MAPS + ["VC_Digsite"]]
        for m in BOB_NOTE_MAPS + ["VC_Digsite"]:
            needed.extend(self.world._full_kit_items(m))
        self.assertFalse(
            self.multiworld.completion_condition[self.player](
                self.state_with(needed[:-1])))
        self.assertTrue(
            self.multiworld.completion_condition[self.player](
                self.state_with(needed)))


class TestCollectiblesGoal(VCDTestBase):
    options = {"goal": "collect_collectibles", "goal_amount": 3}

    def test_completion_counts_reachable_collectibles(self):
        # Cryogenesis and Gravity Drive hold two collectibles each; the two
        # levels together clear the three-collectible bar. Collectibles need
        # their level's full kit on top of its access.
        cryo = ([access_item_name("Cryogenesis")]
                + list(self.world._full_kit_items("VC_Cryo")))
        both_kits = cryo + [access_item_name("Gravity Drive")] + list(
            self.world._full_kit_items("VC_ZeroG_New"))
        self.assertFalse(self.multiworld.completion_condition[self.player](
            self.state_with(cryo)))
        self.assertTrue(self.multiworld.completion_condition[self.player](
            self.state_with(both_kits)))


class TestCollectiblesGoalFullAmount(VCDTestBase):
    # 39 is the collectible cap, so it survives the clamp and must still fill.
    options = {"goal": "collect_collectibles", "goal_amount": 39}

    def test_amount_kept(self):
        self.assertEqual(int(self.world.options.goal_amount.value), 39)


class TestLevelPool(VCDTestBase):
    options = {"level_pool": {"Splatter Station", "Cryogenesis", "Gravity Drive"},
               "goal_amount": 3}

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
               "goal_amount": 2}

    def test_gated_checks_absent_open_area_drops_present(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for gated in BOB_GATED_LOCATIONS:
            self.assertNotIn(gated, names)
        self.assert_location_exists(
            collectible_name("Unearthly Excavation", "Bolter"))
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
    options = {"goal": "collect_collectibles", "goal_amount": 4,
               "level_pool": {"Cryogenesis", "Gravity Drive"}}

    def test_completion_needs_both_pooled_levels(self):
        cryo = ([access_item_name("Cryogenesis")]
                + list(self.world._full_kit_items("VC_Cryo")))
        both_kits = cryo + [access_item_name("Gravity Drive")] + list(
            self.world._full_kit_items("VC_ZeroG_New"))
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
                            "goal": "complete_levels", "goal_amount": 3})

    def test_level_goal_over_level_count_raises(self):
        with self.assertRaises(OptionError):
            self._generate({"goal": "complete_levels", "goal_amount": 39})

    def test_default_goal_amount_over_small_pool_raises(self):
        # The default amount is every level; a two-level pool cannot carry it.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station", "Cryogenesis"}})

    def test_collectible_goal_over_pooled_collectibles_raises(self):
        # The two pooled levels hold four collectibles between them.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Cryogenesis", "Gravity Drive"},
                            "goal": "collect_collectibles", "goal_amount": 5})

    def test_collectible_goal_without_collectible_levels_raises(self):
        # Splatter Station holds no collectibles at all.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station"},
                            "goal": "collect_collectibles", "goal_amount": 1})

    def test_randomized_pool_cannot_rescue_an_impossible_goal(self):
        # The draw only picks from the candidates, so a candidate set without
        # collectibles still fails the collectible goal.
        with self.assertRaises(OptionError):
            self._generate({"level_pool": {"Splatter Station"},
                            "randomize_level_pool": True,
                            "goal": "collect_collectibles", "goal_amount": 1})

    def test_empty_pool_raises(self):
        with self.assertRaises(OptionError):
            self._generate({"level_pool": set(), "goal_amount": 1})


class TestRandomizedPoolLevelGoal(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "complete_levels",
               "goal_amount": 4}

    def test_pool_is_large_enough_for_the_goal(self):
        self.assertGreaterEqual(len(self.world.pooled_maps), 4)
        self.assertTrue(set(self.world.pooled_maps).issubset(MAP_NAMES))

    def test_option_value_reflects_the_drawn_pool(self):
        self.assertEqual({DISPLAY_BY_MAP[m] for m in self.world.pooled_maps},
                         self.world.options.level_pool.value)


class TestRandomizedPoolEmployeeGoal(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "employee_of_the_month",
               "goal_amount": 6}

    def test_pool_is_large_enough_for_the_goal(self):
        self.assertGreaterEqual(len(self.world.pooled_maps), 6)


class TestRandomizedPoolCollectiblesGoal(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "collect_collectibles",
               "goal_amount": 5}

    def test_pool_carries_enough_collectibles(self):
        pooled = set(self.world.pooled_maps)
        chain_present = pooled.issuperset(BOB_NOTE_MAPS + ["VC_Digsite"])
        countable = sum(1 for m, t, _ in COLLECTIBLES if m in pooled
                        and (chain_present or t not in GATED_COLLECTIBLE_TOKENS))
        self.assertGreaterEqual(countable, 5)


class TestRandomizedPoolAllCollectibles(VCDTestBase):
    options = {"randomize_level_pool": True, "goal": "collect_collectibles",
               "goal_amount": 39}

    def test_the_gate_chain_is_forced_in(self):
        # 39 needs the gate-locked Red Keycard, so the whole chain joins.
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
               "goal": "complete_levels", "goal_amount": 2}

    def test_pool_stays_inside_the_candidates_and_fits_the_goal(self):
        candidates = {"VC_SplatterStation", "VC_Cryo", "VC_ZeroG_New",
                      "VC_IceStation", "VC_Darkening"}
        self.assertTrue(set(self.world.pooled_maps).issubset(candidates))
        self.assertGreaterEqual(len(self.world.pooled_maps), 2)


class TestCompleteFew(VCDTestBase):
    options = {"goal": "complete_levels", "goal_amount": 5,
               "milestone_step": 10}


class TestToolsanityBands(unittest.TestCase):
    def test_mop_only_caps(self):
        from ..toolsanity import DEFAULT_FREE_KEYS, rung_in_logic
        kit = frozenset(DEFAULT_FREE_KEYS)
        # Waste Disposal is 73 percent moppable with no lift on the level.
        self.assertTrue(rung_in_logic("VC_Sewer", 65, 5, kit))
        self.assertFalse(rung_in_logic("VC_Sewer", 70, 5, kit))
        # Incubation Emergency is 16 percent moppable minus the lift
        # reservation: not even the first rung clears with slack.
        self.assertFalse(rung_in_logic("VC_Incubator", 5, 5, kit))

    def test_no_hands_ceiling_on_key_gated_levels(self):
        from ..toolsanity import DEFAULT_FREE_KEYS, rung_in_logic, toolset_cap
        kit = frozenset(DEFAULT_FREE_KEYS)
        # House of Horror walls its deeper areas behind carried keys: without
        # hands the measured ceiling is 45 percent, well under the 56 the mop
        # share minus the lift reservation would otherwise credit.
        self.assertEqual(toolset_cap("VC_Horror_01", 5, kit), 45.0)
        self.assertTrue(rung_in_logic("VC_Horror_01", 40, 5, kit))
        self.assertFalse(rung_in_logic("VC_Horror_01", 45, 5, kit))
        # With hands the ceiling lifts and the mop share carries further.
        self.assertTrue(rung_in_logic(
            "VC_Horror_01", 45, 5, kit | {"Hands", "Incinerator"}))
        # A map absent from the ceiling table keeps its pure band arithmetic:
        # Waste Disposal mop-only is exactly its scanned mop share.
        self.assertAlmostEqual(toolset_cap("VC_Sewer", 5, kit),
                               15940.0 / 21758.5 * 100.0)

    def test_fine_steps_keep_the_five_point_slack(self):
        from ..toolsanity import DEFAULT_FREE_KEYS, rung_in_logic
        kit = frozenset(DEFAULT_FREE_KEYS)
        # At step 1 the slack stays 5 points, so the mop-only ladder on Waste
        # Disposal (73.26 percent) tops out at rung 68, not 72.
        self.assertTrue(rung_in_logic("VC_Sewer", 68, 1, kit))
        self.assertFalse(rung_in_logic("VC_Sewer", 69, 1, kit))

    def test_full_kit_reaches_the_usable_total(self):
        from ..toolsanity import full_kit_keys, toolset_cap
        held = frozenset(full_kit_keys("VC_Incubator"))
        # Incubation Emergency's known maximum is 117.67; the ladder tops out
        # at the floored 115 even though its bands sum to far less.
        self.assertEqual(toolset_cap("VC_Incubator", 5, held), 115.0)

    def test_welder_and_vendor_bands_need_the_mop(self):
        from ..toolsanity import toolset_cap
        # A hard start holding welder and vendor but no mop gains neither
        # band: the welder leaves soot and restocking ends in scrubbing.
        without_mop = frozenset({"Hands", "Incinerator", "Welder", "Vendor"})
        with_mop = without_mop | {"Mop", "SloshOMatic"}
        self.assertGreater(toolset_cap("VC_Uprinsing", 5, with_mop),
                           toolset_cap("VC_Uprinsing", 5, without_mop) + 15.0)


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
