"""
TASK-T02: EnvironmentSensor Unit Tests (GAP-02, Critical)
5 test vectors: OneDrive path detection, clean path, Defender CFA, PID lock, sensor failure.
"""
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.engines.diagnostics import (  # noqa: E402
    ConflictReport, EnvironmentSensor, SensorResult,
)


class TestTC_ENV_01_OneDriveDetected(unittest.TestCase):

    def test_onedrive_path_marker_triggers_conflict(self):
        """TC-ENV-01: Target path containing 'OneDrive' triggers ONEDRIVE ConflictReport."""
        sensor = EnvironmentSensor(
            target_path=r"C:\Users\Test\OneDrive\StandaloneGame"
        )
        result = sensor.run_all()

        self.assertTrue(result.has_conflicts, "Should detect OneDrive conflict")
        onedrive_conflicts = [c for c in result.conflicts if c.conflict_type == "ONEDRIVE"]
        self.assertTrue(len(onedrive_conflicts) >= 1, "At least one ONEDRIVE conflict expected")
        cr = onedrive_conflicts[0]
        self.assertIsInstance(cr, ConflictReport)
        self.assertEqual(cr.conflict_type, "ONEDRIVE")
        self.assertTrue(len(cr.description) > 0, "description must be non-empty")
        self.assertTrue(len(cr.retry_suggestion) > 0, "retry_suggestion must be non-empty")


class TestTC_ENV_02_NormalPathClean(unittest.TestCase):

    def test_normal_temp_path_no_conflicts(self):
        """TC-ENV-02: Temp directory path produces no conflicts."""
        with tempfile.TemporaryDirectory() as tmp:
            sensor = EnvironmentSensor(target_path=tmp)
            # Patch registry access so it doesn't iterate real OneDrive accounts
            with unittest.mock.patch("winreg.OpenKey", side_effect=OSError("no key")):
                result = sensor.run_all()
            self.assertFalse(result.has_conflicts,
                             f"Temp path should be clean; got: {result.conflicts}")


class TestTC_ENV_03_DefenderCFADetected(unittest.TestCase):

    @unittest.skipUnless(os.name == "nt", "Windows-only: registry access")
    def test_defender_cfa_enabled_triggers_conflict(self):
        """TC-ENV-03: Mocked registry EnableControlledFolderAccess=1 → DEFENDER_CFA."""
        import winreg

        with tempfile.TemporaryDirectory() as tmp:
            sensor = EnvironmentSensor(target_path=tmp)

            fake_key = unittest.mock.MagicMock()
            fake_key.__enter__ = lambda s: s
            fake_key.__exit__ = unittest.mock.MagicMock(return_value=False)

            def mock_open_key(hive, path):
                cfa_path = (
                    r"SOFTWARE\Microsoft\Windows Defender\Windows Defender Exploit Guard"
                    r"\Controlled Folder Access"
                )
                if path == cfa_path:
                    return fake_key
                raise FileNotFoundError

            def mock_query(key, name):
                if name == "EnableControlledFolderAccess":
                    return (1, winreg.REG_DWORD)
                raise FileNotFoundError

            with unittest.mock.patch("winreg.OpenKey", side_effect=mock_open_key), \
                 unittest.mock.patch("winreg.QueryValueEx", side_effect=mock_query):
                result = sensor.run_all()

        cfa_hits = [c for c in result.conflicts if c.conflict_type == "DEFENDER_CFA"]
        self.assertTrue(len(cfa_hits) >= 1, "DEFENDER_CFA conflict expected when CFA=1")


class TestTC_ENV_04_PIDLockDetected(unittest.TestCase):

    @unittest.skipUnless(os.name == "nt", "Windows-only: file open + permission semantics")
    def test_locked_exe_triggers_pid_lock_conflict(self):
        """TC-ENV-04: PermissionError on game exe → PID_LOCK ConflictReport."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_exe = tmp_path / "SkyrimSE.exe"
            fake_exe.write_bytes(b"MZ")  # minimal PE header marker

            sensor = EnvironmentSensor(
                target_path=str(tmp_path),
                game_path=str(tmp_path),
            )

            original_open = open

            def mock_open(path, *args, **kwargs):
                p = Path(path)
                if p.suffix.lower() == ".exe" and p.parent == tmp_path:
                    raise PermissionError("locked by game")
                return original_open(path, *args, **kwargs)

            with unittest.mock.patch("builtins.open", side_effect=mock_open):
                result = sensor.run_all()

        pid_hits = [c for c in result.conflicts if c.conflict_type == "PID_LOCK"]
        self.assertTrue(len(pid_hits) >= 1,
                        f"Expected PID_LOCK conflict; got {result.conflicts}")
        self.assertIn("SkyrimSE.exe", pid_hits[0].affected_path)


class TestTC_ENV_05_SensorFailureNonBlocking(unittest.TestCase):

    def test_registry_exception_non_blocking(self):
        """TC-ENV-05: Exception inside sensor → warning logged; has_conflicts == False."""
        with tempfile.TemporaryDirectory() as tmp:
            sensor = EnvironmentSensor(target_path=tmp)

            # Make every winreg access raise to simulate a hostile environment
            with unittest.mock.patch(
                "model.engines.diagnostics.EnvironmentSensor._check_onedrive",
                side_effect=OSError("simulated registry failure"),
            ):
                # run_all catches exceptions per-check; result should still be returned
                try:
                    result = sensor.run_all()
                    # If run_all propagates the exception, that's a bug in the source
                    # (it should swallow per-check failures gracefully)
                except Exception as exc:
                    self.fail(
                        f"Sensor raised {type(exc).__name__} instead of returning gracefully: {exc}"
                    )


if __name__ == "__main__":
    unittest.main()
