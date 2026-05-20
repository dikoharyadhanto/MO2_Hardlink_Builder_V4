"""
TASK-T05: Error Attribution Audit — 100% classification coverage (GAP-05, High)
5 test vectors: static audit of raise/logger.error calls + functional fault injection.
"""
import re
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

_ENGINE_DIR = _SRC_ROOT / "model" / "engines"
_FAULT_KEYWORDS = {"TOOL_FAULT", "MOD_FAULT", "ENV_FAULT"}
_ATTRIBUTION_PATTERNS = [re.compile(kw) for kw in _FAULT_KEYWORDS]


def _source_files():
    return list(_SRC_ROOT.rglob("*.py"))


def _has_attribution(line: str) -> bool:
    return any(p.search(line) for p in _ATTRIBUTION_PATTERNS)


def _nearby_context(lines, idx, window=5):
    """Return lines[idx-window : idx+window+1] as a single string."""
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    return "\n".join(f"  {i+start}: {lines[i+start]}" for i in range(end - start))


class TestTC_ERR_01_AllRaisesClassified(unittest.TestCase):

    def test_all_runtime_error_raises_have_attribution(self):
        """TC-ERR-01: Every raise RuntimeError(...) call includes a fault classification."""
        unclassified = []

        for src_file in _source_files():
            try:
                lines = src_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                stripped = line.strip()
                if not (stripped.startswith("raise ") and "RuntimeError" in stripped):
                    continue
                # Check this line and a window around it for classification keywords
                context = _nearby_context(lines, idx, window=3)
                if not _has_attribution(context):
                    unclassified.append(
                        f"{src_file.relative_to(_SRC_ROOT)}:{idx+1}  →  {stripped}"
                    )

        self.assertEqual(
            unclassified, [],
            "Unclassified RuntimeError raises found:\n" + "\n".join(unclassified),
        )


class TestTC_ERR_02_LoggerErrorCallsHaveContext(unittest.TestCase):

    def test_logger_error_calls_not_empty_strings(self):
        """TC-ERR-02: All logger.error(...) calls include a non-trivial message."""
        empty_errors = []

        for src_file in _source_files():
            try:
                lines = src_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for idx, line in enumerate(lines):
                if "logger.error(" not in line and "audit_logger.error(" not in line:
                    continue
                # Heuristic: message shouldn't be an empty string literal
                if re.search(r'logger\.error\(\s*["\']["\']', line):
                    empty_errors.append(
                        f"{src_file.relative_to(_SRC_ROOT)}:{idx+1}  →  {line.strip()}"
                    )

        self.assertEqual(
            empty_errors, [],
            "logger.error() calls with empty messages found:\n" + "\n".join(empty_errors),
        )


class TestTC_ERR_03_ToolFaultOnCorruptManifest(unittest.TestCase):

    def test_layered_manifest_load_raises_on_corrupt_schema(self):
        """TC-ERR-03: Loading corrupt manifest raises ValueError (TOOL_FAULT class)."""
        from model.state import LayeredManifest

        with tempfile.TemporaryDirectory() as tmp:
            corrupt = Path(tmp) / "manifest.json"
            # Write an old-style flat manifest (missing 'mod_index' / 'path_owners')
            corrupt.write_text('{"mapping": {"a/b.dds": {}}}', encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                LayeredManifest.load(str(corrupt))

            msg = str(ctx.exception)
            self.assertIn("full rebuild", msg.lower(),
                          "Error message must instruct user to do a full rebuild")


class TestTC_ERR_04_ModFaultOnScanPermissionError(unittest.TestCase):

    def test_scan_failure_recorded_per_mod_not_raised(self):
        """TC-ERR-04: Inaccessible mod folder is recorded in failed_mods, not raised."""
        from model.engines.scanner_engine import ScannerEngine

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mods_dir = tmp_path / "mods"
            mods_dir.mkdir()
            overwrite = tmp_path / "overwrite"
            overwrite.mkdir()
            profile = tmp_path / "profile"
            profile.mkdir()
            (profile / "modlist.txt").write_text("+TestMod\n", encoding="utf-8")
            output = tmp_path / "meta"
            output.mkdir()

            scanner = ScannerEngine(
                mods_dir=str(mods_dir),
                overwrite_dir=str(overwrite),
                profile_dir=str(profile),
                output_dir=str(output),
            )

            # Create a mod folder but make it scannable — scanner.failed_mods records errors
            mod_folder = mods_dir / "TestMod"
            mod_folder.mkdir()

            # _scan_folder should handle exceptions and store them in failed_mods
            broken_path = mods_dir / "BrokenMod"
            broken_path.mkdir()
            mapping = {}
            # Patch os.walk to simulate permission error on BrokenMod
            import unittest.mock
            import os

            original_walk = os.walk

            def patched_walk(path, *args, **kwargs):
                if "BrokenMod" in str(path):
                    raise PermissionError("Access denied")
                return original_walk(path, *args, **kwargs)

            with unittest.mock.patch("os.walk", side_effect=patched_walk):
                scanner._scan_folder(broken_path, "BrokenMod", mapping)

            self.assertIn("BrokenMod", scanner.failed_mods,
                          "BrokenMod scan failure must be recorded in failed_mods")
            self.assertTrue(len(scanner.failed_mods["BrokenMod"]) >= 1)


class TestTC_ERR_05_EnvFaultOnReadOnlyTarget(unittest.TestCase):

    def test_linker_hardlink_fallback_on_readonly(self):
        """TC-ERR-05: LinkerExecutor falls back to copy (not crash) when hardlink fails."""
        from model.engines.linker_executor import LinkerExecutor

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            game = tmp_path / "game"
            game.mkdir()
            meta = tmp_path / "meta"
            meta.mkdir()

            linker = LinkerExecutor(
                standalone_path=str(standalone),
                original_game_path=str(game),
                output_dir=str(meta),
            )

            # Create source file
            source = tmp_path / "source.nif"
            source.write_bytes(b"MESH" * 64)
            target = standalone / "Data" / "source.nif"
            target.parent.mkdir(parents=True, exist_ok=True)

            # Patch os.link to raise OSError (simulates cross-drive / read-only)
            import unittest.mock
            import shutil

            with unittest.mock.patch("os.link", side_effect=OSError("cross-drive")):
                method = linker._hardlink_verified(source, target)

            # Should have fallen back to copy, not crashed
            self.assertIn("copy", method,
                          f"Expected copy fallback, got: {method}")
            self.assertTrue(target.exists(), "Target file must exist after copy fallback")


if __name__ == "__main__":
    unittest.main()
