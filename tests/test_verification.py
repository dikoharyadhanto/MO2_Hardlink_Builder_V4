"""
TASK-T07: VerificationEngine Unit Tests (GAP-07, High)
4 test vectors: missing files, zero-byte, clean deployment, quick inode check.
"""
import json
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

from model.engines.verification_engine import (  # noqa: E402
    TieredVerificationEngine,
    VerificationEngine,
)


def _write_manifest(path: Path, entries: dict) -> None:
    """Write a mapping_manifest.json where entries = {rel_key: {mod_origin, size_bytes, ...}}."""
    manifest = {"version": 3, "mapping": entries}
    path.write_text(json.dumps(manifest), encoding="utf-8")


class TestTC_VER_01_MissingFilesDetected(unittest.TestCase):

    def test_missing_files_flagged(self):
        """TC-VER-01: verify_deployment detects files present in manifest but absent on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            meta_dir = tmp_path / "meta"
            meta_dir.mkdir()

            manifest_path = meta_dir / "mapping_manifest.json"

            # 10 paths declared; only 8 deployed on disk
            entries = {}
            for i in range(10):
                rel_key = f"data/textures/tex_{i:02d}.dds"
                entries[rel_key] = {
                    "mod_origin": "TestMod",
                    "size_bytes": 512,
                    "preferred_path": rel_key.replace("/", "\\"),
                }
                if i < 8:
                    target = standalone / rel_key
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"X" * 512)

            _write_manifest(manifest_path, entries)

            engine = VerificationEngine()
            engine.verify_deployment(
                manifest_path=str(manifest_path),
                standalone_path=str(standalone),
            )

            missing = engine.results["missing_files"]
            self.assertEqual(len(missing), 2,
                             f"Expected 2 missing files, got {len(missing)}: {missing}")
            missing_paths = {m["file"] for m in missing}
            self.assertIn("data/textures/tex_08.dds", missing_paths)
            self.assertIn("data/textures/tex_09.dds", missing_paths)


class TestTC_VER_02_ZeroByteFilesDetected(unittest.TestCase):

    def test_zero_byte_file_flagged_when_manifest_says_nonzero(self):
        """TC-VER-02: File with size 0 on disk but manifest says size > 0 → zero_byte_files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            meta_dir = tmp_path / "meta"
            meta_dir.mkdir()

            rel_key = "data/textures/corrupt.dds"
            entries = {
                rel_key: {
                    "mod_origin": "TestMod",
                    "size_bytes": 1024,   # manifest says 1 KB
                    "preferred_path": rel_key.replace("/", "\\"),
                }
            }
            manifest_path = meta_dir / "mapping_manifest.json"
            _write_manifest(manifest_path, entries)

            # Deploy a 0-byte file
            target = standalone / rel_key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"")    # 0 bytes

            engine = VerificationEngine()
            engine.verify_deployment(
                manifest_path=str(manifest_path),
                standalone_path=str(standalone),
            )

            zeros = engine.results["zero_byte_files"]
            self.assertEqual(len(zeros), 1)
            self.assertEqual(zeros[0]["file"], rel_key)


class TestTC_VER_03_CleanDeploymentProducesNoIssues(unittest.TestCase):

    def test_clean_deployment_zero_issues(self):
        """TC-VER-03: All files present with correct size → all result lists empty."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            meta_dir = tmp_path / "meta"
            meta_dir.mkdir()

            entries = {}
            for i in range(5):
                rel_key = f"data/meshes/mesh_{i}.nif"
                entries[rel_key] = {
                    "mod_origin": "GoodMod",
                    "size_bytes": 256,
                    "preferred_path": rel_key.replace("/", "\\"),
                }
                target = standalone / rel_key
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"N" * 256)

            manifest_path = meta_dir / "mapping_manifest.json"
            _write_manifest(manifest_path, entries)

            engine = VerificationEngine()
            engine.verify_deployment(
                manifest_path=str(manifest_path),
                standalone_path=str(standalone),
            )

            self.assertEqual(engine.results["missing_files"], [])
            self.assertEqual(engine.results["zero_byte_files"], [])


class TestTC_VER_04_TieredQuickCheckInoneParity(unittest.TestCase):

    @unittest.skipUnless(os.name == "nt", "Hardlink inode parity only meaningful on Windows/NTFS")
    def test_quick_check_passes_on_matching_sizes(self):
        """TC-VER-04: TieredVerificationEngine quick check passes on correctly-sized files."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            meta_dir = tmp_path / "meta"
            meta_dir.mkdir()

            source_dir = tmp_path / "mods" / "TestMod"
            source_dir.mkdir(parents=True)

            entries = {}
            for i in range(10):
                rel_key = f"data/textures/t_{i:02d}.dds"
                src = source_dir / f"t_{i:02d}.dds"
                src.write_bytes(b"T" * 128)

                target = standalone / rel_key
                target.parent.mkdir(parents=True, exist_ok=True)
                # Hardlink source → standalone (same inode)
                try:
                    os.link(src, target)
                except OSError:
                    import shutil
                    shutil.copy2(src, target)

                entries[rel_key] = {
                    "mod_origin": "TestMod",
                    "size_bytes": 128,
                    "source": str(src),
                    "preferred_path": rel_key.replace("/", "\\"),
                }

            manifest_path = meta_dir / "mapping_manifest.json"
            _write_manifest(manifest_path, entries)

            tve = TieredVerificationEngine(
                manifest_path=str(manifest_path),
                standalone_path=str(standalone),
            )
            result = tve.run_quick()

            self.assertEqual(result["missing"], [],
                             f"No missing files expected; got: {result['missing']}")
            self.assertEqual(result["mismatches"], [],
                             f"No size mismatches expected; got: {result['mismatches']}")


if __name__ == "__main__":
    unittest.main()
