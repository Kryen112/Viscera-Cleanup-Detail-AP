"""Byte-layout tests for the grants save codec the mod reads via BasicLoadObject."""
import struct
import tempfile
import unittest
from pathlib import Path

from .bases import read_fstring, read_sav_properties
from .. import grants


class TestGrantsCodec(unittest.TestCase):
    def test_layout_round_trips(self) -> None:
        data = grants.build("VC_Hall,VC_Cryo")
        offset = 0
        revision = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        marker = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        name, offset = read_fstring(data, offset)
        type_name, offset = read_fstring(data, offset)
        prop_size = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        array_index = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        value_start = offset
        value, offset = read_fstring(data, offset)
        terminator, offset = read_fstring(data, offset)

        self.assertEqual(revision, 1)
        self.assertEqual(marker, -1)
        self.assertEqual(name, "UnlockedMaps")
        self.assertEqual(type_name, "StrProperty")
        self.assertEqual(array_index, 0)
        self.assertEqual(value, "VC_Hall,VC_Cryo")
        self.assertEqual(terminator, "None")
        self.assertEqual(prop_size, offset - len(grants._fstring("None")) - value_start)
        self.assertEqual(offset, len(data))

    def test_build_from_maps_dedups_and_orders(self) -> None:
        data = grants.build_from_maps(["VC_Hall", "VC_Cryo", "VC_Hall", ""])
        # Same as building the joined, de-duplicated, order-preserving string.
        self.assertEqual(data, grants.build("VC_Hall,VC_Cryo"))

    def test_empty_is_valid(self) -> None:
        data = grants.build_from_maps([])
        self.assertEqual(data, grants.build(""))

    def test_write_carries_maps_and_tools_properties(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "VCArchipelagoGrants.sav"
            grants.write(path, ["VC_Hall", "VC_Cryo", "VC_Hall"],
                         "VC_Hall:Hands Welder,VC_Cryo:",
                         "VC_Hall:Hands Welder Incinerator,VC_Cryo:Hands",
                         ["VC_Hall", "VC_Cryo"], ["VC_Cryo"])
            properties = read_sav_properties(path.read_bytes())
        self.assertEqual(properties, {
            "UnlockedMaps": "VC_Hall,VC_Cryo",
            "UnlockedTools": "VC_Hall:Hands Welder,VC_Cryo:",
            "PresentTools": "VC_Hall:Hands Welder Incinerator,VC_Cryo:Hands",
            "SelfCleaningMaps": "VC_Hall,VC_Cryo",
            "SqueakyBootsMaps": "VC_Cryo",
        })

    def test_write_defaults_to_toolsanity_off(self) -> None:
        # Empty UnlockedTools and PresentTools are the toolsanity-off
        # contract: the mod treats every tool as unlocked and the HUD panel
        # shows the all-available fallback. Empty SelfCleaningMaps means the
        # mop dirties normally everywhere; empty SqueakyBootsMaps means the
        # janitor tracks bloody footprints everywhere.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "VCArchipelagoGrants.sav"
            grants.write(path, ["VC_Hall"])
            properties = read_sav_properties(path.read_bytes())
        self.assertEqual(properties["UnlockedTools"], "")
        self.assertEqual(properties["PresentTools"], "")
        self.assertEqual(properties["SelfCleaningMaps"], "")
        self.assertEqual(properties["SqueakyBootsMaps"], "")


if __name__ == "__main__":
    unittest.main()
