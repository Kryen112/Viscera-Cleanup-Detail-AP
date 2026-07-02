"""Codec for the grants save file the client writes and the mod reads.

The mod reads ``Saves\\VCArchipelagoGrants.sav`` via ``BasicLoadObject`` into a
``VCArchipelagoGrants`` object holding one ``StrProperty``, ``UnlockedMaps``: the
comma-separated internal map names the player may enter. This writes that file in
the byte layout ``BasicLoadObject`` expects: a single tagged property terminated
by ``"None"``.

Byte layout (little-endian), decoded from a mod-written file:
    int32 revision = 1
    int32 = -1                      (header marker BasicSaveObject emits)
    FString "UnlockedMaps"          (property name)
    FString "StrProperty"           (property type)
    int32 propertySize              (byte length of the value FString)
    int32 arrayIndex = 0
    FString <value>                 (the comma-separated map names)
    FString "None"                  (property-list terminator)

An FString is ``int32 length-including-null`` then that many ASCII bytes ending in
a NUL.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable

REVISION = 1


def _fstring(text: str) -> bytes:
    raw = text.encode("ascii") + b"\x00"
    return struct.pack("<i", len(raw)) + raw


def build(unlocked_maps: str) -> bytes:
    """Serialize a comma-separated map-name string into the .sav byte layout."""
    value = _fstring(unlocked_maps)
    return (
        struct.pack("<i", REVISION)
        + struct.pack("<i", -1)
        + _fstring("UnlockedMaps")
        + _fstring("StrProperty")
        + struct.pack("<i", len(value))
        + struct.pack("<i", 0)
        + value
        + _fstring("None")
    )


def build_from_maps(map_names: Iterable[str]) -> bytes:
    """Serialize an iterable of internal map names, joined with commas. Order is
    preserved and duplicates are dropped so the file is stable across writes."""
    seen: list[str] = []
    for name in map_names:
        if name and name not in seen:
            seen.append(name)
    return build(",".join(seen))


def write(path: Path, map_names: Iterable[str]) -> None:
    """Write the grants file atomically, so the mod never reads a half-written
    file. Writes to a temporary sibling and replaces the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_from_maps(map_names)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
