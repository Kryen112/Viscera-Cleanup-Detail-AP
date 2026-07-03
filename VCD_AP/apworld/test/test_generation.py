"""Generation and data-integrity tests.

The option-bearing subclasses inherit WorldTestBase's fill and reachability
tests, so each exercises a full generation. TestData needs no world.
"""

import unittest

from .bases import VCDTestBase
from ..items import ITEM_NAME_TO_ID
from ..levels import LEVELS, MAP_NAMES
from ..locations import (LOCATION_NAME_TO_ID, MILESTONE_PERCENT,
                         milestone_enabled, punch_out_name, speedrun_name)


class TestDefault(VCDTestBase):
    options = {}

    def test_speedrun_locations_absent_by_default(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        for _map, display, _title in LEVELS:
            self.assertNotIn(speedrun_name(display), names)


class TestSpeedrunsanity(VCDTestBase):
    options = {"speedrunsanity": True}

    def test_speedrun_locations_exist(self):
        for _map, display, _title in LEVELS:
            self.assert_location_exists(speedrun_name(display))


class TestTrapPercentage(VCDTestBase):
    options = {"trap_percentage": 50}

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


class TestNoTrapsByDefault(VCDTestBase):
    options = {}

    def test_pool_has_no_traps(self):
        from ..traps import TRAP_NAMES
        for item in self.multiworld.itempool:
            self.assertNotIn(item.name, TRAP_NAMES)


class TestStep25(VCDTestBase):
    options = {"milestone_step": 25}


class TestFewStartingLevels(VCDTestBase):
    options = {"starting_levels": 3}


class TestEmployeeGoal(VCDTestBase):
    options = {"goal": "employee_of_the_month", "goal_amount": 5}


class TestFindBobGoal(VCDTestBase):
    options = {"goal": "find_bob"}


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
        # Punch Out + 19 clean rungs + Employee of the Month + Speedrun = 22.
        from ..locations import LOCATION_MAP
        for _map, display, _title in LEVELS:
            count = sum(1 for m in LOCATION_MAP.values() if m == _map)
            self.assertEqual(count, 22, display)

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
