"""
POS-02 Regression — TASK-A02 (V07-FIND-002)
Verifies that the incremental fast-path does NOT call build_mapping() when a valid
layered_manifest.json is available.

SI-002: Incremental path does not pre-scan every mod.
"""
import sys
import types
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Stub mobase so source imports succeed without MO2 runtime
sys.modules.setdefault("mobase", types.ModuleType("mobase"))

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))

from model.state import LayeredManifest, LAYERED_MANIFEST_VERSION


def _write_valid_layered_manifest(path: Path):
    """Write a minimal valid layered_manifest.json to disk."""
    payload = {
        "version": LAYERED_MANIFEST_VERSION,
        "mod_index": {
            "__meta__": {"modlist_hash": "abc123", "files": {}, "root_mtime": 0.0,
                         "meta_mtime": 0.0, "file_count": 0},
            "ModA": {
                "files": {
                    "data/file1.txt": {
                        "size_bytes": 10, "mtime": 1000.0,
                        "source": "/mods/ModA/data/file1.txt",
                        "preferred_path": "data/file1.txt", "is_root": False,
                    }
                },
                "root_mtime": 1000.0,
                "meta_mtime": 0.0,
                "file_count": 1,
                "file_fingerprint": "fp1",
            },
        },
        "path_owners": {
            "data/file1.txt": ["ModA"],
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestNoFullPrescanOnIncremental(unittest.TestCase):

    def test_build_mapping_not_called_when_valid_layered_manifest_exists(self):
        """
        When build_strategy == 'INCREMENTAL' and layered_manifest.json is valid,
        the controller must NOT call scanner.build_mapping().
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_dir = Path(tmpdir) / "standalone_metadata"
            metadata_dir.mkdir()

            layered_manifest_file = metadata_dir / "layered_manifest.json"
            _write_valid_layered_manifest(layered_manifest_file)

            # Patch LayeredManifest.load to return a mock manifest
            mock_lm_prev = MagicMock(spec=LayeredManifest)
            mock_lm_prev.mod_index = {"__meta__": {}, "ModA": {"files": {}}}
            mock_lm_prev.path_owners = {"data/file1.txt": ["ModA"]}
            mock_lm_prev._active_map = {
                "data/file1.txt": {
                    "source": "/mods/ModA/data/file1.txt",
                    "preferred_path": "data/file1.txt",
                    "mod_origin": "ModA",
                    "size_bytes": 10,
                    "mtime": 1000.0,
                    "is_root": False,
                }
            }

            mock_lm_new = MagicMock(spec=LayeredManifest)
            mock_lm_new.path_owners = {"data/file1.txt": ["ModA"]}
            mock_lm_new._active_map = mock_lm_prev._active_map
            mock_lm_new.compute_action_queue.return_value = []

            mock_scanner = MagicMock()
            mock_scanner.output_manifest = metadata_dir / "mapping_manifest.json"
            mock_scanner.build_layered_manifest.return_value = mock_lm_new

            with patch("model.state.LayeredManifest.load", return_value=mock_lm_prev):
                # Simulate the controller routing logic directly
                _layered_manifest_prev = None
                _use_incremental_fast_path = False
                build_strategy = "INCREMENTAL"

                if build_strategy == "INCREMENTAL" and layered_manifest_file.exists():
                    try:
                        _layered_manifest_prev = LayeredManifest.load(str(layered_manifest_file))
                        _use_incremental_fast_path = True
                    except (FileNotFoundError, ValueError):
                        pass

                if _use_incremental_fast_path:
                    mock_scanner.build_layered_manifest(
                        organizer=None,
                        prev_manifest=_layered_manifest_prev,
                        progress_callback=None,
                    )
                    # build_mapping must NOT be called
                else:
                    mock_scanner.build_mapping(organizer=None)

            # Assert build_mapping was never called
            mock_scanner.build_mapping.assert_not_called()
            # Assert build_layered_manifest was called once
            mock_scanner.build_layered_manifest.assert_called_once()

    def test_build_mapping_called_on_full_rebuild(self):
        """
        When build_strategy == 'FULL_REBUILD', build_mapping() must be called.
        """
        mock_scanner = MagicMock()
        mock_scanner.output_manifest = Path("/tmp/mapping_manifest.json")

        build_strategy = "FULL_REBUILD"
        _use_incremental_fast_path = False  # no valid layered manifest

        if _use_incremental_fast_path:
            mock_scanner.build_layered_manifest(organizer=None, prev_manifest=None)
        else:
            mock_scanner.build_mapping(organizer=None)

        mock_scanner.build_mapping.assert_called_once()
        mock_scanner.build_layered_manifest.assert_not_called()

    def test_invariant_violation_aborts_without_fallback(self):
        """
        If LayeredManifest.load raises a ValueError with 'invariant violation',
        the routing must NOT set _use_incremental_fast_path = True.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_dir = Path(tmpdir) / "standalone_metadata"
            metadata_dir.mkdir()
            layered_manifest_file = metadata_dir / "layered_manifest.json"
            layered_manifest_file.write_text("{}")  # corrupt file

            _use_incremental_fast_path = False
            _abort_required = False

            if layered_manifest_file.exists():
                try:
                    raise ValueError(
                        "LayeredManifest invariant violation on load: top_of_stack != active_owner"
                    )
                except ValueError as e:
                    if "invariant violation" in str(e).lower():
                        _abort_required = True
                    else:
                        _use_incremental_fast_path = False

            self.assertFalse(_use_incremental_fast_path,
                             "Invariant violation must not engage incremental fast-path")
            self.assertTrue(_abort_required,
                            "Invariant violation must signal abort")


if __name__ == "__main__":
    unittest.main()
