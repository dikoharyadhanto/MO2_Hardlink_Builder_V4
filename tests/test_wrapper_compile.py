"""
TASK-T04: C# Wrapper Compilation Isolation Tests (GAP-04, High)
4 test vectors: csc.exe discovery, template token substitution,
batch fallback generation, .cs source cleanup.
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

from model.engines.feature_generator import (  # noqa: E402
    _CSC_SEARCH_PATHS,
    _CS_TEMPLATE,
    _deploy_bat_fallback,
    _find_csc,
    _generate_cs_source,
    wrap_loaders,
)


class TestTC_WRAP_01_CscExeDiscovery(unittest.TestCase):

    def test_csc_discovery_returns_valid_path_or_none(self):
        """TC-WRAP-01: _find_csc() returns a Path str if found, else None."""
        result = _find_csc()
        if result is not None:
            self.assertTrue(os.path.isfile(result),
                            f"_find_csc() returned non-existent path: {result}")
            self.assertTrue(result.endswith("csc.exe"),
                            "Discovered path must point to csc.exe")
        # None is valid — means no compiler on this machine


class TestTC_WRAP_02_TemplateTokenSubstitution(unittest.TestCase):

    def test_all_tokens_replaced(self):
        """TC-WRAP-02: _generate_cs_source replaces all {ALLCAPS} tokens."""
        src = _generate_cs_source(
            is_stealth=True,
            mo2_profile_path=r"C:\TestProfile",
            docs_name="TestGame",
            game_name="TestGame",
            appdata_name="TestGame",
            ini_prefix="TestIni",
            uses_plugins_txt=True,
            uses_bethesda_ini=True,
        )
        # All expected replacements done
        self.assertIn("true", src,   "IS_STEALTH token must be replaced with 'true'")
        self.assertIn(r"C:\TestProfile", src, "MO2_PROFILE_PATH token must be replaced")
        self.assertIn("TestGame", src, "DOCS_NAME / GAME_NAME must be replaced")
        self.assertIn("TestIni", src, "INI_PREFIX token must be replaced")
        # No raw tokens remaining
        import re
        remaining = re.findall(r"\{[A-Z_]+\}", src)
        self.assertEqual(remaining, [],
                         f"Unreplaced tokens remain in generated C# source: {remaining}")

    def test_stealth_false_injects_false(self):
        """is_stealth=False → 'false' injected for IS_STEALTH."""
        src = _generate_cs_source(
            is_stealth=False,
            mo2_profile_path=r"C:\P",
            docs_name="X",
            game_name="X",
        )
        # The boolean token is the literal C# keyword
        self.assertIn("bool isStealth      = false;", src)


class TestTC_WRAP_03_BatchFallbackWhenAllCscPathsFail(unittest.TestCase):

    def test_bat_fallback_generated_when_no_compiler(self):
        """TC-WRAP-03: wrap_loaders creates .bat when all csc.exe paths are absent."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Create a fake original exe so the hijack path triggers
            fake_loader = "FakeLoader.exe"
            (tmp_path / fake_loader).write_bytes(b"MZ")

            # Patch _find_csc to always return None
            import unittest.mock
            with unittest.mock.patch(
                "model.engines.feature_generator._find_csc", return_value=None
            ):
                result = wrap_loaders(
                    standalone_path=str(tmp_path),
                    known_loaders=[fake_loader],
                    game_exe="",
                    is_stealth=False,
                    mo2_profile_path="",
                    docs_name="TestGame",
                    appdata_name="TestGame",
                    ini_prefix="Test",
                )

            self.assertGreaterEqual(result["bat_wrappers"], 1,
                                    "At least one .bat wrapper must be created")
            bat_files = list(tmp_path.glob("*.bat"))
            self.assertTrue(len(bat_files) >= 1, ".bat file must exist in standalone dir")

            bat_content = bat_files[0].read_text(encoding="utf-8")
            self.assertIn("csc.exe unavailable or compile failed", bat_content,
                          ".bat must contain the expected fallback warning phrase")

    def test_deploy_bat_fallback_creates_bat_with_correct_content(self):
        """TC-WRAP-03 extension: _deploy_bat_fallback produces well-formed .bat."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            wrapper_path = tmp_path / "skse64_loader.exe"
            original_name = "_skse64_loader_original.exe"

            _deploy_bat_fallback(wrapper_path, original_name)

            bat_path = tmp_path / "skse64_loader.bat"
            self.assertTrue(bat_path.exists(), ".bat must be created")
            content = bat_path.read_text(encoding="utf-8")
            self.assertIn(original_name, content, "bat must reference the original exe name")
            self.assertIn("@echo off", content, "bat must have @echo off")


class TestTC_WRAP_04_CsSourceDeleted(unittest.TestCase):

    @unittest.skipIf(_find_csc() is None, "csc.exe not available — skip compilation test")
    def test_cs_source_deleted_after_compilation(self):
        """TC-WRAP-04: No .cs files remain in standalone after wrap_loaders completes."""
        csc = _find_csc()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_loader = "FakeGame.exe"
            (tmp_path / fake_loader).write_bytes(b"MZ")

            wrap_loaders(
                standalone_path=str(tmp_path),
                known_loaders=[fake_loader],
                game_exe="",
                is_stealth=False,
                mo2_profile_path="",
                docs_name="TestGame",
                appdata_name="TestGame",
                ini_prefix="Test",
            )

            cs_files = list(tmp_path.glob("*.cs"))
            self.assertEqual(cs_files, [],
                             f".cs source files must be deleted after compilation; found: {cs_files}")


if __name__ == "__main__":
    unittest.main()
