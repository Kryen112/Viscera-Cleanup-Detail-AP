"""Archipelago client for Viscera Cleanup Detail.

The mod and this client talk through two files in the game install (the mod cannot
open a socket). The mod writes its state to
``UDKGame\\Config\\UDKVCArchipelago.ini`` whenever it changes; this client polls
that file, maps the state it reports (cleanliness rungs, punch-out, speedrun) to
location checks, and sends them. In the other direction this client writes the
unlocked-level set to ``Saves\\VCArchipelagoGrants.sav``, which the mod reads to
gate levels, plus the spawn queue (traps.py), the toast feed (messages.py), and
the remaining milestone percents (milestones.py).

State the client recovers from the framework, never from memory: checked locations
(so reconnecting re-derives what to send) and received items (so the grants file is
rebuilt from the item list plus the seed's starting levels).
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

import Utils
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser,
                          gui_enabled, server_loop)
from NetUtils import ClientStatus

from . import VCDWorld, grants, installer, messages, milestones, toolsanity, traps
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


def print_json_relevant(args: dict, slot_concerns_self, team: "int | None",
                        ) -> bool:
    """True when a PrintJSON packet is an item transfer involving this slot:
    an ItemSend (or same-team ItemCheat) this slot receives or sends."""
    if args.get("type") not in ("ItemSend", "ItemCheat"):
        return False
    if args.get("type") == "ItemCheat" and args.get("team") != team:
        return False
    item = args.get("item")
    return item is not None and (slot_concerns_self(args.get("receiving", -1))
                                 or slot_concerns_self(item.player))


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
        elif part_type == "color":
            segments.append((messages.named_color(part.get("color", "")), text))
        else:
            segments.append((messages.WHITE, text))
    return segments


def goal_locations_from_slot_data(slot_data: dict) -> "tuple[list[int], int]":
    """The location ids whose checks count toward the goal, and how many are
    needed. Level goals count only the pooled levels. The collectible goal
    keeps the full list: collectible checks outside the pool never exist
    server-side, so they never arrive as checked."""
    goal = slot_data.get("goal", "complete_levels")
    amount = int(slot_data.get("goal_amount", len(LEVELS)))
    pooled_maps = slot_data.get("pooled_maps")
    pooled = set(m for m, _, _ in LEVELS) if pooled_maps is None else set(pooled_maps)
    pooled_displays = [d for m, d, _ in LEVELS if m in pooled]
    if goal == "employee_of_the_month":
        return [LOCATION_NAME_TO_ID[employee_of_the_month_name(d)]
                for d in pooled_displays], amount
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
        return False
    return "UDK.exe" in result.stdout


def looks_like_install(path: Path) -> bool:
    """A folder counts as a Viscera install only if it holds the game exe. An
    unset UserFolderPath resolves to the Archipelago root, so a non-empty value is
    not enough on its own."""
    return (path / "Binaries" / "Win32" / "UDK.exe").is_file()


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

    def _cmd_restore(self) -> None:
        """Restore your career saves, undoing Archipelago save isolation. Close the
        game first."""
        self.ctx.restore_saves()

    def _cmd_installmod(self) -> None:
        """Install (or update) the precompiled VCArchipelago game mod into the
        install folder. Close the game first."""
        asyncio.create_task(self.ctx.install_mod())


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
        self.last_grants_written: "str | None" = None
        self.last_traps_written: "str | None" = None
        # Items already held when this session connected; traps at or below
        # this index are never applied, so a connect cannot dump a backlog.
        self.trap_baseline: "int | None" = None
        # The slot's shared applied counter from server data storage. None until
        # the connect-time Get answers; the traps file is not written before
        # then, so a too-low baseline can never reach the mod. The counter only
        # ever rises (the server folds writes with max), so a new co-op host
        # skips everything another host already applied.
        self.storage_traps_applied: "int | None" = None
        self.last_traps_pushed: int = 0
        # The toast feed the mod's HUD shows in game. The tag rotates per
        # connect, so the mod replays only this session's unseen entries.
        self.message_tag: "str | None" = None
        self.message_index: int = 0
        self.message_entries: list[str] = []
        self.last_messages_written: "str | None" = None
        self.last_milestones_written: "str | None" = None
        self.goal_location_ids: list[int] = []
        self.goal_need: int = 0
        self.last_seq: "str | None" = None
        self.game_launched: bool = False
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
        auto-launch the game if that setting is on."""
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
        if not self.game_launched and bool(VCDWorld.settings.auto_launch_game):
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
        self.game_launched = True
        client_logger.info("Launched Viscera Cleanup Detail.")

    def game_running(self) -> bool:
        # The client-launched process is authoritative, but a game the player
        # started themselves must count too: swapping saves or replacing the
        # mod package under a live game corrupts state.
        if self.game_process is not None and self.game_process.poll() is None:
            return True
        return game_process_running()

    async def install_mod(self) -> None:
        """Copy the precompiled mod package into the install and wire it up (via
        /installmod and the connect check). Nothing compiles: every player runs
        the same package bytes, so the package GUID matches across installs and
        co-op joins work."""
        if not self.install_dir:
            client_logger.warning("No install folder set. Use /install first.")
            return
        if self.game_running():
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
        if self.game_running():
            client_logger.warning(
                "This apworld carries a different mod than the install, but the "
                "game is running. Close it and run /installmod, then relaunch.")
            return
        client_logger.info(
            "This apworld carries a different mod than the install; updating it.")
        await self.install_mod()

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
        elif cmd == "Retrieved":
            keys = args.get("keys", {})
            storage_key = self.traps_applied_storage_key()
            if storage_key in keys:
                self._fold_storage_traps_applied(keys[storage_key])
        elif cmd == "SetReply":
            if args.get("key") == self.traps_applied_storage_key():
                self._fold_storage_traps_applied(args.get("value"))
        elif cmd == "RoomUpdate":
            # The framework has already folded the packet's checked locations
            # into the sets, so this write carries the server-confirmed view.
            self.write_milestones_if_changed()
        elif cmd == "ReceivedItems":
            self._on_received_items(args)

    def _on_received_items(self, args: dict) -> None:
        """Folds granted level accesses and tool unlocks into the grants
        state, and advances the trap bookkeeping."""
        # The first packet after connect (index 0) is the full resync list:
        # everything in it predates this session, so it sets the trap baseline.
        # A slot with no items gets no resync packet at all; the connect-time
        # storage answer then resolves the baseline to zero, so a live batch
        # arriving later at index 0 is never mistaken for the resync.
        if self.trap_baseline is None and int(args.get("index", 0)) == 0:
            self.trap_baseline = len(args.get("items", []))
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
        self.trap_baseline = None
        # A fresh save set swaps in on connect, so every file writes fresh
        # even when its payload matches the previous session's.
        self.last_grants_written = None
        self.last_traps_written = None
        self.storage_traps_applied = None
        self.last_traps_pushed = 0
        self.message_tag = messages.session_tag(self.seed_name)
        self.message_index = 0
        self.message_entries = []
        self.last_messages_written = None
        self.last_milestones_written = None
        self.enqueue_message([(messages.WHITE, "Archipelago connected.")])
        # Subscribe to the slot's shared applied counter and fetch it; the
        # Retrieved answer releases the traps-file write gate.
        key = self.traps_applied_storage_key()
        asyncio.create_task(self.send_msgs([
            {"cmd": "SetNotify", "keys": [key]},
            {"cmd": "Get", "keys": [key]},
        ]))
        asyncio.create_task(self.setup_and_launch())

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        if not self.slot:
            return
        if not print_json_relevant(args, self.slot_concerns_self, self.team):
            return
        self.enqueue_message(message_segments(args.get("data", []), self))

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

    def traps_applied_storage_key(self) -> str:
        # Data storage is room-scoped, so the seed never goes in the key.
        return f"vcd_traps_applied_{self.team}_{self.slot}"

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
        # The server answers the connect-time Get only after the resync
        # packet, so a baseline still unset here means the slot held no items
        # at connect and the server skipped the empty resync entirely.
        if self.trap_baseline is None:
            self.trap_baseline = 0
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
                             ",".join(boots_ordered)]))
        if payload == self.last_grants_written:
            return
        try:
            grants.write(self.install_dir / "Saves" / "VCArchipelagoGrants.sav",
                         ordered, tools_string, present_string,
                         clean_mop_ordered, boots_ordered)
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
        if self.storage_traps_applied is None:
            return
        seed_tag, baseline, queue = traps.queue_fields(
            self.seed_name, self.trap_baseline,
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
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.finished_game = True
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
        seq = state.get("APSeq")
        if not seq or seq == ctx.last_seq:
            continue
        ctx.last_seq = seq
        await ctx.apply_mod_state(state)


def launch() -> None:
    Utils.init_logging("VCDClient", exception_logger="Client")

    async def main() -> None:
        parser = get_base_parser()
        parser.add_argument("--install", default=None,
                            help="Path to the Viscera install directory.")
        args = parser.parse_args()

        ctx = VCDContext(args.connect, args.password)
        if args.install:
            ctx.set_install_dir(args.install)
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
    launch()
