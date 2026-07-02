from test.bases import WorldTestBase

from BaseClasses import CollectionState

from .. import VCDWorld


class VCDTestBase(WorldTestBase):
    game = "Viscera Cleanup Detail"
    world: VCDWorld

    def state_with(self, names: list[str]) -> CollectionState:
        """A CollectionState holding exactly the named items (no sweep)."""
        state = CollectionState(self.multiworld)
        for name in names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        return state

    def assert_location_exists(self, name: str) -> None:
        try:
            self.world.get_location(name)
        except KeyError:
            self.fail(f"expected location {name!r} to exist")
