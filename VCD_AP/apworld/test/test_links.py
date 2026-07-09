"""Tests for the link-event channel: the alias table maps linked trap names
onto this game's trap types, and the links file carries the session tag, the
death link flag, and the entries the mod parses."""
import tempfile
import unittest
from pathlib import Path

from .bases import read_sav_properties
from .. import links
from ..traps import TRAP_TYPE_BY_NAME


class TestLinkedTrapMatching(unittest.TestCase):
    def test_native_names_map_to_themselves(self) -> None:
        # Linked Viscera seeds exchange traps one to one.
        for name, queue_type in TRAP_TYPE_BY_NAME.items():
            self.assertEqual(links.local_trap_type(name), queue_type)

    def test_every_alias_lands_on_a_real_trap_type(self) -> None:
        local_types = set(TRAP_TYPE_BY_NAME.values())
        for name, queue_type in links.LINKED_TRAP_TYPE_BY_NAME.items():
            self.assertIn(queue_type, local_types, name)

    def test_common_foreign_names_map_broadly(self) -> None:
        self.assertEqual(links.local_trap_type("Ice Trap"), "Slowdown")
        self.assertEqual(links.local_trap_type("Thwimp Trap"), "MessDump")
        self.assertEqual(links.local_trap_type("Gravity Trap"), "ZeroGravity")
        self.assertEqual(links.local_trap_type("Banana Trap"), "BucketSpill")
        self.assertEqual(links.local_trap_type("Magnet Trap"), "Magnetize")

    def test_unknown_names_are_ignored(self) -> None:
        self.assertIsNone(links.local_trap_type("Ring Trap"))
        self.assertIsNone(links.local_trap_type(""))

    def test_the_death_type_is_no_trap_type(self) -> None:
        # The mod switches on the type token, so Death must stay distinct.
        self.assertNotIn(links.DEATH_TYPE, TRAP_TYPE_BY_NAME.values())
        self.assertNotIn(links.DEATH_TYPE, links.LINKED_TRAP_TYPE_BY_NAME)


class TestLinksFile(unittest.TestCase):
    def test_write_carries_tag_flag_and_entries(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "VCArchipelagoLinks.sav"
            links.write(path, "seed_1-feedface", True,
                        ["1:Death", "2:Slowdown"])
            properties = read_sav_properties(path.read_bytes())
        self.assertEqual(properties["SessionTag"], "seed_1-feedface")
        self.assertEqual(properties["DeathLinkOn"], "1")
        self.assertEqual(properties["Entries"], "1:Death,2:Slowdown")

    def test_death_link_off_and_no_entries_still_write(self) -> None:
        # The file always writes on connect so leftovers cannot linger.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "VCArchipelagoLinks.sav"
            links.write(path, "seed_1-feedface", False, [])
            properties = read_sav_properties(path.read_bytes())
        self.assertEqual(properties["DeathLinkOn"], "0")
        self.assertEqual(properties["Entries"], "")


if __name__ == "__main__":
    unittest.main()
