"""
TASK-T13: Performance Benchmarks — SI-2 + SI-4 (GAP-13, Medium)
TC-BM-01: VerificationEngine.verify_deployment on 50K-file manifest < 180s (5-run median)
TC-BM-02: Incremental build scan with 1000-mod modlist, <5 changes < 30s (5-run median)

Run directly: python tests/benchmark_si2_si4.py
These benchmarks are deliberately NOT in the unittest discovery path (no TestCase subclass
for the benchmark methods) so they don't slow down the standard test suite.
CI/CD should call this file explicitly to verify performance gates.
"""
import json
import os
import random
import statistics
import sys
import tempfile
import time
import types
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

sys.modules.setdefault("mobase", types.ModuleType("mobase"))

from model.engines.verification_engine import VerificationEngine  # noqa: E402
from model.engines.scanner_engine import ScannerEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _create_50k_deployment(tmp_path: Path):
    """Create a manifest + deployed files for 50K entries. Returns manifest_path."""
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    meta = tmp_path / "meta"
    meta.mkdir()

    # Write files in batches to avoid tempdir overhead
    extensions = [".dds", ".nif", ".wav", ".hkx", ".esp", ".bsa"]
    subdirs = [
        "data/textures/landscape",
        "data/textures/actors",
        "data/meshes/architecture",
        "data/meshes/actors",
        "data/sound/voice",
        "data/scripts/source",
    ]

    mapping = {}
    total = 50_000
    for i in range(total):
        subdir = subdirs[i % len(subdirs)]
        ext = extensions[i % len(extensions)]
        rel_key = f"{subdir}/file_{i:06d}{ext}"
        target = standalone / rel_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"X" * 128)
        mapping[rel_key] = {
            "mod_origin": f"Mod_{i // 50}",
            "size_bytes": 128,
            "preferred_path": rel_key.replace("/", "\\"),
        }

    manifest_path = meta / "mapping_manifest.json"
    manifest_path.write_text(
        json.dumps({"version": 3, "mapping": mapping}), encoding="utf-8"
    )
    return manifest_path, str(standalone)


def _create_1000_mod_setup(tmp_path: Path):
    """
    Create a 1000-mod modlist with 50 files per mod.
    Returns (mods_dir, profile_dir, overwrite_dir, output_dir).
    """
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    overwrite_dir = tmp_path / "overwrite"
    overwrite_dir.mkdir()
    output_dir = tmp_path / "meta"
    output_dir.mkdir()

    modlist_lines = []
    for i in range(1000):
        mod_name = f"Mod_{i:04d}"
        mod_dir = mods_dir / mod_name
        (mod_dir / "data" / "textures").mkdir(parents=True)
        for j in range(50):
            (mod_dir / "data" / "textures" / f"tex_{j:02d}.dds").write_bytes(b"T" * 64)
        modlist_lines.append(f"+{mod_name}")

    (profile_dir / "modlist.txt").write_text("\n".join(modlist_lines), encoding="utf-8")
    return mods_dir, profile_dir, overwrite_dir, output_dir


# ---------------------------------------------------------------------------
# TC-BM-01: VerificationEngine 50K manifest < 180s
# ---------------------------------------------------------------------------

def benchmark_si2_verify_50k(runs=5):
    """SI-2 benchmark: verify_deployment on 50K files."""
    print(f"\n{'='*60}")
    print("TC-BM-01: SI-2 — VerificationEngine 50K file verification")
    print(f"{'='*60}")
    timings = []

    for run in range(runs):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            print(f"  Run {run+1}/{runs}: creating 50K files...", end=" ", flush=True)
            manifest_path, standalone_path = _create_50k_deployment(tmp_path)

            engine = VerificationEngine()
            t0 = time.perf_counter()
            engine.verify_deployment(
                manifest_path=str(manifest_path),
                standalone_path=standalone_path,
            )
            elapsed = time.perf_counter() - t0
            timings.append(elapsed)
            missing = len(engine.results["missing_files"])
            print(f"{elapsed:.2f}s (missing={missing})")

    median_s = statistics.median(timings)
    print(f"\n  Timings: {[f'{t:.2f}s' for t in timings]}")
    print(f"  Median:  {median_s:.2f}s  (threshold: 180s)")
    passed = median_s < 180.0
    status = "PASS" if passed else "FAIL"
    print(f"  Result:  {status}")
    return {"test": "TC-BM-01", "median_s": median_s, "threshold_s": 180.0, "passed": passed}


# ---------------------------------------------------------------------------
# TC-BM-02: Incremental scan with 1000 mods, <5 changes < 30s
# ---------------------------------------------------------------------------

def benchmark_si4_incremental_1000mods(runs=5):
    """SI-4 benchmark: incremental scan on 1000-mod list with 3 dirty mods."""
    print(f"\n{'='*60}")
    print("TC-BM-02: SI-4 — Incremental scan 1000 mods (<5 changes)")
    print(f"{'='*60}")
    timings = []

    for run in range(runs):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            print(f"  Run {run+1}/{runs}: creating 1000-mod setup...", end=" ", flush=True)

            mods_dir, profile_dir, overwrite_dir, output_dir = _create_1000_mod_setup(tmp_path)

            scanner = ScannerEngine(
                mods_dir=str(mods_dir),
                overwrite_dir=str(overwrite_dir),
                profile_dir=str(profile_dir),
                output_dir=str(output_dir),
            )

            # Full build first (establishes baseline manifest)
            scanner.build_mapping()

            # Dirty 3 mods by touching files — simulates <5 changes
            dirty_mods = ["Mod_0010", "Mod_0100", "Mod_0500"]
            for mod_name in dirty_mods:
                target = mods_dir / mod_name / "data" / "textures" / "tex_00.dds"
                target.write_bytes(b"T" * 128)  # size change → dirty

            # Measure incremental rescan
            t0 = time.perf_counter()
            scanner.build_mapping()
            elapsed = time.perf_counter() - t0
            timings.append(elapsed)
            print(f"{elapsed:.2f}s")

    median_s = statistics.median(timings)
    print(f"\n  Timings: {[f'{t:.2f}s' for t in timings]}")
    print(f"  Median:  {median_s:.2f}s  (threshold: 30s)")
    passed = median_s < 30.0
    status = "PASS" if passed else "FAIL"
    print(f"  Result:  {status}")
    return {"test": "TC-BM-02", "median_s": median_s, "threshold_s": 30.0, "passed": passed}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("\nMO2 Hardlink Builder — Performance Benchmark Suite")
    print("=" * 60)
    print("Note: TC-BM-01 creates 50K temp files — may take several minutes.")
    print("=" * 60)

    results = []
    results.append(benchmark_si2_verify_50k(runs=5))
    results.append(benchmark_si4_incremental_1000mods(runs=5))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for r in results:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"  [{flag}] {r['test']}  median={r['median_s']:.2f}s  threshold={r['threshold_s']}s")
        if not r["passed"]:
            all_pass = False

    exit_code = 0 if all_pass else 1
    print(f"\n{'All benchmarks PASSED' if all_pass else 'SOME BENCHMARKS FAILED'}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
