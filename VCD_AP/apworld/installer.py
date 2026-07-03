"""Installs the VCArchipelago mod into a game install, from the client.

The packaged apworld carries the mod source under ``data/mod`` (staged there by
build_apworld.py). ``deploy`` copies it into the install's ``Development\\Src``
tree, wires the package into the compile and load lists in DefaultEngine.ini
(the only stock file it edits, backed up first), registers the Archipelago mode
provider and the SaveConfig base as their own ini files, and wires the same
lines into the generated UDKEngine.ini in place. The generated inis carry the
player's saved settings (view bob, audio, and the rest), so they are edited,
never cleared. ``compile_mod`` then runs ``UDK.exe make`` and reads the verdict
from the fresh package file and Launch.log. Both are idempotent.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

MOD_PACKAGE = "VCArchipelago"
MOD_DATA_DIR = Path(__file__).parent / "data" / "mod" / MOD_PACKAGE / "Classes"
BACKUP_DIR_NAME = "_archipelago_backup"

SECTION_HEADER = re.compile(r"^\s*\[.+\]\s*$")

VIEWPORT_STOCK = "GameViewportClientClassName=VisceraGame.VCGameViewportClient"
VIEWPORT_ARCHIPELAGO = (
    "GameViewportClientClassName=VCArchipelago.VCGameViewportClient_Archipelago")

# No ValidTitles line: an empty list passes the menu's title filter, so the
# Archipelago mode exists under every title (base game and all the DLC).
PROVIDER_INI_LINES = [
    "[VCGame_Archipelago VCUIDataProvider_GameInfo]",
    'GameClass="VCArchipelago.VCGame_Archipelago"',
    'FriendlyName="Archipelago"',
    'Description="Archipelago"',
    'PreviewImageMarkup=""',
    "GamePicAspectRatio=1.0",
    "SortOrder=350",
]

STATE_BASE_INI_LINES = [
    "[VCArchipelago.VCArchipelagoState]",
    "APSeq=0",
    "APCleanPct=0",
    "APMap=",
    "APMilestones=",
]


def _mod_sources() -> "list[tuple[str, bytes]]":
    """The packaged mod source files as (name, bytes). Reads the data directory
    directly from a source checkout, or through importlib.resources when the
    world is zipimported from a packaged .apworld."""
    if MOD_DATA_DIR.is_dir():
        return [(path.name, path.read_bytes())
                for path in sorted(MOD_DATA_DIR.glob("*.uc"))]
    from importlib import resources
    root = resources.files(__package__) / "data" / "mod" / MOD_PACKAGE / "Classes"
    try:
        entries = [entry for entry in root.iterdir() if entry.name.endswith(".uc")]
    except (FileNotFoundError, NotADirectoryError):
        return []
    return sorted(((entry.name, entry.read_bytes()) for entry in entries))


def _read_ini_lines(path: Path) -> list[str]:
    # latin-1 round-trips every byte, so a stray non-ASCII character in a
    # player's ini can never corrupt a rewrite.
    return path.read_text(encoding="latin-1").splitlines()


def _write_ini_lines(path: Path, lines: "list[str]") -> None:
    path.write_text("\r\n".join(lines) + "\r\n", encoding="latin-1")


def _backup_once(config_dir: Path, path: Path) -> None:
    backup_dir = config_dir.parent.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(exist_ok=True)
    destination = backup_dir / path.name
    if path.is_file() and not destination.exists():
        shutil.copy2(path, destination)


def _add_line_to_section(path: Path, section: str, line: str,
                         create_section: bool = False) -> bool:
    """Add a line at the end of an ini section unless already present. Returns
    whether the file changed."""
    lines = _read_ini_lines(path)
    if line in lines:
        return False
    out: list[str] = []
    in_section = False
    inserted = False
    for existing in lines:
        if SECTION_HEADER.match(existing):
            if in_section and not inserted:
                out.append(line)
                inserted = True
            in_section = existing.strip().lower() == section.lower()
        out.append(existing)
    if in_section and not inserted:
        out.append(line)
        inserted = True
    if not inserted:
        if not create_section:
            raise ValueError(f"section {section} not found in {path.name}")
        out.append(section)
        out.append(line)
    _write_ini_lines(path, out)
    return True


def deploy(install_dir: Path) -> list[str]:
    """Deploy the mod source and config into the install. Returns log lines."""
    install_dir = Path(install_dir)
    config = install_dir / "UDKGame" / "Config"
    default_engine = config / "DefaultEngine.ini"
    if not default_engine.is_file():
        raise FileNotFoundError(f"{default_engine} not found; is this a Viscera install?")
    sources = _mod_sources()
    if not sources:
        raise FileNotFoundError(
            "no mod source in the apworld package; it was packaged without data/mod")

    log: list[str] = []
    source_dir = install_dir / "Development" / "Src" / MOD_PACKAGE / "Classes"
    if source_dir.is_dir():
        shutil.rmtree(source_dir)
    source_dir.mkdir(parents=True)
    for name, content in sources:
        (source_dir / name).write_bytes(content)
    log.append(f"Copied {len(sources)} mod source files.")

    _backup_once(config, default_engine)
    if _add_line_to_section(default_engine, "[UnrealEd.EditorEngine]",
                            f"+EditPackages={MOD_PACKAGE}"):
        log.append("Added the package to the compile list.")
    if _add_line_to_section(default_engine, "[Engine.ScriptPackages]",
                            f"+NonNativePackages={MOD_PACKAGE}"):
        log.append("Added the package to the game load list.")

    engine_lines = _read_ini_lines(default_engine)
    if VIEWPORT_ARCHIPELAGO not in engine_lines:
        if VIEWPORT_STOCK not in engine_lines:
            raise ValueError("stock viewport client line not found in DefaultEngine.ini")
        engine_lines = [VIEWPORT_ARCHIPELAGO if line == VIEWPORT_STOCK else line
                        for line in engine_lines]
        _write_ini_lines(default_engine, engine_lines)
        log.append("Swapped in the Archipelago viewport client.")

    _write_ini_lines(config / "VCArchipelagoProviders.ini", PROVIDER_INI_LINES)
    state_base = config / "DefaultVCArchipelago.ini"
    if not state_base.is_file():
        _write_ini_lines(state_base, STATE_BASE_INI_LINES)
    log.append("Registered the Archipelago mode and state file.")

    # The generated UDKEngine.ini masks the Default arrays, so the package
    # lines and the viewport swap must land in it too. It is edited in place:
    # clearing it would also wipe the player's saved engine settings, and
    # UDKGame.ini (view bob and the other game settings) holds nothing of ours
    # and is never touched.
    _wire_generated_engine_ini(config, log)
    return log


def _wire_generated_engine_ini(config: Path, log: "list[str]") -> None:
    """Apply the DefaultEngine.ini wiring to the generated UDKEngine.ini in
    place. A mirror without any recognizable viewport line cannot be edited
    safely; that one file is cleared and regenerates on launch."""
    generated = config / "UDKEngine.ini"
    if not generated.is_file():
        return
    _backup_once(config, generated)
    lines = _read_ini_lines(generated)
    if VIEWPORT_ARCHIPELAGO not in lines and VIEWPORT_STOCK not in lines:
        generated.unlink()
        log.append("Cleared an unrecognizable UDKEngine.ini (it regenerates "
                   "on launch).")
        return
    changed = _add_line_to_section(generated, "[UnrealEd.EditorEngine]",
                                   f"EditPackages={MOD_PACKAGE}",
                                   create_section=True)
    changed = _add_line_to_section(generated, "[Engine.ScriptPackages]",
                                   f"NonNativePackages={MOD_PACKAGE}",
                                   create_section=True) or changed
    lines = _read_ini_lines(generated)
    if VIEWPORT_STOCK in lines:
        lines = [VIEWPORT_ARCHIPELAGO if line == VIEWPORT_STOCK else line
                 for line in lines]
        _write_ini_lines(generated, lines)
        changed = True
    if changed:
        log.append("Wired the mod into the generated UDKEngine.ini in place.")


def compile_mod(install_dir: Path, timeout_seconds: float = 120.0) -> tuple[bool, str]:
    """Run UDK.exe make and report whether the package was rebuilt cleanly. The
    make console sometimes never exits on its own, so it is stopped once the
    timeout passes (the compile itself finishes long before)."""
    install_dir = Path(install_dir)
    udk = install_dir / "Binaries" / "Win32" / "UDK.exe"
    package = install_dir / "UDKGame" / "Script" / f"{MOD_PACKAGE}.u"
    launch_log = install_dir / "UDKGame" / "Logs" / "Launch.log"
    if not udk.is_file():
        return False, f"UDK.exe not found at {udk}."

    before = package.stat().st_mtime if package.is_file() else 0.0
    process = subprocess.Popen([str(udk), "make"], cwd=str(udk.parent))
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
    time.sleep(0.5)

    # The make run rewrites Launch.log, so the log verdict is authoritative: a
    # failed compile leaves the old package file untouched, which on its own
    # would look like "already compiled".
    try:
        log_text = launch_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log_text = ""
    # An up-to-date tree logs the no-work line instead of a success summary.
    compiled_clean = ("Success - 0 error(s)" in log_text
                      or "No scripts need recompiling" in log_text)
    if not package.is_file():
        return False, f"Compile failed: the mod package was not produced; check {launch_log}."
    if not compiled_clean:
        return False, f"Compile failed; check {launch_log}."
    if package.stat().st_mtime <= before:
        return True, "Mod already up to date."
    return True, "Mod compiled cleanly. Relaunch the game to load it."
