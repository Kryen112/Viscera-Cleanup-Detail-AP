#!/usr/bin/env python
"""Run the Viscera Cleanup Detail world's WorldTestBase suite.

The apworld package is junctioned into an Archipelago checkout's worlds/
directory, so the tests only run from inside that checkout: they import AP's
test.bases and reach the world via a relative import. This wrapper locates the
checkout and runs pytest there.

Set AP_ROOT to point at the Archipelago checkout (the one holding the
worlds/viscera_cleanup_detail junction). Without it, the default is a sibling
Archipelago/ folder next to this repo.
"""
import os
import subprocess
import sys
from pathlib import Path

WORLD_TEST_PATH = "worlds/viscera_cleanup_detail/test"

# scripts/ -> VCD_AP/ -> repo root -> Archipelago-play/ -> Archipelago/
repo_root = Path(__file__).resolve().parent.parent.parent
default_ap_root = repo_root.parent / "Archipelago"
ap_root = Path(os.environ.get("AP_ROOT", default_ap_root)).resolve()

if not (ap_root / WORLD_TEST_PATH).is_dir():
    sys.exit(
        f"Cannot find {WORLD_TEST_PATH} under {ap_root}.\n"
        "Set AP_ROOT to your Archipelago checkout (the one with the "
        "worlds/viscera_cleanup_detail junction)."
    )

result = subprocess.run(
    [sys.executable, "-m", "pytest", WORLD_TEST_PATH, "-q"],
    cwd=ap_root,
)
sys.exit(result.returncode)
