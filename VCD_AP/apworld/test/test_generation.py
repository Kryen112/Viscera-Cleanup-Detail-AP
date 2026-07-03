"""Generation and data-integrity tests.

The option-bearing subclasses inherit WorldTestBase's fill and reachability
tests, so each exercises a full generation. TestData needs no world.
"""

import unittest

from Options import OptionError

from .bases import VCDTestBase
from ..collectibles import (BOB_NOTE_MAPS, BOB_NOTES, COLLECTIBLES,
                            GATED_COLLECTIBLE_TOKENS)
from ..items import ITEM_NAME_TO_ID, access_item_name
from ..levels import DISPLAY_BY_MAP, LEVELS, MAP_NAMES
from ..locations import (BOB_GATED_LOCATIONS, DIGSITE_GATES_LOCATION,
                         FIND_BOB_LOCATION, LOCATION_MAP,
                         LOCATION_NAME_TO_ID, MILESTONE_PERCENT,
                         collectible_name, milestone_enabled, milestone_name,
                         over_100_rungs, punch_out_name, speedrun_name,
                         top_rung)


class TestDefault(VCDTestBase):
    options = {}

    def test_speedrun_locations_absent_by_default(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for _map, display, _title in LEVELS:
            self.assertNotIn(speedrun_name(display), names)

    def test_bob_gated_checks_need_every_note_level_plus_the_digsite(self):
        needed = [access_item_name(DISPLAY_BY_MAP[m])
                  for m in BOB_NOTE_MAPS + ["VC_Digsite"]]
        gated = [DIGSITE_GATES_LOCATION, FIND_BOB_LOCATION]
        gated += [collectible_name(DISPLAY_BY_MAP[m], c)
                  for m, t, c in COLLECTIBLES if t in GATED_COLLECTIBLE_TOKENS]
        for name in gated:
            self.assertFalse(
                self.multiworld.get_location(name, self.player).can_reach(
                    self.state_with(needed[:-1])), name)
            self.assertTrue(
                self.multiworld.get_location(name, self.player).can_reach(
                    self.state_with(needed)), name)

    def test_collectibles_need_only_their_level(self):
        # Except the gate-locked ones, which the Bob-gated test covers.
        for map_name, token, collectible in COLLECTIBLES:
            if token in GATED_COLLECTIBLE_TOKENS:
                continue
            display = DISPLAY_BY_MAP[map_name]
            location = self.multiworld.get_location(
                collectible_name(display, collectible), self.player)
            self.assertTrue(
                location.can_reach(self.state_with([access_item_name(display)])))


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


class TestStep25(VCDTestBase):
    options = {"milestone_step": 25}


class TestFewStartingLevels(VCDTestBase):
    options = {"starting_levels": 3}


class TestEmployeeGoal(VCDTestBase):
    options = {"goal": "employee_of_the_month", "goal_amount": 5}


class TestFindBobGoal(VCDTestBase):
    options = {"goal": "find_bob"}

    def test_completion_requires_the_note_levels(self):
        needed = [access_item_name(DISPLAY_BY_MAP[m])
                  for m in BOB_NOTE_MAPS + ["VC_Digsite"]]
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
        # levels together clear the three-collectible bar.
        one = self.state_with([access_item_name("Cryogenesis")])
        both = self.state_with([access_item_name("Cryogenesis"),
                                access_item_name("Gravity Drive")])
        self.assertFalse(self.multiworld.completion_condition[self.player](one))
        self.assertTrue(self.multiworld.completion_condition[self.player](both))


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
        one = self.state_with([access_item_name("Cryogenesis")])
        both = self.state_with([access_item_name("Cryogenesis"),
                                access_item_name("Gravity Drive")])
        self.assertFalse(self.multiworld.completion_condition[self.player](one))
        self.assertTrue(self.multiworld.completion_condition[self.player](both))


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
    options = {"goal": "complete_levels", "goal_amount": 5, "milestone_step": 20}


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
        # Punch Out + 19 clean rungs + Employee of the Month + Speedrun = 22,
        # plus the level's collectibles, its Bob note, and the Digsite events.
        for _map, display, _title in LEVELS:
            expected = 22 + len(over_100_rungs(_map))
            expected += sum(1 for m, _t, _c in COLLECTIBLES if m == _map)
            expected += sum(1 for m, _t in BOB_NOTES if m == _map)
            if _map == "VC_Digsite":
                expected += 2
            count = sum(1 for m in LOCATION_MAP.values() if m == _map)
            self.assertEqual(count, expected, display)

    def test_top_rung_floors_to_step_then_backs_off_one(self):
        # Athena's Wrath peaks at 154.04 percent.
        self.assertEqual(top_rung("VC_Hall", 5), 145)
        self.assertEqual(top_rung("VC_Hall", 10), 140)
        self.assertEqual(top_rung("VC_Hall", 25), 125)
        # Gravity Drive peaks at 113.78: one over-100 rung at step 5, none wider.
        self.assertEqual(top_rung("VC_ZeroG_New", 5), 105)
        self.assertEqual(top_rung("VC_ZeroG_New", 10), 100)
        self.assertEqual(over_100_rungs("VC_ZeroG_New"), [105])

    def test_collectible_tokens_unique(self):
        tokens = ([t for _m, t, _c in COLLECTIBLES] + [t for _m, t in BOB_NOTES])
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertEqual(len(COLLECTIBLES), 39)

    def test_milestone_step_gating(self):
        # Punch Out (not a milestone) is always enabled.
        self.assertTrue(milestone_enabled(punch_out_name(LEVELS[0][1]), 25))
        # A milestone rung is enabled only when its percent is a multiple of step.
        enabled_25 = [n for n in MILESTONE_PERCENT if milestone_enabled(n, 25)]
        self.assertTrue(all(MILESTONE_PERCENT[n] % 25 == 0 for n in enabled_25))
        # Every rung sits on a 5% boundary, so step 5 enables all of them.
        self.assertTrue(all(p % 5 == 0 for p in MILESTONE_PERCENT.values()))


if __name__ == "__main__":
    unittest.main()
