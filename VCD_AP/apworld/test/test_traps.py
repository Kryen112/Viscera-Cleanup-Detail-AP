"""Tests for the spawn queue: the codec layout the mod reads, the queue the
client derives from the received-item list, and the baseline that keeps a
connect from replaying a backlog."""
import unittest

from .bases import read_sav_properties
from .. import grants, traps
from ..items import ITEM_ID_BASE, ITEM_NAME_TO_ID, SQUEAKY_BOOTS_ITEMS

QUEUE_ID_TO_TYPE = {
    ITEM_NAME_TO_ID[name]: queue_type
    for name, queue_type in traps.QUEUE_TYPE_BY_NAME.items()
}
MESS_DUMP = ITEM_NAME_TO_ID["Mess Dump Trap"]
SLOWDOWN = ITEM_NAME_TO_ID["Slowdown Trap"]
SPEEDUP = ITEM_NAME_TO_ID["Speedup Trap"]
MAGNETIZE = ITEM_NAME_TO_ID["Magnetize Trap"]
ZERO_GRAVITY = ITEM_NAME_TO_ID["Zero Gravity Trap"]
CLEAN_BUCKET = ITEM_NAME_TO_ID["Clean Water Bucket"]
EMPTY_BIN = ITEM_NAME_TO_ID["Empty Bin"]
FILLER = ITEM_NAME_TO_ID["Overtime Pay"]


class TestTrapsFile(unittest.TestCase):
    def test_multi_property_layout_round_trips(self) -> None:
        data = grants.build_object([
            ("SeedTag", "seed_1"),
            ("BaselineIndex", "4"),
            ("TrapQueue", "5:MessDump,9:Slowdown"),
        ])
        self.assertEqual(read_sav_properties(data), {
            "SeedTag": "seed_1",
            "BaselineIndex": "4",
            "TrapQueue": "5:MessDump,9:Slowdown",
        })

    def test_single_property_build_matches_grants_layout(self) -> None:
        # The grants file is a frozen contract; the generalized builder must
        # produce byte-identical output for it.
        self.assertEqual(grants.build("VC_Hall,VC_Cryo"),
                         grants.build_object([("UnlockedMaps", "VC_Hall,VC_Cryo")]))


class TestBuildQueue(unittest.TestCase):
    def test_queue_indexes_are_one_based_positions(self) -> None:
        received = [FILLER, MESS_DUMP, FILLER, FILLER, SLOWDOWN]
        self.assertEqual(traps.build_queue(received, QUEUE_ID_TO_TYPE),
                         "2:MessDump,5:Slowdown")

    def test_useful_items_ride_the_queue_in_receive_order(self) -> None:
        received = [MESS_DUMP, CLEAN_BUCKET, FILLER, EMPTY_BIN]
        self.assertEqual(traps.build_queue(received, QUEUE_ID_TO_TYPE),
                         "1:MessDump,2:CleanBucket,4:EmptyBin")

    def test_speedup_rides_the_queue_with_its_own_token(self) -> None:
        received = [SLOWDOWN, FILLER, SPEEDUP]
        self.assertEqual(traps.build_queue(received, QUEUE_ID_TO_TYPE),
                         "1:Slowdown,3:Speedup")

    def test_magnetize_rides_the_queue_with_its_own_token(self) -> None:
        received = [FILLER, MAGNETIZE, MESS_DUMP]
        self.assertEqual(traps.build_queue(received, QUEUE_ID_TO_TYPE),
                         "2:Magnetize,3:MessDump")

    def test_zero_gravity_rides_the_queue_with_its_own_token(self) -> None:
        received = [ZERO_GRAVITY, FILLER, SLOWDOWN]
        self.assertEqual(traps.build_queue(received, QUEUE_ID_TO_TYPE),
                         "1:ZeroGravity,3:Slowdown")

    def test_no_queued_items_is_empty(self) -> None:
        self.assertEqual(traps.build_queue([FILLER, FILLER], QUEUE_ID_TO_TYPE), "")


class TestItemIdStability(unittest.TestCase):
    def test_new_names_append_after_the_frozen_tail(self) -> None:
        # A seed generated before the speedup trap existed keeps its ids: the
        # older names hold their positions and the new name appends after them.
        # The absolute anchor (26 level-access items, 2 filler names, and the
        # retired Spare Bucket slot ahead of the first trap) catches a shift
        # of the whole tail too.
        self.assertEqual(ITEM_NAME_TO_ID["Mess Dump Trap"], ITEM_ID_BASE + 29)
        self.assertEqual(ITEM_NAME_TO_ID["Clean Water Bucket"],
                         ITEM_NAME_TO_ID["Slowdown Trap"] + 1)
        self.assertEqual(ITEM_NAME_TO_ID["Empty Bin"],
                         ITEM_NAME_TO_ID["Clean Water Bucket"] + 1)
        self.assertEqual(ITEM_NAME_TO_ID["Speedup Trap"],
                         ITEM_NAME_TO_ID["Empty Bin"] + 1)

    def test_magnetize_appends_after_the_frozen_tail(self) -> None:
        # The magnetize trap sits after the last Squeaky Clean Boots id, so no
        # earlier id can shift.
        self.assertEqual(ITEM_NAME_TO_ID["Magnetize Trap"],
                         ITEM_NAME_TO_ID[SQUEAKY_BOOTS_ITEMS[-1]] + 1)

    def test_zero_gravity_appends_after_the_frozen_tail(self) -> None:
        # The zero gravity trap is the newest name, so it sits after the
        # magnetize trap and holds the highest id in the table.
        self.assertEqual(ITEM_NAME_TO_ID["Zero Gravity Trap"],
                         ITEM_NAME_TO_ID["Magnetize Trap"] + 1)
        self.assertEqual(ITEM_NAME_TO_ID["Zero Gravity Trap"],
                         max(ITEM_NAME_TO_ID.values()))

    def test_retired_names_hold_their_id_slot_but_leave_the_table(self) -> None:
        # The retired Spare Bucket keeps its slot as a gap, so the ids behind
        # it never shift and the name never reaches the datapackage.
        self.assertNotIn("Spare Bucket", ITEM_NAME_TO_ID)
        self.assertNotIn(ITEM_ID_BASE + 28, ITEM_NAME_TO_ID.values())
        self.assertEqual(ITEM_NAME_TO_ID["Coffee Break"], ITEM_ID_BASE + 27)


class TestQueueFields(unittest.TestCase):
    def test_fixed_baseline_is_kept(self) -> None:
        seed, baseline, queue = traps.queue_fields(
            "seed_1", 1, [FILLER, MESS_DUMP], QUEUE_ID_TO_TYPE)
        self.assertEqual((seed, baseline, queue), ("seed_1", 1, "2:MessDump"))

    def test_unknown_baseline_counts_every_known_item(self) -> None:
        # Before the resync packet fixes the baseline, everything known so far
        # is baselined, so the queued trap (index 2) can never apply early.
        seed, baseline, queue = traps.queue_fields(
            "seed_1", None, [FILLER, MESS_DUMP], QUEUE_ID_TO_TYPE)
        self.assertEqual((seed, baseline, queue), ("seed_1", 2, "2:MessDump"))

    def test_unknown_baseline_with_no_items_is_zero(self) -> None:
        self.assertEqual(traps.queue_fields("seed_1", None, [], QUEUE_ID_TO_TYPE),
                         ("seed_1", 0, ""))

    def test_applied_floor_below_baseline_keeps_baseline(self) -> None:
        _, baseline, _ = traps.queue_fields(
            "seed_1", 5, [FILLER, MESS_DUMP], QUEUE_ID_TO_TYPE, applied_floor=3)
        self.assertEqual(baseline, 5)

    def test_applied_floor_above_baseline_raises_it(self) -> None:
        # Another co-op host already applied past this client's connect
        # baseline; the fold keeps those entries from replaying here.
        _, baseline, _ = traps.queue_fields(
            "seed_1", 1, [FILLER, MESS_DUMP], QUEUE_ID_TO_TYPE, applied_floor=2)
        self.assertEqual(baseline, 2)

    def test_no_applied_floor_leaves_baseline_alone(self) -> None:
        _, baseline, _ = traps.queue_fields(
            "seed_1", 1, [FILLER, MESS_DUMP], QUEUE_ID_TO_TYPE, applied_floor=None)
        self.assertEqual(baseline, 1)

    def test_applied_floor_folds_into_unknown_baseline_too(self) -> None:
        _, baseline, _ = traps.queue_fields(
            "seed_1", None, [FILLER, MESS_DUMP], QUEUE_ID_TO_TYPE, applied_floor=4)
        self.assertEqual(baseline, 4)


if __name__ == "__main__":
    unittest.main()
