"""
TASK-T01: SI-5 Load Order Parity Test Suite (GAP-01, Critical)
18 test vectors across 6 categories verifying LayeredManifest priority resolution.

Tests operate entirely in RAM — no real mod directories or mobase needed.
"""
import sys
import types
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.state import LayeredManifest  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fe(source="/fake/src", size=1024, mtime=100.0,
        preferred="Data\\file.ext", is_root=False):
    """Create a minimal file-entry dict matching LayeredManifest Layer A schema."""
    return {
        "size_bytes": size,
        "mtime": mtime,
        "source": source,
        "preferred_path": preferred,
        "is_root": is_root,
    }


def _mod_entry(files_dict):
    return {
        "files": files_dict,
        "root_mtime": 0.0,
        "meta_mtime": 0.0,
        "file_count": len(files_dict),
        "file_fingerprint": "deadbeef",
    }


def _build(mods_with_files, load_order):
    """
    Build a LayeredManifest from raw dicts.
    mods_with_files: {mod_name: {path_key: file_entry}}
    load_order: [mod_name_lowest, ..., mod_name_highest]
    """
    m = LayeredManifest()
    for name, files in mods_with_files.items():
        m.mod_index[name] = _mod_entry(files)
    m.full_recompute_layer_b(load_order)
    return m


# ---------------------------------------------------------------------------
# Category (a): Direct File Conflicts
# ---------------------------------------------------------------------------

class TestSI5_A_DirectConflicts(unittest.TestCase):

    def test_SI5_A_01_two_mod_higher_priority_wins(self):
        """SI5-A-01: Mod A (pri 50) > Mod B (pri 30) for same path."""
        pk = "data/textures/armor.dds"
        m = _build(
            {
                "Mod A": {pk: _fe("/A/armor.dds")},
                "Mod B": {pk: _fe("/B/armor.dds")},
            },
            load_order=["Mod B", "Mod A"],   # B=low, A=high
        )
        self.assertEqual(m.path_owners[pk][0], "Mod A")
        self.assertEqual(m._active_map[pk]["mod_origin"], "Mod A")
        self.assertEqual(m._active_map[pk]["source"], "/A/armor.dds")

    def test_SI5_A_02_three_mod_highest_priority_wins(self):
        """SI5-A-02: Three mods (pri 10 / 25 / 40) — pri-40 wins, all three in stack."""
        pk = "data/meshes/sword.nif"
        m = _build(
            {
                "P10": {pk: _fe("/P10/sword.nif")},
                "P25": {pk: _fe("/P25/sword.nif")},
                "P40": {pk: _fe("/P40/sword.nif")},
            },
            load_order=["P10", "P25", "P40"],
        )
        self.assertEqual(m.path_owners[pk][0], "P40")
        self.assertEqual(len(m.path_owners[pk]), 3)
        self.assertEqual(m._active_map[pk]["mod_origin"], "P40")

    def test_SI5_A_03_identical_size_higher_priority_wins(self):
        """SI5-A-03: Byte-identical files — winner is determined by priority, not content."""
        pk = "data/textures/sky.dds"
        m = _build(
            {
                "LowMod":  {pk: _fe("/Low/sky.dds",  size=8192)},
                "HighMod": {pk: _fe("/High/sky.dds", size=8192)},
            },
            load_order=["LowMod", "HighMod"],
        )
        self.assertEqual(m.path_owners[pk][0], "HighMod")
        self.assertEqual(m._active_map[pk]["source"], "/High/sky.dds")


# ---------------------------------------------------------------------------
# Category (b): Override Chains
# ---------------------------------------------------------------------------

class TestSI5_B_OverrideChains(unittest.TestCase):

    def test_SI5_B_01_three_mod_cascade(self):
        """SI5-B-01: Mod X(lo) → Mod Y(mid) → Mod Z(hi); a.dds owned by Y, b.dds by Z."""
        pa = "data/textures/a.dds"
        pb = "data/textures/b.dds"
        m = _build(
            {
                "Mod X": {pa: _fe("/X/a.dds")},
                "Mod Y": {pa: _fe("/Y/a.dds")},
                "Mod Z": {pb: _fe("/Z/b.dds")},
            },
            load_order=["Mod X", "Mod Y", "Mod Z"],
        )
        # a.dds: Y (index 1) beats X (index 0)
        self.assertEqual(m.path_owners[pa][0], "Mod Y")
        self.assertIn("Mod X", m.path_owners[pa])
        # b.dds: only Z
        self.assertEqual(m.path_owners[pb][0], "Mod Z")

    def test_SI5_B_02_empty_mid_chain_mod_absent_from_stacks(self):
        """SI5-B-02: Empty mod B in the chain — B must not appear in any stack."""
        pk = "data/textures/x.dds"
        m = _build(
            {
                "Mod A": {pk: _fe("/A/x.dds")},
                "Mod B": {},               # zero files
                "Mod C": {pk: _fe("/C/x.dds")},
            },
            load_order=["Mod A", "Mod B", "Mod C"],
        )
        self.assertEqual(m.path_owners[pk][0], "Mod C")
        for owners in m.path_owners.values():
            self.assertNotIn("Mod B", owners, "Empty mod must not appear in any stack")

    def test_SI5_B_03_subset_override_action_queue(self):
        """SI5-B-03: Mod B overrides subset of Mod A's files; action queue correct."""
        pa = "data/textures/a.dds"
        pb = "data/textures/b.dds"
        pc = "data/textures/c.dds"

        # Old state: only Mod A provided a/b/c
        old = _build(
            {"Mod A": {pa: _fe("/A/a.dds"), pb: _fe("/A/b.dds"), pc: _fe("/A/c.dds")}},
            load_order=["Mod A"],
        )

        # New state: Mod B (higher) provides a.dds only
        new = _build(
            {
                "Mod A": {pa: _fe("/A/a.dds"), pb: _fe("/A/b.dds"), pc: _fe("/A/c.dds")},
                "Mod B": {pa: _fe("/B/a.dds")},
            },
            load_order=["Mod A", "Mod B"],
        )

        self.assertEqual(new._active_map[pa]["mod_origin"], "Mod B")
        self.assertEqual(new._active_map[pb]["mod_origin"], "Mod A")
        self.assertEqual(new._active_map[pc]["mod_origin"], "Mod A")

        queue = new.compute_action_queue(old)
        link_paths = {op[1] for op in queue if op[0] == "LINK"}
        self.assertIn(pa, link_paths, "a.dds owner changed — must be re-linked")
        self.assertNotIn(pb, link_paths, "b.dds owner unchanged — no LINK needed")
        self.assertNotIn(pc, link_paths, "c.dds owner unchanged — no LINK needed")


# ---------------------------------------------------------------------------
# Category (c): Deactivated Mods
# ---------------------------------------------------------------------------

class TestSI5_C_DeactivatedMods(unittest.TestCase):

    def test_SI5_C_01_disabled_mod_not_in_path_owners(self):
        """SI5-C-01: Disabled mod is excluded from active_mods; its paths absent."""
        pk = "data/textures/disabled.dds"
        # Simulate disabled mod by NOT including it in load_order
        m = _build(
            {
                "ActiveMod":   {pk: _fe("/Active/disabled.dds")},
                "DisabledMod": {pk: _fe("/Disabled/disabled.dds")},
            },
            load_order=["ActiveMod"],   # DisabledMod not in load_order
        )
        self.assertIn(pk, m.path_owners)
        self.assertNotIn("DisabledMod", m.path_owners.get(pk, []))
        self.assertEqual(m._active_map[pk]["mod_origin"], "ActiveMod")

    def test_SI5_C_02_fully_overridden_mod_not_active_owner(self):
        """SI5-C-02: Mod present in load_order but all its files overridden — not active owner."""
        pk = "data/textures/shared.dds"
        m = _build(
            {
                "LowMod":  {pk: _fe("/Low/shared.dds")},
                "HighMod": {pk: _fe("/High/shared.dds")},
            },
            load_order=["LowMod", "HighMod"],
        )
        # LowMod is in mod_index with its file, but not the active owner
        self.assertIn(pk, m.mod_index["LowMod"]["files"])
        self.assertEqual(m.path_owners[pk][0], "HighMod")
        # LowMod has zero entries in _active_map for its overridden files
        low_owned = [p for p, e in m._active_map.items() if e.get("mod_origin") == "LowMod"]
        self.assertEqual(low_owned, [], "All LowMod paths overridden — zero active entries")

    def test_SI5_C_03_disabled_mod_triggers_delete_in_action_queue(self):
        """SI5-C-03: Mod was active; now excluded from load_order → DELETE in queue."""
        pk = "data/textures/orphan.dds"

        # Old state: "OldMod" owned the path
        old = _build({"OldMod": {pk: _fe("/Old/orphan.dds")}}, load_order=["OldMod"])

        # New state: OldMod excluded (disabled); no other mod covers that path
        new = _build({"OldMod": {pk: _fe("/Old/orphan.dds")}}, load_order=[])
        # path_owners is empty because load_order is empty
        self.assertNotIn(pk, new.path_owners)

        queue = new.compute_action_queue(old)
        delete_ops = [op for op in queue if op[0] == "DELETE"]
        self.assertTrue(any(op[1] == pk for op in delete_ops),
                        "Disabled mod's file must produce DELETE in action queue")


# ---------------------------------------------------------------------------
# Category (d): Separator Plugins
# ---------------------------------------------------------------------------

class TestSI5_D_SeparatorPlugins(unittest.TestCase):

    def test_SI5_D_01_separator_not_in_mod_index(self):
        """SI5-D-01: Separator names in load_order produce no mod_index artifact."""
        pk = "data/textures/real.dds"
        # Separators in MO2 modlist.txt start with a name ending in '_separator'.
        # _get_active_mods() filters them via mobase API in production.
        # Here we test that a separator entry with NO files is invisible.
        m = _build(
            {
                "=== My Separator ===": {},     # separator — no files
                "RealMod":             {pk: _fe("/Real/real.dds")},
            },
            load_order=["=== My Separator ===", "RealMod"],
        )
        sep_files = m.mod_index.get("=== My Separator ===", {}).get("files", {})
        self.assertEqual(len(sep_files), 0,
                         "Separator has no files — no file artifacts created")
        self.assertEqual(m.path_owners[pk][0], "RealMod")

    def test_SI5_D_02_consecutive_separators_no_artifacts(self):
        """SI5-D-02: Multiple consecutive separators produce no path_owners entries."""
        pk = "data/meshes/item.nif"
        m = _build(
            {
                "--- Sep 1 ---": {},
                "--- Sep 2 ---": {},
                "--- Sep 3 ---": {},
                "ContentMod":   {pk: _fe("/Content/item.nif")},
            },
            load_order=["--- Sep 1 ---", "--- Sep 2 ---", "--- Sep 3 ---", "ContentMod"],
        )
        for key, owners in m.path_owners.items():
            for sep_name in ["--- Sep 1 ---", "--- Sep 2 ---", "--- Sep 3 ---"]:
                self.assertNotIn(sep_name, owners, f"Separator {sep_name} must not own any path")
        self.assertEqual(m.path_owners[pk][0], "ContentMod")


# ---------------------------------------------------------------------------
# Category (e): BSA / Archive Precedence
# ---------------------------------------------------------------------------

class TestSI5_E_BSAArchivePrecedence(unittest.TestCase):
    """
    The Python scanner does NOT expand BSA archive contents — it registers
    the .bsa file itself as a deployable file entry in Layer A.  These tests
    verify that behaviour: BSA files are tracked and prioritised as regular
    mod files.  Virtual-path expansion within BSA requires the mobase API and
    is handled at the MO2 host level.
    """

    def test_SI5_E_01_bsa_file_registered_as_regular_entry(self):
        """SI5-E-01: .bsa file is a valid deployable entry; higher-priority mod wins."""
        pk_bsa = "data/textures - meshes.bsa"
        m = _build(
            {
                "Mod A": {pk_bsa: _fe("/A/Textures.bsa", size=1_000_000)},
                "Mod B": {pk_bsa: _fe("/B/Textures.bsa", size=1_000_000)},
            },
            load_order=["Mod A", "Mod B"],
        )
        self.assertEqual(m.path_owners[pk_bsa][0], "Mod B",
                         "Higher-priority mod's BSA wins")

    def test_SI5_E_02_bsa_only_mod_registered(self):
        """SI5-E-02: Mod providing only a .bsa — file appears in mod_index."""
        pk_bsa = "data/skyrim.bsa"
        m = _build(
            {"BsaOnlyMod": {pk_bsa: _fe("/BSA/skyrim.bsa")}},
            load_order=["BsaOnlyMod"],
        )
        self.assertIn(pk_bsa, m.path_owners)
        self.assertEqual(m.path_owners[pk_bsa][0], "BsaOnlyMod")
        self.assertEqual(m.mod_index["BsaOnlyMod"]["file_count"], 1)

    def test_SI5_E_03_conflicting_bsa_higher_priority_wins(self):
        """SI5-E-03: Two mods with same BSA filename — higher priority wins."""
        pk_bsa = "data/update.bsa"
        pk_loose = "data/textures/unique.dds"
        m = _build(
            {
                "LowMod":  {pk_bsa: _fe("/Low/update.bsa"),  pk_loose: _fe("/Low/unique.dds")},
                "HighMod": {pk_bsa: _fe("/High/update.bsa")},
            },
            load_order=["LowMod", "HighMod"],
        )
        self.assertEqual(m.path_owners[pk_bsa][0], "HighMod")
        self.assertEqual(m.path_owners[pk_loose][0], "LowMod")


# ---------------------------------------------------------------------------
# Category (f): Empty Mods and Zero-File Mods
# ---------------------------------------------------------------------------

class TestSI5_F_EmptyMods(unittest.TestCase):

    def test_SI5_F_01_zero_deployable_files_no_error(self):
        """SI5_F-01: Mod with only blacklisted files (empty effective set) — no error."""
        # We simulate this by creating a mod_entry with zero files (blacklist already excluded)
        m = _build(
            {"EmptyMod": {}},
            load_order=["EmptyMod"],
        )
        empty_files = m.mod_index["EmptyMod"]["files"]
        self.assertEqual(len(empty_files), 0)
        # No entries in path_owners from EmptyMod
        for owners in m.path_owners.values():
            self.assertNotIn("EmptyMod", owners)

    def test_SI5_F_02_meta_ini_only_mod_zero_files(self):
        """SI5_F-02: Mod with meta.ini only → scanner produces zero entries; no error."""
        # meta.ini is in blacklist_files — never registered
        m = _build({"MetaOnlyMod": {}}, load_order=["MetaOnlyMod"])
        self.assertEqual(m.mod_index["MetaOnlyMod"]["file_count"], 0)
        self.assertEqual(len(m.path_owners), 0)

    def test_SI5_F_03_zero_byte_file_deployed_as_normal_hardlink(self):
        """SI5_F-03: 0-byte file deployed normally; size_bytes=0 recorded in manifest."""
        pk = "data/scripts/empty.pex"
        m = _build(
            {"Mod X": {pk: _fe("/X/empty.pex", size=0)}},
            load_order=["Mod X"],
        )
        self.assertIn(pk, m.path_owners)
        self.assertEqual(m._active_map[pk]["size_bytes"], 0)
        self.assertEqual(m._active_map[pk]["mod_origin"], "Mod X")


if __name__ == "__main__":
    unittest.main()
