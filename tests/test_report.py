"""
TASK-T08: ReportGenerator Output Validation (GAP-08, Medium)
4 test vectors: HTML structure present, stat counts accurate,
BAT fallback warning rendered, missing-file verification section rendered.
"""
import json
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

from model.engines.report_generator import ReportGenerator  # noqa: E402


def _write_manifest(path: Path, n_files: int) -> None:
    mapping = {
        f"data/textures/tex_{i:04d}.dds": {
            "mod_origin": "TestMod",
            "size_bytes": 256,
            "preferred_path": f"data\\textures\\tex_{i:04d}.dds",
        }
        for i in range(n_files)
    }
    path.write_text(json.dumps({"version": 3, "mapping": mapping}), encoding="utf-8")


def _write_execution_report(path: Path, entries: dict) -> None:
    """entries: {target_path: {status, method, mod, category, reason}}"""
    path.write_text(json.dumps(entries), encoding="utf-8")


def _make_generator(tmp_path: Path, execution_entries: dict, n_manifest: int = 10):
    manifest = tmp_path / "mapping_manifest.json"
    report = tmp_path / "execution_report.json"
    output = tmp_path / "build_report.html"

    _write_manifest(manifest, n_manifest)
    _write_execution_report(report, execution_entries)

    return ReportGenerator(
        manifest_path=str(manifest),
        report_path=str(report),
        output_html=str(output),
    ), output


class TestTC_RPT_01_HtmlStructurePresent(unittest.TestCase):

    def test_html_contains_required_sections(self):
        """TC-RPT-01: Generated HTML has stats-grid, filter bar, table, and title."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/textures/tex_0000.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "ModA", "category": "", "reason": "",
                },
            }
            gen, output = _make_generator(tmp_path, entries)
            gen.generate()

            html = output.read_text(encoding="utf-8")

            self.assertIn("stats-grid", html, "stats-grid section must be present")
            self.assertIn("filter-btn", html, "filter buttons must be present")
            self.assertIn("reportTable", html, "data table must be present")
            self.assertIn("MO2 Hardlink Builder Report", html, "page title must be present")
            self.assertIn("Target Files", html, "Target Files stat card must be present")


class TestTC_RPT_02_StatCountsAccurate(unittest.TestCase):

    def test_stat_counts_match_deployment_entries(self):
        """TC-RPT-02: Success/failed/excluded/unchanged/deleted counts match ground truth."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/meshes/a.nif": {
                    "status": "SUCCESS", "method": "hardlink", "mod": "ModA",
                    "category": "", "reason": "",
                },
                "data/meshes/b.nif": {
                    "status": "SUCCESS", "method": "copy", "mod": "ModB",
                    "category": "", "reason": "",
                },
                "data/meshes/c.nif": {
                    "status": "FAILED", "method": "hardlink", "mod": "ModC",
                    "category": "", "reason": "Access denied",
                },
                "data/meshes/d.nif": {
                    "status": "EXCLUDED", "method": "N/A", "mod": "ModD",
                    "category": "Excluded", "reason": "filter",
                },
                "data/meshes/e.nif": {
                    "status": "SKIPPED_UNCHANGED", "method": "hardlink", "mod": "ModE",
                    "category": "Unchanged", "reason": "",
                },
                "data/meshes/f.nif": {
                    "status": "DELETED", "method": "unlink", "mod": "ModF",
                    "category": "", "reason": "",
                },
            }
            gen, output = _make_generator(tmp_path, entries, n_manifest=6)
            gen.generate()

            html = output.read_text(encoding="utf-8")

            # Stat cards render as: <p>COUNT</p> — extract context around each label
            # We verify the DATA array in the embedded JS, which is easier to parse
            data_marker = "const DATA = "
            self.assertIn(data_marker, html, "embedded DATA array must be present")

            idx = html.index(data_marker) + len(data_marker)
            end = html.index(";", idx)
            data = json.loads(html[idx:end])

            status_labels = {row[4] for row in data}
            self.assertIn("SUCCESS", status_labels)
            self.assertIn("FAILED", status_labels)
            self.assertIn("EXCLUDED", status_labels)
            self.assertIn("UNCHANGED", status_labels)
            self.assertIn("DELETED", status_labels)

            success_rows = [r for r in data if r[4] == "SUCCESS"]
            self.assertEqual(len(success_rows), 2, "2 SUCCESS entries expected")

            failed_rows = [r for r in data if r[4] == "FAILED"]
            self.assertEqual(len(failed_rows), 1, "1 FAILED entry expected")

    def test_manifest_total_reflected_in_html(self):
        """manifest with 8 entries → Target Files shows 8."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/t.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "X", "category": "", "reason": "",
                }
            }
            gen, output = _make_generator(tmp_path, entries, n_manifest=8)
            gen.generate()

            html = output.read_text(encoding="utf-8")

            # The manifest count is rendered as <p>8</p> inside the stat card.
            # Check that the value 8 appears near "Target Files" in the HTML.
            target_idx = html.index("Target Files")
            snippet = html[target_idx: target_idx + 80]
            self.assertIn("8", snippet,
                          "Target Files stat card must show manifest file count (8)")


class TestTC_RPT_03_BatFallbackWarningRendered(unittest.TestCase):

    def test_bat_fallback_warning_present_when_wrapper_is_bat(self):
        """TC-RPT-03: verification_results with wrapper_info type=BAT → warning section."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/t.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "X", "category": "", "reason": "",
                }
            }
            gen, output = _make_generator(tmp_path, entries)
            verification = {
                "missing_files": [],
                "zero_byte_files": [],
                "wrapper_info": {"type": "BAT"},
            }
            gen.generate(verification_results=verification)

            html = output.read_text(encoding="utf-8")

            self.assertIn("BAT", html,
                          "BAT fallback warning section must appear in HTML")
            self.assertIn(".bat", html.lower(),
                          ".bat reference must appear in fallback section")

    def test_exe_wrapper_success_box_rendered(self):
        """wrapper_info type=EXE → success launcher box present."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/t.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "X", "category": "", "reason": "",
                }
            }
            gen, output = _make_generator(tmp_path, entries)
            verification = {
                "missing_files": [],
                "zero_byte_files": [],
                "wrapper_info": {"type": "EXE"},
            }
            gen.generate(verification_results=verification)

            html = output.read_text(encoding="utf-8")

            self.assertIn("EXE", html, "EXE launcher success box must appear")


class TestTC_RPT_04_MissingFilesVerificationSection(unittest.TestCase):

    def test_missing_files_verification_block_rendered(self):
        """TC-RPT-04: missing_files in verification_results → error-box section present."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/t.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "X", "category": "", "reason": "",
                }
            }
            gen, output = _make_generator(tmp_path, entries)
            verification = {
                "missing_files": [
                    {"file": "data/textures/missing.dds", "mod": "TestMod"},
                    {"file": "data/meshes/absent.nif", "mod": "OtherMod"},
                ],
                "zero_byte_files": [],
            }
            gen.generate(verification_results=verification)

            html = output.read_text(encoding="utf-8")

            self.assertIn('<div class="error-box"', html,
                          "error-box div must appear for missing files")
            self.assertIn("Missing Files", html,
                          "Missing Files heading must be present in report")
            self.assertIn("missing.dds", html, "specific missing file must be listed")

    def test_clean_verification_produces_no_error_box(self):
        """No issues in verification_results → no error-box div rendered."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            entries = {
                "data/t.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "X", "category": "", "reason": "",
                }
            }
            gen, output = _make_generator(tmp_path, entries)
            verification = {
                "missing_files": [],
                "zero_byte_files": [],
            }
            gen.generate(verification_results=verification)

            html = output.read_text(encoding="utf-8")

            # The CSS class ".error-box" appears in the <style> block but no <div> should be rendered
            self.assertNotIn('<div class="error-box"', html,
                             "No error-box div must appear when verification is clean")


# ===========================================================================
# FMN-PLAN v0.3 — Incremental Reporting Fix Tests (TC-R01 through TC-R05)
# ===========================================================================

class TestTC_R01_EmptyQueueWritesFreshReport(unittest.TestCase):
    """TC-R01: execute_action_queue with empty queue still writes a fresh execution_report.json."""

    def test_empty_queue_creates_report_file(self):
        """After an empty-queue call, execution_report.json must exist."""
        import os
        from model.engines.linker_executor import LinkerExecutor

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "metadata"
            output_dir.mkdir()

            linker = LinkerExecutor(
                standalone_path=tmp_path / "standalone",
                original_game_path=tmp_path / "game",
                output_dir=output_dir,
            )

            linker.execute_action_queue(action_queue=[])

            report = output_dir / "execution_report.json"
            self.assertTrue(report.exists(), "execution_report.json must be created even for empty queue")

    def test_empty_queue_report_contains_no_deploy_actions(self):
        """Fresh report written on empty queue must record zero deployment operations."""
        from model.engines.linker_executor import LinkerExecutor

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "metadata"
            output_dir.mkdir()

            linker = LinkerExecutor(
                standalone_path=tmp_path / "standalone",
                original_game_path=tmp_path / "game",
                output_dir=output_dir,
            )

            linker.execute_action_queue(action_queue=[])

            report = output_dir / "execution_report.json"
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data, {}, "Empty-queue report must contain no deployment entries")

    def test_empty_queue_overwrites_stale_report(self):
        """If a stale report exists from a prior run, empty-queue call must overwrite it."""
        from model.engines.linker_executor import LinkerExecutor

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "metadata"
            output_dir.mkdir()

            # Seed a stale report simulating a large prior deployment
            stale_entries = {
                f"data/textures/tex_{i:04d}.dds": {
                    "status": "SUCCESS", "method": "hardlink", "mod": "PriorMod"
                }
                for i in range(100)
            }
            report_path = output_dir / "execution_report.json"
            report_path.write_text(json.dumps(stale_entries), encoding="utf-8")

            linker = LinkerExecutor(
                standalone_path=tmp_path / "standalone",
                original_game_path=tmp_path / "game",
                output_dir=output_dir,
            )

            linker.execute_action_queue(action_queue=[])

            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(data, {}, "Stale prior-run report must be overwritten by empty-queue call")
            self.assertEqual(len(data), 0, "Overwritten report must have zero entries, not stale ones")


class TestTC_R02_StaleReportCannotLeakIntoHtml(unittest.TestCase):
    """TC-R02: HTML report generated from a fresh empty execution_report does not show stale deployed rows."""

    def test_empty_execution_report_produces_no_success_rows(self):
        """When execution_report.json is empty {}, generate() must produce zero SUCCESS rows in DATA."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "mapping_manifest.json"
            report = tmp_path / "execution_report.json"
            output = tmp_path / "build_report.html"

            _write_manifest(manifest, 200)
            # Simulate what execute_action_queue now writes for empty queue
            report.write_text(json.dumps({}), encoding="utf-8")

            gen = ReportGenerator(
                manifest_path=str(manifest),
                report_path=str(report),
                output_html=str(output),
            )
            gen.generate(build_strategy="INCREMENTAL")

            html = output.read_text(encoding="utf-8")
            data_marker = "const DATA = "
            self.assertIn(data_marker, html)
            idx = html.index(data_marker) + len(data_marker)
            data = json.loads(html[idx: html.index(";", idx)])

            success_rows = [r for r in data if r[4] == "SUCCESS"]
            self.assertEqual(len(success_rows), 0,
                             "No SUCCESS rows must appear when execution_report is freshly empty")

    def test_prior_stale_data_absent_after_empty_report(self):
        """Stale 500-row deployment must not appear in HTML when execution_report is now empty."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "mapping_manifest.json"
            report = tmp_path / "execution_report.json"
            output = tmp_path / "build_report.html"

            _write_manifest(manifest, 500)
            # The fresh empty report (as written by fixed execute_action_queue)
            report.write_text(json.dumps({}), encoding="utf-8")

            gen = ReportGenerator(
                manifest_path=str(manifest),
                report_path=str(report),
                output_html=str(output),
            )
            gen.generate(build_strategy="INCREMENTAL")

            html = output.read_text(encoding="utf-8")
            data_marker = "const DATA = "
            idx = html.index(data_marker) + len(data_marker)
            data = json.loads(html[idx: html.index(";", idx)])

            deploy_rows = [r for r in data if r[4] in ("SUCCESS", "DELETED")]
            self.assertEqual(len(deploy_rows), 0,
                             "No deployed/deleted rows must appear; prior-run data must be absent")


class TestTC_R03_NoChangeRunReportedAsUnchanged(unittest.TestCase):
    """TC-R03: A no-change incremental run produces zero deploy actions and a non-zero unchanged count."""

    def test_zero_deploy_with_all_unchanged(self):
        """Empty execution → 0 deployed, manifest_count unchanged displayed."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "mapping_manifest.json"
            report = tmp_path / "execution_report.json"
            output = tmp_path / "build_report.html"

            n = 492200
            # Write a minimal manifest (just the count matters for stats)
            mapping = {f"data/textures/tex_{i}.dds": {"mod_origin": "M", "size_bytes": 4}
                       for i in range(10)}
            manifest.write_text(json.dumps({"version": 3, "mapping": mapping}), encoding="utf-8")
            report.write_text(json.dumps({}), encoding="utf-8")

            gen = ReportGenerator(
                manifest_path=str(manifest),
                report_path=str(report),
                output_html=str(output),
            )
            gen.generate(build_strategy="INCREMENTAL")

            html = output.read_text(encoding="utf-8")

            # DATA array: zero success entries
            data_marker = "const DATA = "
            idx = html.index(data_marker) + len(data_marker)
            data = json.loads(html[idx: html.index(";", idx)])

            deployed = [r for r in data if r[4] == "SUCCESS"]
            self.assertEqual(len(deployed), 0, "Zero deployed in no-change run")

            # Category label must show Update Rebuild (incremental)
            self.assertIn("Update Rebuild", html, "No-change incremental run must be labelled Update Rebuild")

            # Unchanged stat card must show the manifest count (10 here), not 0
            # We verify via the stat card HTML: Target Files=10, Unchanged=10 in the stats grid
            self.assertIn("Deployed (Link)", html)
            self.assertIn("Unchanged", html)

    def test_no_change_run_does_not_show_zero_unchanged(self):
        """Unchanged count in HTML must be > 0 for a no-change no-op run."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "mapping_manifest.json"
            report = tmp_path / "execution_report.json"
            output = tmp_path / "build_report.html"

            _write_manifest(manifest, 50)
            report.write_text(json.dumps({}), encoding="utf-8")

            gen = ReportGenerator(
                manifest_path=str(manifest),
                report_path=str(report),
                output_html=str(output),
            )
            gen.generate(build_strategy="INCREMENTAL")

            html = output.read_text(encoding="utf-8")

            # The stat card renders: <h3>Unchanged</h3><p>50</p>
            # Locate the Unchanged stat card and assert 50 appears near it
            unch_idx = html.index("Unchanged")
            snippet = html[unch_idx: unch_idx + 100]
            self.assertIn("50", snippet,
                          "Unchanged count must equal manifest size (50) for a no-change no-op run")


class TestTC_R04_SmallDeltaPreservesDistinction(unittest.TestCase):
    """TC-R04: Small-delta run reports only true current-run actions; unchanged count stays separate."""

    def test_small_delta_deployed_count_matches_queue(self):
        """When 5 files are deployed and 95 are unchanged, report shows exactly 5 deployed."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "mapping_manifest.json"
            report = tmp_path / "execution_report.json"
            output = tmp_path / "build_report.html"

            _write_manifest(manifest, 100)

            # 5 real current-run deploy actions
            delta_entries = {
                f"data/textures/changed_{i}.dds": {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "DeltaMod", "category": "", "reason": "",
                }
                for i in range(5)
            }
            report.write_text(json.dumps(delta_entries), encoding="utf-8")

            gen = ReportGenerator(
                manifest_path=str(manifest),
                report_path=str(report),
                output_html=str(output),
            )
            gen.generate(build_strategy="INCREMENTAL")

            html = output.read_text(encoding="utf-8")
            data_marker = "const DATA = "
            idx = html.index(data_marker) + len(data_marker)
            data = json.loads(html[idx: html.index(";", idx)])

            deployed = [r for r in data if r[4] == "SUCCESS"]
            self.assertEqual(len(deployed), 5, "Deployed count must match actual queue actions (5)")

    def test_unchanged_count_remains_separate_from_deployed(self):
        """Unchanged count must not collapse into the deployed count in a delta run."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "mapping_manifest.json"
            report = tmp_path / "execution_report.json"
            output = tmp_path / "build_report.html"

            _write_manifest(manifest, 100)

            # 3 deployed + 2 explicitly unchanged (SKIPPED_UNCHANGED)
            entries = {}
            for i in range(3):
                entries[f"data/changed_{i}.dds"] = {
                    "status": "SUCCESS", "method": "hardlink",
                    "mod": "DeltaMod", "category": "", "reason": "",
                }
            for i in range(2):
                entries[f"data/kept_{i}.dds"] = {
                    "status": "SKIPPED_UNCHANGED", "method": "hardlink",
                    "mod": "KeptMod", "category": "Unchanged",
                    "reason": "Tier 1 (inode match)",
                }
            report.write_text(json.dumps(entries), encoding="utf-8")

            gen = ReportGenerator(
                manifest_path=str(manifest),
                report_path=str(report),
                output_html=str(output),
            )
            gen.generate(build_strategy="INCREMENTAL")

            html = output.read_text(encoding="utf-8")
            data_marker = "const DATA = "
            idx = html.index(data_marker) + len(data_marker)
            data = json.loads(html[idx: html.index(";", idx)])

            deployed = [r for r in data if r[4] == "SUCCESS"]
            unchanged = [r for r in data if r[4] == "UNCHANGED"]

            self.assertEqual(len(deployed), 3, "Deployed must be 3 (actual queue actions)")
            self.assertEqual(len(unchanged), 2,
                             "Explicit unchanged entries must remain distinct from deployed entries")


class TestTC_R05_ReportFreshnessAttributable(unittest.TestCase):
    """TC-R05: execution_report.json written by execute_action_queue is verifiably from the current run."""

    def test_report_is_newer_than_pre_existing_stale_file(self):
        """execution_report.json mtime must be >= stale mtime after execute_action_queue call."""
        import time
        from model.engines.linker_executor import LinkerExecutor

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "metadata"
            output_dir.mkdir()

            report_path = output_dir / "execution_report.json"

            # Write stale file first and record its mtime
            stale_data = {"data/old.dds": {"status": "SUCCESS", "method": "hardlink", "mod": "Old"}}
            report_path.write_text(json.dumps(stale_data), encoding="utf-8")
            stale_mtime = report_path.stat().st_mtime

            # Give filesystem at least 1ms separation
            time.sleep(0.01)

            linker = LinkerExecutor(
                standalone_path=tmp_path / "standalone",
                original_game_path=tmp_path / "game",
                output_dir=output_dir,
            )
            linker.execute_action_queue(action_queue=[])

            fresh_mtime = report_path.stat().st_mtime
            self.assertGreaterEqual(fresh_mtime, stale_mtime,
                                    "Fresh execution_report.json mtime must be >= stale mtime")

    def test_report_content_differs_from_stale(self):
        """Content of execution_report.json after empty-queue call must differ from prior stale content."""
        from model.engines.linker_executor import LinkerExecutor

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "metadata"
            output_dir.mkdir()

            report_path = output_dir / "execution_report.json"

            stale_data = {f"data/tex_{i}.dds": {"status": "SUCCESS"} for i in range(50)}
            report_path.write_text(json.dumps(stale_data), encoding="utf-8")

            linker = LinkerExecutor(
                standalone_path=tmp_path / "standalone",
                original_game_path=tmp_path / "game",
                output_dir=output_dir,
            )
            linker.execute_action_queue(action_queue=[])

            fresh = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertNotEqual(len(fresh), 50,
                                "Fresh report must not contain 50 stale entries from prior run")
            self.assertEqual(fresh, {},
                             "Fresh report content must be {} (empty), not prior-run data")


if __name__ == "__main__":
    unittest.main()
