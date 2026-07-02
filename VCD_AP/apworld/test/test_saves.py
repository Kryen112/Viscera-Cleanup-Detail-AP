"""Tests for per-seed save isolation. These exercise the file swaps against a temp
install, so the real career-saves guarantees are checked without touching a game."""
import tempfile
import unittest
from pathlib import Path

from .. import saves


def _write(directory: Path, name: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def _read(path: Path) -> "str | None":
    return path.read_text(encoding="utf-8") if path.exists() else None


class TestSaveManager(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)
        self.manager = saves.SaveManager(self.install)
        # A career save the isolation must preserve.
        _write(self.install / "Saves", "career.txt", "career")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_isolate_stashes_career_and_starts_fresh(self) -> None:
        self.manager.isolate("SeedA")
        self.assertTrue(self.manager.is_isolated())
        self.assertEqual(self.manager.active_seed(), "SeedA")
        # Career preserved, active Saves is fresh (no career file).
        self.assertEqual(_read(self.install / "Saves_AP_Career" / "career.txt"), "career")
        self.assertIsNone(_read(self.install / "Saves" / "career.txt"))

    def test_restore_brings_career_back_and_removes_grants(self) -> None:
        self.manager.isolate("SeedA")
        _write(self.install / "Saves", saves.GRANTS_FILENAME, "grant")
        message = self.manager.restore()
        self.assertIn("Restored", message)
        self.assertFalse(self.manager.is_isolated())
        self.assertEqual(_read(self.install / "Saves" / "career.txt"), "career")
        # The grants file must be gone so normal play shows every level.
        self.assertIsNone(_read(self.install / "Saves" / saves.GRANTS_FILENAME))

    def test_switching_seeds_persists_and_resumes(self) -> None:
        self.manager.isolate("SeedA")
        _write(self.install / "Saves", "job.txt", "seed-a-progress")
        self.manager.isolate("SeedB")
        # SeedA's progress is stored, SeedB starts fresh.
        self.assertIsNone(_read(self.install / "Saves" / "job.txt"))
        self.manager.isolate("SeedA")
        # Resuming SeedA brings its progress back.
        self.assertEqual(_read(self.install / "Saves" / "job.txt"), "seed-a-progress")

    def test_isolate_same_seed_is_noop(self) -> None:
        self.manager.isolate("SeedA")
        _write(self.install / "Saves", "job.txt", "progress")
        self.manager.isolate("SeedA")
        self.assertEqual(_read(self.install / "Saves" / "job.txt"), "progress")

    def test_restore_without_isolation_is_safe(self) -> None:
        message = self.manager.restore()
        self.assertIn("nothing to restore", message)
        self.assertEqual(_read(self.install / "Saves" / "career.txt"), "career")

    def test_refuses_to_clobber_existing_career_backup(self) -> None:
        _write(self.install / "Saves_AP_Career", "old.txt", "do not lose")
        with self.assertRaises(RuntimeError):
            self.manager.isolate("SeedA")
        # The stray backup is untouched.
        self.assertEqual(_read(self.install / "Saves_AP_Career" / "old.txt"), "do not lose")


if __name__ == "__main__":
    unittest.main()
