"""
TASK-S06: Save Artifact Lifecycle Tests (FMN-PLAN-v2)
8 test vectors: template pattern assertions (TC-S01 to TC-S05), quarantine
regression (TC-S06), and verify_save_artifacts behavior (TC-S07, TC-S08).
"""
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

from model.engines.feature_generator import _generate_cs_source  # noqa: E402
from model.engines.verification_engine import VerificationEngine  # noqa: E402


def _get_template_source():
    """Return a representative generated C# source for pattern assertions."""
    return _generate_cs_source(
        is_stealth=True,
        mo2_profile_path=r"C:\MO2\profiles\Default",
        docs_name="Skyrim Special Edition",
        game_name="SkyrimSE",
        appdata_name="Skyrim Special Edition",
        ini_prefix="Skyrim",
        uses_plugins_txt=True,
        uses_bethesda_ini=True,
    )


class TestTC_S01_DocsOnlySavesPreserved(unittest.TestCase):

    def test_template_tracks_docs_only_saves(self):
        """TC-S01: Template identifies Documents-only saves and skips them in post-game sync."""
        src = _get_template_source()
        self.assertIn("docsOnlySaves", src,
                      "Template must declare docsOnlySaves list")
        self.assertIn("docs_only_saves", src,
                      "Template must persist docs_only_saves in state JSON")
        self.assertIn("docsOnlySet", src,
                      "Template must build a HashSet from docsOnlySaves for O(1) lookup")

    def test_template_skips_docs_only_in_sync(self):
        """TC-S01: docsOnlySet.Contains check present in transactional save sync loop."""
        src = _get_template_source()
        self.assertIn("docsOnlySet.Contains(rel)", src,
                      "Post-game sync must skip Documents-only saves via docsOnlySet")


class TestTC_S02_DocsOnlySavesRecovery(unittest.TestCase):

    def test_template_recovery_skips_docs_only(self):
        """TC-S02: Recovery path reads docs_only_saves from state and skips those files."""
        src = _get_template_source()
        self.assertIn("docsOnlyRec", src,
                      "Recovery must declare docsOnlyRec set")
        self.assertIn("docsOnlyRec.Contains(rel)", src,
                      "Recovery must skip Documents-only saves")


class TestTC_S03_NormalExitBakCleanup(unittest.TestCase):

    def test_template_cleans_bak_after_normal_sync(self):
        """TC-S03: After post-game save sync, .bak_standalone files are deleted."""
        src = _get_template_source()
        # Verify cleanup block exists after sync
        self.assertIn("TASK-S02", src,
                      "Template must contain TASK-S02 cleanup comment")
        self.assertIn("*.bak_standalone", src,
                      "Template must search for *.bak_standalone files for cleanup")
        self.assertIn("bakCleaned", src,
                      "Template must count and log cleaned .bak_standalone artifacts")

    def test_bak_cleanup_uses_safeDelete(self):
        """TC-S03: Cleanup uses SafeDelete so failures are logged not thrown."""
        src = _get_template_source()
        # SafeDelete appears in the cleanup block context
        bak_cleanup_start = src.find("bakCleaned")
        self.assertGreater(bak_cleanup_start, 0)
        cleanup_context = src[bak_cleanup_start:bak_cleanup_start + 400]
        self.assertIn("SafeDelete", cleanup_context,
                      "Cleanup must use SafeDelete for safe file removal")


class TestTC_S04_RecoveryBakCleanup(unittest.TestCase):

    def test_template_recovery_cleans_bak_after_sync(self):
        """TC-S04: After recovery save sync, .bak_standalone files are removed from source."""
        src = _get_template_source()
        rec_start = src.find("RecoverIfNeeded")
        self.assertGreater(rec_start, 0, "RecoverIfNeeded must exist in template")
        rec_block = src[rec_start:rec_start + 5000]
        self.assertIn("*.bak_standalone", rec_block,
                      "Recovery must clean up .bak_standalone files after sync")


class TestTC_S05_RecoveryExcludesBakArtifacts(unittest.TestCase):

    def test_template_recovery_skips_bak_standalone(self):
        """TC-S05: Recovery never copies .bak_standalone files into MO2 saves."""
        src = _get_template_source()
        rec_start = src.find("RecoverIfNeeded")
        rec_block = src[rec_start:rec_start + 5000]
        self.assertIn(".bak_standalone", rec_block,
                      "Recovery block must reference .bak_standalone")
        # The skip guard must appear before the File.Copy in the recovery sync loop
        bak_skip_idx = rec_block.find("Skip tool-owned backup artifacts")
        copy_idx = rec_block.find("File.Copy(sf, dst, true)")
        self.assertGreater(bak_skip_idx, 0,
                           "Recovery must have .bak_standalone skip guard comment")
        self.assertGreater(copy_idx, bak_skip_idx,
                           "Skip guard must appear before File.Copy in recovery loop")


class TestTC_S06_ConflictQuarantineRegression(unittest.TestCase):

    def test_profile_sync_still_quarantines_conflicts(self):
        """TC-S06: ProfileSync conflict quarantine behavior is not regressed."""
        import os
        from model.engines.profile_sync import ProfileSync

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile_dir = tmp_path / "profile"
            profile_dir.mkdir()
            sa_path = tmp_path / "standalone"
            sa_path.mkdir()

            original_env = os.environ.get("LOCALAPPDATA", "")
            os.environ["LOCALAPPDATA"] = str(tmp_path / "fake_localappdata")
            try:
                sync = ProfileSync(
                    profile_dir=str(profile_dir),
                    sa_path=str(sa_path),
                    docs_name="TestGame",
                    appdata_name="TestGame",
                    ini_prefix="Test",
                    game_name="TestGame",
                    profile_name="TestProfile",
                    portable_mode=True,
                )
            finally:
                if original_env:
                    os.environ["LOCALAPPDATA"] = original_env
                else:
                    os.environ.pop("LOCALAPPDATA", None)

            # Seed conflict: same filename in standalone and MO2
            win_saves = sync.win_docs / "Saves"
            win_saves.mkdir(parents=True, exist_ok=True)
            (win_saves / "Save1.ess").write_bytes(b"NEW_SAVE")

            mo2_saves = profile_dir / "saves"
            mo2_saves.mkdir(parents=True, exist_ok=True)
            (mo2_saves / "Save1.ess").write_bytes(b"OLD_SAVE")

            sync.sync_saves_to_mo2()

            # Original MO2 save must not be silently overwritten
            self.assertEqual(
                (mo2_saves / "Save1.ess").read_bytes(), b"OLD_SAVE",
                "Conflict must not silently overwrite existing MO2 save",
            )
            # A quarantine directory must have been created
            quarantine_dirs = [
                d for d in mo2_saves.iterdir()
                if d.is_dir() and "Standalone_Export_save" in d.name
            ]
            self.assertGreater(
                len(quarantine_dirs), 0,
                "Conflicting save must be quarantined, not overwritten",
            )


class TestTC_S07_VerifyArtifactsFlagsLeftovers(unittest.TestCase):

    def test_bak_standalone_flagged_as_save_issue(self):
        """TC-S07: verify_save_artifacts flags .bak_standalone files as save_issues."""
        with tempfile.TemporaryDirectory() as tmp:
            saves_dir = Path(tmp)
            # Create real saves plus leftover .bak_standalone artifacts
            (saves_dir / "Save1.ess").write_bytes(b"SAVE")
            (saves_dir / "Save1.ess.bak_standalone").write_bytes(b"BAK")
            (saves_dir / "Save2.ess.bak_standalone").write_bytes(b"BAK2")

            ve = VerificationEngine()
            ve.verify_save_artifacts(str(saves_dir), game_not_running=True)

            issues = ve.results["save_issues"]
            self.assertEqual(len(issues), 1, "Exactly one save_issue entry expected")
            issue = issues[0]
            self.assertIn("2", issue["summary"],
                          "Summary must mention count of leftover artifacts")
            self.assertEqual(issue["source"], "SaveArtifactCheck")
            self.assertEqual(len(issue["missing_files"]), 2,
                             "Both .bak_standalone files must be listed")

    def test_subdirectory_bak_standalone_also_flagged(self):
        """TC-S07 extension: .bak_standalone in subdirectory is also caught."""
        with tempfile.TemporaryDirectory() as tmp:
            saves_dir = Path(tmp)
            sub = saves_dir / "subdir"
            sub.mkdir()
            (sub / "Save3.ess.bak_standalone").write_bytes(b"BAK")

            ve = VerificationEngine()
            ve.verify_save_artifacts(str(saves_dir), game_not_running=True)

            self.assertEqual(len(ve.results["save_issues"]), 1)
            self.assertIn("Save3.ess.bak_standalone",
                          ve.results["save_issues"][0]["missing_files"])

    def test_game_running_skips_check(self):
        """TC-S07: When game_not_running=False, no check is performed."""
        with tempfile.TemporaryDirectory() as tmp:
            saves_dir = Path(tmp)
            (saves_dir / "Save1.ess.bak_standalone").write_bytes(b"BAK")

            ve = VerificationEngine()
            ve.verify_save_artifacts(str(saves_dir), game_not_running=False)

            self.assertEqual(ve.results["save_issues"], [],
                             "No check should run while game is running")


class TestTC_S08_VerifyArtifactsPassesClean(unittest.TestCase):

    def test_clean_saves_folder_has_no_issues(self):
        """TC-S08: verify_save_artifacts raises no issues for a clean saves folder."""
        with tempfile.TemporaryDirectory() as tmp:
            saves_dir = Path(tmp)
            (saves_dir / "Save1.ess").write_bytes(b"SAVE")
            (saves_dir / "Save2.ess").write_bytes(b"SAVE2")

            ve = VerificationEngine()
            ve.verify_save_artifacts(str(saves_dir), game_not_running=True)

            self.assertEqual(ve.results["save_issues"], [],
                             "Clean saves folder must produce no save issues")

    def test_empty_saves_folder_has_no_issues(self):
        """TC-S08 extension: empty saves folder produces no issues."""
        with tempfile.TemporaryDirectory() as tmp:
            saves_dir = Path(tmp)

            ve = VerificationEngine()
            ve.verify_save_artifacts(str(saves_dir), game_not_running=True)

            self.assertEqual(ve.results["save_issues"], [])

    def test_nonexistent_path_does_not_raise(self):
        """TC-S08 extension: non-existent path is silently skipped."""
        ve = VerificationEngine()
        try:
            ve.verify_save_artifacts(r"C:\nonexistent\saves\path", game_not_running=True)
        except Exception as exc:
            self.fail(f"verify_save_artifacts raised unexpectedly: {exc}")
        self.assertEqual(ve.results["save_issues"], [])


if __name__ == "__main__":
    unittest.main()
