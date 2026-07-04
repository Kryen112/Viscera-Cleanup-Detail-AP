"""Tests for the client's mod-state parsing: the state file snapshot maps to
location names, with the punch-out and speedrun policy applied, and only a
snapshot stamped with the connected seed counts."""
import unittest

from ..client import (goal_locations_from_slot_data, location_names_from_state,
                      parse_rungs, state_is_current, traps_applied_to_push)
from ..levels import LEVELS
from ..locations import LOCATION_NAME_TO_ID


class TestParseRungs(unittest.TestCase):
    def test_parses_comma_separated_ints(self) -> None:
        self.assertEqual(parse_rungs("5,10,15"), [5, 10, 15])

    def test_ignores_junk_and_blanks(self) -> None:
        self.assertEqual(parse_rungs(" 5, ,x,20 "), [5, 20])

    def test_empty_is_empty(self) -> None:
        self.assertEqual(parse_rungs(""), [])


class TestStateIsCurrent(unittest.TestCase):
    def test_matching_seed_counts(self) -> None:
        self.assertTrue(state_is_current({"APSeedTag": "seed_1"}, "seed_1"))

    def test_foreign_seed_is_ignored(self) -> None:
        # The exact stale-state hazard: a new seed must never replay the last
        # session's leftovers.
        self.assertFalse(state_is_current({"APSeedTag": "seed_1"}, "seed_2"))

    def test_unstamped_state_is_ignored(self) -> None:
        self.assertFalse(state_is_current({"APMilestones": "5,10"}, "seed_1"))
        self.assertFalse(state_is_current({"APSeedTag": ""}, "seed_1"))

    def test_unknown_seed_name_is_ignored(self) -> None:
        self.assertFalse(state_is_current({"APSeedTag": "seed_1"}, None))
        self.assertFalse(state_is_current({"APSeedTag": ""}, ""))


class TestLocationNamesFromState(unittest.TestCase):
    def test_unknown_map_yields_nothing(self) -> None:
        state = {"APMap": "VC_NotAMap", "APMilestones": "5", "APPunchedOut": "1"}
        self.assertEqual(location_names_from_state(state), [])

    def test_rungs_map_to_milestones_and_employee_of_the_month(self) -> None:
        state = {"APMap": "VC_Hall", "APMilestones": "5,10,100"}
        self.assertEqual(location_names_from_state(state), [
            "Athena's Wrath - Clean 5%",
            "Athena's Wrath - Clean 10%",
            "Athena's Wrath - Employee of the Month",
        ])

    def test_over_100_rungs_are_their_own_milestones(self) -> None:
        state = {"APMap": "VC_Hall", "APMilestones": "100,105,110"}
        self.assertEqual(location_names_from_state(state), [
            "Athena's Wrath - Employee of the Month",
            "Athena's Wrath - Clean 105%",
            "Athena's Wrath - Clean 110%",
        ])

    def test_punch_out_in_good_standing(self) -> None:
        state = {"APMap": "VC_Hall", "APPunchedOut": "1", "APFired": "0"}
        self.assertEqual(location_names_from_state(state),
                         ["Athena's Wrath - Punch Out"])

    def test_fired_punch_out_is_not_a_check(self) -> None:
        state = {"APMap": "VC_Hall", "APPunchedOut": "1", "APFired": "1"}
        self.assertEqual(location_names_from_state(state), [])

    def test_no_punch_out_without_the_flag(self) -> None:
        state = {"APMap": "VC_Hall", "APFired": "0", "APSpeedrun": "0"}
        self.assertEqual(location_names_from_state(state), [])

    def test_speedrun_flag_maps_to_speedrun(self) -> None:
        state = {"APMap": "VC_Hall", "APPunchedOut": "1", "APFired": "0",
                 "APSpeedrun": "1"}
        self.assertEqual(location_names_from_state(state), [
            "Athena's Wrath - Punch Out",
            "Athena's Wrath - Speedrun",
        ])

    def test_trunk_finds_map_to_home_level_locations(self) -> None:
        # Tokens resolve to their home level even when banked elsewhere: the
        # glasses and the Cryo note belong to Cryogenesis, banked from VC_Hall.
        state = {"APMap": "VC_Hall",
                 "APTrunkFinds": "VCSpecialDrop_Item2,Note_Bob_Cryo01,Junk"}
        self.assertEqual(location_names_from_state(state), [
            "Cryogenesis - Glasses",
            "Cryogenesis - Bob Note",
        ])

    def test_bob_event_flags(self) -> None:
        state = {"APMap": "VC_Digsite", "APDigsiteGates": "1", "APFoundBob": "1"}
        self.assertEqual(location_names_from_state(state), [
            "Unearthly Excavation - Open the Digsite Gates",
            "Unearthly Excavation - Find Bob",
        ])


class TestTrapsAppliedToPush(unittest.TestCase):
    def test_advance_on_the_connected_seed_pushes(self) -> None:
        state = {"APTrapSeed": "seed_1", "APTrapsApplied": "7"}
        self.assertEqual(traps_applied_to_push(state, "seed_1", 5), 7)

    def test_foreign_seed_pushes_nothing(self) -> None:
        # A leftover counter from another seed must never move this room's mark.
        state = {"APTrapSeed": "seed_1", "APTrapsApplied": "7"}
        self.assertIsNone(traps_applied_to_push(state, "seed_2", 0))

    def test_unknown_seed_name_pushes_nothing(self) -> None:
        state = {"APTrapSeed": "seed_1", "APTrapsApplied": "7"}
        self.assertIsNone(traps_applied_to_push(state, None, 0))
        self.assertIsNone(traps_applied_to_push(state, "", 0))

    def test_missing_fields_push_nothing(self) -> None:
        self.assertIsNone(traps_applied_to_push({}, "seed_1", 0))
        self.assertIsNone(traps_applied_to_push({"APTrapSeed": "seed_1"},
                                                "seed_1", 0))

    def test_non_numeric_counter_pushes_nothing(self) -> None:
        state = {"APTrapSeed": "seed_1", "APTrapsApplied": "junk"}
        self.assertIsNone(traps_applied_to_push(state, "seed_1", 0))
        state["APTrapsApplied"] = "-3"
        self.assertIsNone(traps_applied_to_push(state, "seed_1", 0))

    def test_no_progress_pushes_nothing(self) -> None:
        state = {"APTrapSeed": "seed_1", "APTrapsApplied": "5"}
        self.assertIsNone(traps_applied_to_push(state, "seed_1", 5))
        self.assertIsNone(traps_applied_to_push(state, "seed_1", 6))


class TestGoalLocationsFromSlotData(unittest.TestCase):
    def test_level_goal_counts_only_pooled_levels(self) -> None:
        ids, need = goal_locations_from_slot_data({
            "goal": "complete_levels", "goal_amount": 2,
            "pooled_maps": ["VC_SplatterStation", "VC_Cryo"]})
        self.assertEqual(need, 2)
        self.assertCountEqual(ids, [
            LOCATION_NAME_TO_ID["Splatter Station - Punch Out"],
            LOCATION_NAME_TO_ID["Cryogenesis - Punch Out"]])

    def test_missing_pool_means_every_level(self) -> None:
        ids, need = goal_locations_from_slot_data({
            "goal": "employee_of_the_month", "goal_amount": 26})
        self.assertEqual(len(ids), len(LEVELS))
        self.assertEqual(need, 26)

    def test_find_bob_needs_exactly_one(self) -> None:
        ids, need = goal_locations_from_slot_data({"goal": "find_bob"})
        self.assertEqual(len(ids), 1)
        self.assertEqual(need, 1)


if __name__ == "__main__":
    unittest.main()
