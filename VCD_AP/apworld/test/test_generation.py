"""Generation and data-integrity tests.

The option-bearing subclasses inherit WorldTestBase's fill and reachability
tests, so each exercises a full generation. TestData needs no world.
"""

import unittest

from .bases import VCDTestBase
from ..items import ITEM_NAME_TO_ID
from ..levels import LEVELS, MAP_NAMES
from ..locations import (LOCATION_NAME_TO_ID, MILESTONE_PERCENT,
                         milestone_enabled, punch_out_name)


class TestDefault(VCDTestBase):
    options = {}


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
