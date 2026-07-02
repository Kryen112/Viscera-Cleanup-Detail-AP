"""Per-seed save isolation, so an Archipelago seed keeps its own Office, job saves,
and collectibles apart from the player's career saves.

Layout inside the install:
    Saves\\               the active set the game reads
    Saves_AP_Career\\     the player's real saves, stashed while a seed is active
    Saves_AP_Seeds\\<seed>\\   one folder per Archipelago seed
    Saves_AP_state.json  what is stashed and which seed is active (crash recovery)

Every swap is a directory rename on one volume (atomic), and the career folder is
only ever moved, never overwritten, so a partial run cannot lose the real saves.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

GRANTS_FILENAME = "VCArchipelagoGrants.sav"


def seed_folder_name(seed: str) -> str:
    """A filesystem-safe folder name for a seed."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", seed or "")
    return cleaned or "unnamed"


class SaveManager:
    def __init__(self, install_dir: Path) -> None:
        self.install_dir = Path(install_dir)
        self.saves = self.install_dir / "Saves"
        self.career = self.install_dir / "Saves_AP_Career"
        self.seeds_root = self.install_dir / "Saves_AP_Seeds"
        self.state_path = self.install_dir / "Saves_AP_state.json"

    def _read_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_state(self, career_stashed: bool, active_seed: "str | None") -> None:
        self.state_path.write_text(
            json.dumps({"career_stashed": career_stashed, "active_seed": active_seed}),
            encoding="utf-8")

    def is_isolated(self) -> bool:
        return bool(self._read_state().get("career_stashed"))

    def active_seed(self) -> "str | None":
        return self._read_state().get("active_seed")

    def _seed_dir(self, seed: str) -> Path:
        return self.seeds_root / seed_folder_name(seed)

    def isolate(self, seed: str) -> str:
        """Stash the career (once), persist any other active seed, then load this
        seed (resume) or start it fresh. Returns a status line for the player."""
        state = self._read_state()
        stashed = bool(state.get("career_stashed"))
        active = state.get("active_seed")
        folder = seed_folder_name(seed)

        if stashed and active == folder:
            return f"Already on Archipelago seed '{folder}'."

        self.seeds_root.mkdir(parents=True, exist_ok=True)

        if not stashed:
            if self.career.exists():
                raise RuntimeError(
                    f"{self.career} exists but state says the career is not stashed; "
                    "refusing to overwrite it.")
            if self.saves.exists():
                self.saves.rename(self.career)
            else:
                self.career.mkdir(parents=True)
            self._write_state(True, None)
        elif active:
            if self.saves.exists():
                destination = self._seed_dir(active)
                if destination.exists():
                    raise RuntimeError(
                        f"{destination} exists; cannot persist the active seed.")
                self.saves.rename(destination)
            self._write_state(True, None)

        if self.saves.exists():
            raise RuntimeError(f"{self.saves} still exists; cannot load '{folder}'.")
        seed_dir = self._seed_dir(seed)
        if seed_dir.exists():
            seed_dir.rename(self.saves)
            result = f"Resumed Archipelago seed '{folder}'."
        else:
            self.saves.mkdir(parents=True)
            result = f"Started a fresh save set for Archipelago seed '{folder}'."
        self._write_state(True, folder)
        return result

    def restore(self) -> str:
        """Persist the active seed and move the career saves back. Removes the grants
        file so normal play shows every level again."""
        state = self._read_state()
        if not state.get("career_stashed"):
            return "Career saves are already in place; nothing to restore."

        active = state.get("active_seed")
        if self.saves.exists():
            if not active:
                raise RuntimeError(
                    f"{self.saves} present but no active seed recorded; not "
                    "overwriting. Resolve by hand.")
            destination = self._seed_dir(active)
            if destination.exists():
                raise RuntimeError(f"{destination} exists; cannot persist the seed.")
            self.saves.rename(destination)

        if not self.career.exists():
            raise RuntimeError(f"{self.career} is missing; cannot restore the career.")
        self.career.rename(self.saves)
        grants_file = self.saves / GRANTS_FILENAME
        if grants_file.exists():
            grants_file.unlink()
        self._write_state(False, None)
        return "Restored your career saves."
