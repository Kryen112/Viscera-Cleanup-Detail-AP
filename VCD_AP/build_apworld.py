"""Build the viscera_cleanup_detail .apworld and install it to the local Archipelago.

Run from the repo root:
    py -3.12 VCD_AP/build_apworld.py

Packaging only, no code generation. The apworld Python is committed source, not
generated. This stages the mod into apworld/data/mod (the source classes for
reference plus the one canonical compiled VCArchipelago.u the client deploys),
then invokes Archipelago's native `Build APWorlds` Launcher to zip the world,
then copies the result into the local custom_worlds dir(s).

The compiled package is the artifact every player must share: the package GUID
is stamped at compile time, and co-op only joins between identical packages.
The build refuses to package a VCArchipelago.u whose source-hash manifest does
not match the current mod source; run scripts\\install_mod.ps1 to rebuild it.
"""

from __future__ import annotations

import hashlib
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


def manifest_pairs(source: Path, compiled: Path) -> "list[tuple[str, str]]":
    """A sorted (sha256, name) pair per mod source file plus one for the
    compiled package itself, binding the package bytes to the source they were
    built from. The dev build script records the same pairs."""
    pairs = [
        (hashlib.sha256(unreal_file.read_bytes()).hexdigest(), unreal_file.name)
        for unreal_file in source.glob("*.uc")
    ]
    pairs.append((hashlib.sha256(compiled.read_bytes()).hexdigest(), compiled.name))
    return sorted(pairs)


def stage_mod() -> None:
    """Copy the mod source and the canonical compiled package into the package
    data dir so the shipped apworld carries them. The staged copy is a build
    artifact, not committed. A compiled package whose manifest does not match
    the current source fails the build."""
    source = VCD_AP_DIR / "mod" / "VCArchipelago" / "Classes"
    compiled = VCD_AP_DIR / "mod" / "Compiled" / "VCArchipelago.u"
    manifest = VCD_AP_DIR / "mod" / "Compiled" / "VCArchipelago.u.sources"
    if not compiled.is_file() or not manifest.is_file():
        raise FileNotFoundError(
            f"no canonical compiled package at {compiled}; build it with "
            "scripts\\install_mod.ps1")
    expected = manifest_pairs(source, compiled)
    if len(expected) < 2:
        raise FileNotFoundError(f"no mod source found under {source}")
    # Sorted-pair compare, so the manifest's line order, line endings, and
    # trailing whitespace never matter.
    recorded = sorted(
        tuple(line.split()) for line
        in manifest.read_text(encoding="ascii").splitlines() if line.strip())
    if recorded != expected:
        raise ValueError(
            "the compiled VCArchipelago.u was built from different mod source; "
            "rebuild it with scripts\\install_mod.ps1 before packaging")

    staged_root = VCD_AP_DIR / "apworld" / "data" / "mod" / "VCArchipelago"
    if staged_root.is_dir():
        shutil.rmtree(staged_root)
    staged_classes = staged_root / "Classes"
    staged_classes.mkdir(parents=True)
    count = 0
    for unreal_file in sorted(source.glob("*.uc")):
        shutil.copy2(unreal_file, staged_classes / unreal_file.name)
        count += 1
    shutil.copy2(compiled, staged_root / "VCArchipelago.u")
    print(f"Staged the compiled package and {count} source files into apworld/data/mod")


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
    stage_mod()
    zip_path = build_apworld_zip()
    if zip_path is None:
        return 1
    print(f"Built {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    install_apworld(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
