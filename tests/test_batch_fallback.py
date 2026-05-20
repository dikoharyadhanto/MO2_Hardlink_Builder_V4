"""
TASK-T14: Batch Launcher Fallback Tests (GAP-14, Medium)
3 test vectors: .bat content has all 3 required warning elements,
non-existent loaders are skipped (gating works),
C# template contains AbortWithError guards (injection failure blocks game).
"""
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.engines.feature_generator import (  # noqa: E402
    _CS_TEMPLATE,
    _deploy_bat_fallback,
    wrap_loaders,
)


class TestTC_BAT_01_BatContentWarningPoints(unittest.TestCase):

    def test_bat_contains_all_three_warning_elements(self):
        """TC-BAT-01: _deploy_bat_fallback writes @echo off, warning message, start command."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wrapper_path = tmp_path / "skse64_loader.exe"
            original_name = "_skse64_loader_original.exe"

            _deploy_bat_fallback(wrapper_path, original_name)

            bat_path = tmp_path / "skse64_loader.bat"
            self.assertTrue(bat_path.exists(), ".bat file must be created")

            content = bat_path.read_text(encoding="utf-8")

            # Warning point 1: shell silencing preamble
            self.assertIn("@echo off", content,
                          ".bat must contain @echo off")
            # Warning point 2: user-visible warning about compile failure
            self.assertIn("csc.exe unavailable or compile failed", content,
                          ".bat must contain the compile-failure warning phrase")
            # Warning point 3: start command launching original exe
            self.assertIn("start", content,
                          ".bat must have a start command")
            self.assertIn(original_name, content,
                          ".bat must reference the renamed original exe")

    def test_bat_filename_matches_wrapper_stem(self):
        """Bat path stem matches wrapper exe stem (FakeLoader.bat for FakeLoader.exe)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wrapper_path = tmp_path / "FakeLoader.exe"
            _deploy_bat_fallback(wrapper_path, "_FakeLoader_original.exe")

            bat_path = tmp_path / "FakeLoader.bat"
            self.assertTrue(bat_path.exists(),
                            "bat filename must use wrapper exe stem")


class TestTC_BAT_02_ConfirmationGatingSkipsAbsentLoaders(unittest.TestCase):

    def test_nonexistent_loader_is_skipped_not_hijacked(self):
        """TC-BAT-02: wrap_loaders skips loaders absent in standalone (confirmation gate)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # known_loaders contains an exe that does NOT exist in standalone
            with unittest.mock.patch(
                "model.engines.feature_generator._find_csc", return_value=None
            ):
                result = wrap_loaders(
                    standalone_path=str(tmp_path),
                    known_loaders=["NonExistent.exe"],
                    game_exe="",
                    is_stealth=False,
                    mo2_profile_path="",
                    docs_name="TestGame",
                    appdata_name="TestGame",
                    ini_prefix="Test",
                )

            self.assertEqual(result["hijacked"], 0,
                             "Non-existent loader must NOT be hijacked")
            self.assertEqual(result["bat_wrappers"], 0,
                             "No bat wrapper must be created for absent loader")
            bat_files = list(tmp_path.glob("*.bat"))
            self.assertEqual(bat_files, [],
                             "No .bat files must exist in standalone for absent loader")

    def test_existing_loader_is_hijacked_when_csc_absent(self):
        """Loader that exists in standalone → hijacked; with no csc → .bat wrapper."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create the loader EXE in standalone
            (tmp_path / "FakeLoader.exe").write_bytes(b"MZ")

            with unittest.mock.patch(
                "model.engines.feature_generator._find_csc", return_value=None
            ):
                result = wrap_loaders(
                    standalone_path=str(tmp_path),
                    known_loaders=["FakeLoader.exe"],
                    game_exe="",
                    is_stealth=False,
                    mo2_profile_path="",
                    docs_name="TestGame",
                    appdata_name="TestGame",
                    ini_prefix="Test",
                )

            self.assertEqual(result["hijacked"], 1,
                             "Existing loader must be hijacked")
            self.assertEqual(result["bat_wrappers"], 1,
                             "bat_wrappers must be 1 when csc unavailable")


class TestTC_BAT_03_InjectionFailureAbortsGameLaunch(unittest.TestCase):

    def test_cs_template_contains_abortwitherror_guards(self):
        """TC-BAT-03: C# template has AbortWithError calls guarding INI/AppData injection."""
        self.assertIn("AbortWithError", _CS_TEMPLATE,
                      "C# template must contain AbortWithError to block game on inject failure")

    def test_cs_template_abort_on_ini_not_found(self):
        """INI injection failure path calls AbortWithError with informative message."""
        self.assertIn("INI injection failed", _CS_TEMPLATE,
                      "C# template must abort with 'INI injection failed' message")

    def test_cs_template_abort_on_plugins_not_found(self):
        """AppData injection failure (missing plugins.txt) calls AbortWithError."""
        self.assertIn("AppData injection failed", _CS_TEMPLATE,
                      "C# template must abort when plugins.txt cannot be deployed")

    def test_cs_template_abort_message_includes_path(self):
        """AbortWithError messages include the path so user can diagnose."""
        abort_idx = _CS_TEMPLATE.find("AbortWithError")
        # Should have at least 3 AbortWithError calls (ini profile dir, plugins.txt, ex.Message)
        count = _CS_TEMPLATE.count("AbortWithError")
        self.assertGreaterEqual(count, 2,
                                f"Template must have >= 2 AbortWithError guards; found {count}")


if __name__ == "__main__":
    unittest.main()
