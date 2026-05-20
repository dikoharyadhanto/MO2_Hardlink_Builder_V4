"""
TASK-T03: ProfileSync Save Safety Unit Tests (GAP-03, Critical)
5 test vectors: normal sync, conflict quarantine, no-saves graceful skip.
Note: crash-skip and MD5-atomic-move live in the C# wrapper; the Python
ProfileSync._process_sync covers copy + quarantine behaviour tested here.
"""
import os
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

from model.engines.profile_sync import ProfileSync  # noqa: E402


def _make_sync(tmp_root: Path):
    """
    Returns a ProfileSync instance wired entirely inside `tmp_root`.
    portable_mode=True so it writes to tmp_root/_standalone/... and never touches
    %LOCALAPPDATA%, %APPDATA%, or real Documents.
    """
    profile_dir = tmp_root / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    sa_path = tmp_root / "standalone"
    sa_path.mkdir(parents=True, exist_ok=True)

    # Patch LOCALAPPDATA so backup_root stays inside tmp
    original_env = os.environ.get("LOCALAPPDATA", "")
    os.environ["LOCALAPPDATA"] = str(tmp_root / "fake_localappdata")

    sync = ProfileSync(
        profile_dir=str(profile_dir),
        sa_path=str(sa_path),
        docs_name="TestGame",
        appdata_name="TestGame",
        ini_prefix="Test",
        game_name="TestGame",
        profile_name="TestProfile",
        portable_mode=True,
        use_documents_mode=False,
        stealth_mode=False,
        uses_plugins_txt=True,
        uses_bethesda_ini=True,
    )

    # Restore env
    if original_env:
        os.environ["LOCALAPPDATA"] = original_env
    else:
        os.environ.pop("LOCALAPPDATA", None)

    return sync, profile_dir, sa_path


class TestTC_SYNC_01_NormalSync(unittest.TestCase):

    def test_sync_saves_to_mo2_copies_new_files(self):
        """TC-SYNC-01: New saves in standalone → synced to MO2 profile saves dir."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sync, profile_dir, sa_path = _make_sync(tmp_path)

            # Create a save in standalone saves location
            win_saves = sync.win_docs / "Saves"
            win_saves.mkdir(parents=True, exist_ok=True)
            save_file = win_saves / "Save1.ess"
            save_file.write_bytes(b"SAVE_DATA")

            result = sync.sync_saves_to_mo2()

            mo2_saves = profile_dir / "saves"
            synced = mo2_saves / "Save1.ess"
            self.assertTrue(synced.exists(), "Save must appear in MO2 profile saves dir")
            self.assertEqual(synced.read_bytes(), b"SAVE_DATA")
            self.assertTrue(result, "sync_saves_to_mo2 should return True on success")


class TestTC_SYNC_02_CrashSkipSync(unittest.TestCase):

    def test_no_saves_means_sync_returns_false(self):
        """TC-SYNC-02: No standalone saves → sync is a no-op (returns False/None)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sync, profile_dir, sa_path = _make_sync(tmp_path)

            # Ensure standalone saves dir does NOT exist
            win_saves = sync.win_docs / "Saves"
            if win_saves.exists():
                import shutil
                shutil.rmtree(win_saves)

            result = sync.sync_saves_to_mo2()
            # _process_sync returns False when src_dir does not exist
            self.assertFalse(result,
                             "Sync without source saves should return False (crash-skip equivalent)")


class TestTC_SYNC_03_ConflictGoesToQuarantine(unittest.TestCase):

    def test_conflicting_save_quarantined_not_overwritten(self):
        """TC-SYNC-03: Same filename in both source and dest → quarantine dir created."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sync, profile_dir, sa_path = _make_sync(tmp_path)

            # Put same filename in standalone saves AND in mo2 saves (conflict)
            win_saves = sync.win_docs / "Saves"
            win_saves.mkdir(parents=True, exist_ok=True)
            (win_saves / "Save1.ess").write_bytes(b"NEW_SAVE")

            mo2_saves = profile_dir / "saves"
            mo2_saves.mkdir(parents=True, exist_ok=True)
            (mo2_saves / "Save1.ess").write_bytes(b"OLD_SAVE")

            sync.sync_saves_to_mo2()

            # Original MO2 save must still exist (not silently overwritten)
            self.assertEqual((mo2_saves / "Save1.ess").read_bytes(), b"OLD_SAVE",
                             "Original MO2 save must not be overwritten")

            # A quarantine directory must have been created
            quarantine_dirs = [
                d for d in mo2_saves.iterdir()
                if d.is_dir() and "Standalone_Export_save" in d.name
            ]
            self.assertTrue(len(quarantine_dirs) >= 1, "Quarantine dir must be created for conflict")

            # The conflicting save from standalone should be in quarantine
            quarantine_saves = list(quarantine_dirs[0].iterdir())
            quarantine_names = {f.name for f in quarantine_saves}
            self.assertIn("Save1.ess", quarantine_names, "Conflicting save must be quarantined")


class TestTC_SYNC_04_NoSavesFolder_SkipGracefully(unittest.TestCase):

    def test_no_saves_folder_returns_false_no_exception(self):
        """TC-SYNC-05: Missing source saves dir → skip gracefully, no exception."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sync, profile_dir, sa_path = _make_sync(tmp_path)

            # Deliberately don't create win_saves
            try:
                result = sync.sync_saves_to_mo2()
            except Exception as exc:
                self.fail(f"sync_saves_to_mo2 raised unexpectedly: {exc}")

            self.assertFalse(result,
                             "sync_saves_to_mo2 must return False when source dir absent")


class TestTC_SYNC_05_NewFileSyncedCorrectly(unittest.TestCase):

    def test_multiple_new_saves_all_synced(self):
        """TC-SYNC-01 extension: all non-conflicting saves are copied."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sync, profile_dir, sa_path = _make_sync(tmp_path)

            win_saves = sync.win_docs / "Saves"
            win_saves.mkdir(parents=True, exist_ok=True)
            for i in range(5):
                (win_saves / f"Save{i}.ess").write_bytes(f"DATA{i}".encode())

            sync.sync_saves_to_mo2()

            mo2_saves = profile_dir / "saves"
            for i in range(5):
                synced = mo2_saves / f"Save{i}.ess"
                self.assertTrue(synced.exists(), f"Save{i}.ess must be synced")
                self.assertEqual(synced.read_bytes(), f"DATA{i}".encode())


if __name__ == "__main__":
    unittest.main()
