"""
POS-03 Regression — TASK-A03 (V07-FIND-003)
Verifies that Gate 2 returns dirty when a deeply-nested file changes (same size,
unchanged root mtime) at ANY position in the file list — including the 4th file
which the old first-three-alphabetical sample would have missed.

SI-003: Gate 2 detects deep-file changes beyond first sample.
"""
import sys
import types
import os
import tempfile
import unittest
from pathlib import Path

# Stub mobase so source imports succeed without MO2 runtime
sys.modules.setdefault("mobase", types.ModuleType("mobase"))

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))

from model.engines.scanner_engine import ScannerEngine


def _make_scanner(tmpdir: Path) -> ScannerEngine:
    """Return a ScannerEngine pointed at a temporary profile/output dir."""
    profile_dir = tmpdir / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "modlist.txt").write_text("+ModA\n")
    return ScannerEngine(
        mods_dir=str(tmpdir / "mods"),
        overwrite_dir=str(tmpdir / "overwrite"),
        profile_dir=str(profile_dir),
        output_dir=str(tmpdir / "metadata"),
    )


def _create_mod_with_nested_files(mod_folder: Path, file_contents: dict):
    """
    Creates nested deployable files at data/subdir/fileN.txt.
    file_contents: {"fileA.txt": "content", ...}
    Files are placed at data/subdir/<name> so path depth >= 2 for fingerprint.
    """
    subdir = mod_folder / "Data" / "subdir"
    subdir.mkdir(parents=True, exist_ok=True)
    for name, content in file_contents.items():
        (subdir / name).write_text(content)


class TestGate2DeepFileDetection(unittest.TestCase):

    def test_gate2_dirty_when_fourth_file_mtime_changes(self):
        """
        POS-03: Mod has 4 nested deployable files (fileA–fileD).
        Only fileD (alphabetically last) changes mtime with SAME size.
        Root mtime is NOT updated (simulated by restoring it after the edit).
        Gate 2 must return dirty=True.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            scanner = _make_scanner(tmpdir)

            mod_folder = tmpdir / "mods" / "ModA"
            file_contents = {
                "fileA.txt": "aaaaaaaaaa",  # 10 bytes
                "fileB.txt": "bbbbbbbbbb",
                "fileC.txt": "cccccccccc",
                "fileD.txt": "dddddddddd",  # This will change mtime, same size
            }
            _create_mod_with_nested_files(mod_folder, file_contents)

            # Capture initial fingerprint via Gate 3 scan
            layer_a_entry = scanner._gate3_scan_mod("ModA", mod_folder)

            # Record root mtime BEFORE touching fileD
            root_mtime_before = mod_folder.stat().st_mtime

            # Simulate changing fileD content while preserving size (same content length)
            file_d = mod_folder / "Data" / "subdir" / "fileD.txt"
            file_d.write_text("DDDDDDDDDD")  # same length, different content → new mtime

            # Restore root directory mtime to simulate Windows not updating parent dir mtime
            os.utime(mod_folder, (root_mtime_before, root_mtime_before))
            # Also restore meta.ini mtime (absent here, so it stays 0)

            # Gate 2 must detect the change
            is_dirty = scanner._gate2_mod_dirty("ModA", mod_folder, layer_a_entry)
            self.assertTrue(is_dirty,
                "Gate 2 must return dirty when fileD's mtime changes "
                "even though root_mtime was restored and file is not in first-3 sample")

    def test_gate2_clean_when_nothing_changes(self):
        """
        Gate 2 must return clean=False when no files change.
        Verifies the baseline (no false positives).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            scanner = _make_scanner(tmpdir)

            mod_folder = tmpdir / "mods" / "ModA"
            _create_mod_with_nested_files(mod_folder, {
                "fileA.txt": "aaaaaaaaaa",
                "fileB.txt": "bbbbbbbbbb",
                "fileC.txt": "cccccccccc",
                "fileD.txt": "dddddddddd",
            })

            layer_a_entry = scanner._gate3_scan_mod("ModA", mod_folder)

            # No changes — Gate 2 must say clean
            is_dirty = scanner._gate2_mod_dirty("ModA", mod_folder, layer_a_entry)
            self.assertFalse(is_dirty,
                "Gate 2 must return clean when no files change (no false positive)")

    def test_gate2_dirty_when_file_count_changes(self):
        """
        Gate 2 file_count signal: adding a file must trigger dirty.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            scanner = _make_scanner(tmpdir)

            mod_folder = tmpdir / "mods" / "ModA"
            _create_mod_with_nested_files(mod_folder, {
                "fileA.txt": "aaaaaaaaaa",
            })

            layer_a_entry = scanner._gate3_scan_mod("ModA", mod_folder)

            # Add a new file
            (mod_folder / "Data" / "subdir" / "fileE.txt").write_text("eeeeeeeeee")

            is_dirty = scanner._gate2_mod_dirty("ModA", mod_folder, layer_a_entry)
            self.assertTrue(is_dirty, "Gate 2 must be dirty when file_count increases")

    def test_fingerprint_stored_in_gate3_entry(self):
        """
        Gate 3 scan output must contain 'file_fingerprint' key.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            scanner = _make_scanner(tmpdir)

            mod_folder = tmpdir / "mods" / "ModA"
            _create_mod_with_nested_files(mod_folder, {"fileA.txt": "aaaaaaaaaa"})

            entry = scanner._gate3_scan_mod("ModA", mod_folder)

            self.assertIn("file_fingerprint", entry,
                          "_gate3_scan_mod must store file_fingerprint in Layer A entry")
            self.assertIsInstance(entry["file_fingerprint"], str)
            self.assertEqual(len(entry["file_fingerprint"]), 64,
                             "file_fingerprint must be a SHA-256 hex digest (64 chars)")


if __name__ == "__main__":
    unittest.main()
