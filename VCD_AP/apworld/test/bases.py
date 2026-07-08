import struct

from test.bases import WorldTestBase

from BaseClasses import CollectionState

from .. import VCDWorld


def read_fstring(data: bytes, offset: int) -> "tuple[str, int]":
    """Decode one FString from .sav bytes: int32 length then ASCII ending in NUL."""
    length = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    raw = data[offset:offset + length]
    return raw[:-1].decode("ascii"), offset + length


def read_sav_properties(data: bytes) -> dict[str, str]:
    """Decode a BasicSaveObject-layout .sav into its named string properties."""
    offset = 8  # revision int plus the -1 marker
    out: dict[str, str] = {}
    while True:
        name, offset = read_fstring(data, offset)
        if name == "None":
            break
        type_name, offset = read_fstring(data, offset)
        assert type_name == "StrProperty"
        offset += 8  # property size plus array index
        value, offset = read_fstring(data, offset)
        out[name] = value
    return out


class VCDTestBase(WorldTestBase):
    game = "Viscera Cleanup Detail"
    world: VCDWorld

    def state_with(self, names: list[str]) -> CollectionState:
        """A CollectionState holding exactly the named items (no sweep). The
        seed's random precollected starting levels are removed first, so the
        state is deterministic across seeds."""
        state = CollectionState(self.multiworld)
        for item in self.multiworld.precollected_items[self.player]:
            state.remove(item)
        for name in names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        return state

    def pickup_kit(self, map_name: str,
                   extra: "tuple[str, ...]" = ()) -> list[str]:
        """A flat satisfying kit for the level's pickup and clean-kit rules:
        every required item plus the first member of each any-of group (the
        tool unlock, not its Self-Cleaning Mop stand-in)."""
        needed, groups = self.world._pickup_requirements(map_name, tuple(extra))
        return list(needed) + [group[0] for group in groups]

    def created_item_names(self) -> list[str]:
        """Every item the seed created for the player: the itempool, the
        precollected starting items, and any items locked into locations by
        pre_fill (a started level's keystone tool)."""
        names = [item.name for item in self.multiworld.itempool]
        names += [item.name
                  for item in self.multiworld.precollected_items[self.player]]
        names += [loc.item.name for loc in self.multiworld.get_locations(
            self.player) if loc.item is not None and loc.locked]
        return names

    def assert_location_exists(self, name: str) -> None:
        try:
            self.world.get_location(name)
        except KeyError:
            self.fail(f"expected location {name!r} to exist")
