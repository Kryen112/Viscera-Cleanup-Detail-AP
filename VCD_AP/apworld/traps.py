"""The spawn queue file the client writes and the mod reads. It carries every
received item with an in-level effect: traps and useful supply drops alike.

``Saves\\VCArchipelagoTraps.sav`` holds three string properties (see grants.py
for the byte layout):
- ``SeedTag``: the connected seed, so a stale file from another seed is never
  replayed.
- ``BaselineIndex``: how many items the player already held when this session
  connected, raised to the slot's shared applied counter from server data
  storage. Entries at or below the baseline are treated as already applied, so
  a fresh connect never dumps a backlog and a new co-op host never replays
  what another host already applied.
- ``TrapQueue``: the full ordered queue as ``index:Type`` entries, e.g.
  ``"3:MessDump,7:CleanBucket"``. Indexes are 1-based positions in the
  framework's received-item list, so the queue is rebuilt identically on every
  reconnect; the mod tracks the last index it applied and applies each new
  entry once.
"""
from __future__ import annotations

from pathlib import Path

from . import grants

# Item name to the type token the mod switches on.
TRAP_TYPE_BY_NAME: dict[str, str] = {
    "Mess Dump Trap": "MessDump",
    "Bucket Spill Trap": "BucketSpill",
    "Slowdown Trap": "Slowdown",
    "Speedup Trap": "Speedup",
    "Magnetize Trap": "Magnetize",
}
TRAP_NAMES: list[str] = list(TRAP_TYPE_BY_NAME)

# Helpful supply drops that ride the same queue as traps, with their own tokens.
USEFUL_TYPE_BY_NAME: dict[str, str] = {
    "Clean Water Bucket": "CleanBucket",
    "Empty Bin": "EmptyBin",
}
USEFUL_NAMES: list[str] = list(USEFUL_TYPE_BY_NAME)

# Every queued spawn type, trap and useful alike, for building the queue.
QUEUE_TYPE_BY_NAME: dict[str, str] = {**TRAP_TYPE_BY_NAME, **USEFUL_TYPE_BY_NAME}


def build_queue(received_item_ids: "list[int]", queue_id_to_type: "dict[int, str]",
                ) -> str:
    """The full spawn queue implied by the received-item list: one ``index:Type``
    entry per trap or useful item, 1-based, in receive order."""
    entries = [
        f"{position}:{queue_id_to_type[item_id]}"
        for position, item_id in enumerate(received_item_ids, start=1)
        if item_id in queue_id_to_type
    ]
    return ",".join(entries)


def queue_fields(seed_name: str, trap_baseline: "int | None",
                 received_item_ids: "list[int]",
                 queue_id_to_type: "dict[int, str]",
                 applied_floor: "int | None" = None) -> "tuple[str, int, str]":
    """The (seed tag, baseline, queue) triple the traps file carries. Before the
    resync packet fixes the baseline, every item known so far counts into it, so
    the queue and baseline written together are always consistent and a connect
    can never replay a backlog. ``applied_floor`` is the slot's shared applied
    counter from server data storage; folding it into the baseline keeps a new
    co-op host from replaying entries another host already applied."""
    baseline = (trap_baseline if trap_baseline is not None
                else len(received_item_ids))
    if applied_floor is not None:
        baseline = max(baseline, applied_floor)
    return seed_name, baseline, build_queue(received_item_ids, queue_id_to_type)


def write(path: Path, seed_tag: str, baseline_index: int, queue: str) -> None:
    """Write the traps file atomically. Always written on connect, even with an
    empty queue, so a stale file from another seed cannot linger."""
    grants.write_atomic(Path(path), grants.build_object([
        ("SeedTag", seed_tag),
        ("BaselineIndex", str(baseline_index)),
        ("TrapQueue", queue),
    ]))
