"""Installs the VCArchipelago mod into a game install, from the client.

The packaged apworld carries the mod under ``data/mod``: the source classes for
reference and one canonical compiled ``VCArchipelago.u`` (staged and verified
by build_apworld.py). ``deploy`` copies that package file into the install's
``UDKGame\\Script``, wires the load list and the viewport swap into
DefaultEngine.ini (the only stock file it edits, backed up first), registers
the Archipelago mode provider and the SaveConfig base as their own ini files,
and wires the same lines into the generated UDKEngine.ini in place. The
generated inis carry the player's saved settings (view bob, audio, and the
rest), so they are edited, never cleared.

Nothing compiles on a player machine. Every install runs the same package
bytes, so the package GUID matches everywhere and co-op joins work; a locally
compiled package would carry its own GUID and split the players. Deploy
therefore also removes any compile wiring present in the install (a deployed
source tree and the EditPackages lines), so the game can never offer to
rebuild scripts locally and fork the GUID. Idempotent.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

MOD_PACKAGE = "VCArchipelago"
MOD_PACKAGE_DATA = (Path(__file__).parent / "data" / "mod" / MOD_PACKAGE
                    / f"{MOD_PACKAGE}.u")
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


def _packaged_module_bytes() -> "bytes | None":
    """The canonical compiled package carried by the apworld. Reads the data
    directory directly from a source checkout, or through importlib.resources
    when the world is zipimported from a packaged .apworld."""
    if MOD_PACKAGE_DATA.is_file():
        return MOD_PACKAGE_DATA.read_bytes()
    from importlib import resources
    entry = (resources.files(__package__) / "data" / "mod" / MOD_PACKAGE
             / f"{MOD_PACKAGE}.u")
    try:
        return entry.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _ini_encoding(path: Path) -> str:
    """The engine rewrites a config as UTF-16 once any non-ANSI character
    lands in a saved setting. Detecting that by BOM keeps such a file
    editable; anything else reads as latin-1, which round-trips every byte,
    so a stray non-ASCII character can never corrupt a rewrite."""
    with path.open("rb") as handle:
        head = handle.read(2)
    if head in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    return "latin-1"


def _read_ini_lines(path: Path) -> list[str]:
    return path.read_text(encoding=_ini_encoding(path)).splitlines()


def _write_ini_lines(path: Path, lines: "list[str]") -> None:
    encoding = _ini_encoding(path) if path.is_file() else "latin-1"
    path.write_text("\r\n".join(lines) + "\r\n", encoding=encoding)


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


def _remove_exact_line(path: Path, line: str) -> bool:
    """Drop every occurrence of a line from an ini. Returns whether the file
    changed."""
    lines = _read_ini_lines(path)
    kept = [existing for existing in lines if existing != line]
    if len(kept) == len(lines):
        return False
    _write_ini_lines(path, kept)
    return True


def deploy(install_dir: Path) -> list[str]:
    """Deploy the compiled mod package and config into the install. Returns
    log lines."""
    install_dir = Path(install_dir)
    config = install_dir / "UDKGame" / "Config"
    default_engine = config / "DefaultEngine.ini"
    if not default_engine.is_file():
        raise FileNotFoundError(f"{default_engine} not found; is this a Viscera install?")
    module_bytes = _packaged_module_bytes()
    if module_bytes is None:
        raise FileNotFoundError(
            "no compiled mod package in the apworld; it was packaged without data/mod")

    log: list[str] = []
    script_dir = install_dir / "UDKGame" / "Script"
    script_dir.mkdir(parents=True, exist_ok=True)
    target = script_dir / f"{MOD_PACKAGE}.u"
    if not target.is_file() or target.read_bytes() != module_bytes:
        target.write_bytes(module_bytes)
        log.append("Copied the compiled mod package.")

    # A leftover source tree plus compile wiring would let the game offer a
    # local script rebuild, which forks the package GUID and breaks co-op.
    source_dir = install_dir / "Development" / "Src" / MOD_PACKAGE
    if source_dir.is_dir():
        shutil.rmtree(source_dir)
        log.append("Removed the locally deployed mod source (the package ships "
                   "compiled).")

    _backup_once(config, default_engine)
    if _remove_exact_line(default_engine, f"+EditPackages={MOD_PACKAGE}"):
        log.append("Removed the package from the compile list.")
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

    # The generated UDKEngine.ini masks the Default arrays, so the load list
    # and the viewport swap must land in it too. It is edited in place:
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
    changed = _remove_exact_line(generated, f"EditPackages={MOD_PACKAGE}")
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


def mod_is_current(install_dir: Path) -> bool:
    """Whether the install already runs this apworld's package, byte for byte.
    An apworld packaged without a mod counts as current, so it can never
    trigger an install loop."""
    module_bytes = _packaged_module_bytes()
    if module_bytes is None:
        return True
    installed = Path(install_dir) / "UDKGame" / "Script" / f"{MOD_PACKAGE}.u"
    try:
        return installed.read_bytes() == module_bytes
    except OSError:
        return False
