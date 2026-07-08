"""Tests for the mod installer's deploy step, against a throwaway install tree."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .. import installer

PACKAGE_BYTES = b"canonical compiled package"

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


class InstallerCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.install = Path(self._tmp.name)
        self.config = self.install / "UDKGame" / "Config"
        self.config.mkdir(parents=True)
        (self.config / "DefaultEngine.ini").write_text(DEFAULT_ENGINE, encoding="ascii")
        (self.config / "UDKEngine.ini").write_text(GENERATED_ENGINE, encoding="ascii")
        (self.config / "UDKGame.ini").write_text(GENERATED_GAME, encoding="ascii")
        packaged = Path(self._tmp.name) / "packaged" / "VCArchipelago.u"
        packaged.parent.mkdir()
        packaged.write_bytes(PACKAGE_BYTES)
        self._patch = mock.patch.object(installer, "MOD_PACKAGE_DATA", packaged)
        self._patch.start()
        self.installed_package = (self.install / "UDKGame" / "Script"
                                  / "VCArchipelago.u")

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()


class TestDeploy(InstallerCase):
    def test_deploy_wires_everything(self) -> None:
        installer.deploy(self.install)
        self.assertEqual(self.installed_package.read_bytes(), PACKAGE_BYTES)
        engine = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        self.assertIn("+NonNativePackages=VCArchipelago", engine)
        self.assertIn(installer.VIEWPORT_ARCHIPELAGO, engine)
        self.assertNotIn(installer.VIEWPORT_STOCK + "\n", engine)
        self.assertTrue((self.config / "VCArchipelagoProviders.ini").is_file())
        self.assertTrue((self.config / "DefaultVCArchipelago.ini").is_file())

    def test_deploy_never_adds_compile_wiring(self) -> None:
        # A player install must hold no compile path to the package: a local
        # rebuild would restamp the package GUID and split co-op.
        installer.deploy(self.install)
        engine = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
        self.assertNotIn("EditPackages=VCArchipelago", engine)
        self.assertNotIn("EditPackages=VCArchipelago", generated)
        self.assertFalse(
            (self.install / "Development" / "Src" / "VCArchipelago").exists())

    def test_deploy_removes_stale_compile_wiring(self) -> None:
        # An install set up by the old compiling installer carries deployed
        # source and EditPackages lines; deploy strips them all.
        stale_source = (self.install / "Development" / "Src" / "VCArchipelago"
                        / "Classes")
        stale_source.mkdir(parents=True)
        (stale_source / "VCGame_Archipelago.uc").write_text("class;\n",
                                                            encoding="ascii")
        default_engine = self.config / "DefaultEngine.ini"
        default_engine.write_text(
            DEFAULT_ENGINE.replace("+EditPackages=VisceraGame",
                                   "+EditPackages=VisceraGame\n"
                                   "+EditPackages=VCArchipelago"),
            encoding="ascii")
        generated = self.config / "UDKEngine.ini"
        generated.write_text(
            GENERATED_ENGINE.replace("EditPackages=VisceraGame",
                                     "EditPackages=VisceraGame\n"
                                     "EditPackages=VCArchipelago"),
            encoding="ascii")
        installer.deploy(self.install)
        self.assertNotIn("EditPackages=VCArchipelago",
                         default_engine.read_text(encoding="ascii"))
        self.assertNotIn("EditPackages=VCArchipelago",
                         generated.read_text(encoding="ascii"))
        self.assertFalse(
            (self.install / "Development" / "Src" / "VCArchipelago").exists())

    def test_generated_engine_ini_is_wired_in_place(self) -> None:
        installer.deploy(self.install)
        generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
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

    def test_utf16_generated_engine_ini_is_edited_not_cleared(self) -> None:
        # The engine rewrites a config as UTF-16 once a non-ANSI character
        # lands in a setting; such a file must be wired in place in its own
        # encoding, never treated as unrecognizable and cleared.
        generated = self.config / "UDKEngine.ini"
        generated.write_text(GENERATED_ENGINE, encoding="utf-16")
        installer.deploy(self.install)
        self.assertTrue(generated.exists())
        raw = generated.read_bytes()
        self.assertEqual(raw[:2], b"\xff\xfe")
        text = raw.decode("utf-16")
        self.assertIn(installer.VIEWPORT_ARCHIPELAGO, text)
        self.assertIn("NonNativePackages=VCArchipelago", text)
        self.assertNotIn("EditPackages=VCArchipelago", text)

    def test_deploy_is_idempotent(self) -> None:
        installer.deploy(self.install)
        first = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        first_generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
        installer.deploy(self.install)
        second = (self.config / "DefaultEngine.ini").read_text(encoding="ascii")
        second_generated = (self.config / "UDKEngine.ini").read_text(encoding="ascii")
        self.assertEqual(first, second)
        self.assertEqual(first_generated, second_generated)
        self.assertEqual(first.count("+NonNativePackages=VCArchipelago"), 1)
        self.assertEqual(first_generated.count("NonNativePackages=VCArchipelago"), 1)

    def test_added_lines_land_inside_their_sections(self) -> None:
        installer.deploy(self.install)
        lines = (self.config / "DefaultEngine.ini").read_text(
            encoding="ascii").splitlines()
        package_index = lines.index("+NonNativePackages=VCArchipelago")
        section_index = lines.index("[Engine.ScriptPackages]")
        next_sections = [i for i, line in enumerate(lines)
                         if i > section_index and line.startswith("[")]
        next_section = min(next_sections) if next_sections else len(lines)
        self.assertTrue(section_index < package_index < next_section)

    def test_missing_engine_ini_raises(self) -> None:
        (self.config / "DefaultEngine.ini").unlink()
        with self.assertRaises(FileNotFoundError):
            installer.deploy(self.install)

    def test_apworld_without_packaged_module_raises(self) -> None:
        with mock.patch.object(installer, "_packaged_module_bytes",
                               return_value=None):
            with self.assertRaises(FileNotFoundError):
                installer.deploy(self.install)


class TestModIsCurrent(InstallerCase):
    def test_matching_install_is_current(self) -> None:
        installer.deploy(self.install)
        self.assertTrue(installer.mod_is_current(self.install))

    def test_missing_installed_package_is_stale(self) -> None:
        self.assertFalse(installer.mod_is_current(self.install))

    def test_different_installed_package_is_stale(self) -> None:
        installer.deploy(self.install)
        self.installed_package.write_bytes(b"a locally compiled package")
        self.assertFalse(installer.mod_is_current(self.install))

    def test_apworld_without_packaged_module_is_current(self) -> None:
        with mock.patch.object(installer, "_packaged_module_bytes",
                               return_value=None):
            self.assertTrue(installer.mod_is_current(self.install))


if __name__ == "__main__":
    unittest.main()
