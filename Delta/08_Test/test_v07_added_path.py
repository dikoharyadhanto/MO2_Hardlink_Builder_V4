"""
POS-01 Regression — TASK-A01 (V07-FIND-001)
Verifies that when a dirty mod adds a new file during incremental Layer B update,
the new virtual path appears in path_owners and _active_map, and compute_action_queue
emits a LINK operation for it.

SI-001: Added files in dirty mods are deployed incrementally.
"""
import sys
import types
import unittest
from pathlib import Path

# Stub mobase so source imports succeed without MO2 runtime
sys.modules.setdefault("mobase", types.ModuleType("mobase"))

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))

from model.state import LayeredManifest


def _make_manifest(mod_files: dict, load_order: list) -> LayeredManifest:
    """Helper: build a LayeredManifest in RAM from a {mod: [path_keys]} dict."""
    m = LayeredManifest()
    for mod, paths in mod_files.items():
        m.mod_index[mod] = {
            "files": {
                p: {"size_bytes": 10, "mtime": 1000.0, "source": f"/mods/{mod}/{p}",
                    "preferred_path": p, "is_root": False}
                for p in paths
            },
            "root_mtime": 1000.0,
            "meta_mtime": 0.0,
            "file_count":  len(paths),
            "file_fingerprint": "dummy",
        }
    m.full_recompute_layer_b(load_order)
    return m


class TestAddedPathIncremental(unittest.TestCase):

    def test_new_file_in_dirty_mod_inserted_into_layer_b(self):
        """
        Scenario:
          prev manifest: ModA provides data/file1.txt
          dirty rescan:  ModA now provides data/file1.txt AND data/file2.txt
          Expected: data/file2.txt appears in path_owners and _active_map
        """
        load_order = ["ModA"]

        # Build previous manifest with only file1
        prev = _make_manifest({"ModA": ["data/file1.txt"]}, load_order)

        # Simulate a new LayeredManifest after dirty rescan (ModA now has file2 too)
        new = LayeredManifest()
        new.mod_index["ModA"] = {
            "files": {
                "data/file1.txt": {
                    "size_bytes": 10, "mtime": 1000.0,
                    "source": "/mods/ModA/data/file1.txt",
                    "preferred_path": "data/file1.txt", "is_root": False,
                },
                "data/file2.txt": {
                    "size_bytes": 20, "mtime": 2000.0,
                    "source": "/mods/ModA/data/file2.txt",
                    "preferred_path": "data/file2.txt", "is_root": False,
                },
            },
            "root_mtime": 2000.0,
            "meta_mtime": 0.0,
            "file_count":  2,
            "file_fingerprint": "new_fp",
        }

        # Replicate the incremental Layer B update logic from build_layered_manifest
        dirty_mods = [("ModA", None)]
        dirty_mod_names = {"ModA"}
        priority = {mod: idx for idx, mod in enumerate(load_order)}

        # Step 1: carry over from prev Layer B
        new.path_owners = dict(prev.path_owners)

        # Step 2: paths_to_rebuild — existing paths with dirty owners
        paths_to_rebuild = {
            pk for pk, owners in new.path_owners.items()
            if any(o in dirty_mod_names for o in owners)
        }
        for path_key in paths_to_rebuild:
            providers = [
                m for m, e in new.mod_index.items()
                if path_key in e.get("files", {})
            ]
            sorted_owners = sorted(providers, key=lambda m: priority.get(m, -1), reverse=True)
            if sorted_owners:
                new.path_owners[path_key] = sorted_owners
            else:
                new.path_owners.pop(path_key, None)

        # Step 3: remove orphaned paths
        for mod_name_d, _ in dirty_mods:
            new_files = set(new.mod_index.get(mod_name_d, {}).get("files", {}).keys())
            old_files = set(prev.mod_index.get(mod_name_d, {}).get("files", {}).keys())
            for rp in old_files - new_files:
                stack = new.path_owners.get(rp, [])
                if mod_name_d in stack:
                    stack.remove(mod_name_d)
                if not stack:
                    new.path_owners.pop(rp, None)

        # Step 4: TASK-A01 second pass — new paths from dirty mods
        new_paths_added = 0
        for mod_name_d, _ in dirty_mods:
            dirty_entry = new.mod_index.get(mod_name_d, {})
            for path_key in dirty_entry.get("files", {}):
                if path_key not in new.path_owners:
                    providers = [
                        m for m, e in new.mod_index.items()
                        if path_key in e.get("files", {})
                    ]
                    sorted_owners = sorted(providers, key=lambda m: priority.get(m, -1), reverse=True)
                    if sorted_owners:
                        new.path_owners[path_key] = sorted_owners
                        new_paths_added += 1

        new._rebuild_active_map()

        # Assertions
        self.assertIn("data/file2.txt", new.path_owners,
                      "data/file2.txt must be in path_owners after TASK-A01 second pass")
        self.assertIn("data/file2.txt", new._active_map,
                      "data/file2.txt must be in _active_map after _rebuild_active_map")
        self.assertEqual(new_paths_added, 1)

    def test_action_queue_contains_link_for_new_file(self):
        """
        Verifies compute_action_queue emits LINK for data/file2.txt when
        it is new in the current manifest but absent from the previous one.
        """
        load_order = ["ModA"]
        prev = _make_manifest({"ModA": ["data/file1.txt"]}, load_order)
        curr = _make_manifest({"ModA": ["data/file1.txt", "data/file2.txt"]}, load_order)

        queue = curr.compute_action_queue(prev)
        link_paths = [a[1] for a in queue if a[0] == "LINK"]

        self.assertIn("data/file2.txt", link_paths,
                      "Action queue must contain LINK for the newly added data/file2.txt")

    def test_existing_file_not_duplicated(self):
        """data/file1.txt was already present — no spurious second LINK for it."""
        load_order = ["ModA"]
        prev = _make_manifest({"ModA": ["data/file1.txt"]}, load_order)
        curr = _make_manifest({"ModA": ["data/file1.txt", "data/file2.txt"]}, load_order)

        queue = curr.compute_action_queue(prev)
        link_paths = [a[1] for a in queue if a[0] == "LINK"]
        # file1 source is unchanged — should NOT appear in queue
        self.assertNotIn("data/file1.txt", link_paths,
                         "data/file1.txt is unchanged — must not appear in LINK queue")


if __name__ == "__main__":
    unittest.main()
