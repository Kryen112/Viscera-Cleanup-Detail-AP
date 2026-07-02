"""Byte-layout tests for the grants save codec the mod reads via BasicLoadObject."""
import struct
import unittest

from .. import grants


def _read_fstring(data: bytes, offset: int) -> "tuple[str, int]":
    length = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    raw = data[offset:offset + length]
    return raw[:-1].decode("ascii"), offset + length


class TestGrantsCodec(unittest.TestCase):
    def test_layout_round_trips(self) -> None:
        data = grants.build("VC_Hall,VC_Cryo")
        offset = 0
        revision = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        marker = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        name, offset = _read_fstring(data, offset)
        type_name, offset = _read_fstring(data, offset)
        prop_size = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        array_index = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        value_start = offset
        value, offset = _read_fstring(data, offset)
        terminator, offset = _read_fstring(data, offset)

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


if __name__ == "__main__":
    unittest.main()
