import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services import symbolizer


class ResolveCdbPathTests(unittest.TestCase):
    def setUp(self):
        symbolizer._cached_cdb_path = None

    def tearDown(self):
        symbolizer._cached_cdb_path = None

    def test_uses_configured_path_when_it_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            configured = Path(temp_dir) / "x86" / "cdb.exe"
            configured.parent.mkdir()
            configured.touch()

            with patch.object(symbolizer.config, "CDB_PATH", str(configured)), patch.object(
                symbolizer, "_windbg_package_install_locations"
            ) as package_locations:
                resolved = symbolizer.resolve_cdb_path()

            self.assertEqual(resolved, configured)
            package_locations.assert_not_called()

    def test_relocates_versioned_windbg_package_and_preserves_architecture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            configured = root / "Microsoft.WinDbg_old" / "x86" / "cdb.exe"
            current_package = root / "Microsoft.WinDbg_current"
            current_cdb = current_package / "x86" / "cdb.exe"
            current_cdb.parent.mkdir(parents=True)
            current_cdb.touch()

            with patch.object(symbolizer.config, "CDB_PATH", str(configured)), patch.object(
                symbolizer, "_windows_sdk_cdb_candidates", return_value=[]
            ), patch.object(symbolizer.shutil, "which", return_value=None), patch.object(
                symbolizer, "_windbg_package_install_locations", return_value=[current_package]
            ):
                resolved = symbolizer.resolve_cdb_path()

            self.assertEqual(resolved, current_cdb)

    def test_discards_stale_cached_path_after_an_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_cdb = root / "old" / "x86" / "cdb.exe"
            new_package = root / "new"
            new_cdb = new_package / "x86" / "cdb.exe"
            old_cdb.parent.mkdir(parents=True)
            new_cdb.parent.mkdir(parents=True)
            old_cdb.touch()
            new_cdb.touch()
            symbolizer._cached_cdb_path = old_cdb
            old_cdb.unlink()

            with patch.object(symbolizer.config, "CDB_PATH", str(old_cdb)), patch.object(
                symbolizer, "_windows_sdk_cdb_candidates", return_value=[]
            ), patch.object(symbolizer.shutil, "which", return_value=None), patch.object(
                symbolizer, "_windbg_package_install_locations", return_value=[new_package]
            ):
                resolved = symbolizer.resolve_cdb_path()

            self.assertEqual(resolved, new_cdb)


class CdbScriptTests(unittest.TestCase):
    def test_script_reloads_renamed_game_image_one_command_per_line(self):
        mod = symbolizer.DumpModule(
            "QingCheng-Win64-Shipping.exe", 0x7FF737980000, 0xE089000, "G", 1, "x.pdb"
        )
        script = symbolizer._build_cdb_command([mod], [("QingCheng-Win64-Shipping", 0x6337B8E)])
        lines = script.splitlines()
        self.assertEqual(lines[0], ".reload /f /i QingCheng-Win64-Shipping.exe=7ff737980000,e089000")
        self.assertIn("ln QingCheng_Win64_Shipping+0x6337b8e", lines)
        self.assertEqual(lines[-1], "q")
        self.assertFalse(any(";" in l for l in lines))


class PCallStackParseTests(unittest.TestCase):
    def test_ignores_command_echo_and_keeps_symbol_and_source(self):
        raw = "\n".join([
            "0:085> .echo @@PCALLSTACK_BEGIN@@",
            "@@PCALLSTACK_BEGIN@@",
            "0:085> .echo @@PCS@@ QingCheng-Win64-Shipping+0x6337b8e",
            "@@PCS@@ QingCheng-Win64-Shipping+0x6337b8e",
            "0:085> ln QingCheng_Win64_Shipping+0x6337b8e",
            r"E:\QingCheng\unit.cpp(251)+0x5",
            "(00007ff7`3dcb7290)   QingCheng_Win64_Shipping!KBEngine::Unit::createComponent+0x8fe   |  (00007ff7`3dcb7ba0)   other",
            "0:085> .echo @@PCALLSTACK_END@@",
            "@@PCALLSTACK_END@@",
        ])
        _, frames = symbolizer._parse_pcallstack_section(raw)
        self.assertEqual(frames, [
            r"00 QingCheng_Win64_Shipping!KBEngine::Unit::createComponent+0x8fe  [E:\QingCheng\unit.cpp(251)]"
        ])


if __name__ == "__main__":
    unittest.main()
