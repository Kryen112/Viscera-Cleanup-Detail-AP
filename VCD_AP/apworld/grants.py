"""Codec for the save files the client writes and the mod reads via
``BasicLoadObject``: the grants file (``Saves\\VCArchipelagoGrants.sav``, one
``StrProperty`` named ``UnlockedMaps``) and, through ``build_object``, any
sibling file holding a list of string properties (the traps file uses this).

Byte layout (little-endian), decoded from a mod-written file:
    int32 revision = 1
    int32 = -1                      (header marker BasicSaveObject emits)
    per property:
        FString <name>              (property name)
        FString "StrProperty"       (property type)
        int32 propertySize          (byte length of the value FString)
        int32 arrayIndex = 0
        FString <value>
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


def build_object(properties: "list[tuple[str, str]]") -> bytes:
    """Serialize named string properties into the .sav byte layout."""
    data = struct.pack("<i", REVISION) + struct.pack("<i", -1)
    for name, value in properties:
        encoded = _fstring(value)
        data += (
            _fstring(name)
            + _fstring("StrProperty")
            + struct.pack("<i", len(encoded))
            + struct.pack("<i", 0)
            + encoded
        )
    return data + _fstring("None")


def build(unlocked_maps: str) -> bytes:
    """Serialize a comma-separated map-name string into the .sav byte layout."""
    return build_object([("UnlockedMaps", unlocked_maps)])


def build_from_maps(map_names: Iterable[str]) -> bytes:
    """Serialize an iterable of internal map names, joined with commas. Order is
    preserved and duplicates are dropped so the file is stable across writes."""
    seen: list[str] = []
    for name in map_names:
        if name and name not in seen:
            seen.append(name)
    return build(",".join(seen))


def write_atomic(path: Path, data: bytes) -> None:
    """Write a .sav atomically, so the mod never reads a half-written file.
    Writes to a temporary sibling and replaces the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def write(path: Path, map_names: Iterable[str]) -> None:
    """Write the grants file atomically."""
    write_atomic(path, build_from_maps(map_names))
