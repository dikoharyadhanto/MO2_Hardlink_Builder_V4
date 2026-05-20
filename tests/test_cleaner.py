"""
TASK-T10: CleanerEngine Unit Tests (GAP-10, Medium)
4 test vectors: safety check blocks non-standalone, safety check passes on standalone,
harvest_generated_files, total_cleanup.
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

from model.engines.cleaner_engine import CleanerEngine  # noqa: E402


def _make_cleaner(sa_path, mo2_path, mods_path=None, tmp_root=None):
    """Create CleanerEngine with all path args inside tmp dirs."""
    local_appdata = str(tmp_root / "fake_localappdata") if tmp_root else os.environ.get("LOCALAPPDATA", str(sa_path / "fake_la"))
    appdata = str(tmp_root / "fake_appdata") if tmp_root else os.environ.get("APPDATA", str(sa_path / "fake_ra"))

    orig_la = os.environ.get("LOCALAPPDATA", "")
    orig_ra = os.environ.get("APPDATA", "")
    os.environ["LOCALAPPDATA"] = local_appdata
    os.environ["APPDATA"] = appdata

    engine = CleanerEngine(
        sa_path=str(sa_path),
        mo2_path=str(mo2_path),
        steam_path=None,
        docs_name="TestGame",
        appdata_name="TestGame",
        game_name="TestGame",
        profile_name="TestProfile",
        portable_mode=True,
        mods_path=str(mods_path) if mods_path else None,
        overwrite_path=None,
    )

    os.environ["LOCALAPPDATA"] = orig_la or local_appdata
    os.environ["APPDATA"] = orig_ra or appdata
    return engine


class TestTC_CLN_01_SafetyBlocksNonStandalonePath(unittest.TestCase):

    def test_safety_check_blocks_mo2_as_standalone(self):
        """TC-CLN-01: check_safety() returns is_safe=False when SA is inside MO2 dir."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mo2 = tmp_path / "MO2"
            mo2.mkdir()
            # Standalone INSIDE MO2 — must be blocked
            sa = mo2 / "StandaloneFolder"
            sa.mkdir()

            engine = _make_cleaner(sa, mo2, tmp_root=tmp_path)
            is_safe, msg = engine.check_safety()

            self.assertFalse(is_safe, "SA inside MO2 must be blocked")
            self.assertIn("FORBIDDEN", msg.upper())


class TestTC_CLN_02_SafetyPassesOnStandalonePath(unittest.TestCase):

    def test_safety_check_passes_when_standalone_marker_present(self):
        """TC-CLN-02: check_safety() returns is_safe=True when standalone_metadata exists."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mo2 = tmp_path / "MO2"
            mo2.mkdir()
            sa = tmp_path / "Standalone"
            sa.mkdir()

            # Create standalone_metadata marker
            (sa / "standalone_metadata").write_text("game=TestGame")

            engine = _make_cleaner(sa, mo2, tmp_root=tmp_path)
            is_safe, msg = engine.check_safety()

            self.assertTrue(is_safe, f"Standalone with marker must pass safety; msg: {msg}")

    def test_safety_check_passes_on_separate_dir_without_marker(self):
        """check_safety() passes when SA is a separate, unrelated directory."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mo2 = tmp_path / "MO2"
            mo2.mkdir()
            sa = tmp_path / "Standalone"
            sa.mkdir()

            engine = _make_cleaner(sa, mo2, tmp_root=tmp_path)
            is_safe, msg = engine.check_safety()

            self.assertTrue(is_safe, f"Separate dirs must pass safety; msg: {msg}")


class TestTC_CLN_03_HarvestCopiesGeneratedFiles(unittest.TestCase):

    @unittest.skipUnless(os.name == "nt", "Link count semantics only reliable on NTFS")
    def test_harvest_generated_files_copies_gameplay_generated_files(self):
        """TC-CLN-03: Files with st_nlink==1 (not hardlinked) are harvested."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mo2 = tmp_path / "MO2"
            mo2.mkdir()
            sa = tmp_path / "Standalone"
            sa.mkdir()
            mods = tmp_path / "mods"
            mods.mkdir()

            # Create a file in standalone that was NOT hardlinked (gameplay-generated)
            generated_dir = sa / "Data" / "SKSE" / "Plugins"
            generated_dir.mkdir(parents=True)
            gen_file = generated_dir / "SomePlugin.json"
            gen_file.write_text('{"data": true}', encoding="utf-8")
            # st_nlink == 1 since no hardlink was made

            # Empty manifest (no entries → secondary gate allows everything)
            manifest_path = tmp_path / "manifest.json"
            import json
            manifest_path.write_text(json.dumps({"version": 3, "mapping": {}}))

            engine = _make_cleaner(sa, mo2, mods_path=mods, tmp_root=tmp_path)
            result = engine.harvest_generated_files(str(manifest_path))

            harvest_mod = mods / "standalone_generated_files"
            self.assertGreaterEqual(result["harvested"], 1,
                                    "At least one generated file must be harvested")
            self.assertTrue(harvest_mod.exists(), "standalone_generated_files mod must be created")


class TestTC_CLN_04_TotalCleanupRemovesContents(unittest.TestCase):

    def test_total_cleanup_empties_standalone_directory(self):
        """TC-CLN-04: total_cleanup() removes all files from standalone dir."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mo2 = tmp_path / "MO2"
            mo2.mkdir()
            sa = tmp_path / "Standalone"
            sa.mkdir()

            # Populate standalone with some content
            data_dir = sa / "Data" / "textures"
            data_dir.mkdir(parents=True)
            for i in range(5):
                (data_dir / f"tex_{i}.dds").write_bytes(b"D" * 64)
            (sa / "standalone_metadata").write_text("game=TestGame")

            engine = _make_cleaner(sa, mo2, tmp_root=tmp_path)
            result = engine.total_cleanup()

            self.assertIn(result["status"], ("FINISHED", "PARTIAL_FAILURE"),
                          f"Unexpected status: {result['status']}")
            # The standalone dir itself must still exist (we clean contents, not the dir)
            self.assertTrue(sa.exists(), "Standalone dir itself must survive total_cleanup")

            remaining = list(sa.iterdir())
            self.assertEqual(remaining, [],
                             f"Standalone must be empty after total_cleanup; found: {remaining}")


if __name__ == "__main__":
    unittest.main()
