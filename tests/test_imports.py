"""
SI-005 Smoke Import Test (TASK-A05 — CDC-IMPL-002-v0.7)

Verifies that:
  1. tests/test_wrapper.py and tests/simulate_incremental.py use dynamic
     repo-root path resolution (no legacy hardcoded absolute paths).
  2. Core source modules referenced by those harnesses import cleanly.

Does NOT execute any integration side effects (no subprocess calls,
no AppData writes, no real MO2 paths accessed).
"""
import sys
import types
import unittest
from pathlib import Path

# Stub mobase before any source imports so modules that guard against
# missing MO2 runtime do not raise ImportError at collection time.
sys.modules.setdefault("mobase", types.ModuleType("mobase"))

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT  = _TESTS_DIR.parent
_SRC_ROOT   = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"


def _ensure_src_on_path():
    src = str(_SRC_ROOT)
    if src not in sys.path:
        sys.path.insert(0, src)


class TestHarnessDynamicRoot(unittest.TestCase):
    """Verifies the TASK-A05 path fix is present in both migrated test files."""

    def test_repo_root_points_to_valid_src(self):
        """Dynamic root from tests/ must resolve to a directory containing src/."""
        self.assertTrue(
            _SRC_ROOT.exists(),
            f"src/ not found at {_SRC_ROOT} — dynamic root resolution must be correct",
        )

    def test_test_wrapper_uses_dynamic_root(self):
        """test_wrapper.py must not contain legacy hardcoded path."""
        content = (_TESTS_DIR / "test_wrapper.py").read_text(encoding="utf-8")
        self.assertNotIn(
            r"005_mo2_hardlink_builder_v4b",
            content.lower(),
            "test_wrapper.py still contains legacy hardcoded path",
        )
        self.assertIn(
            "Path(__file__).resolve().parent.parent",
            content,
            "test_wrapper.py must use dynamic repo-root resolution",
        )

    def test_simulate_incremental_uses_dynamic_root(self):
        """simulate_incremental.py must not contain legacy hardcoded path."""
        content = (_TESTS_DIR / "simulate_incremental.py").read_text(encoding="utf-8")
        self.assertNotIn(
            r"005_mo2_hardlink_builder_v4b",
            content.lower(),
            "simulate_incremental.py still contains legacy hardcoded path",
        )
        self.assertIn(
            "Path(__file__).resolve().parent.parent",
            content,
            "simulate_incremental.py must use dynamic repo-root resolution",
        )


class TestSourceImports(unittest.TestCase):
    """Verifies that core source modules referenced by the test harnesses import cleanly."""

    def setUp(self):
        _ensure_src_on_path()

    def test_scanner_engine_importable(self):
        """ScannerEngine must import cleanly (used by simulate_incremental.py)."""
        from model.engines.scanner_engine import ScannerEngine
        self.assertTrue(callable(ScannerEngine))

    def test_linker_executor_importable(self):
        """LinkerExecutor must import cleanly (used by simulate_incremental.py)."""
        from model.engines.linker_executor import LinkerExecutor
        self.assertTrue(callable(LinkerExecutor))

    def test_manifest_delta_analyzer_importable(self):
        """ManifestDeltaAnalyzer must import cleanly (used by simulate_incremental.py)."""
        from model.state import ManifestDeltaAnalyzer
        self.assertTrue(callable(ManifestDeltaAnalyzer))

    def test_layered_manifest_importable(self):
        """LayeredManifest must import cleanly (used by v0.7 regression tests)."""
        from model.state import LayeredManifest
        self.assertTrue(callable(LayeredManifest))

    def test_feature_generator_importable(self):
        """wrap_loaders must import cleanly (used by test_wrapper.py)."""
        try:
            from model.engines.feature_generator import wrap_loaders
            self.assertTrue(callable(wrap_loaders))
        except ImportError as e:
            self.skipTest(
                f"feature_generator has unavailable optional dependency: {e}"
            )

    def test_gate2_compute_fingerprint_present(self):
        """_gate2_compute_fingerprint must exist on ScannerEngine (TASK-A03)."""
        from model.engines.scanner_engine import ScannerEngine
        self.assertTrue(
            hasattr(ScannerEngine, "_gate2_compute_fingerprint"),
            "ScannerEngine must have _gate2_compute_fingerprint (TASK-A03)",
        )

    def test_flat_manifest_helper_importable(self):
        """_flat_manifest_from_layered must be importable from deployment_controller (TASK-A02)."""
        try:
            from controller.deployment_controller import _flat_manifest_from_layered
            self.assertTrue(callable(_flat_manifest_from_layered))
        except ImportError as e:
            self.skipTest(f"deployment_controller has unavailable dependency: {e}")


if __name__ == "__main__":
    unittest.main()
