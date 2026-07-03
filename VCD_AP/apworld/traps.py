"""The trap queue file the client writes and the mod reads.

``Saves\\VCArchipelagoTraps.sav`` holds three string properties (see grants.py
for the byte layout):
- ``SeedTag``: the connected seed, so a stale file from another seed is never
  replayed.
- ``BaselineIndex``: how many items the player already held when this session
  connected. Traps at or below the baseline are treated as already applied, so
  a fresh connect never dumps a backlog into the level.
- ``TrapQueue``: the full ordered queue as ``index:Type`` entries, e.g.
  ``"3:MessDump,7:Slowdown"``. Indexes are 1-based positions in the framework's
  received-item list, so the queue is rebuilt identically on every reconnect;
  the mod tracks the last index it applied and applies each new trap once.
"""
from __future__ import annotations

from pathlib import Path

from . import grants

# Item name to the type token the mod switches on.
TRAP_TYPE_BY_NAME: dict[str, str] = {
    "Mess Dump Trap": "MessDump",
    "Bucket Spill Trap": "BucketSpill",
    "Slowdown Trap": "Slowdown",
}
TRAP_NAMES: list[str] = list(TRAP_TYPE_BY_NAME)


def build_queue(received_item_ids: "list[int]", trap_id_to_type: "dict[int, str]",
                ) -> str:
    """The full trap queue implied by the received-item list: one ``index:Type``
    entry per trap item, 1-based, in receive order."""
    entries = [
        f"{position}:{trap_id_to_type[item_id]}"
        for position, item_id in enumerate(received_item_ids, start=1)
        if item_id in trap_id_to_type
    ]
    return ",".join(entries)


def queue_fields(seed_name: str, trap_baseline: "int | None",
                 received_item_ids: "list[int]",
                 trap_id_to_type: "dict[int, str]") -> "tuple[str, int, str]":
    """The (seed tag, baseline, queue) triple the traps file carries. Before the
    resync packet fixes the baseline, every item known so far counts into it, so
    the queue and baseline written together are always consistent and a connect
    can never replay a backlog."""
    baseline = (trap_baseline if trap_baseline is not None
                else len(received_item_ids))
    return seed_name, baseline, build_queue(received_item_ids, trap_id_to_type)


def write(path: Path, seed_tag: str, baseline_index: int, queue: str) -> None:
    """Write the traps file atomically. Always written on connect, even with an
    empty queue, so a stale file from another seed cannot linger."""
    grants.write_atomic(Path(path), grants.build_object([
        ("SeedTag", seed_tag),
        ("BaselineIndex", str(baseline_index)),
        ("TrapQueue", queue),
    ]))
