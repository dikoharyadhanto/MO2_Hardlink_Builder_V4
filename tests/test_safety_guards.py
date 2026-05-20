"""
TASK-T11: Cross-Contamination Guard Tests (GAP-11, Medium)
4 test vectors: game mismatch blocks, profile mismatch blocks,
matching game+profile allows, no metadata file allows.

The guard lives in BuildWorker.run() (deployment_controller.py) which requires
Qt + mobase at import time. This module mirrors the guard logic as a pure helper
function (_check_contamination_guard) so it can be tested without Qt.
The helper is a faithful copy of the 12-line guard block starting at the
"FEAT-0X: Safety check" comment in BuildWorker.run().
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


# ---------------------------------------------------------------------------
# Helper: mirrors BuildWorker.run() cross-contamination guard exactly
# ---------------------------------------------------------------------------

def _check_contamination_guard(sa_path, game_name: str, profile_name: str):
    """Returns (allowed: bool, error_msg: str)."""
    metadata_file = Path(sa_path) / "standalone_metadata" / "standalone_metadata.json"
    if not metadata_file.exists():
        return True, ""

    with open(metadata_file, "r", encoding="utf-8") as f:
        saved_meta = json.load(f)

    saved_game = saved_meta.get("game_info", {}).get("game_name", "")
    saved_profile = saved_meta.get("mo2_info", {}).get("mo2_profile_name", "")

    if saved_game and saved_profile:
        if saved_game != game_name or saved_profile != profile_name:
            return False, (
                f"Cross-Profile Contamination Risk Detected!\n\n"
                f"Target Standalone was previously built with:\n"
                f"  Game: {saved_game}\n"
                f"  Profile: {saved_profile}\n\n"
                f"Current Active MO2 State:\n"
                f"  Game: {game_name}\n"
                f"  Profile: {profile_name}\n\n"
                f"To prevent severe file corruption, the tool refuses to rebuild in this directory."
            )

    return True, ""


def _write_metadata(sa_path: Path, game_name: str, profile_name: str) -> None:
    """Write a minimal standalone_metadata.json under sa_path/standalone_metadata/."""
    md_dir = sa_path / "standalone_metadata"
    md_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "game_info": {"game_name": game_name},
        "mo2_info": {"mo2_profile_name": profile_name},
    }
    (md_dir / "standalone_metadata.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTC_SAFE_01_GameMismatchBlocksBuild(unittest.TestCase):

    def test_game_mismatch_blocks_build(self):
        """TC-SAFE-01: metadata has game='Skyrim SE'; current='Fallout 4' → blocked."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "Standalone"
            sa.mkdir()
            _write_metadata(sa, "Skyrim Special Edition", "Default")

            allowed, msg = _check_contamination_guard(sa, "Fallout 4", "Default")

            self.assertFalse(allowed, "Game mismatch must block the build")
            self.assertIn("Skyrim Special Edition", msg)
            self.assertIn("Fallout 4", msg)
            self.assertIn("Contamination", msg)


class TestTC_SAFE_02_ProfileMismatchBlocksBuild(unittest.TestCase):

    def test_profile_mismatch_blocks_build(self):
        """TC-SAFE-02: metadata has profile='Profile A'; current='Profile B' → blocked."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "Standalone"
            sa.mkdir()
            _write_metadata(sa, "Skyrim Special Edition", "Profile A")

            allowed, msg = _check_contamination_guard(
                sa, "Skyrim Special Edition", "Profile B"
            )

            self.assertFalse(allowed, "Profile mismatch must block the build")
            self.assertIn("Profile A", msg)
            self.assertIn("Profile B", msg)

    def test_both_mismatched_also_blocked(self):
        """Both game and profile differ → still blocked."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "Standalone"
            sa.mkdir()
            _write_metadata(sa, "Skyrim Special Edition", "Profile A")

            allowed, _ = _check_contamination_guard(sa, "Fallout 4", "Profile B")

            self.assertFalse(allowed, "Any field mismatch must block the build")


class TestTC_SAFE_03_MatchingMetadataAllowsBuild(unittest.TestCase):

    def test_matching_game_and_profile_allows_build(self):
        """TC-SAFE-03: metadata matches current game+profile → build proceeds."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "Standalone"
            sa.mkdir()
            _write_metadata(sa, "Skyrim Special Edition", "Default")

            allowed, msg = _check_contamination_guard(
                sa, "Skyrim Special Edition", "Default"
            )

            self.assertTrue(allowed, f"Matching metadata must allow build; msg: {msg}")
            self.assertEqual(msg, "")


class TestTC_SAFE_04_NoMetadataAllowsBuild(unittest.TestCase):

    def test_no_metadata_file_allows_build(self):
        """TC-SAFE-04: no standalone_metadata.json → build proceeds without check."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "FreshStandalone"
            sa.mkdir()
            # No metadata file created — fresh standalone

            allowed, msg = _check_contamination_guard(
                sa, "Skyrim Special Edition", "Default"
            )

            self.assertTrue(allowed, f"No metadata must allow build; msg: {msg}")

    def test_metadata_dir_exists_but_file_absent_allows_build(self):
        """metadata dir present but .json absent → treated as first build → allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "Standalone"
            sa.mkdir()
            (sa / "standalone_metadata").mkdir()
            # .json not written

            allowed, msg = _check_contamination_guard(
                sa, "Skyrim Special Edition", "Default"
            )

            self.assertTrue(allowed, f"Missing JSON must allow build; msg: {msg}")

    def test_partial_metadata_missing_profile_allows_build(self):
        """metadata.json present but mo2_profile_name empty → guard skips (partial write)."""
        with tempfile.TemporaryDirectory() as tmp:
            sa = Path(tmp) / "Standalone"
            sa.mkdir()
            md_dir = sa / "standalone_metadata"
            md_dir.mkdir()
            # Only game_name set, profile absent
            (md_dir / "standalone_metadata.json").write_text(
                json.dumps({"game_info": {"game_name": "Skyrim Special Edition"}, "mo2_info": {}}),
                encoding="utf-8",
            )

            allowed, msg = _check_contamination_guard(
                sa, "Fallout 4", "Default"
            )

            # Guard requires BOTH fields to be non-empty before blocking
            self.assertTrue(allowed,
                            "Partial metadata (missing profile) must not block build")


if __name__ == "__main__":
    unittest.main()
