"""Tests for the spawn queue: the codec layout the mod reads, the queue the
client derives from the received-item list, and the baseline that keeps a
connect from replaying a backlog."""
import unittest

from .bases import read_sav_properties
from .. import grants, traps
from ..items import ITEM_NAME_TO_ID

QUEUE_ID_TO_TYPE = {
    ITEM_NAME_TO_ID[name]: queue_type
    for name, queue_type in traps.QUEUE_TYPE_BY_NAME.items()
}
MESS_DUMP = ITEM_NAME_TO_ID["Mess Dump Trap"]
SLOWDOWN = ITEM_NAME_TO_ID["Slowdown Trap"]
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

    def test_no_queued_items_is_empty(self) -> None:
        self.assertEqual(traps.build_queue([FILLER, FILLER], QUEUE_ID_TO_TYPE), "")


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


if __name__ == "__main__":
    unittest.main()
