"""Tests for the client's mod-state parsing: the state file snapshot maps to
location names, with the punch-out and speedrun policy applied."""
import unittest

from ..client import location_names_from_state, parse_rungs


class TestParseRungs(unittest.TestCase):
    def test_parses_comma_separated_ints(self) -> None:
        self.assertEqual(parse_rungs("5,10,15"), [5, 10, 15])

    def test_ignores_junk_and_blanks(self) -> None:
        self.assertEqual(parse_rungs(" 5, ,x,20 "), [5, 20])

    def test_empty_is_empty(self) -> None:
        self.assertEqual(parse_rungs(""), [])


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


if __name__ == "__main__":
    unittest.main()
