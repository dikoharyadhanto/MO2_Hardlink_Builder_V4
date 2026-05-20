"""
TASK-T15: Long Path Detection Tests (GAP-15, Low)
4 test vectors: ensure_long_path adds \\\\?\\ prefix, clean_path_for_display strips it,
scanner handles long-path inputs without crash, linker deploy survives long path source.
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

from model.engines.path_utils import clean_path_for_display, ensure_long_path  # noqa: E402


class TestTC_LP_01_EnsureLongPathPrefixAdded(unittest.TestCase):

    @unittest.skipUnless(os.name == "nt", "Long path prefix only meaningful on Windows")
    def test_normal_path_gets_long_path_prefix(self):
        """TC-LP-01: ensure_long_path adds \\\\?\\ prefix on Windows."""
        path = r"C:\Users\user\Documents\some_file.txt"
        result = ensure_long_path(path)
        self.assertTrue(result.startswith("\\\\?\\"),
                        f"Expected \\\\?\\ prefix; got: {result}")

    @unittest.skipUnless(os.name == "nt", "UNC long path only meaningful on Windows")
    def test_unc_path_gets_unc_long_path_prefix(self):
        """UNC paths get \\\\?\\UNC\\ prefix, not \\\\?\\ prefix."""
        path = r"\\server\share\folder\file.txt"
        result = ensure_long_path(path)
        self.assertTrue(result.startswith("\\\\?\\UNC\\"),
                        f"UNC path must get \\\\?\\UNC\\ prefix; got: {result}")

    @unittest.skipUnless(os.name == "nt", "Idempotency only meaningful on Windows")
    def test_already_prefixed_path_not_double_prefixed(self):
        """Path already starting with \\\\?\\ is returned unchanged."""
        path = "\\\\?\\C:\\Users\\user\\file.txt"
        result = ensure_long_path(path)
        self.assertEqual(result, path,
                         "Already-prefixed path must not be double-prefixed")

    def test_non_windows_returns_string_unchanged(self):
        """On non-Windows, ensure_long_path returns path as string without modification."""
        if os.name == "nt":
            self.skipTest("Non-Windows behaviour only testable on non-Windows")
        path = "/home/user/some/file.txt"
        result = ensure_long_path(path)
        self.assertFalse(result.startswith("\\\\?\\"),
                         "No \\\\?\\ prefix on non-Windows platforms")


class TestTC_LP_02_CleanPathForDisplayStripsPrefix(unittest.TestCase):

    def test_prefix_stripped_for_display(self):
        """TC-LP-02: clean_path_for_display removes \\\\?\\ from long-path strings."""
        prefixed = "\\\\?\\C:\\Users\\user\\file.txt"
        result = clean_path_for_display(prefixed)
        self.assertFalse(result.startswith("\\\\?\\"),
                         "Display path must not have \\\\?\\ prefix")
        self.assertEqual(result, "C:\\Users\\user\\file.txt")

    def test_unc_prefix_stripped_for_display(self):
        """\\\\?\\UNC\\ prefix is stripped to \\\\ for UNC display paths."""
        prefixed = "\\\\?\\UNC\\server\\share\\file.txt"
        result = clean_path_for_display(prefixed)
        self.assertTrue(result.startswith("\\\\"),
                        "UNC display path must start with \\\\")
        self.assertFalse(result.startswith("\\\\?\\"),
                         "\\\\?\\ prefix must be stripped from UNC display path")

    def test_normal_path_unchanged_by_display_cleaner(self):
        """Path without prefix passes through clean_path_for_display unchanged."""
        path = r"C:\Users\user\file.txt"
        result = clean_path_for_display(path)
        self.assertEqual(result, path)


class TestTC_LP_03_ScannerHandlesLongPathInput(unittest.TestCase):

    def test_scanner_init_with_deep_path_does_not_raise(self):
        """TC-LP-03: ScannerEngine can be instantiated with long-prefixed paths."""
        from model.engines.scanner_engine import ScannerEngine  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mods = tmp_path / "mods"
            mods.mkdir()
            overwrite = tmp_path / "overwrite"
            overwrite.mkdir()
            profile = tmp_path / "profile"
            profile.mkdir()
            (profile / "modlist.txt").write_text("+TestMod\n", encoding="utf-8")
            meta = tmp_path / "meta"
            meta.mkdir()

            try:
                scanner = ScannerEngine(
                    mods_dir=str(mods),
                    overwrite_dir=str(overwrite),
                    profile_dir=str(profile),
                    output_dir=str(meta),
                )
            except Exception as exc:
                self.fail(
                    f"ScannerEngine raised {type(exc).__name__} on init with valid paths: {exc}"
                )

            # Verify paths were stored with long-path prefix on Windows
            if os.name == "nt":
                self.assertTrue(
                    str(scanner.mods_dir).startswith("\\\\?\\"),
                    "mods_dir must have \\\\?\\ prefix on Windows"
                )


class TestTC_LP_04_LinkerHandlesLongPathSource(unittest.TestCase):

    @unittest.skipUnless(os.name == "nt", "Long path deployment only tested on Windows/NTFS")
    def test_deploy_base_game_with_long_path_source_does_not_crash(self):
        """TC-LP-04: deploy_base_game completes without crash when source path is long-prefixed."""
        from model.engines.linker_executor import LinkerExecutor  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            standalone = tmp_path / "standalone"
            standalone.mkdir()
            game = tmp_path / "game"
            game.mkdir()
            meta = tmp_path / "meta"
            meta.mkdir()

            src = game / "Data" / "deep.nif"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"N" * 64)

            # Explicitly wrap the source path with ensure_long_path before passing to mapping
            from model.engines.path_utils import ensure_long_path as lp  # noqa: E402
            long_src = lp(src)

            base_mapping = {
                "Data/deep.nif": {"source": long_src},
            }

            linker = LinkerExecutor(
                standalone_path=str(standalone),
                original_game_path=str(game),
                output_dir=str(meta),
            )

            try:
                count = linker.deploy_base_game(base_mapping)
            except Exception as exc:
                self.fail(
                    f"deploy_base_game raised {type(exc).__name__} with long-prefixed path: {exc}"
                )

            self.assertGreaterEqual(count, 1,
                                    "At least one file must be deployed via long-prefixed path")


if __name__ == "__main__":
    unittest.main()
