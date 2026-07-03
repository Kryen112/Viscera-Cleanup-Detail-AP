"""Tests for the mod installer's deploy step, against a throwaway install tree."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .. import installer

DEFAULT_ENGINE = """[URL]
Protocol=unreal

[UnrealEd.EditorEngine]
+EditPackages=VisceraGame

[Engine.Engine]
GameViewportClientClassName=VisceraGame.VCGameViewportClient

[Engine.ScriptPackages]
+NonNativePackages=VisceraGame
"""

# A generated mirror: full arrays, no + syntax, plus a player engine setting.
GENERATED_ENGINE = """[URL]
Protocol=unreal

[UnrealEd.EditorEngine]
EditPackages=Core
EditPackages=VisceraGame

[Engine.Engine]
GameViewportClientClassName=VisceraGame.VCGameViewportClient
Console=VisceraGame.VCConsole

[Engine.ScriptPackages]
NonNativePackages=VisceraGame
"""

# Player game settings, view bob disabled.
GENERATED_GAME = """[RSGCore.RSPawn]
Bob=0.000000
bWeaponBob=true
"""


class TestDeploy(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)
        self.config = self.install / "UDKGame" / "Config"
        self.config.mkdir(parents=True)
        (self.config / "DefaultEngine.ini").write_text(DEFAULT_ENGINE, encoding="ascii")
        (self.config / "UDKEngine.ini").write_text(GENERATED_ENGINE, encoding="ascii")
        (self.config / "UDKGame.ini").write_text(GENERATED_GAME, encoding="ascii")
        mod_data = Path(self._tmp.name) / "data" / "VCArchipelago" / "Classes"
        mod_data.mkdir(parents=True)
        (mod_data / "VCGame_Archipelago.uc").write_text("class;\n", encoding="ascii")
        self._patch = mock.patch.object(installer, "MOD_DATA_DIR", mod_data)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_deploy_wires_everything(self) -> None:
        installer.deploy(self.install)
        engine = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        self.assertIn("+EditPackages=VCArchipelago", engine)
        self.assertIn("+NonNativePackages=VCArchipelago", engine)
        self.assertIn(installer.VIEWPORT_ARCHIPELAGO, engine)
        self.assertNotIn(installer.VIEWPORT_STOCK + "\n", engine)
        self.assertTrue((self.install / "Development" / "Src" / "VCArchipelago"
                         / "Classes" / "VCGame_Archipelago.uc").is_file())
        self.assertTrue((self.config / "VCArchipelagoProviders.ini").is_file())
        self.assertTrue((self.config / "DefaultVCArchipelago.ini").is_file())

    def test_generated_engine_ini_is_wired_in_place(self) -> None:
        installer.deploy(self.install)
        generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
        self.assertIn("EditPackages=VCArchipelago", generated)
        self.assertIn("NonNativePackages=VCArchipelago", generated)
        self.assertIn(installer.VIEWPORT_ARCHIPELAGO, generated)
        # The player's engine setting survives, and a backup exists.
        self.assertIn("Console=VisceraGame.VCConsole", generated)
        self.assertTrue((self.install / installer.BACKUP_DIR_NAME
                         / "UDKEngine.ini").is_file())

    def test_game_settings_are_left_alone(self) -> None:
        installer.deploy(self.install)
        self.assertEqual(
            (self.config / "UDKGame.ini").read_text(encoding="ascii"),
            GENERATED_GAME)

    def test_unrecognizable_generated_engine_ini_is_cleared(self) -> None:
        (self.config / "UDKEngine.ini").write_text("generated\n", encoding="ascii")
        installer.deploy(self.install)
        self.assertFalse((self.config / "UDKEngine.ini").exists())
        self.assertTrue((self.install / installer.BACKUP_DIR_NAME
                         / "UDKEngine.ini").is_file())

    def test_deploy_is_idempotent(self) -> None:
        installer.deploy(self.install)
        first = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        first_generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
        installer.deploy(self.install)
        second = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        second_generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
        self.assertEqual(first, second)
        self.assertEqual(first_generated, second_generated)
        self.assertEqual(first.count("+EditPackages=VCArchipelago"), 1)
        self.assertEqual(first_generated.count("EditPackages=VCArchipelago"), 1)

    def test_added_lines_land_inside_their_sections(self) -> None:
        installer.deploy(self.install)
        lines = (self.config / "DefaultEngine.ini").read_text(
            encoding="ascii").splitlines()
        edit_index = lines.index("+EditPackages=VCArchipelago")
        section_index = lines.index("[UnrealEd.EditorEngine]")
        next_section = min(i for i, line in enumerate(lines)
                           if i > section_index and line.startswith("["))
        self.assertTrue(section_index < edit_index < next_section)

    def test_missing_engine_ini_raises(self) -> None:
        (self.config / "DefaultEngine.ini").unlink()
        with self.assertRaises(FileNotFoundError):
            installer.deploy(self.install)


class TestCompileMod(unittest.TestCase):
    """compile_mod with the UDK process mocked out; the verdict comes from the
    log and the package file the fake run leaves behind."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)
        (self.install / "Binaries" / "Win32").mkdir(parents=True)
        (self.install / "Binaries" / "Win32" / "UDK.exe").write_bytes(b"")
        (self.install / "UDKGame" / "Script").mkdir(parents=True)
        (self.install / "UDKGame" / "Logs").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, log_text: str, write_package: bool) -> "tuple[bool, str]":
        def fake_popen(cmd, cwd=None, **_extras):
            self.command = cmd
            (self.install / "UDKGame" / "Logs" / "Launch.log").write_text(
                log_text, encoding="utf-8")
            if write_package:
                (self.install / "UDKGame" / "Script" / "VCArchipelago.u"
                 ).write_bytes(b"u")
            return mock.Mock(wait=mock.Mock(return_value=0))
        with mock.patch.object(installer.subprocess, "Popen", fake_popen), \
                mock.patch.object(installer.time, "sleep"):
            return installer.compile_mod(self.install)

    def test_clean_compile(self) -> None:
        ok, message = self._run("Log: Success - 0 error(s), 0 warning(s)", True)
        self.assertTrue(ok)
        self.assertIn("compiled cleanly", message)

    def test_make_runs_unattended(self) -> None:
        # The unattended flags let the hidden make window exit on its own.
        self._run("Log: Success - 0 error(s), 0 warning(s)", True)
        self.assertIn("-unattended", self.command)
        self.assertIn("-nopause", self.command)

    def test_error_with_stale_package_is_a_failure(self) -> None:
        # A failed compile leaves the old package untouched; the log decides.
        (self.install / "UDKGame" / "Script" / "VCArchipelago.u").write_bytes(b"u")
        ok, message = self._run("Error, 'X' : bad", False)
        self.assertFalse(ok)
        self.assertIn("Compile failed", message)

    def test_up_to_date_tree(self) -> None:
        (self.install / "UDKGame" / "Script" / "VCArchipelago.u").write_bytes(b"u")
        ok, message = self._run("Log: No scripts need recompiling.", False)
        self.assertTrue(ok)
        self.assertIn("up to date", message)

    def test_no_package_produced(self) -> None:
        ok, message = self._run("Log: Success - 0 error(s), 0 warning(s)", False)
        self.assertFalse(ok)
        self.assertIn("not produced", message)


class TestModIsCurrent(unittest.TestCase):
    """mod_is_current against hand-built deploy and compile outcomes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)
        mod_data = self.install / "packaged" / "Classes"
        mod_data.mkdir(parents=True)
        (mod_data / "VCGame_Archipelago.uc").write_text("class;\n", encoding="ascii")
        self._patch = mock.patch.object(installer, "MOD_DATA_DIR", mod_data)
        self._patch.start()
        self.source_dir = (self.install / "Development" / "Src" / "VCArchipelago"
                           / "Classes")
        self.package = self.install / "UDKGame" / "Script" / "VCArchipelago.u"

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def _deploy_and_compile(self) -> None:
        self.source_dir.mkdir(parents=True)
        (self.source_dir / "VCGame_Archipelago.uc").write_text(
            "class;\n", encoding="ascii")
        self.package.parent.mkdir(parents=True)
        self.package.write_bytes(b"u")
        source_time = (self.source_dir / "VCGame_Archipelago.uc").stat().st_mtime
        os.utime(self.package, (source_time + 10, source_time + 10))

    def test_matching_install_is_current(self) -> None:
        self._deploy_and_compile()
        self.assertTrue(installer.mod_is_current(self.install))

    def test_name_order_matches_across_sort_styles(self) -> None:
        # These two names sort differently as Path objects (case-insensitive on
        # Windows) than as plain strings; a mismatch reads a fresh install as
        # stale forever.
        names = ("VCGameViewportClient_Archipelago.uc", "VCGame_Archipelago.uc")
        for name in names:
            (installer.MOD_DATA_DIR / name).write_text("class;\n", encoding="ascii")
        self._deploy_and_compile()
        for name in names:
            (self.source_dir / name).write_text("class;\n", encoding="ascii")
        source_time = max(path.stat().st_mtime
                          for path in self.source_dir.glob("*.uc"))
        os.utime(self.package, (source_time + 10, source_time + 10))
        self.assertTrue(installer.mod_is_current(self.install))

    def test_missing_deploy_is_stale(self) -> None:
        self.assertFalse(installer.mod_is_current(self.install))

    def test_changed_source_is_stale(self) -> None:
        self._deploy_and_compile()
        (self.source_dir / "VCGame_Archipelago.uc").write_text(
            "class; // old\n", encoding="ascii")
        source_time = (self.source_dir / "VCGame_Archipelago.uc").stat().st_mtime
        os.utime(self.package, (source_time + 10, source_time + 10))
        self.assertFalse(installer.mod_is_current(self.install))

    def test_extra_deployed_file_is_stale(self) -> None:
        self._deploy_and_compile()
        (self.source_dir / "VCLeftover.uc").write_text("class;\n", encoding="ascii")
        self.assertFalse(installer.mod_is_current(self.install))

    def test_missing_package_is_stale(self) -> None:
        self._deploy_and_compile()
        self.package.unlink()
        self.assertFalse(installer.mod_is_current(self.install))

    def test_package_older_than_source_is_stale(self) -> None:
        # A deploy whose compile never landed leaves a package behind the sources.
        self._deploy_and_compile()
        source_time = (self.source_dir / "VCGame_Archipelago.uc").stat().st_mtime
        os.utime(self.package, (source_time - 10, source_time - 10))
        self.assertFalse(installer.mod_is_current(self.install))

    def test_apworld_without_mod_source_is_current(self) -> None:
        with mock.patch.object(installer, "_mod_sources", return_value=[]):
            self.assertTrue(installer.mod_is_current(self.install))


if __name__ == "__main__":
    unittest.main()
