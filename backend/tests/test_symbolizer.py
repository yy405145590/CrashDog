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


if __name__ == "__main__":
    unittest.main()
