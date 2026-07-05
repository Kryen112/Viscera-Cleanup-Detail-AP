"""The remaining-milestones file the client writes and the mod reads. It
drives the HUD's next-milestone indicator under the cleanliness readout.

``Saves\\VCArchipelagoMilestones.sav`` holds two string properties (see
grants.py for the byte layout):
- ``SeedTag``: the connected seed, so a stale file from another seed never
  drives the indicator.
- ``RemainingByMap``: per-level percents whose milestone check the server has
  not confirmed yet, ascending, e.g. ``"VC_Hall:85 90 95 100,VC_Cryo:"``. A
  map listed with no percents has every milestone confirmed checked; a map
  absent from the list has no data in this seed, which the HUD shows as
  unknown. Server state only: the file advances when the server confirms a
  check, never on a local guess.
"""
from __future__ import annotations

from pathlib import Path

from . import grants
from .levels import LEVELS
from .locations import LOCATION_MAP, LOCATION_NAME_TO_ID, MILESTONE_PERCENT


def remaining_percents_by_map(missing: "set[int]", created: "set[int]",
                              ) -> dict[str, list[int]]:
    """Per level, the ascending percents whose milestone (or Employee of the
    Month, or over-100) check the server still misses. A level appears once the
    seed created any percent check for it, so a fully checked level shows an
    empty list; levels outside the seed never appear."""
    by_map: dict[str, list[int]] = {}
    for name, percent in MILESTONE_PERCENT.items():
        location_id = LOCATION_NAME_TO_ID[name]
        if location_id not in created:
            continue
        percents = by_map.setdefault(LOCATION_MAP[name], [])
        if location_id in missing:
            percents.append(percent)
    for percents in by_map.values():
        percents.sort()
    return by_map


def encode_remaining(by_map: dict[str, list[int]]) -> str:
    """The RemainingByMap string, levels in table order so writes are stable:
    ``"VC_Hall:85 90 95 100,VC_Cryo:"``."""
    return ",".join(
        f"{map_name}:{' '.join(str(p) for p in by_map[map_name])}"
        for map_name, _, _ in LEVELS if map_name in by_map)


def write(path: Path, seed_tag: str, remaining_by_map: str) -> None:
    """Write the milestones file atomically. Always written on connect, even
    fully cleared, so a stale file from another seed cannot linger."""
    grants.write_atomic(Path(path), grants.build_object([
        ("SeedTag", seed_tag),
        ("RemainingByMap", remaining_by_map),
    ]))
