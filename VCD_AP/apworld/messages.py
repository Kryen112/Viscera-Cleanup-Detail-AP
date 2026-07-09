"""The toast feed file the client writes and the mod's HUD reads.

``Saves\\VCArchipelagoMessages.sav`` holds two string properties (grants.py has
the byte layout):
- ``SessionTag``: the connected seed plus a per-connect nonce. The HUD resets
  its shown counter when the tag changes, so a fresh client session replays its
  own feed from the top and another seed's leftovers never show.
- ``Messages``: entries joined by newline. Each entry is ``index:segments``
  with a 1-based index that only rises within a session; segments are joined by
  tab, and each segment is six hex characters ``RRGGBB`` followed by its text.
  The file is a binary property bag, so the control-character delimiters are
  safe; the text itself is sanitized to printable ASCII.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import grants

ENTRY_SEPARATOR = "\n"
SEGMENT_SEPARATOR = "\t"

# Entries kept in the file; the oldest fall off. Indexes keep rising, so the
# mod's shown counter stays valid across the drop.
MAX_ENTRIES = 200

# The Archipelago text-client palette (NetUtils JSONtoTextParser.color_codes).
COLOR_BY_NAME: dict[str, str] = {
    "black": "000000",
    "red": "EE0000",
    "green": "00FF7F",
    "yellow": "FAFAD2",
    "blue": "6495ED",
    "magenta": "EE00EE",
    "cyan": "00EEEE",
    "slateblue": "6D8BE8",
    "plum": "AF99EF",
    "salmon": "FA8072",
    "white": "FFFFFF",
    "orange": "FF7700",
}

WHITE = COLOR_BY_NAME["white"]
LOCATION_COLOR = COLOR_BY_NAME["green"]
OWN_PLAYER_COLOR = COLOR_BY_NAME["magenta"]
OTHER_PLAYER_COLOR = COLOR_BY_NAME["yellow"]
ENTRANCE_COLOR = COLOR_BY_NAME["blue"]


def item_color(flags: int) -> str:
    """The palette hex for an item's classification flags, matching the text
    client's precedence: progression, then useful, then trap, else filler."""
    if flags & 0b001:
        return COLOR_BY_NAME["plum"]
    if flags & 0b010:
        return COLOR_BY_NAME["slateblue"]
    if flags & 0b100:
        return COLOR_BY_NAME["salmon"]
    return COLOR_BY_NAME["cyan"]


# Hint-status colors by NetUtils.HintStatus value, matching the text client:
# found green, priority plum, avoid salmon, no-priority slateblue,
# unspecified white.
HINT_STATUS_COLOR_NAMES: dict[int, str] = {
    0: "white",
    10: "slateblue",
    20: "salmon",
    30: "plum",
    40: "green",
}


def hint_status_color(status: int) -> str:
    """The palette hex for a hint-status part; an unknown status reads red,
    as in the text client."""
    return COLOR_BY_NAME[HINT_STATUS_COLOR_NAMES.get(status, "red")]


def named_color(name: str) -> str:
    """The palette hex for a PrintJSON color name. Compound values like
    "bold;green" keep their first known color; unknown values read as white."""
    for part in (name or "").split(";"):
        if part in COLOR_BY_NAME:
            return COLOR_BY_NAME[part]
    return WHITE


def sanitize(text: str) -> str:
    """Printable ASCII only: the .sav codec writes ASCII FStrings, and the
    delimiters (tab, newline) must never appear inside a segment's text."""
    cleaned = "".join(ch if ch.isprintable() else " " for ch in text)
    return cleaned.encode("ascii", "replace").decode("ascii")


def encode_segments(segments: "list[tuple[str, str]]") -> str:
    """Tab-joined colored segments. Adjacent segments with the same color
    merge; segments whose text sanitizes away drop. Empty when nothing
    displayable remains."""
    merged: list[tuple[str, str]] = []
    for color, text in segments:
        text = sanitize(text)
        if not text:
            continue
        if merged and merged[-1][0] == color:
            merged[-1] = (color, merged[-1][1] + text)
        else:
            merged.append((color, text))
    return SEGMENT_SEPARATOR.join(f"{color}{text}" for color, text in merged)


def encode_entry(index: int, segments: "list[tuple[str, str]]") -> str:
    """One feed entry: the index, a colon, then the encoded segments."""
    return f"{index}:{encode_segments(segments)}"


def session_tag(seed_name: "str | None") -> str:
    """A fresh tag for one client session on one seed. The nonce makes a
    reconnect distinguishable, so the mod replays only the new session's feed."""
    nonce = uuid.uuid4().hex[:8]
    return f"{seed_name or 'unseeded'}-{nonce}"


def build(tag: str, entries: "list[str]") -> bytes:
    """Serialize the feed file, keeping only the newest MAX_ENTRIES entries."""
    return grants.build_object([
        ("SessionTag", tag),
        ("Messages", ENTRY_SEPARATOR.join(entries[-MAX_ENTRIES:])),
    ])


def write(path: Path, tag: str, entries: "list[str]") -> None:
    """Write the feed file atomically. Written fresh on every connect, even
    empty, so a stale file from another seed or session cannot linger."""
    grants.write_atomic(Path(path), build(tag, entries))
