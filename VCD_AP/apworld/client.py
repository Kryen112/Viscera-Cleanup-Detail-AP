"""Archipelago client for Viscera Cleanup Detail.

The mod and this client talk through two files in the game install (the mod cannot
open a socket). The mod writes its state to
``UDKGame\\Config\\UDKVCArchipelago.ini`` whenever it changes; this client polls
that file, maps the state it reports (cleanliness rungs, punch-out, speedrun) to
location checks, and sends them. In the other direction this client writes the
unlocked-level set to ``Saves\\VCArchipelagoGrants.sav``, which the mod reads to
gate levels, plus the spawn queue (traps.py), the toast feed (messages.py), the
remaining milestone percents (milestones.py), and the link-event queue for
DeathLink and TrapLink (links.py).

State the client recovers from the framework, never from memory: checked locations
(so reconnecting re-derives what to send) and received items (so the grants file is
rebuilt from the item list plus the seed's starting levels).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import Utils
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser,
                          gui_enabled, server_loop)
from NetUtils import ClientStatus

from . import (VCDWorld, grants, installer, links, messages, milestones,
               toolsanity, traps)
from .saves import SaveManager, seed_folder_name
from .collectibles import BOB_NOTE_MAP_BY_TOKEN, COLLECTIBLE_BY_TOKEN
from .items import (ITEM_NAME_TO_ID, access_item_name,
                    self_cleaning_mop_name, squeaky_boots_name)
from .levels import DISPLAY_BY_MAP, LEVELS
from .locations import (COLLECTIBLE_LOCATION_NAMES, DIGSITE_GATES_LOCATION,
                        FIND_BOB_LOCATION, LOCATION_NAME_TO_ID, bob_note_name,
                        collectible_name, employee_of_the_month_name,
                        milestone_name, punch_out_name, speedrun_name)

# Player-facing lines go to the "Client" logger, or they do not show in the client
# window.
client_logger = logging.getLogger("Client")

STATE_SECTION = "[vcarchipelago.vcarchipelagostate]"
POLL_SECONDS = 1.0

# Received-item id to internal map name, so a granted access item unlocks its level.
ACCESS_ID_TO_MAP: dict[int, str] = {
    ITEM_NAME_TO_ID[access_item_name(display)]: map_name
    for map_name, display, _title in LEVELS
}

# Received-item id to the queued spawn type token the mod switches on, for
# traps and useful supply drops alike.
QUEUE_ID_TO_TYPE: dict[int, str] = {
    ITEM_NAME_TO_ID[name]: queue_type
    for name, queue_type in traps.QUEUE_TYPE_BY_NAME.items()
}

# Trap type token back to the item name, for the TrapLink bounce a fired
# trap sends out.
TRAP_NAME_BY_TYPE: dict[str, str] = {
    queue_type: name for name, queue_type in traps.TRAP_TYPE_BY_NAME.items()
}


class LinkKind(NamedTuple):
    """One bounce link the player can flip while connected."""
    noun: str                       # "DeathLink"
    command: str                    # "/deathlink"
    slot_data_key: str              # "death_link"
    state_attribute: str            # "death_link_enabled"
    updater: str                    # the coroutine that moves the tag
    carries_into_links_file: bool   # the mod reads this link's flag


# The two links a player may flip mid-run. Neither is an item nor a location,
# so toggling one cannot change what the seed requires or make it unsolvable.
LINK_KINDS: dict[str, LinkKind] = {
    "death": LinkKind("DeathLink", "/deathlink", "death_link",
                      "death_link_enabled", "update_death_link", True),
    "trap": LinkKind("TrapLink", "/traplink", "trap_link",
                     "trap_link_enabled", "update_trap_link", False),
}

# Accepted on/off words for the link commands and /autoplay. "seed" drops a
# link override and a bare command flips the effective state, so neither
# needs a row here.
ON_OFF_ARGUMENTS: dict[str, bool] = {"on": True, "true": True, "1": True,
                                     "off": False, "false": False, "0": False}

# Received-item id to (internal map name, tool key), so a granted tool item
# unlocks its tool on its level through the grants file.
TOOL_ID_TO_MAP_KEY: dict[int, "tuple[str, str]"] = {
    ITEM_NAME_TO_ID[toolsanity.tool_item_name(display, key)]: (map_name, key)
    for map_name, display, _title in LEVELS
    for key in toolsanity.TOOL_KEY_ORDER
}

# Received-item id to internal map name for the Self-Cleaning Mop, so a
# granted mop unlock keeps its level's mop from dirtying.
CLEAN_MOP_ID_TO_MAP: dict[int, str] = {
    ITEM_NAME_TO_ID[self_cleaning_mop_name(display)]: map_name
    for map_name, display, _title in LEVELS
}

# Received-item id to internal map name for the Squeaky Clean Boots, so a
# granted boots unlock keeps its level's janitor from tracking bloody prints.
SQUEAKY_BOOTS_ID_TO_MAP: dict[int, str] = {
    ITEM_NAME_TO_ID[squeaky_boots_name(display)]: map_name
    for map_name, display, _title in LEVELS
}


def read_mod_state(install_dir: Path) -> dict[str, str]:
    """Parse the mod's state section from UDKVCArchipelago.ini. Returns an empty
    dict if the file is absent or the section is missing."""
    ini = install_dir / "UDKGame" / "Config" / "UDKVCArchipelago.ini"
    try:
        text = ini.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped.lower() == STATE_SECTION
            continue
        if in_section and "=" in stripped:
            key, _, value = stripped.partition("=")
            out[key.strip()] = value.strip()
    return out


def traps_applied_to_push(state: dict[str, str], seed_name: "str | None",
                          last_pushed: int) -> "int | None":
    """The mod's applied trap counter when it is worth pushing to server data
    storage: it belongs to the connected seed and exceeds what this client
    already pushed. None otherwise."""
    if not seed_name or state.get("APTrapSeed") != seed_name:
        return None
    applied = state.get("APTrapsApplied", "")
    if not applied.isdigit():
        return None
    if int(applied) <= last_pushed:
        return None
    return int(applied)


def death_count_to_bounce(state: dict[str, str], seed_name: "str | None",
                          last_seen: "int | None") -> "tuple[int, bool] | None":
    """The mod's organic death counter when it is comparable: (count, bounce),
    where bounce is False on the first same-seed sighting (the baseline adopts
    silently, so a reconnect never re-bounces an old death) and True on a
    rise. None when the state is another seed's or the counter did not move.
    A missing counter reads as 0, so the session's first death still rises."""
    if not state_is_current(state, seed_name):
        return None
    raw = state.get("APDeathCount", "")
    count = int(raw) if raw.isdigit() else 0
    if last_seen is None:
        return count, False
    if count <= last_seen:
        return None
    return count, True


def spawn_marker_to_bounce(state: dict[str, str], seed_name: "str | None",
                           last_seen: "str | None",
                           ) -> "tuple[str, str | None] | None":
    """The mod's last-applied spawn marker ("index:Type") when it is
    comparable: (marker, trap name to bounce), where the name is None on the
    first same-seed sighting (the baseline adopts silently) and on a non-trap
    spawn (a supply drop). None when the state is another seed's or the marker
    did not move. Only the item queue writes the marker, never the link
    queue, so an inbound linked trap can never bounce back out."""
    if not state_is_current(state, seed_name):
        return None
    marker = state.get("APLastSpawn", "")
    if last_seen is None:
        return marker, None
    if marker == last_seen or ":" not in marker:
        return None
    return marker, TRAP_NAME_BY_TYPE.get(marker.split(":", 1)[1])


def death_cause(slot_name: str, state: dict[str, str]) -> str:
    """The plain cause line the other players see for this janitor's death."""
    display = DISPLAY_BY_MAP.get(state.get("APMap", ""))
    if display:
        return f"{slot_name} died while cleaning {display}."
    return f"{slot_name} died on the job."


def parse_rungs(milestones: str) -> list[int]:
    """Turn the mod's "5,10,15" rung string into a list of ints."""
    rungs: list[int] = []
    for part in milestones.split(","):
        part = part.strip()
        if part.isdigit():
            rungs.append(int(part))
    return rungs


def trunk_find_names(trunk_finds: str) -> list[str]:
    """Location names for the mod's banked-trunk tokens. A token names either a
    collectible class or a Bob note archetype; both are unique game-wide and map
    to their home level's location no matter where they were banked (carrying a
    collectible onward always required its home level first). Unknown tokens are
    ignored."""
    names: list[str] = []
    for token in trunk_finds.split(","):
        token = token.strip()
        if token in COLLECTIBLE_BY_TOKEN:
            map_name, collectible = COLLECTIBLE_BY_TOKEN[token]
            names.append(collectible_name(DISPLAY_BY_MAP[map_name], collectible))
        elif token in BOB_NOTE_MAP_BY_TOKEN:
            names.append(bob_note_name(DISPLAY_BY_MAP[BOB_NOTE_MAP_BY_TOKEN[token]]))
    return names


def location_names_from_state(state: dict[str, str]) -> list[str]:
    """The location names a mod state snapshot implies. Policy lives here: each
    reported rung is a milestone (100 is Employee of the Month), a punch-out in
    good standing (not fired) is the Punch Out check, the speedrun flag is the
    Speedrun check, banked trunk tokens are collectible and Bob note checks, and
    the Digsite stat flags are the two Bob events. Unknown maps yield nothing."""
    display = DISPLAY_BY_MAP.get(state.get("APMap", ""))
    if not display:
        return []
    names: list[str] = []
    for rung in parse_rungs(state.get("APMilestones", "")):
        # Exactly 100 is Employee of the Month; rungs past it are their own
        # above_and_beyond milestones (rungs beyond the seed's ladder resolve
        # to nothing and drop out downstream).
        names.append(employee_of_the_month_name(display) if rung == 100
                     else milestone_name(display, rung))
    if state.get("APPunchedOut") == "1" and state.get("APFired") != "1":
        names.append(punch_out_name(display))
        if state.get("APSpeedrun") == "1":
            names.append(speedrun_name(display))
    names.extend(trunk_find_names(state.get("APTrunkFinds", "")))
    if state.get("APDigsiteGates") == "1":
        names.append(DIGSITE_GATES_LOCATION)
    if state.get("APFoundBob") == "1":
        names.append(FIND_BOB_LOCATION)
    return names


# PrintJSON types that toast for everyone: chat, joins and parts, goals,
# release and collect announcements, and the countdown. A packet with no type
# is a plain server notice (the console /send cheat text travels typeless).
AMBIENT_MESSAGE_TYPES = frozenset({
    None, "Chat", "ServerChat", "Join", "Part", "Goal", "Release", "Collect",
    "Countdown"})


def print_json_relevant(args: dict, slot_concerns_self, team: "int | None",
                        ) -> bool:
    """True when a PrintJSON packet belongs in the toast feed: an item
    transfer or hint involving this slot (an ItemCheat only from the own
    team), or an ambient line everyone sees. Command results and protocol
    bookkeeping stay in the client window."""
    message_type = args.get("type")
    if message_type in ("ItemSend", "ItemCheat", "Hint"):
        if message_type == "ItemCheat" and args.get("team") != team:
            return False
        item = args.get("item")
        return item is not None and (slot_concerns_self(args.get("receiving", -1))
                                     or slot_concerns_self(item.player))
    return message_type in AMBIENT_MESSAGE_TYPES


def message_segments(parts: "list[dict]", ctx: "VCDContext",
                     ) -> "list[tuple[str, str]]":
    """Colored (hex, text) segments for a PrintJSON part list, mirroring the
    text client's palette and name resolution."""
    segments: list[tuple[str, str]] = []
    for part in parts:
        part_type = part.get("type", "text")
        text = part.get("text", "")
        if part_type == "player_id":
            player = int(text)
            color = (messages.OWN_PLAYER_COLOR if ctx.slot_concerns_self(player)
                     else messages.OTHER_PLAYER_COLOR)
            segments.append((color, ctx.player_names[player]))
        elif part_type == "player_name":
            segments.append((messages.OTHER_PLAYER_COLOR, text))
        elif part_type == "item_id":
            name = ctx.item_names.lookup_in_slot(int(text), part.get("player"))
            segments.append((messages.item_color(int(part.get("flags", 0))), name))
        elif part_type == "item_name":
            segments.append((messages.item_color(int(part.get("flags", 0))), text))
        elif part_type == "location_id":
            name = ctx.location_names.lookup_in_slot(int(text), part.get("player"))
            segments.append((messages.LOCATION_COLOR, name))
        elif part_type == "location_name":
            segments.append((messages.LOCATION_COLOR, text))
        elif part_type == "entrance_name":
            segments.append((messages.ENTRANCE_COLOR, text))
        elif part_type == "hint_status":
            segments.append((messages.hint_status_color(
                part.get("hint_status", -1)), text))
        elif part_type == "color":
            segments.append((messages.named_color(part.get("color", "")), text))
        else:
            segments.append((messages.WHITE, text))
    return segments


def goal_locations_from_slot_data(slot_data: dict) -> "tuple[list[int], int]":
    """The location ids whose checks count toward the goal, and how many are
    needed. The level goal counts only the pooled levels. The collectible goal
    keeps the full list: collectible checks outside the pool never exist
    server-side, so they never arrive as checked."""
    goal = slot_data.get("goal", "complete_levels")
    amount = int(slot_data.get("goal_amount", len(LEVELS)))
    pooled_maps = slot_data.get("pooled_maps")
    pooled = set(m for m, _, _ in LEVELS) if pooled_maps is None else set(pooled_maps)
    pooled_displays = [d for m, d, _ in LEVELS if m in pooled]
    if goal == "find_bob":
        return [LOCATION_NAME_TO_ID[FIND_BOB_LOCATION]], 1
    if goal == "collect_collectibles":
        return [LOCATION_NAME_TO_ID[name]
                for name in COLLECTIBLE_LOCATION_NAMES], amount
    return [LOCATION_NAME_TO_ID[punch_out_name(d)]
            for d in pooled_displays], amount


def state_is_current(state: dict[str, str], seed_name: "str | None") -> bool:
    """Whether a state snapshot belongs to the connected seed. The mod stamps
    the state with the seed tag it reads from the traps file; a missing or
    foreign tag means the file is another seed's leftovers and must not send
    checks."""
    return bool(seed_name) and state.get("APSeedTag") == seed_name


# The mod publishes the starting score truncated to an int, so half a point
# of drift is expected; anything past a whole point means the level changed.
START_SCORE_TOLERANCE = 1.0


def start_score_mismatch(
        state: dict[str, str]) -> "tuple[str, float, float] | None":
    """A live starting cleanup score that disagrees with the shipped scan
    table: (map, live, expected), or None when consistent or not comparable.
    The logic tables are transcribed measurements, so a mismatch means the
    live level no longer matches what the logic was built on."""
    map_name = state.get("APMap", "")
    expected = toolsanity.scan_start_score(map_name)
    if expected is None:
        return None
    try:
        live = float(state.get("APStartScore", "0"))
    except ValueError:
        return None
    if live <= 0:
        return None
    if abs(live - expected) <= START_SCORE_TOLERANCE:
        return None
    return map_name, live, expected


def game_process_running() -> bool:
    """Whether any UDK.exe runs, including one the client did not launch."""
    if sys.platform != "win32":
        return False
    try:
        # A short timeout: this runs on the event loop, and tasklist answers in
        # well under a second when healthy.
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq UDK.exe", "/NH"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        # The callers guard destructive moves (a save swap, a package
        # overwrite), so an unanswerable check fails closed: assume running.
        return True
    return "UDK.exe" in result.stdout


def looks_like_install(path: Path) -> bool:
    """A folder counts as a Viscera install only if it holds the game exe. An
    unset UserFolderPath resolves to the Archipelago root, so a non-empty value is
    not enough on its own."""
    return (path / "Binaries" / "Win32" / "UDK.exe").is_file()


def auto_launch_setting() -> bool:
    """The auto_launch_game host.yaml setting."""
    return bool(VCDWorld.settings.auto_launch_game)


class VCDCommandProcessor(ClientCommandProcessor):
    def _cmd_install(self, path: str = "") -> None:
        """Choose the Viscera install folder (the one holding Binaries and UDKGame)
        and save it to host.yaml. With no argument, opens a folder picker. Typing a
        path is discouraged: the command parser eats backslashes."""
        chosen = path if path and Path(path).is_dir() else Utils.open_directory(
            "Select the Viscera install folder (holds Binaries and UDKGame)",
            suggest=str(self.ctx.install_dir or ""))
        if not chosen:
            self.output("No folder selected.")
            return
        if not looks_like_install(Path(chosen)):
            self.output("That folder has no Binaries\\Win32\\UDK.exe. Pick the Viscera "
                        "install root (it holds Binaries and UDKGame).")
            return
        self.ctx.set_install_dir(chosen)
        self.output(f"Install folder set to {self.ctx.install_dir} (saved to host.yaml).")

    def _cmd_play(self) -> None:
        """Launch the game, or relaunch it to resume after quitting."""
        self.ctx.launch_game()

    def _cmd_autoplay(self, state: str = "") -> None:
        """Turn auto-launch on or off for this client session, overriding the
        auto_launch_game setting. Usage: /autoplay [on | off]. Bare /autoplay
        flips it. Applies to your next connect; /play starts the game now."""
        argument = state.strip().lower()
        if argument in ON_OFF_ARGUMENTS:
            self.ctx.auto_launch_override = ON_OFF_ARGUMENTS[argument]
        elif argument == "":
            self.ctx.auto_launch_override = not self.ctx.auto_launch_wanted()
        else:
            self.output("Usage: /autoplay [on | off]. Bare /autoplay flips it.")
            return
        if self.ctx.auto_launch_wanted():
            self.output("Auto-launch is on: the game starts when you connect (/play "
                        "starts it now). Resets when the client restarts.")
        else:
            self.output("Auto-launch is off: the game stays closed when you connect "
                        "(/play starts it). Resets when the client restarts. Set "
                        "auto_launch_game in host.yaml to make it permanent.")

    def _cmd_restore(self) -> None:
        """Restore your career saves, undoing Archipelago save isolation. Close the
        game first."""
        self.ctx.restore_saves()

    def _cmd_installmod(self) -> None:
        """Install (or update) the precompiled VCArchipelago game mod into the
        install folder. Close the game first."""
        asyncio.create_task(self.ctx.install_mod())

    def _cmd_uninstall(self) -> None:
        """Remove the mod and all its wiring from the install folder and restore
        your career saves. Close the game first. Connecting to a room installs
        the mod again while auto-install is on (the default)."""
        self.ctx.uninstall_mod()

    def _set_link(self, kind: str, state: str) -> None:
        """Shared body of the two link commands: resolve the argument to an
        override, re-apply the tag, and report what the seed rolled once slot
        data has arrived."""
        link_kind = LINK_KINDS[kind]
        argument = state.strip().lower()
        if argument in ON_OFF_ARGUMENTS:
            self.ctx.link_overrides[kind] = ON_OFF_ARGUMENTS[argument]
        elif argument == "seed":
            self.ctx.link_overrides[kind] = None
        elif argument == "":
            self.ctx.link_overrides[kind] = not self.ctx.link_wanted(kind)
        else:
            self.output(f"Usage: {link_kind.command} [on | off | seed]. "
                        f"Bare {link_kind.command} flips it.")
            return
        wanted = self.ctx.link_wanted(kind)
        self.ctx.apply_link_state(kind, wanted)
        word = "on" if wanted else "off"
        if not self.ctx.link_seed_known:
            # Not connected yet, so what the seed rolled is still unknown.
            if self.ctx.link_overrides[kind] is None:
                self.output(f"{link_kind.noun} follows whatever the seed "
                            f"rolls.")
            else:
                self.output(f"{link_kind.noun} is now {word}, whatever the "
                            f"seed rolls.")
        elif self.ctx.link_overrides[kind] is None:
            self.output(f"{link_kind.noun} follows the seed again: {word}.")
        else:
            seed_word = "on" if self.ctx.link_seed_state[kind] else "off"
            self.output(f"{link_kind.noun} is now {word} (the seed rolled "
                        f"{seed_word}). Survives a reconnect. Resets when the "
                        f"client restarts.")

    def _cmd_deathlink(self, state: str = "") -> None:
        """Turn DeathLink on or off mid-run, overriding what the seed rolled.
        Usage: /deathlink [on | off | seed]. Bare /deathlink flips it and
        'seed' drops the override. While it is on, any death takes the whole
        crew down."""
        self._set_link("death", state)

    def _cmd_traplink(self, state: str = "") -> None:
        """Turn TrapLink on or off mid-run, overriding what the seed rolled.
        Usage: /traplink [on | off | seed]. Bare /traplink flips it and 'seed'
        drops the override. Turning it off stops both the traps you send and
        the ones you receive."""
        self._set_link("trap", state)


class VCDContext(CommonContext):
    game = "Viscera Cleanup Detail"
    # Receive remote items, our own items, and starting inventory.
    items_handling = 0b111
    command_processor = VCDCommandProcessor

    def __init__(self, server_address: "str | None", password: "str | None") -> None:
        super().__init__(server_address, password)
        self.install_dir: "Path | None" = None
        self.unlocked_maps: set[str] = set()
        # Toolsanity: whether the seed locks tools, each level's free starting
        # pair source, and the tool keys unlocked so far per map.
        self.toolsanity: bool = False
        self.hard_start_maps: set[str] = set()
        self.pooled_maps: list[str] = []
        self.unlocked_tools: "dict[str, set[str]]" = {}
        # Maps where the janitor holds the Self-Cleaning Mop unlock.
        self.clean_mop_maps: set[str] = set()
        # Maps where the janitor holds the Squeaky Clean Boots unlock.
        self.squeaky_boots_maps: set[str] = set()
        # Whether the mod keeps the punch-out report filled for the janitor.
        self.auto_fill_punchout_report: bool = False
        self.last_grants_written: "str | None" = None
        self.last_traps_written: "str | None" = None
        # The slot's baseline and applied counter from server data storage.
        # The baseline is written once at the slot's first-ever connect (the
        # items held then predate every session, so entries at or below it
        # never apply and a connect cannot dump a backlog); the server owns it
        # from then on, so no packet-order inference is ever needed. Both are
        # None until the connect-time Get answers; the traps file is not
        # written before then, so a too-low baseline can never reach the mod.
        # The applied counter only ever rises (the server folds writes with
        # max), so a new co-op host skips everything another host already
        # applied and a reconnect never truncates an in-flight burst.
        self.storage_traps_baseline: "int | None" = None
        self.storage_traps_applied: "int | None" = None
        # Maps already warned about a stale-looking scan constant, so the
        # tripwire fires once per level per connect, not once per poll.
        self.start_score_warned: set[str] = set()
        self.last_traps_pushed: int = 0
        # The toast feed the mod's HUD shows in game. The tag rotates per
        # connect, so the mod replays only this session's unseen entries.
        self.message_tag: "str | None" = None
        self.message_index: int = 0
        self.message_entries: list[str] = []
        self.last_messages_written: "str | None" = None
        self.last_milestones_written: "str | None" = None
        # DeathLink and TrapLink: whether the slot plays with each (from slot
        # data), the link-event queue the mod applies (inbound deaths and
        # linked traps; its tag rotates per connect like the toast feed's),
        # and the last mod-published death count and spawn marker seen. The
        # last-seen pair stays None until the first same-seed sighting adopts
        # it as the baseline, so a connect never re-bounces old state.
        self.death_link_enabled: bool = False
        self.trap_link_enabled: bool = False
        # A link the player flipped by command, per kind: None follows the
        # seed. Set outside the connect path on purpose, so an override
        # survives a reconnect. A client only ever talks to the one seed it
        # first latched, so restarting it is what hands the links back.
        self.link_overrides: dict[str, "bool | None"] = {
            kind: None for kind in LINK_KINDS}
        self.link_seed_state: dict[str, bool] = {
            kind: False for kind in LINK_KINDS}
        self.link_seed_known: bool = False
        self.link_tag: "str | None" = None
        self.link_index: int = 0
        self.link_entries: list[str] = []
        self.last_links_written: "str | None" = None
        self.last_death_count: "int | None" = None
        self.last_spawn_marker: "str | None" = None
        self.goal_location_ids: list[int] = []
        self.goal_need: int = 0
        self.last_seq: "str | None" = None
        # /autoplay override for this client session. None follows the
        # auto_launch_game setting; True or False beats it on every connect.
        self.auto_launch_override: "bool | None" = None
        # Armed by connect() and the startup connect, consumed by the next
        # Connected's launch step, so only a connection the player asked for
        # launches the game. The framework's automatic reconnect never arms it.
        self.player_connect_pending: bool = False
        self.saves_ready: bool = False
        self.game_process: "subprocess.Popen | None" = None

        folder = str(VCDWorld.settings.install_folder)
        if folder and looks_like_install(Path(folder)):
            self.install_dir = Path(folder)
        self.save_manager: "SaveManager | None" = (
            SaveManager(self.install_dir) if self.install_dir else None)
        if self.save_manager and self.save_manager.is_isolated():
            client_logger.info(
                f"Save isolation is active (seed '{self.save_manager.active_seed()}'). "
                "Your career saves are stashed; use /restore to bring them back.")

    def set_install_dir(self, path: str) -> None:
        self.install_dir = Path(path)
        self.save_manager = SaveManager(self.install_dir)
        self._save_install_folder(str(self.install_dir))
        # A newly set directory may already have a grants file to reconcile.
        self.last_grants_written = None
        self.write_grants_if_changed()

    def _save_install_folder(self, path: str) -> None:
        """Persist the install folder to host.yaml, so the player picks it once."""
        try:
            import settings as ap_settings
            current = VCDWorld.settings.install_folder
            VCDWorld.settings.install_folder = type(current)(path)
            ap_settings.get_settings().save()
        except Exception as error:
            client_logger.warning(
                f"Could not save the install folder to host.yaml ({error}); set "
                "viscera_cleanup_detail_options -> install_folder there yourself.")

    async def setup_and_launch(self) -> None:
        """On connect: make sure an install folder is known (picker on first run),
        bring the installed mod up to date, isolate this seed's saves, then
        auto-launch the game when the player made this connection, the /autoplay
        override (else the auto_launch_game setting) asks for it, and no game is
        up yet."""
        # Consume the arm before the first await, so a Connected the player did
        # not ask for (the framework's automatic reconnect) never launches.
        player_asked = self.player_connect_pending
        self.player_connect_pending = False
        if not self.install_dir:
            if gui_enabled:
                await self.pick_install_dir()
            else:
                client_logger.warning(
                    "No install folder set. Use /install, or set "
                    "viscera_cleanup_detail_options -> install_folder in host.yaml.")
        if not self.install_dir:
            return
        if bool(VCDWorld.settings.auto_install_mod):
            await self.ensure_mod_current()
        self._isolate_saves()
        self.saves_ready = True
        self.write_grants_if_changed()
        self.write_traps_if_changed()
        self.write_messages_if_changed()
        self.write_milestones_if_changed()
        self.write_links_if_changed()
        if not player_asked or not self.auto_launch_wanted():
            return
        # A running game never gets a duplicate, whether this client launched
        # it or the player did.
        if await self.game_is_up():
            client_logger.info(
                "Not auto-launching: Viscera Cleanup Detail looks to be running "
                "already. If it is not, type /play.")
            return
        self.launch_game()

    def _isolate_saves(self) -> None:
        """Swap in this seed's own save set, unless disabled. Skipped if the game is
        already running, so saves are never swapped under a live game."""
        if not (self.save_manager and bool(VCDWorld.settings.isolate_saves)):
            return
        if not self.seed_name:
            return
        already_on_seed = (
            self.save_manager.is_isolated()
            and self.save_manager.active_seed() == seed_folder_name(self.seed_name))
        if self.game_running() and not already_on_seed:
            client_logger.warning(
                "The game is already running, so save isolation was skipped. Close "
                "the game and reconnect to isolate this seed's saves.")
            return
        try:
            client_logger.info(self.save_manager.isolate(self.seed_name))
        except Exception as error:
            client_logger.error(
                f"Save isolation failed ({error}); using the current saves as-is.")

    async def pick_install_dir(self) -> None:
        """Open a folder picker off the event loop and save the choice."""
        loop = asyncio.get_event_loop()
        chosen = await loop.run_in_executor(
            None, Utils.open_directory,
            "Select the Viscera install folder (holds Binaries and UDKGame)")
        if not chosen:
            client_logger.warning(
                "No install folder chosen. Use /install to try again, or set "
                "viscera_cleanup_detail_options -> install_folder in host.yaml.")
            return
        if not looks_like_install(Path(chosen)):
            client_logger.warning(
                f"'{chosen}' has no Binaries\\Win32\\UDK.exe, so it is not a Viscera "
                "install folder. Not saved; use /install to try again.")
            return
        self.set_install_dir(chosen)
        client_logger.info(f"Install folder set to {self.install_dir} (saved to host.yaml).")

    def launch_game(self) -> None:
        if not self.install_dir:
            client_logger.warning("No install folder set. Use /install first.")
            return
        exe = self.install_dir / "Binaries" / "Win32" / "UDK.exe"
        if not exe.is_file():
            client_logger.error(f"UDK.exe not found at {exe}.")
            return
        try:
            self.game_process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
        except OSError as error:
            client_logger.error(f"Could not launch the game: {error}")
            return
        client_logger.info("Launched Viscera Cleanup Detail.")

    def auto_launch_wanted(self) -> bool:
        """Whether a connect launches the game: the /autoplay override when
        set, else the auto_launch_game setting."""
        if self.auto_launch_override is not None:
            return self.auto_launch_override
        return auto_launch_setting()

    def game_running(self) -> bool:
        # The client-launched process is authoritative, but a game the player
        # started themselves must count too: swapping saves or replacing the
        # mod package under a live game corrupts state.
        if self.game_process is not None and self.game_process.poll() is None:
            return True
        return game_process_running()

    async def game_is_up(self) -> bool:
        """game_running() for the connect path: the process probe shells out to
        tasklist, so it runs off the event loop instead of stalling it."""
        return await asyncio.get_event_loop().run_in_executor(None, self.game_running)

    async def install_mod(self) -> None:
        """Copy the precompiled mod package into the install and wire it up (via
        /installmod and the connect check). Nothing compiles: every player runs
        the same package bytes, so the package GUID matches across installs and
        co-op joins work."""
        if not self.install_dir:
            client_logger.warning("No install folder set. Use /install first.")
            return
        if await self.game_is_up():
            client_logger.warning(
                "The game is running. Close it first, then run /installmod.")
            return
        try:
            for line in installer.deploy(self.install_dir):
                client_logger.info(line)
        except (OSError, ValueError) as error:
            client_logger.error(f"Mod install failed: {error}")
            return
        client_logger.info("Mod installed. Relaunch the game to load it.")

    async def ensure_mod_current(self) -> None:
        """Install the packaged mod when the install carries a different one (on
        connect, before the game launches). Quiet when nothing changed. A failed
        check only warns: the rest of the connect setup must still run."""
        try:
            current = installer.mod_is_current(self.install_dir)
        except Exception as error:
            client_logger.warning(f"Could not check the installed mod: {error}")
            return
        if current:
            return
        if await self.game_is_up():
            client_logger.warning(
                "This apworld carries a different mod than the install, but the "
                "game is running. Close it and run /installmod, then relaunch.")
            return
        client_logger.info(
            "This apworld carries a different mod than the install; updating it.")
        await self.install_mod()

    def uninstall_mod(self) -> None:
        """Take the mod and every config edit back out of the install and bring
        the career saves home (manual, via /uninstall). Steam's verify and
        uninstall leave the mod's files behind, so this is the removal path."""
        if not self.install_dir:
            client_logger.warning("No install folder set. Use /install first.")
            return
        if self.game_running():
            client_logger.warning(
                "The game is running. Close it first, then run /uninstall.")
            return
        # Stops the data channel writers first, so a still-open connection can
        # never write into the restored career saves or recreate a removed
        # file, whether or not a later step fails.
        self.saves_ready = False
        if self.save_manager and self.save_manager.is_isolated():
            try:
                client_logger.info(self.save_manager.restore())
            except Exception as error:
                client_logger.error(
                    f"Could not restore your career saves ({error}); uninstall "
                    "stopped before touching the mod. Run /uninstall again once "
                    "that is resolved.")
                return
        try:
            removal_log = installer.remove(self.install_dir)
        except (OSError, ValueError) as error:
            client_logger.error(f"Mod removal failed: {error}")
            return
        for line in removal_log:
            client_logger.info(line)
        if not removal_log:
            client_logger.info("No mod files found; the install was already clean.")
        if self.save_manager:
            try:
                note = self.save_manager.discard_isolation_state()
            except OSError as error:
                note = f"Could not tidy the save isolation bookkeeping: {error}"
            if note:
                client_logger.info(note)
        client_logger.info(
            "Mod uninstalled; the install is back to stock. Connecting to an "
            "Archipelago room installs it again while auto_install_mod is on "
            "in host.yaml (the default).")

    def restore_saves(self) -> None:
        """Move the career saves back and stop isolating (manual, via /restore)."""
        if not self.save_manager:
            client_logger.warning("No install folder set.")
            return
        if self.game_running():
            client_logger.warning(
                "The game is still running. Close it first, then run /restore.")
            return
        try:
            client_logger.info(self.save_manager.restore())
            self.saves_ready = False
        except Exception as error:
            client_logger.error(f"Could not restore your career saves: {error}")

    async def shutdown(self) -> None:
        # Manual-only restore, but also on a clean client close if the game is not
        # running (never swap saves under a live game).
        if self.save_manager and self.save_manager.is_isolated():
            if self.game_running():
                client_logger.warning(
                    "Career saves are still stashed (the game is running). Close it, "
                    "relaunch the client, and run /restore to get them back.")
            else:
                try:
                    client_logger.info(self.save_manager.restore())
                except Exception as error:
                    client_logger.error(
                        f"Could not restore career saves on exit: {error}")
        await super().shutdown()

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "RoomInfo":
            # The framework only compares seed_name, it never sets it; save
            # isolation and the trap queue both key on it. Set it only while
            # unset, mirroring the framework's own mismatch guard, so a
            # rejected foreign-server connect cannot adopt the wrong seed.
            if not self.seed_name:
                self.seed_name = args.get("seed_name")
        elif cmd == "Connected":
            self._on_connected(args.get("slot_data", {}))
            # The connect packet carries the server's checked set, so a goal
            # reached before a disconnect or client restart resolves here.
            asyncio.create_task(self.maybe_send_goal())
        elif cmd == "Retrieved":
            keys = args.get("keys", {})
            applied_key = self.traps_applied_storage_key()
            if applied_key in keys:
                self._fold_storage_traps_applied(keys[applied_key])
            baseline_key = self.traps_baseline_storage_key()
            if baseline_key in keys:
                self._resolve_storage_baseline(keys[baseline_key])
        elif cmd == "SetReply":
            if args.get("key") == self.traps_applied_storage_key():
                self._fold_storage_traps_applied(args.get("value"))
            elif args.get("key") == self.traps_baseline_storage_key():
                self._adopt_storage_baseline(args.get("value"))
        elif cmd == "RoomUpdate":
            # The framework has already folded the packet's checked locations
            # into the sets, so this write and the goal count both carry the
            # server-confirmed view. The goal check must run here: the send in
            # apply_mod_state races this confirmation, and a punch-out is the
            # level's last state bump, so no later poll retries it.
            self.write_milestones_if_changed()
            asyncio.create_task(self.maybe_send_goal())
        elif cmd == "ReceivedItems":
            self._on_received_items(args)
        elif cmd == "Bounced":
            self._on_bounced(args)

    def _on_bounced(self, args: dict) -> None:
        """Inbound TrapLink bounces queue the closest local trap for the mod.
        DeathLink bounces ride the framework's on_deathlink hook instead. The
        live flag is checked alongside the tag because a mid-run disable sets
        the flag now and drops the tag a loop turn later, so the flag alone
        closes that window."""
        if not self.trap_link_enabled:
            return
        if "TrapLink" not in self.tags or "TrapLink" not in args.get("tags", []):
            return
        if not self.slot:
            return
        data = args.get("data", {})
        # A malformed bounce from a buggy foreign client must not raise inside
        # the packet handler and drop the connection.
        if not isinstance(data, dict):
            return
        source = str(data.get("source", ""))
        # The server bounces our own broadcast back; the source name filters it.
        if not source or source == self.player_names[self.slot]:
            return
        trap_name = str(data.get("trap_name", ""))
        local_type = links.local_trap_type(trap_name)
        if local_type is None:
            return
        local_name = TRAP_NAME_BY_TYPE[local_type]
        line = (f"TrapLink: received {trap_name} from {source}."
                if local_name == trap_name else
                f"TrapLink: received {trap_name} from {source} (as {local_name}).")
        client_logger.info(line)
        self.enqueue_message([(messages.named_color("salmon"), line)])
        self.enqueue_link(local_type)

    def _on_received_items(self, args: dict) -> None:
        """Folds granted level accesses and tool unlocks into the grants
        state, and advances the trap bookkeeping."""
        changed = False
        for item in args.get("items", []):
            map_name = ACCESS_ID_TO_MAP.get(item.item)
            if map_name and map_name not in self.unlocked_maps:
                self.unlocked_maps.add(map_name)
                changed = True
            tool = TOOL_ID_TO_MAP_KEY.get(item.item)
            if tool is not None:
                tool_map, tool_key = tool
                held = self.unlocked_tools.setdefault(tool_map, set())
                if tool_key not in held:
                    held.add(tool_key)
                    changed = True
            clean_mop_map = CLEAN_MOP_ID_TO_MAP.get(item.item)
            if clean_mop_map is not None and clean_mop_map not in self.clean_mop_maps:
                self.clean_mop_maps.add(clean_mop_map)
                changed = True
            boots_map = SQUEAKY_BOOTS_ID_TO_MAP.get(item.item)
            if boots_map is not None and boots_map not in self.squeaky_boots_maps:
                self.squeaky_boots_maps.add(boots_map)
                changed = True
        if changed:
            self.write_grants_if_changed()
        self.write_traps_if_changed()

    def _on_connected(self, slot_data: dict) -> None:
        """Resets the per-connect state from the slot data and kicks off the
        install setup and the data-storage subscription."""
        self.unlocked_maps = set(slot_data.get("started_maps", []))
        self.toolsanity = bool(slot_data.get("toolsanity", False))
        self.hard_start_maps = set(slot_data.get("hard_start_maps", []))
        self.pooled_maps = list(slot_data.get("pooled_maps", []))
        self.unlocked_tools = {}
        self.clean_mop_maps = set()
        self.squeaky_boots_maps = set()
        self._set_goal(slot_data)
        self.saves_ready = False
        # A stale sequence would make the reconnected bridge skip the mod's
        # re-emitted full state, losing any check that died with the old
        # socket; re-applying the same state is idempotent.
        self.last_seq = None
        # A fresh save set swaps in on connect, so every file writes fresh
        # even when its payload matches the previous session's.
        self.last_grants_written = None
        self.last_traps_written = None
        self.storage_traps_baseline = None
        self.storage_traps_applied = None
        self.last_traps_pushed = 0
        self.message_tag = messages.session_tag(self.seed_name)
        self.message_index = 0
        self.message_entries = []
        self.last_messages_written = None
        self.last_milestones_written = None
        self.start_score_warned = set()
        self.auto_fill_punchout_report = bool(
            slot_data.get("auto_fill_punchout_report", False))
        self.link_tag = messages.session_tag(self.seed_name)
        self.link_index = 0
        self.link_entries = []
        self.last_links_written = None
        self.last_death_count = None
        self.last_spawn_marker = None
        self.refresh_links(slot_data)
        self.enqueue_message([(messages.WHITE, "Archipelago connected.")])
        # Subscribe to the slot's shared baseline and applied counter and
        # fetch both; the Retrieved answer releases the traps-file write gate.
        keys = [self.traps_baseline_storage_key(),
                self.traps_applied_storage_key()]
        asyncio.create_task(self.send_msgs([
            {"cmd": "SetNotify", "keys": keys},
            {"cmd": "Get", "keys": keys},
        ]))
        asyncio.create_task(self.setup_and_launch())

    def refresh_links(self, slot_data: dict) -> None:
        """Apply both link tags for a connected slot. Runs on every connect, so
        a reconnect re-asserts them. An override beats slot data, so a
        reconnect keeps the player's choice instead of silently reverting to
        what the seed rolled. The framework refuses a connect whose seed name
        differs from the one already latched, so an override can only ever
        outlive its own seed by restarting the client."""
        self.link_seed_known = True
        for kind, link_kind in LINK_KINDS.items():
            self.link_seed_state[kind] = bool(
                slot_data.get(link_kind.slot_data_key, False))
            self.apply_link_state(kind, self.link_wanted(kind))

    def link_wanted(self, kind: str) -> bool:
        """Effective state of one link: the player's override when they have
        set one, else what the seed rolled."""
        override = self.link_overrides[kind]
        return self.link_seed_state[kind] if override is None else override

    def apply_link_state(self, kind: str, enabled: bool) -> None:
        """Register or drop one link's tag to match. Applied unconditionally,
        so a tag that ever drifted from its flag is repaired rather than left.
        Death link also carries into the links file, whose flag is what the mod
        sweeps the crew on."""
        link_kind = LINK_KINDS[kind]
        setattr(self, link_kind.state_attribute, enabled)
        asyncio.create_task(getattr(self, link_kind.updater)(enabled))
        if link_kind.carries_into_links_file:
            self.write_links_if_changed()

    async def update_trap_link(self, trap_link: bool) -> None:
        """Set the TrapLink connection tag on or off, mirroring the
        framework's own update_death_link."""
        old_tags = self.tags.copy()
        if trap_link:
            self.tags.add("TrapLink")
        else:
            self.tags -= {"TrapLink"}
        if old_tags != self.tags and self.server and not self.server.socket.closed:
            await self.send_msgs([{"cmd": "ConnectUpdate", "tags": self.tags}])

    def on_deathlink(self, data: dict) -> None:
        """An inbound death: the framework logs it; this queues the kill for
        the mod and toasts it in game."""
        super().on_deathlink(data)
        # The guard precedes the toast, so a death arriving in the turn between
        # a mid-run disable and the tag dropping never toasts with no kill
        # behind it.
        if not self.death_link_enabled:
            return
        source = str(data.get("source", "someone"))
        cause = str(data.get("cause", "") or "").strip()
        line = cause if cause else f"DeathLink: received from {source}."
        self.enqueue_message([(messages.named_color("red"), line)])
        self.enqueue_link(links.DEATH_TYPE)

    async def announce_death(self, state: dict[str, str]) -> None:
        """Send the janitor's own death out over DeathLink."""
        if not self.slot:
            return
        await self.send_death(death_cause(self.player_names[self.slot], state))
        self.enqueue_message([(messages.named_color("red"),
                               "DeathLink: sent to the other players.")])

    async def send_trap_link(self, trap_name: str) -> None:
        """Broadcast a fired trap to the other TrapLink players."""
        if not self.slot:
            return
        await self.send_msgs([{
            "cmd": "Bounce", "tags": ["TrapLink"],
            "data": {
                "time": time.time(),
                "source": self.player_names[self.slot],
                "trap_name": trap_name,
            },
        }])
        line = f"TrapLink: sent {trap_name} to the other players."
        client_logger.info(line)
        self.enqueue_message([(messages.named_color("salmon"), line)])

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        if not self.slot:
            return
        if not print_json_relevant(args, self.slot_concerns_self, self.team):
            return
        self.enqueue_message(message_segments(args.get("data", []), self))

    async def connect(self, address: "str | None" = None) -> None:
        """Every connection the player asks for (the Connect button, /connect)
        comes through here. The framework's automatic reconnect starts
        server_loop directly and skips it, so arming here is what keeps a
        reconnect the player did not ask for from launching the game."""
        self.player_connect_pending = True
        await super().connect(address)

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        # Skipped during shutdown: the game is closing and the save restore may
        # already have swapped the career saves back in.
        if self.slot and not self.exit_event.is_set():
            self.enqueue_message([(messages.WHITE, "Archipelago disconnected.")])
        await super().disconnect(allow_autoreconnect)

    def enqueue_message(self, segments: "list[tuple[str, str]]") -> None:
        """Append one toast line to the feed and flush it to the game. A line
        with no visible text after sanitizing is dropped, never queued blank."""
        if not self.message_tag:
            return
        if not any(messages.sanitize(text).strip() for _, text in segments):
            return
        self.message_index += 1
        self.message_entries.append(
            messages.encode_entry(self.message_index, segments))
        del self.message_entries[:-messages.MAX_ENTRIES]
        self.write_messages_if_changed()

    def write_messages_if_changed(self) -> None:
        """Write the toast feed (always fresh on connect, even empty, so a
        stale file from another seed or session is overwritten)."""
        if not self.install_dir or not self.saves_ready or not self.message_tag:
            return
        payload = f"{self.message_tag}|{self.message_index}|{len(self.message_entries)}"
        if payload == self.last_messages_written:
            return
        try:
            messages.write(self.install_dir / "Saves" / "VCArchipelagoMessages.sav",
                           self.message_tag, self.message_entries)
        except OSError as error:
            client_logger.error(f"Could not write the messages file: {error}")
            return
        self.last_messages_written = payload

    def enqueue_link(self, link_type: str) -> None:
        """Append one entry to the link-event queue (an inbound death or
        linked trap) and flush it to the game."""
        if not self.link_tag:
            return
        self.link_index += 1
        self.link_entries.append(f"{self.link_index}:{link_type}")
        del self.link_entries[:-links.MAX_ENTRIES]
        self.write_links_if_changed()

    def write_links_if_changed(self) -> None:
        """Write the link-event queue (always fresh on connect, even empty, so
        another session's leftovers are overwritten and the mod's death link
        flag is this connect's)."""
        if not self.install_dir or not self.saves_ready or not self.link_tag:
            return
        payload = (f"{self.link_tag}|{int(self.death_link_enabled)}"
                   f"|{self.link_index}|{len(self.link_entries)}")
        if payload == self.last_links_written:
            return
        try:
            links.write(self.install_dir / "Saves" / "VCArchipelagoLinks.sav",
                        self.link_tag, self.death_link_enabled,
                        self.link_entries)
        except OSError as error:
            client_logger.error(f"Could not write the links file: {error}")
            return
        self.last_links_written = payload

    def traps_applied_storage_key(self) -> str:
        # Data storage is room-scoped, so the seed never goes in the key.
        return f"vcd_traps_applied_{self.team}_{self.slot}"

    def traps_baseline_storage_key(self) -> str:
        return f"vcd_traps_baseline_{self.team}_{self.slot}"

    def _resolve_storage_baseline(self, value: object) -> None:
        """Answer the connect-time baseline read. An absent key means this is
        the slot's first-ever connect: everything held right now predates any
        session, so that count becomes the room's baseline, initialized
        through the server so it is written exactly once (the default only
        lands when the key is still absent; a concurrent connect converges
        through the SetReply)."""
        if value is not None:
            self._adopt_storage_baseline(value)
            return
        count = len(self.items_received)
        key = self.traps_baseline_storage_key()
        asyncio.create_task(self.send_msgs([{
            "cmd": "Set", "key": key, "default": count, "want_reply": True,
            "operations": [{"operation": "default", "value": 0}],
        }]))
        self._adopt_storage_baseline(count)

    def _adopt_storage_baseline(self, value: object) -> None:
        try:
            self.storage_traps_baseline = int(value or 0)
        except (TypeError, ValueError):
            self.storage_traps_baseline = 0
        self.write_traps_if_changed()

    def _fold_storage_traps_applied(self, value: object) -> None:
        """Fold a data-storage reading into the applied floor (a missing key
        reads as 0) and rewrite the traps file if the baseline rose."""
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            number = 0
        if self.storage_traps_applied is not None:
            number = max(number, self.storage_traps_applied)
        self.storage_traps_applied = number
        self.write_traps_if_changed()

    def _set_goal(self, slot_data: dict) -> None:
        self.goal_location_ids, self.goal_need = goal_locations_from_slot_data(
            slot_data)

    def unlocked_tools_string(self) -> str:
        """The toolsanity grants string: every pooled map, listing its free
        starting pair plus every tool item received for it, in the mod's key
        order. Empty when the seed does not lock tools, which the mod reads
        as everything unlocked."""
        if not self.toolsanity:
            return ""
        entries = []
        for map_name, _display, _title in LEVELS:
            if map_name not in self.pooled_maps:
                continue
            keys = set(toolsanity.free_keys(map_name, self.hard_start_maps))
            keys |= self.unlocked_tools.get(map_name, set())
            ordered_keys = [k for k in toolsanity.TOOL_KEY_ORDER if k in keys]
            entries.append(f"{map_name}:{' '.join(ordered_keys)}")
        return ",".join(entries)

    def present_tools_string(self) -> str:
        """The toolsanity present set: every pooled map with the tools the
        level has, in the mod's key order. Constant for the seed (it is the
        superset the HUD panel colors as locked or unlocked); empty when the
        seed does not lock tools."""
        if not self.toolsanity:
            return ""
        entries = []
        for map_name, _display, _title in LEVELS:
            if map_name not in self.pooled_maps:
                continue
            keys = toolsanity.tools_present(map_name)
            entries.append(f"{map_name}:{' '.join(keys)}")
        return ",".join(entries)

    def auto_fill_flag(self) -> str:
        """The punch-out auto fill as the grants file spells it: "1" for on,
        "0" for off. The dedupe payload uses the same spelling as the file."""
        return "1" if self.auto_fill_punchout_report else "0"

    def write_grants_if_changed(self) -> None:
        if not self.install_dir or not self.saves_ready:
            return
        ordered = [m for m, _, _ in LEVELS if m in self.unlocked_maps]
        tools_string = self.unlocked_tools_string()
        present_string = self.present_tools_string()
        clean_mop_ordered = [m for m, _, _ in LEVELS if m in self.clean_mop_maps]
        boots_ordered = [m for m, _, _ in LEVELS if m in self.squeaky_boots_maps]
        payload = ("|".join([",".join(ordered), tools_string, present_string,
                             ",".join(clean_mop_ordered),
                             ",".join(boots_ordered),
                             self.auto_fill_flag()]))
        if payload == self.last_grants_written:
            return
        try:
            grants.write(self.install_dir / "Saves" / "VCArchipelagoGrants.sav",
                         ordered, tools_string, present_string,
                         clean_mop_ordered, boots_ordered,
                         self.auto_fill_punchout_report)
        except OSError as error:
            client_logger.error(f"Could not write the grants file: {error}")
            return
        self.last_grants_written = payload

    def write_traps_if_changed(self) -> None:
        """Write the full trap queue (always on connect, even empty, so a stale
        file from another seed is overwritten). Held until the shared applied
        counter arrives from data storage, so a too-low baseline can never
        reach a mod that is already hosting a level."""
        if not self.install_dir or not self.saves_ready or not self.seed_name:
            return
        if self.storage_traps_applied is None or self.storage_traps_baseline is None:
            return
        seed_tag, baseline, queue = traps.queue_fields(
            self.seed_name, self.storage_traps_baseline,
            [item.item for item in self.items_received], QUEUE_ID_TO_TYPE,
            self.storage_traps_applied)
        payload = f"{seed_tag}|{baseline}|{queue}"
        if payload == self.last_traps_written:
            return
        try:
            traps.write(self.install_dir / "Saves" / "VCArchipelagoTraps.sav",
                        seed_tag, baseline, queue)
        except OSError as error:
            client_logger.error(f"Could not write the traps file: {error}")
            return
        self.last_traps_written = payload

    def write_milestones_if_changed(self) -> None:
        """Write the per-level remaining milestone percents (always on connect,
        even fully cleared, so a stale file from another seed is overwritten).
        Server-confirmed state only: the file is rebuilt from the missing set,
        so the in-game indicator never runs ahead of the server."""
        if not self.install_dir or not self.saves_ready or not self.seed_name:
            return
        encoded = milestones.encode_remaining(milestones.remaining_percents_by_map(
            self.missing_locations, self.server_locations))
        speedrun_maps = milestones.encode_speedrun_maps(
            milestones.speedrun_outstanding_maps(
                self.missing_locations, self.server_locations))
        payload = f"{self.seed_name}|{encoded}|{speedrun_maps}"
        if payload == self.last_milestones_written:
            return
        try:
            milestones.write(
                self.install_dir / "Saves" / "VCArchipelagoMilestones.sav",
                self.seed_name, encoded, speedrun_maps)
        except OSError as error:
            client_logger.error(f"Could not write the milestones file: {error}")
            return
        self.last_milestones_written = payload

    async def apply_mod_state(self, state: dict[str, str]) -> None:
        """Map the current level's reported state (rungs, punch-out, speedrun) to
        location checks and send the ones this seed actually has."""
        if not self.slot:
            return
        if not state_is_current(state, self.seed_name):
            return
        mismatch = start_score_mismatch(state)
        if mismatch is not None and mismatch[0] not in self.start_score_warned:
            self.start_score_warned.add(mismatch[0])
            client_logger.warning(
                "%s reports a starting cleanup score of %.0f, but the logic "
                "tables were measured at %.1f. The logic for this level may "
                "be stale; please report this.",
                mismatch[0], mismatch[1], mismatch[2])
        new_ids: list[int] = []
        for name in location_names_from_state(state):
            loc_id = LOCATION_NAME_TO_ID.get(name)
            if loc_id is not None and loc_id in self.missing_locations:
                new_ids.append(loc_id)
        if new_ids:
            await self.check_locations(new_ids)
        await self.maybe_send_goal()

    async def maybe_send_goal(self) -> None:
        if self.finished_game or not self.goal_location_ids:
            return
        reached = sum(1 for loc_id in self.goal_location_ids
                      if loc_id in self.checked_locations)
        if reached >= self.goal_need:
            # The flag flips before the await: a second task entering during
            # the send must not pass the guard and double-send. A send lost to
            # a dropped socket recovers via the framework, which re-announces
            # the goal on reconnect while the flag is set.
            self.finished_game = True
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            client_logger.info("Goal complete. The shift is over.")
            self.enqueue_message([
                (messages.LOCATION_COLOR, "Goal complete. The shift is over.")])

    def run_gui(self) -> None:
        from kvui import GameManager

        class VCDManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Viscera Cleanup Detail Client"

        self.ui = VCDManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


async def vcd_bridge_loop(ctx: VCDContext) -> None:
    """Poll the mod state file and act on each new APSeq."""
    while not ctx.exit_event.is_set():
        await asyncio.sleep(POLL_SECONDS)
        if not ctx.install_dir or not ctx.slot:
            continue
        state = read_mod_state(ctx.install_dir)
        # The applied trap counter is checked before the APSeq gate: the mod
        # saves it without bumping APSeq. The server-side max op is atomic, so
        # concurrent pushes from two clients can never regress the mark.
        push = traps_applied_to_push(state, ctx.seed_name, ctx.last_traps_pushed)
        if push is not None:
            ctx.last_traps_pushed = push
            await ctx.send_msgs([{
                "cmd": "Set", "key": ctx.traps_applied_storage_key(),
                "default": 0, "want_reply": False,
                "operations": [{"operation": "max", "value": push}],
            }])
        # The death counter and the spawn marker also save without an APSeq
        # bump. Each first same-seed sighting adopts silently as the baseline;
        # only a later move bounces, and only while the matching link is on.
        # Both gates read the live flag as well as the tag, because a mid-run
        # disable clears the flag now and drops the tag a loop turn later.
        death = death_count_to_bounce(state, ctx.seed_name, ctx.last_death_count)
        if death is not None:
            ctx.last_death_count = death[0]
            if death[1] and ctx.death_link_enabled and "DeathLink" in ctx.tags:
                await ctx.announce_death(state)
        spawn = spawn_marker_to_bounce(state, ctx.seed_name,
                                       ctx.last_spawn_marker)
        if spawn is not None:
            ctx.last_spawn_marker = spawn[0]
            if (spawn[1] is not None and ctx.trap_link_enabled
                    and "TrapLink" in ctx.tags):
                await ctx.send_trap_link(spawn[1])
        # A write that failed (a transient share violation) or is still held
        # (the storage read not answered) retries here: each writer no-ops
        # when its last write already carries the current payload.
        ctx.write_grants_if_changed()
        ctx.write_traps_if_changed()
        ctx.write_messages_if_changed()
        ctx.write_milestones_if_changed()
        ctx.write_links_if_changed()
        seq = state.get("APSeq")
        if not seq or seq == ctx.last_seq:
            continue
        ctx.last_seq = seq
        await ctx.apply_mod_state(state)


def parse_launch_args(launch_args: Sequence[str]) -> argparse.Namespace:
    # Parses only the args the component forwards, never sys.argv: a spawned
    # client inherits the launcher's argv, which holds the component name.
    parser = get_base_parser()
    parser.add_argument("--install", default=None,
                        help="Path to the Viscera install directory.")
    return parser.parse_args(launch_args)


def launch(*launch_args: str) -> None:
    Utils.init_logging("VCDClient", exception_logger="Client")

    async def main() -> None:
        args = parse_launch_args(launch_args)

        ctx = VCDContext(args.connect, args.password)
        if args.install:
            ctx.set_install_dir(args.install)
        # A startup connect is the player's own (they opened the client with a
        # room to join), so it arms the launch like the Connect button does.
        if args.connect:
            ctx.player_connect_pending = True
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        bridge_task = asyncio.create_task(vcd_bridge_loop(ctx), name="VCDBridge")

        await ctx.exit_event.wait()
        bridge_task.cancel()
        await ctx.shutdown()

    import colorama
    colorama.init()
    asyncio.run(main())
    colorama.deinit()


if __name__ == "__main__":
    launch(*sys.argv[1:])
