"""
TC-S01 through TC-S12: Scanning refinement test suite (automated cases only; TC-S13 is Director manual).

Covers:
  TC-S01  dir_index seeding on first build
  TC-S02  no-change run avoids full fingerprint traversal
  TC-S03  single dirty subtree limits rescan scope
  TC-S04  deep create/delete (below cached level) still detected
  TC-S05  flat-mod (no subdirectories) fallback
  TC-S06  dir_index version mismatch forces fingerprint fallback
  TC-S07  corrupt/missing dir_index forces fingerprint fallback
  TC-S08  rename/delete/move invalidation
  TC-S09  Smart Incremental parity with Full Verify (multi-scenario)
  TC-S10  conflict winner parity under incremental subtree reuse
  TC-S11  timing logs emitted for all required scan stages
  TC-S12  no source marker files written to mod directories
"""
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.engines.scanner_engine import (  # noqa: E402
    DIR_INDEX_VERSION,
    ScannerEngine,
)
from model.state import LayeredManifest  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_organizer(active_mod_names: list):
    mod_list = MagicMock()
    mod_list.allMods.return_value = list(active_mod_names)
    mod_list.allModsByProfilePriority.return_value = list(active_mod_names)
    mod_list.state.return_value = 0x02
    organizer = MagicMock()
    organizer.modList.return_value = mod_list
    organizer.profile.return_value = MagicMock()
    return organizer


def _write_file(path: Path, content: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    # Push mtime into the past so later _touch_file calls are distinguishable.
    t = path.stat().st_mtime - 3.0
    os.utime(str(path), (t, t))


def _touch_file(path: Path, content: bytes = b"modified") -> None:
    path.write_bytes(content)


class _ScannerBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.mods_dir = self.tmp / "mods"
        self.overwrite_dir = self.tmp / "overwrite"
        self.profile_dir = self.tmp / "profile"
        self.output_dir = self.tmp / "output"
        for d in (self.mods_dir, self.overwrite_dir, self.profile_dir, self.output_dir):
            d.mkdir(parents=True)
        self._modlist_path = self.profile_dir / "modlist.txt"
        self._modlist_path.write_text("+Placeholder\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _engine(self) -> ScannerEngine:
        return ScannerEngine(
            mods_dir=str(self.mods_dir),
            overwrite_dir=str(self.overwrite_dir),
            profile_dir=str(self.profile_dir),
            output_dir=str(self.output_dir),
        )

    def _build(self, mods: list, prev: LayeredManifest = None) -> LayeredManifest:
        eng = self._engine()
        organizer = _make_organizer(mods)
        return eng.build_layered_manifest(organizer=organizer, prev_manifest=prev)

    def _update_modlist(self, mod_names: list) -> None:
        content = "".join(f"+{n}\n" for n in mod_names)
        self._modlist_path.write_text(content, encoding="utf-8")

    def _parity_check(self, incremental: LayeredManifest, full_verify: LayeredManifest,
                      label: str = "", min_keys: int = 1) -> None:
        prefix = f"[{label}] " if label else ""
        self.assertGreaterEqual(
            len(full_verify._active_map), min_keys,
            f"{prefix}full_verify active_map must have at least {min_keys} key(s); got empty map",
        )
        self.assertEqual(
            set(incremental._active_map.keys()),
            set(full_verify._active_map.keys()),
            f"{prefix}parity: active_map key sets differ",
        )
        for k in full_verify._active_map:
            fv = full_verify._active_map[k]
            inc = incremental._active_map[k]
            self.assertEqual(inc.get("mod_origin"), fv.get("mod_origin"),
                             f"{prefix}mod_origin mismatch at {k}")
            self.assertEqual(inc.get("source"), fv.get("source"),
                             f"{prefix}source mismatch at {k}")
            self.assertEqual(inc.get("size_bytes"), fv.get("size_bytes"),
                             f"{prefix}size_bytes mismatch at {k}")
            self.assertAlmostEqual(
                float(inc.get("mtime", 0)), float(fv.get("mtime", 0)),
                places=1, msg=f"{prefix}mtime mismatch at {k}",
            )
        self.assertEqual(
            set(incremental.path_owners.keys()),
            set(full_verify.path_owners.keys()),
            f"{prefix}path_owners key sets differ",
        )
        for k in full_verify.path_owners:
            self.assertEqual(
                incremental.path_owners[k][0],
                full_verify.path_owners[k][0],
                f"{prefix}winning owner differs at {k}",
            )


# ---------------------------------------------------------------------------
# TC-S01: First build seeds dir_index
# ---------------------------------------------------------------------------

class TestTC_S01_FirstBuildSeedsDirIndex(_ScannerBase):

    def test_dir_index_present_after_first_build(self):
        """TC-S01a: mod entry contains dir_index with correct version after fresh build."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "file.esp", b"esp")
        _write_file(mod_dir / "Data" / "Meshes" / "sword.nif", b"nif")
        self._update_modlist(["ModA"])

        result = self._build(["ModA"])

        entry = result.mod_index.get("ModA", {})
        self.assertIn("dir_index", entry)
        self.assertEqual(entry.get("dir_index_version"), DIR_INDEX_VERSION)

    def test_dir_index_includes_root_and_subdirs(self):
        """TC-S01b: dir_index always tracks root ('') and all file ancestor directories."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "a.nif", b"nif")
        _write_file(mod_dir / "Data" / "Textures" / "b.dds", b"dds")
        self._update_modlist(["ModA"])

        result = self._build(["ModA"])

        dir_index = result.mod_index["ModA"]["dir_index"]
        self.assertIn("", dir_index, "root ('') must always be tracked")
        keys_lower = {k.lower() for k in dir_index}
        self.assertTrue(
            any("data" in k for k in keys_lower),
            f"Expected 'data' dir tracked; got: {sorted(dir_index.keys())}",
        )

    def test_dir_index_root_file_count_matches_entry(self):
        """TC-S01c: dir_index root file_count equals the layer-A file_count."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"a")
        _write_file(mod_dir / "Data" / "Meshes" / "b.nif", b"b")
        _write_file(mod_dir / "Data" / "Textures" / "c.dds", b"c")
        self._update_modlist(["ModA"])

        result = self._build(["ModA"])
        entry = result.mod_index["ModA"]
        root_count = entry["dir_index"].get("", {}).get("file_count", -1)
        self.assertEqual(root_count, entry["file_count"])


# ---------------------------------------------------------------------------
# TC-S02: No-change cached run avoids full fingerprint traversal
# ---------------------------------------------------------------------------

class TestTC_S02_NoChangeAvoidsFingerprintCall(_ScannerBase):

    def test_no_dirty_mods_on_unchanged_second_run(self):
        """TC-S02a: active maps are identical between first and no-change second build."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "sword.nif", b"nif")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        second = self._build(["ModA"], prev=first)

        self.assertEqual(first._active_map.keys(), second._active_map.keys())
        for k in first._active_map:
            self.assertEqual(
                first._active_map[k]["mod_origin"],
                second._active_map[k]["mod_origin"],
            )

    def test_fingerprint_not_called_when_dir_index_valid(self):
        """TC-S02b: _gate2_compute_fingerprint is NOT invoked on a clean second run."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "file.esp", b"x")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])

        eng = self._engine()
        call_count = [0]
        original_fp = eng._gate2_compute_fingerprint

        def _counting_fp(folder):
            call_count[0] += 1
            return original_fp(folder)

        eng._gate2_compute_fingerprint = _counting_fp
        eng.build_layered_manifest(
            organizer=_make_organizer(["ModA"]),
            prev_manifest=first,
        )
        self.assertEqual(
            call_count[0], 0,
            f"_gate2_compute_fingerprint must not be called when dir_index is valid; "
            f"was called {call_count[0]} time(s)",
        )


# ---------------------------------------------------------------------------
# TC-S03: Single dirty subtree limits rescan scope
# ---------------------------------------------------------------------------

class TestTC_S03_SingleDirtySubtreeParity(_ScannerBase):

    def test_parity_after_single_subtree_change(self):
        """TC-S03: changing one file in one subtree → incremental matches full verify."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "sword.nif", b"nif_v1")
        _write_file(mod_dir / "Data" / "Textures" / "armor.dds", b"dds_v1")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])

        time.sleep(0.05)
        _touch_file(mod_dir / "Data" / "Meshes" / "sword.nif", b"nif_v2")

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])

        self.assertEqual(
            set(incremental._active_map.keys()),
            set(full_verify._active_map.keys()),
        )
        for k in full_verify._active_map:
            self.assertEqual(
                incremental._active_map[k]["mod_origin"],
                full_verify._active_map[k]["mod_origin"],
                f"mod_origin mismatch at {k}",
            )
            self.assertEqual(
                incremental._active_map[k]["source"],
                full_verify._active_map[k]["source"],
                f"source mismatch at {k}",
            )


# ---------------------------------------------------------------------------
# TC-S04: Deep create/delete below cached level still detected
# ---------------------------------------------------------------------------

class TestTC_S04_DeepMutationDetected(_ScannerBase):

    def test_file_create_at_depth3_detected(self):
        """TC-S04a: creating a file at depth 3 is detected; incremental matches full verify."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "Armor" / "sword.nif", b"v1")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        _write_file(mod_dir / "Data" / "Meshes" / "Armor" / "shield.nif", b"new")

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])

        new_key = "data/meshes/armor/shield.nif"
        self.assertIn(new_key, incremental._active_map,
                      "newly created depth-3 file must appear in incremental result")
        self.assertEqual(
            set(incremental._active_map.keys()),
            set(full_verify._active_map.keys()),
            "incremental must match full verify after deep create",
        )

    def test_file_delete_at_depth3_detected(self):
        """TC-S04b: deleting a file at depth 3 is detected; no orphan stale entry."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "Armor" / "sword.nif", b"v1")
        _write_file(mod_dir / "Data" / "Meshes" / "Armor" / "shield.nif", b"v1")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        (mod_dir / "Data" / "Meshes" / "Armor" / "shield.nif").unlink()

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])

        del_key = "data/meshes/armor/shield.nif"
        self.assertNotIn(del_key, incremental._active_map,
                         "deleted depth-3 file must not appear in incremental result")
        self.assertEqual(
            set(incremental._active_map.keys()),
            set(full_verify._active_map.keys()),
            "incremental must match full verify after deep delete",
        )


# ---------------------------------------------------------------------------
# TC-S05: Flat mod fallback
# ---------------------------------------------------------------------------

class TestTC_S05_FlatModFallback(_ScannerBase):

    def test_flat_mod_dir_index_has_root_entry(self):
        """TC-S05a: flat mod (files only in Data/) gets a dir_index with root entry."""
        mod_dir = self.mods_dir / "FlatMod"
        _write_file(mod_dir / "Data" / "plugin.esp", b"v1")
        self._update_modlist(["FlatMod"])

        result = self._build(["FlatMod"])
        dir_index = result.mod_index.get("FlatMod", {}).get("dir_index", {})
        self.assertIn("", dir_index, "flat mod root must be tracked in dir_index")

    def test_flat_mod_change_detected_and_parity(self):
        """TC-S05b: file change in flat mod is detected; incremental matches full verify."""
        mod_dir = self.mods_dir / "FlatMod"
        _write_file(mod_dir / "Data" / "plugin.esp", b"v1")
        self._update_modlist(["FlatMod"])

        first = self._build(["FlatMod"])
        time.sleep(0.05)
        # Delete + recreate so the parent directory mtime changes (in-place overwrite
        # does not update parent dir mtime on Windows NTFS, making the change undetectable
        # by directory-level dirty tracking)
        (mod_dir / "Data" / "plugin.esp").unlink()
        (mod_dir / "Data" / "plugin.esp").write_bytes(b"v2")

        incremental = self._build(["FlatMod"], prev=first)
        full_verify = self._build(["FlatMod"])

        esp_key = "data/plugin.esp"
        self.assertIn(esp_key, incremental._active_map)
        self.assertAlmostEqual(
            incremental._active_map[esp_key]["mtime"],
            full_verify._active_map[esp_key]["mtime"],
            places=1,
        )


# ---------------------------------------------------------------------------
# TC-S06: Version mismatch forces fingerprint fallback
# ---------------------------------------------------------------------------

class TestTC_S06_VersionMismatchForcesFingerprint(_ScannerBase):

    def test_wrong_dir_index_version_triggers_fingerprint(self):
        """TC-S06: invalid dir_index_version causes fingerprint to be used as fallback."""
        import copy
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "file.esp", b"x")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])

        tampered = copy.deepcopy(first)
        tampered.mod_index["ModA"]["dir_index_version"] = DIR_INDEX_VERSION + 99

        eng = self._engine()
        call_count = [0]
        orig = eng._gate2_compute_fingerprint

        def _count(folder):
            call_count[0] += 1
            return orig(folder)

        eng._gate2_compute_fingerprint = _count
        eng.build_layered_manifest(
            organizer=_make_organizer(["ModA"]),
            prev_manifest=tampered,
        )
        self.assertGreater(
            call_count[0], 0,
            "fingerprint must be called when dir_index_version is invalid",
        )


# ---------------------------------------------------------------------------
# TC-S07: Corrupt / missing dir_index forces fingerprint fallback
# ---------------------------------------------------------------------------

class TestTC_S07_CorruptCacheForcesFingerprint(_ScannerBase):

    def test_missing_dir_index_falls_back_to_fingerprint(self):
        """TC-S07a: absent dir_index in prev entry causes fingerprint to be called."""
        import copy
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "file.esp", b"x")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])

        tampered = copy.deepcopy(first)
        tampered.mod_index["ModA"].pop("dir_index", None)
        tampered.mod_index["ModA"].pop("dir_index_version", None)

        eng = self._engine()
        call_count = [0]
        orig = eng._gate2_compute_fingerprint

        def _count(folder):
            call_count[0] += 1
            return orig(folder)

        eng._gate2_compute_fingerprint = _count
        eng.build_layered_manifest(
            organizer=_make_organizer(["ModA"]),
            prev_manifest=tampered,
        )
        self.assertGreater(
            call_count[0], 0,
            "fingerprint must be called when dir_index is missing",
        )

    def test_malformed_dir_index_does_not_crash(self):
        """TC-S07b: malformed dir_index entries do not crash Gate 2; mod is treated as dirty."""
        import copy
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "file.esp", b"x")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])

        tampered = copy.deepcopy(first)
        tampered.mod_index["ModA"]["dir_index"] = {"data": "not_a_dict"}
        tampered.mod_index["ModA"]["dir_index_version"] = DIR_INDEX_VERSION

        result = self._build(["ModA"], prev=tampered)
        self.assertIn("data/file.esp", result._active_map)


# ---------------------------------------------------------------------------
# TC-S08: Rename / delete / move invalidation
# ---------------------------------------------------------------------------

class TestTC_S08_RenameDeleteInvalidation(_ScannerBase):

    def test_directory_rename_parity(self):
        """TC-S08a: renaming a tracked directory → incremental matches full verify."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "sword.nif", b"v1")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        (mod_dir / "Data" / "Meshes").rename(mod_dir / "Data" / "Models")

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])

        old_key = "data/meshes/sword.nif"
        new_key = "data/models/sword.nif"
        self.assertNotIn(old_key, incremental._active_map,
                         "old key must be gone after directory rename")
        self.assertIn(new_key, incremental._active_map,
                      "new key must appear after directory rename")
        self.assertEqual(
            set(incremental._active_map.keys()),
            set(full_verify._active_map.keys()),
        )

    def test_directory_deletion_parity(self):
        """TC-S08b: deleting a tracked directory → incremental matches full verify."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "Meshes" / "sword.nif", b"v1")
        _write_file(mod_dir / "Data" / "Textures" / "armor.dds", b"v1")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        shutil.rmtree(str(mod_dir / "Data" / "Meshes"))

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])

        self.assertNotIn("data/meshes/sword.nif", incremental._active_map,
                         "files from deleted directory must be gone in incremental")
        self.assertEqual(
            set(incremental._active_map.keys()),
            set(full_verify._active_map.keys()),
        )


# ---------------------------------------------------------------------------
# TC-S09: Smart Incremental parity with Full Verify
# ---------------------------------------------------------------------------

class TestTC_S09_SmartIncrementalParity(_ScannerBase):

    def test_parity_no_change(self):
        """TC-S09a: no changes → incremental matches full verify exactly."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"x")
        _write_file(mod_dir / "Data" / "Meshes" / "b.nif", b"y")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])
        self._parity_check(incremental, full_verify, "no-change")

    def test_parity_add_file(self):
        """TC-S09b: adding a file → incremental matches full verify."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"x")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        _write_file(mod_dir / "Data" / "Meshes" / "new.nif", b"new")

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])
        self._parity_check(incremental, full_verify, "add-file")

    def test_parity_remove_file(self):
        """TC-S09c: removing a file → incremental matches full verify."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"x")
        _write_file(mod_dir / "Data" / "Meshes" / "old.nif", b"old")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        (mod_dir / "Data" / "Meshes" / "old.nif").unlink()

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])
        self._parity_check(incremental, full_verify, "remove-file")

    def test_parity_multi_mod_one_dirty(self):
        """TC-S09d: multi-mod modlist, one mod mutated → incremental matches full verify."""
        for name in ("Alpha", "Beta", "Gamma"):
            mod_dir = self.mods_dir / name
            _write_file(mod_dir / "Data" / f"{name}.esp", b"x")
            _write_file(mod_dir / "Data" / "Meshes" / "shared.nif", b"v1")
        self._update_modlist(["Alpha", "Beta", "Gamma"])

        first = self._build(["Alpha", "Beta", "Gamma"])
        time.sleep(0.05)
        _touch_file(
            self.mods_dir / "Beta" / "Data" / "Meshes" / "shared.nif", b"v2_beta"
        )

        incremental = self._build(["Alpha", "Beta", "Gamma"], prev=first)
        full_verify = self._build(["Alpha", "Beta", "Gamma"])
        self._parity_check(incremental, full_verify, "multi-mod")

    def test_parity_orphan_delete_queue_matches(self):
        """TC-S09e: files removed from a mod don't appear in incremental active_map."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "keep.esp", b"keep")
        _write_file(mod_dir / "Data" / "Meshes" / "remove_me.nif", b"old")
        self._update_modlist(["ModA"])

        first = self._build(["ModA"])
        time.sleep(0.05)
        (mod_dir / "Data" / "Meshes" / "remove_me.nif").unlink()

        incremental = self._build(["ModA"], prev=first)
        full_verify = self._build(["ModA"])

        self.assertNotIn("data/meshes/remove_me.nif", incremental._active_map,
                         "removed file must not appear in incremental active_map")
        self._parity_check(incremental, full_verify, "orphan-delete")


# ---------------------------------------------------------------------------
# TC-S10: Conflict winner parity
# ---------------------------------------------------------------------------

class TestTC_S10_ConflictWinnerParity(_ScannerBase):

    def test_conflict_winner_no_change(self):
        """TC-S10a: conflict winner is identical in incremental and full verify (no change)."""
        shared = "data/meshes/sword.nif"
        for name, content in (("Low", b"low"), ("High", b"high")):
            _write_file(self.mods_dir / name / "Data" / "Meshes" / "sword.nif", content)
        self._update_modlist(["Low", "High"])

        first = self._build(["Low", "High"])
        self.assertEqual(first.path_owners[shared][0], "High")

        incremental = self._build(["Low", "High"], prev=first)
        full_verify = self._build(["Low", "High"])

        self.assertEqual(incremental.path_owners[shared][0], "High")
        self.assertEqual(incremental.path_owners[shared], full_verify.path_owners[shared])

    def test_conflict_winner_after_mutating_winner(self):
        """TC-S10b: after mutating the winning mod, owner stack matches full verify."""
        shared = "data/meshes/sword.nif"
        _write_file(self.mods_dir / "ModA" / "Data" / "Meshes" / "sword.nif", b"a_v1")
        _write_file(self.mods_dir / "ModB" / "Data" / "Meshes" / "sword.nif", b"b_v1")
        self._update_modlist(["ModA", "ModB"])

        first = self._build(["ModA", "ModB"])
        self.assertEqual(first.path_owners[shared][0], "ModB")

        time.sleep(0.05)
        _touch_file(self.mods_dir / "ModB" / "Data" / "Meshes" / "sword.nif", b"b_v2")

        incremental = self._build(["ModA", "ModB"], prev=first)
        full_verify = self._build(["ModA", "ModB"])

        self.assertEqual(
            incremental.path_owners[shared][0],
            full_verify.path_owners[shared][0],
        )
        self.assertEqual(
            incremental._active_map[shared]["source"],
            full_verify._active_map[shared]["source"],
        )


# ---------------------------------------------------------------------------
# TC-S11: Timing logs present
# ---------------------------------------------------------------------------

class TestTC_S11_TimingLogsPresent(_ScannerBase):

    def test_all_required_stage_timing_logs_emitted(self):
        """TC-S11: build_layered_manifest emits named timing logs for all required stages."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"x")
        self._update_modlist(["ModA"])

        eng = self._engine()
        log_messages: list = []

        class _Capture(logging.Handler):
            def emit(self, record):
                log_messages.append(record.getMessage())

        handler = _Capture()
        scanner_logger = logging.getLogger("model.engines.scanner_engine")
        scanner_logger.addHandler(handler)
        scanner_logger.setLevel(logging.DEBUG)

        try:
            eng.build_layered_manifest(
                organizer=_make_organizer(["ModA"]),
                prev_manifest=None,
            )
        finally:
            scanner_logger.removeHandler(handler)

        combined = "\n".join(log_messages)
        for stage in ("Gate1", "Gate2", "Gate3", "Layer B"):
            self.assertIn(stage, combined, f"Expected timing log for stage '{stage}'")

        timing_pattern = re.compile(r"\[\d+\.\d+s\]")
        self.assertTrue(
            timing_pattern.search(combined),
            "Expected at least one '[X.XXXs]' timing value in scanner logs",
        )


# ---------------------------------------------------------------------------
# TC-S12: No source marker files written to mod directories
# ---------------------------------------------------------------------------

class TestTC_S12_NoMarkerFilesInModSource(_ScannerBase):

    def _mod_files(self, mod_dir: Path) -> set:
        return {str(p.relative_to(mod_dir)) for p in mod_dir.rglob("*") if p.is_file()}

    def test_no_files_written_during_first_build(self):
        """TC-S12a: fresh build writes no files into mod source directories."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"x")
        _write_file(mod_dir / "Data" / "Meshes" / "b.nif", b"y")
        before = self._mod_files(mod_dir)

        self._update_modlist(["ModA"])
        self._build(["ModA"])

        after = self._mod_files(mod_dir)
        self.assertEqual(after - before, set(),
                         f"No files should be written into mod source dirs; found: {after - before}")

    def test_no_files_written_during_incremental_build(self):
        """TC-S12b: incremental build writes no files into mod source directories."""
        mod_dir = self.mods_dir / "ModA"
        _write_file(mod_dir / "Data" / "a.esp", b"x")
        before = self._mod_files(mod_dir)

        self._update_modlist(["ModA"])
        first = self._build(["ModA"])
        self._build(["ModA"], prev=first)

        after = self._mod_files(mod_dir)
        self.assertEqual(after - before, set(),
                         f"No files should be written during incremental scan; found: {after - before}")


# ---------------------------------------------------------------------------
# TC-S14: Non-standard source layouts — Root/ and non-Data subfolder
# ---------------------------------------------------------------------------

class TestTC_S14_NonStandardSourceLayouts(_ScannerBase):
    """
    Verifies that dir_index tracks physical source directories, not virtual target keys.
    Root/ layout files (mapped to the virtual root, key has no 'root' prefix) and files
    in non-Data subfolders must be tracked via their real on-disk directory paths so that
    dirty detection fires correctly.
    """

    def test_root_layout_dir_index_tracks_physical_source_dir(self):
        """TC-S14a: Root/ layout — dir_index must track 'root/scripts', not virtual 'scripts'."""
        mod_dir = self.mods_dir / "RootMod"
        _write_file(mod_dir / "Root" / "scripts" / "myscript.pex", b"v1")
        self._update_modlist(["RootMod"])

        result = self._build(["RootMod"])
        dir_index = result.mod_index.get("RootMod", {}).get("dir_index", {})

        self.assertIn("root", dir_index,
                      "Root/ layout: physical 'root' dir must be tracked in dir_index")
        self.assertIn("root/scripts", dir_index,
                      "Root/ layout: physical 'root/scripts' dir must be tracked in dir_index")
        self.assertNotIn("scripts", dir_index,
                         "Root/ layout: virtual 'scripts' key must NOT appear in dir_index "
                         "(dir_index must follow physical source layout, not virtual target keys)")

    def test_root_layout_change_detected_and_parity(self):
        """TC-S14b: adding a file to Root/scripts/ is detected; incremental matches full verify."""
        mod_dir = self.mods_dir / "RootMod"
        _write_file(mod_dir / "Root" / "scripts" / "script1.pex", b"v1")
        self._update_modlist(["RootMod"])

        first = self._build(["RootMod"])
        time.sleep(0.05)
        _write_file(mod_dir / "Root" / "scripts" / "script2.pex", b"new")

        incremental = self._build(["RootMod"], prev=first)
        full_verify = self._build(["RootMod"])

        self.assertIn("scripts/script2.pex", incremental._active_map,
                      "new Root/ file must appear in incremental active_map")
        self._parity_check(incremental, full_verify, "root-layout", min_keys=2)

    def test_non_data_subfolder_dir_index_tracks_physical_source_dir(self):
        """TC-S14c: non-Data subfolder — dir_index must track the real physical dir, not data/xxx."""
        mod_dir = self.mods_dir / "CustomMod"
        _write_file(mod_dir / "CustomFolder" / "custom.txt", b"data")
        self._update_modlist(["CustomMod"])

        result = self._build(["CustomMod"])
        dir_index = result.mod_index.get("CustomMod", {}).get("dir_index", {})

        self.assertIn("customfolder", dir_index,
                      "non-Data layout: physical 'customfolder' must be tracked in dir_index")
        self.assertNotIn("data/customfolder", dir_index,
                         "non-Data layout: virtual 'data/customfolder' must NOT appear in dir_index")

    def test_non_data_subfolder_change_detected_and_parity(self):
        """TC-S14d: adding a file to a non-Data subfolder is detected; incremental matches full verify."""
        mod_dir = self.mods_dir / "CustomMod"
        _write_file(mod_dir / "CustomFolder" / "existing.txt", b"v1")
        self._update_modlist(["CustomMod"])

        first = self._build(["CustomMod"])
        time.sleep(0.05)
        _write_file(mod_dir / "CustomFolder" / "new_file.txt", b"new")

        incremental = self._build(["CustomMod"], prev=first)
        full_verify = self._build(["CustomMod"])

        self.assertIn("data/customfolder/new_file.txt", incremental._active_map,
                      "new non-Data file must appear in incremental active_map")
        self._parity_check(incremental, full_verify, "non-data-layout", min_keys=2)


if __name__ == "__main__":
    unittest.main()
