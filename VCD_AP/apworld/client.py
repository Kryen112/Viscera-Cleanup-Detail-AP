"""Archipelago client for Viscera Cleanup Detail.

The mod and this client talk through two files in the game install (the mod cannot
open a socket). The mod writes its state to
``UDKGame\\Config\\UDKVCArchipelago.ini`` whenever it changes; this client polls
that file, maps the state it reports (cleanliness rungs, punch-out, speedrun) to
location checks, and sends them. In the other direction this client writes the
unlocked-level set to ``Saves\\VCArchipelagoGrants.sav``, which the mod reads to
gate levels.

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

from . import VCDWorld, grants, installer, traps
from .saves import SaveManager, seed_folder_name
from .collectibles import BOB_NOTE_MAP_BY_TOKEN, COLLECTIBLE_BY_TOKEN
from .items import ITEM_NAME_TO_ID, access_item_name
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

# Received-item id to the trap type token the mod switches on.
TRAP_ID_TO_TYPE: dict[int, str] = {
    ITEM_NAME_TO_ID[name]: trap_type
    for name, trap_type in traps.TRAP_TYPE_BY_NAME.items()
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
        """Install (or update) the VCArchipelago game mod into the install folder
        and compile it. Close the game first."""
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
        self.last_grants_written: "str | None" = None
        self.last_traps_written: "str | None" = None
        # Items already held when this session connected; traps at or below
        # this index are never applied, so a connect cannot dump a backlog.
        self.trap_baseline: "int | None" = None
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
        if not self.game_launched and bool(VCDWorld.settings.auto_launch_game):
            self.launch_game()

    async def ensure_mod_current(self) -> None:
        """Install the packaged mod when the install carries a different one (on
        connect, before the game launches). Quiet when nothing changed."""
        try:
            current = installer.mod_is_current(self.install_dir)
        except OSError as error:
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
        # started themselves must count too: swapping saves or recompiling
        # under a live game corrupts state.
        if self.game_process is not None and self.game_process.poll() is None:
            return True
        return game_process_running()

    async def install_mod(self) -> None:
        """Deploy the packaged mod source into the install and compile it (via
        /installmod). The compile blocks for up to two minutes, so it runs off
        the event loop."""
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
            client_logger.error(f"Mod deploy failed: {error}")
            return
        client_logger.info("Compiling the mod (up to two minutes)...")
        loop = asyncio.get_event_loop()
        ok, message = await loop.run_in_executor(
            None, installer.compile_mod, self.install_dir)
        (client_logger.info if ok else client_logger.error)(message)

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
            slot_data = args.get("slot_data", {})
            self.unlocked_maps = set(slot_data.get("started_maps", []))
            self._set_goal(slot_data)
            self.saves_ready = False
            self.trap_baseline = None
            self.last_traps_written = None
            asyncio.create_task(self.setup_and_launch())
        elif cmd == "ReceivedItems":
            # The first packet after connect (index 0) is the full resync list:
            # everything in it predates this session, so it sets the trap baseline.
            if self.trap_baseline is None and int(args.get("index", 0)) == 0:
                self.trap_baseline = len(args.get("items", []))
            changed = False
            for item in args.get("items", []):
                map_name = ACCESS_ID_TO_MAP.get(item.item)
                if map_name and map_name not in self.unlocked_maps:
                    self.unlocked_maps.add(map_name)
                    changed = True
            if changed:
                self.write_grants_if_changed()
            self.write_traps_if_changed()

    def _set_goal(self, slot_data: dict) -> None:
        self.goal_location_ids, self.goal_need = goal_locations_from_slot_data(
            slot_data)

    def write_grants_if_changed(self) -> None:
        if not self.install_dir or not self.saves_ready:
            return
        ordered = [m for m, _, _ in LEVELS if m in self.unlocked_maps]
        joined = ",".join(ordered)
        if joined == self.last_grants_written:
            return
        try:
            grants.write(self.install_dir / "Saves" / "VCArchipelagoGrants.sav", ordered)
        except OSError as error:
            client_logger.error(f"Could not write the grants file: {error}")
            return
        self.last_grants_written = joined

    def write_traps_if_changed(self) -> None:
        """Write the full trap queue (always on connect, even empty, so a stale
        file from another seed is overwritten)."""
        if not self.install_dir or not self.saves_ready or not self.seed_name:
            return
        seed_tag, baseline, queue = traps.queue_fields(
            self.seed_name, self.trap_baseline,
            [item.item for item in self.items_received], TRAP_ID_TO_TYPE)
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
