"""Build the viscera_cleanup_detail .apworld and install it to the local Archipelago.

Run from the repo root:
    py -3.12 VCD_AP/build_apworld.py

Packaging only, no code generation. The apworld Python is committed source, not
generated. This invokes Archipelago's native `Build APWorlds` Launcher to zip the
world, then copies the result into the local custom_worlds dir(s).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

VCD_AP_DIR = Path(__file__).resolve().parent

# The Archipelago framework checkout. Default: the sibling of this repo.
AP_FRAMEWORK_DIR = Path(
    os.environ.get("AP_ROOT") or (VCD_AP_DIR.parent.parent / "Archipelago")
).resolve()
APWORLD_GAME_NAME = "Viscera Cleanup Detail"
APWORLD_FILE = "viscera_cleanup_detail.apworld"

# --- LOCAL ONLY, do not commit -------------------------------------------
_DEFAULT_APWORLD_INSTALL_DIRS = [
    Path(r"C:\ProgramData\Archipelago\custom_worlds"),
]
APWORLD_INSTALL_DIRS = (
    [Path(p) for p in os.environ["VCD_APWORLD_INSTALL_DIRS"].split(os.pathsep)]
    if os.environ.get("VCD_APWORLD_INSTALL_DIRS")
    else _DEFAULT_APWORLD_INSTALL_DIRS
)
# --- end LOCAL ONLY -------------------------------------------------------


def build_apworld_zip() -> "Path | None":
    launcher = AP_FRAMEWORK_DIR / "Launcher.py"
    if not launcher.is_file():
        print(
            f"WARNING: AP framework not found at {AP_FRAMEWORK_DIR}; cannot build the "
            f".apworld. Set AP_ROOT or place the Archipelago checkout.",
            file=sys.stderr,
        )
        return None
    cmd = [sys.executable, "Launcher.py", "Build APWorlds", APWORLD_GAME_NAME]
    result = subprocess.run(cmd, cwd=AP_FRAMEWORK_DIR, check=False)
    if result.returncode != 0:
        print(f"ERROR: 'Build APWorlds' exited {result.returncode}; .apworld not produced.", file=sys.stderr)
        return None
    zip_path = AP_FRAMEWORK_DIR / "build" / "apworlds" / APWORLD_FILE
    if not zip_path.is_file():
        print(f"ERROR: Launcher reported success but {zip_path} is missing.", file=sys.stderr)
        return None
    return zip_path


# --- LOCAL ONLY, do not commit -------------------------------------------
def install_apworld(zip_path: Path) -> None:
    for dest_dir in APWORLD_INSTALL_DIRS:
        if not dest_dir.is_dir():
            print(f"  skipped install (no such dir): {dest_dir}")
            continue
        dest = dest_dir / zip_path.name
        shutil.copy2(zip_path, dest)
        print(f"  installed -> {dest}")
# --- end LOCAL ONLY -------------------------------------------------------


def main() -> int:
    zip_path = build_apworld_zip()
    if zip_path is None:
        return 1
    print(f"Built {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    install_apworld(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
