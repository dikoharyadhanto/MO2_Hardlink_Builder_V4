"""
TASK-T06: DeploymentTransactionManager Unit Tests (GAP-06, High)
5 test vectors: begin, tick/checkpoint, complete, get_incomplete_state, resume.
"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.state import (  # noqa: E402
    CHECKPOINT_INTERVAL,
    STATE_FILE_NAME,
    DeploymentTransactionManager,
)


def _make_fake_manifest(path: Path, n_entries: int = 10) -> Path:
    """Write a minimal mapping_manifest.json and return its path."""
    manifest = {"version": 1, "mapping": {f"key_{i}": {} for i in range(n_entries)}}
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


class TestTC_CP_01_BeginWritesStateFile(unittest.TestCase):

    def test_begin_creates_state_file_with_correct_fields(self):
        """TC-CP-01: begin() writes .deployment_state with manifest hash + checkpoint=0."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = _make_fake_manifest(tmp_path / "manifest.json")

            tx = DeploymentTransactionManager(str(tmp_path))
            tx.begin(str(manifest_path))

            state_file = tmp_path / STATE_FILE_NAME
            self.assertTrue(state_file.exists(), ".deployment_state must be created")

            state = json.loads(state_file.read_text())
            self.assertIn("manifest_hash", state)
            self.assertTrue(len(state["manifest_hash"]) == 64,
                            "SHA-256 hash must be 64 hex chars")
            self.assertEqual(state["checkpoint_index"], 0)
            self.assertFalse(state["complete"])


class TestTC_CP_02_TickCheckpointsAt500(unittest.TestCase):

    def test_tick_checkpoints_at_interval_boundary(self):
        """TC-CP-02: tick() checkpoints only after CHECKPOINT_INTERVAL calls."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = _make_fake_manifest(tmp_path / "manifest.json")

            tx = DeploymentTransactionManager(str(tmp_path))
            tx.begin(str(manifest_path))

            state_file = tmp_path / STATE_FILE_NAME

            # Call tick CHECKPOINT_INTERVAL - 1 times → must NOT update checkpoint_index
            for i in range(CHECKPOINT_INTERVAL - 1):
                tx.tick(i)

            state = json.loads(state_file.read_text())
            self.assertEqual(state["checkpoint_index"], 0,
                             "checkpoint_index must still be 0 before interval boundary")

            # One more tick → checkpoint written
            tx.tick(CHECKPOINT_INTERVAL - 1)
            state = json.loads(state_file.read_text())
            self.assertEqual(state["checkpoint_index"], CHECKPOINT_INTERVAL - 1,
                             f"checkpoint_index must be updated at tick {CHECKPOINT_INTERVAL - 1}")


class TestTC_CP_03_CompleteRemovesStateFile(unittest.TestCase):

    def test_complete_deletes_state_file(self):
        """TC-CP-03: complete() removes .deployment_state."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = _make_fake_manifest(tmp_path / "manifest.json")

            tx = DeploymentTransactionManager(str(tmp_path))
            tx.begin(str(manifest_path))

            state_file = tmp_path / STATE_FILE_NAME
            self.assertTrue(state_file.exists())

            tx.complete()
            self.assertFalse(state_file.exists(), ".deployment_state must be removed after complete()")


class TestTC_CP_04_GetIncompleteStateAfterInterruption(unittest.TestCase):

    def test_incomplete_state_returned_when_state_file_present(self):
        """TC-CP-04: get_incomplete_state() returns dict after simulated interruption."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = _make_fake_manifest(tmp_path / "manifest.json")

            tx = DeploymentTransactionManager(str(tmp_path))
            tx.begin(str(manifest_path))

            # Simulate checkpoint at file index 600
            for i in range(CHECKPOINT_INTERVAL + 100):
                tx.tick(i)

            # Do NOT call complete() — simulate crash
            tx2 = DeploymentTransactionManager(str(tmp_path))
            state = tx2.get_incomplete_state()

            self.assertIsNotNone(state, "Should detect incomplete deployment")
            self.assertFalse(state.get("complete", True))
            self.assertGreaterEqual(state.get("checkpoint_index", 0), 0)

    def test_no_state_file_returns_none(self):
        """get_incomplete_state() returns None when no state file exists."""
        with tempfile.TemporaryDirectory() as tmp:
            tx = DeploymentTransactionManager(tmp)
            self.assertIsNone(tx.get_incomplete_state())


class TestTC_CP_05_ResumeSkipsAlreadyDeployedFiles(unittest.TestCase):

    def test_checkpoint_index_reflects_resume_point(self):
        """TC-CP-05: After interruption, checkpoint_index indicates where to resume."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = _make_fake_manifest(tmp_path / "manifest.json", n_entries=2000)

            tx = DeploymentTransactionManager(str(tmp_path))
            tx.begin(str(manifest_path))

            # Simulate deploying 600 files then dying
            for i in range(CHECKPOINT_INTERVAL + 100):
                tx.tick(i)
            # crash — no complete()

            resumed_tx = DeploymentTransactionManager(str(tmp_path))
            state = resumed_tx.get_incomplete_state()

            self.assertIsNotNone(state)
            checkpoint = state["checkpoint_index"]
            # Resume should start from checkpoint_index, skipping 0..checkpoint_index-1
            self.assertGreater(checkpoint, 0,
                               "checkpoint_index must reflect partial progress")
            self.assertLess(checkpoint, 2000,
                            "checkpoint_index must be less than total file count")


if __name__ == "__main__":
    unittest.main()
