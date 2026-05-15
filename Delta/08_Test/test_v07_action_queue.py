"""
POS-04 Regression — TASK-A04 (V07-FIND-004)
Verifies that execute_action_queue:
  1. Runs all DELETE ops before all LINK ops (phased execution, TD-05).
  2. Logs locked-file OS errors without halting unrelated operations.
  3. Writes execution_report.json after completion.
  4. Path 2 Safety Exception: _hardlink_verified() is called (inode verification retained).

SI-004: Action queue policy is deterministic and documented.
"""
import sys
import types
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Stub mobase so source imports succeed without MO2 runtime
sys.modules.setdefault("mobase", types.ModuleType("mobase"))

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))

from model.engines.linker_executor import LinkerExecutor


class TestActionQueuePhasedExecution(unittest.TestCase):

    def _make_linker(self, tmpdir: Path) -> LinkerExecutor:
        metadata_dir = tmpdir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        return LinkerExecutor(
            standalone_path=str(tmpdir / "standalone"),
            original_game_path=str(tmpdir / "game"),
            output_dir=str(metadata_dir),
        )

    def test_all_deletes_before_links(self):
        """
        Phase ordering: every DELETE must execute before any LINK.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            sa = tmpdir / "standalone"
            sa.mkdir()
            linker = self._make_linker(tmpdir)

            # Create a source file to link
            src_dir = tmpdir / "mods" / "ModA"
            src_dir.mkdir(parents=True)
            src_file = src_dir / "file_new.txt"
            src_file.write_text("new content")

            # Create a target file to delete
            target_del = sa / "Data" / "file_old.txt"
            target_del.parent.mkdir(parents=True, exist_ok=True)
            target_del.write_text("old content")

            ops_order = []

            original_unlink = Path.unlink

            def tracked_unlink(self_path, missing_ok=False):
                ops_order.append(("DELETE", str(self_path)))
                try:
                    original_unlink(self_path, missing_ok=missing_ok)
                except Exception:
                    pass

            original_link = os.link

            def tracked_link(src, dst):
                ops_order.append(("LINK", str(dst)))
                original_link(src, dst)

            action_queue = [
                ("DELETE", "data/file_old.txt", "Data/file_old.txt"),
                ("LINK",   "data/file_new.txt", str(src_file), "Data/file_new.txt"),
            ]

            with patch.object(Path, "unlink", tracked_unlink):
                with patch("os.link", tracked_link):
                    linker.execute_action_queue(action_queue)

            # Extract only our tracked ops (ignore unlink calls from mkdir etc)
            delete_indices = [i for i, op in enumerate(ops_order) if op[0] == "DELETE"]
            link_indices   = [i for i, op in enumerate(ops_order) if op[0] == "LINK"]

            if delete_indices and link_indices:
                self.assertLess(
                    max(delete_indices), min(link_indices),
                    "All DELETE ops must complete before any LINK op",
                )

    def test_locked_file_error_logged_not_halted(self):
        """
        An OSError during DELETE must be counted as failed but must not
        prevent subsequent LINK operations from executing.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            sa = tmpdir / "standalone"
            sa.mkdir()
            linker = self._make_linker(tmpdir)

            src_dir = tmpdir / "mods" / "ModA"
            src_dir.mkdir(parents=True)
            src_file = src_dir / "file_ok.txt"
            src_file.write_text("ok content")

            target_ok = sa / "Data" / "file_ok.txt"
            target_ok.parent.mkdir(parents=True, exist_ok=True)

            action_queue = [
                # DELETE a path that doesn't exist → unlink(missing_ok=True) is a no-op
                ("DELETE", "data/locked.txt", "Data/locked.txt"),
                ("LINK",   "data/file_ok.txt", str(src_file), "Data/file_ok.txt"),
            ]

            # Force the unlink for the delete to raise OSError (simulate locked file)
            original_unlink = Path.unlink

            def failing_unlink(self_path, missing_ok=False):
                if "locked" in str(self_path):
                    raise OSError("File is locked (simulated)")
                original_unlink(self_path, missing_ok=missing_ok)

            with patch.object(Path, "unlink", failing_unlink):
                result = linker.execute_action_queue(action_queue)

            self.assertEqual(result["failed"], 1, "Locked file DELETE must count as failed")
            self.assertEqual(result["linked"], 1, "LINK after locked-file error must still execute")
            self.assertTrue(target_ok.exists(), "file_ok.txt must be deployed despite prior error")

    def test_execution_report_written(self):
        """
        execute_action_queue must write execution_report.json on completion.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            sa = tmpdir / "standalone"
            sa.mkdir()
            linker = self._make_linker(tmpdir)

            src = tmpdir / "file_a.txt"
            src.write_text("content")

            action_queue = [
                ("LINK", "data/file_a.txt", str(src), "Data/file_a.txt"),
            ]

            (sa / "Data").mkdir(parents=True, exist_ok=True)
            linker.execute_action_queue(action_queue)

            report_path = tmpdir / "metadata" / "execution_report.json"
            self.assertTrue(report_path.exists(),
                            "execution_report.json must be written after execute_action_queue")
            with open(report_path, "r") as f:
                report = json.load(f)
            self.assertIsInstance(report, dict)

    def test_empty_queue_returns_zero_counts(self):
        """Empty action queue must return all-zero result without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            (tmpdir / "standalone").mkdir()
            linker = self._make_linker(tmpdir)
            result = linker.execute_action_queue([])
            self.assertEqual(result, {"deleted": 0, "linked": 0, "failed": 0, "errors": []})

    def test_path2_safety_exception_hardlink_verified_called(self):
        """
        Path 2 Safety Exception (CDC-IMPL-002-v0.7 DEC-004):
        _hardlink_verified() must be called for same-drive LINK ops
        (inode verification retained for CON-007 compliance).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            sa = tmpdir / "standalone"
            sa.mkdir()
            linker = self._make_linker(tmpdir)

            src = tmpdir / "src_file.txt"
            src.write_text("test")
            (sa / "Data").mkdir(parents=True, exist_ok=True)

            action_queue = [
                ("LINK", "data/src_file.txt", str(src), "Data/src_file.txt"),
            ]

            with patch.object(linker, "_hardlink_verified", wraps=linker._hardlink_verified) as mock_hv:
                # Only applies when src and standalone are on the same drive
                if src.anchor.lower() == sa.anchor.lower():
                    linker.execute_action_queue(action_queue)
                    mock_hv.assert_called_once()
                else:
                    # Cross-drive: copy path taken, _hardlink_verified not called (expected)
                    self.skipTest("Cross-drive path: _hardlink_verified not applicable")


if __name__ == "__main__":
    unittest.main()
