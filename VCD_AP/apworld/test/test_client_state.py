"""Tests for the client's mod-state parsing and its toast feed: the state file
snapshot maps to location names (with the punch-out and speedrun policy, and
only a seed-stamped snapshot counting), and PrintJSON traffic filters and
encodes into the messages file."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from .bases import read_sav_properties
from .. import messages
from ..client import (VCDContext, goal_locations_from_slot_data,
                      location_names_from_state, message_segments, parse_rungs,
                      print_json_relevant, state_is_current,
                      traps_applied_to_push)
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


def _segments_context() -> SimpleNamespace:
    """A stand-in for the connected context: slot 1 is us, with fixed name and
    id lookups."""
    return SimpleNamespace(
        slot_concerns_self=lambda slot: slot == 1,
        player_names={1: "Janitor", 2: "Alice"},
        item_names=SimpleNamespace(
            lookup_in_slot=lambda code, slot=None: f"Item{code}"),
        location_names=SimpleNamespace(
            lookup_in_slot=lambda code, slot=None: f"Location{code}"),
    )


class TestMessageSegments(unittest.TestCase):
    def test_item_send_parts_resolve_names_and_colors(self) -> None:
        parts = [
            {"type": "player_id", "text": "1"},
            {"type": "text", "text": " sent "},
            {"type": "item_id", "text": "42", "flags": 1, "player": 2},
            {"type": "text", "text": " to "},
            {"type": "player_id", "text": "2"},
        ]
        self.assertEqual(message_segments(parts, _segments_context()), [
            ("EE00EE", "Janitor"),
            ("FFFFFF", " sent "),
            ("AF99EF", "Item42"),
            ("FFFFFF", " to "),
            ("FAFAD2", "Alice"),
        ])

    def test_location_and_entrance_and_color_parts(self) -> None:
        parts = [
            {"type": "location_id", "text": "9", "player": 1},
            {"type": "entrance_name", "text": "Vanilla"},
            {"type": "color", "color": "red", "text": "alert"},
            {"type": "color", "color": "unknown", "text": "plain"},
        ]
        self.assertEqual(message_segments(parts, _segments_context()), [
            ("00FF7F", "Location9"),
            ("6495ED", "Vanilla"),
            ("EE0000", "alert"),
            ("FFFFFF", "plain"),
        ])

    def test_trap_flags_color_salmon(self) -> None:
        parts = [{"type": "item_id", "text": "7", "flags": 4, "player": 1}]
        self.assertEqual(message_segments(parts, _segments_context()),
                         [("FA8072", "Item7")])

    def test_untyped_parts_default_to_white_text(self) -> None:
        self.assertEqual(message_segments([{"text": "hello"}],
                                          _segments_context()),
                         [("FFFFFF", "hello")])


def _concerns_slot_one(slot: int) -> bool:
    return slot == 1


class TestPrintJsonRelevant(unittest.TestCase):
    def test_own_receive_and_own_send_are_relevant(self) -> None:
        receive = {"type": "ItemSend", "receiving": 1,
                   "item": SimpleNamespace(player=2)}
        self.assertTrue(print_json_relevant(receive, _concerns_slot_one, 0))
        send = {"type": "ItemSend", "receiving": 2,
                "item": SimpleNamespace(player=1)}
        self.assertTrue(print_json_relevant(send, _concerns_slot_one, 0))

    def test_self_find_is_relevant_once(self) -> None:
        found = {"type": "ItemSend", "receiving": 1,
                 "item": SimpleNamespace(player=1)}
        self.assertTrue(print_json_relevant(found, _concerns_slot_one, 0))

    def test_unrelated_traffic_is_dropped(self) -> None:
        other = {"type": "ItemSend", "receiving": 2,
                 "item": SimpleNamespace(player=3)}
        self.assertFalse(print_json_relevant(other, _concerns_slot_one, 0))
        chat = {"type": "Chat", "receiving": 1,
                "item": SimpleNamespace(player=1)}
        self.assertFalse(print_json_relevant(chat, _concerns_slot_one, 0))
        self.assertFalse(print_json_relevant(
            {"type": "ItemSend", "receiving": 1}, _concerns_slot_one, 0))

    def test_item_cheat_needs_the_own_team(self) -> None:
        cheat = {"type": "ItemCheat", "receiving": 1,
                 "item": SimpleNamespace(player=0), "team": 1}
        self.assertFalse(print_json_relevant(cheat, _concerns_slot_one, 0))
        self.assertTrue(print_json_relevant(cheat, _concerns_slot_one, 1))


def _feed_context(install_dir: "Path | None") -> VCDContext:
    """A context carrying only the toast-feed state, skipping __init__ so no
    framework plumbing is needed."""
    ctx = VCDContext.__new__(VCDContext)
    ctx.message_tag = "seed_1-1a2b3c4d"
    ctx.message_index = 0
    ctx.message_entries = []
    ctx.last_messages_written = None
    ctx.install_dir = install_dir
    ctx.saves_ready = install_dir is not None
    return ctx


class TestEnqueueMessage(unittest.TestCase):
    def test_enqueued_lines_land_in_the_feed_file(self) -> None:
        # The client-authored connect and goal lines ride this exact path.
        with tempfile.TemporaryDirectory() as tmp:
            ctx = _feed_context(Path(tmp))
            ctx.enqueue_message([(messages.WHITE, "Archipelago connected.")])
            ctx.enqueue_message([
                (messages.LOCATION_COLOR, "Goal complete. The shift is over.")])
            data = (Path(tmp) / "Saves" / "VCArchipelagoMessages.sav").read_bytes()
            properties = read_sav_properties(data)
            self.assertEqual(properties["SessionTag"], "seed_1-1a2b3c4d")
            self.assertEqual(properties["Messages"].split("\n"), [
                "1:FFFFFFArchipelago connected.",
                "2:00FF7FGoal complete. The shift is over.",
            ])

    def test_blank_lines_never_queue(self) -> None:
        ctx = _feed_context(None)
        ctx.enqueue_message([(messages.WHITE, "\t\n")])
        ctx.enqueue_message([])
        self.assertEqual(ctx.message_index, 0)
        self.assertEqual(ctx.message_entries, [])

    def test_without_a_session_tag_nothing_queues(self) -> None:
        ctx = _feed_context(None)
        ctx.message_tag = None
        ctx.enqueue_message([(messages.WHITE, "line")])
        self.assertEqual(ctx.message_entries, [])


if __name__ == "__main__":
    unittest.main()
