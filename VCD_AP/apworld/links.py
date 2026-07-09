"""The link-event queue file the client writes and the mod reads: deaths and
traps that arrive over the DeathLink and TrapLink bounce channels rather than
as received items, so they cannot ride the item-indexed trap queue.

``Saves\\VCArchipelagoLinks.sav`` holds three string properties (grants.py has
the byte layout):
- ``SessionTag``: the connected seed plus a per-connect nonce, like the toast
  feed's. The mod baselines its applied counter to the newest entry whenever
  the tag changes, so another session's leftovers never apply.
- ``DeathLinkOn``: "1" when the slot plays with death link, so the mod knows
  to take the whole crew down when any one janitor dies.
- ``Entries``: comma-joined ``index:Type`` entries with a 1-based index that
  only rises within a session. Type is a trap type token or ``Death``. The mod
  applies each entry at most once, only in a cleanable level, and consumes
  without effect (drops, never holds) anything that arrives anywhere else, so
  a stale death can never fire on a later level load.
"""
from __future__ import annotations

from pathlib import Path

from . import grants
from .traps import TRAP_TYPE_BY_NAME

# The queue type token for an inbound DeathLink death.
DEATH_TYPE = "Death"

# Entries kept in the file; the oldest fall off. Indexes keep rising, so the
# mod's applied counter stays valid across the drop.
MAX_ENTRIES = 100

# Inbound TrapLink matching: a linked trap lands as the local trap its name
# maps to, and a name absent here is ignored, per the TrapLink convention.
# Native names map to themselves so linked Viscera seeds exchange one to one;
# the rest are the community's common trap names mapped to the closest local
# effect. Outbound bounces always carry this game's native trap names.
LINKED_TRAP_TYPE_BY_NAME: dict[str, str] = {
    **TRAP_TYPE_BY_NAME,
    # Something dumped on or thrown at the player.
    "Thwimp Trap": "MessDump",
    "Police Trap": "MessDump",
    "Buyon Trap": "MessDump",
    "TNT Barrel Trap": "MessDump",
    "Gooey Bag": "MessDump",
    "Bomb": "MessDump",
    "Bomb Trap": "MessDump",
    "Bee Trap": "MessDump",
    "Paint Trap": "MessDump",
    # A slippery spill underfoot.
    "Banana Trap": "BucketSpill",
    "Spill Trap": "BucketSpill",
    # Movement slowed, stopped, or interrupted.
    "Ice Trap": "Slowdown",
    "Freeze Trap": "Slowdown",
    "Frozen Trap": "Slowdown",
    "Stun Trap": "Slowdown",
    "Paralyze Trap": "Slowdown",
    "Chaos Control Trap": "Slowdown",
    "Honey Trap": "Slowdown",
    "Slow Trap": "Slowdown",
    "Slowness Trap": "Slowdown",
    "Literature Trap": "Slowdown",
    "Exposition Trap": "Slowdown",
    "Cutscene Trap": "Slowdown",
    # Disorientation and scrambled movement.
    "Fuzzy Trap": "ZeroGravity",
    "Confuse Trap": "ZeroGravity",
    "Confusion Trap": "ZeroGravity",
    "Confound Trap": "ZeroGravity",
    "Reversal Trap": "ZeroGravity",
    "Reverse Trap": "ZeroGravity",
    "Reverse Controls Trap": "ZeroGravity",
    "Gravity Trap": "ZeroGravity",
    # Pulls and pushes.
    "Magnet Trap": "Magnetize",
}


def local_trap_type(trap_name: str) -> "str | None":
    """The local trap type token a linked trap name lands as, or None for a
    trap this game has no close equivalent for (ignored, never guessed)."""
    return LINKED_TRAP_TYPE_BY_NAME.get(trap_name)


def write(path: Path, session_tag: str, death_link_on: bool,
          entries: "list[str]") -> None:
    """Write the link-event file atomically. Always written on connect, even
    with no entries, so another session's leftovers cannot linger and the
    death link flag is always this connect's."""
    grants.write_atomic(Path(path), grants.build_object([
        ("SessionTag", session_tag),
        ("DeathLinkOn", "1" if death_link_on else "0"),
        ("Entries", ",".join(entries)),
    ]))
