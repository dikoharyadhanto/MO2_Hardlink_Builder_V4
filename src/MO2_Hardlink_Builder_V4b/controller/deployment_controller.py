"""
ARCH-01: MVC Controller layer.
Bridges model engines ↔ view panels.
Contains: HardlinkBuilderDialog, BuildWorker, CleanWorker, UpdateCheckWorker,
          SynchronousMessenger.
"""
import datetime
import json
import logging
import os
import subprocess
import urllib.request
from pathlib import Path

import mobase

from ..qt_compat import (
    QT_NAME, Qt, QDialog, QVBoxLayout, QLabel,
    QTabWidget, QWidget, QMessageBox, QFileDialog,
    QThread, pyqtSignal, QObject, QWaitCondition, QMutex, QTimer,
)
from ..view.config_panel import BuilderTab
from ..view.progress_panel import ManagerTab
from ..model.config import get_profile_for_game
from ..model.engines.path_utils import ensure_long_path, clean_path_for_display
from ..model.engines.crash_logger import crash_safe, write_crash_log
from ..model.engines.report_generator import ReportGenerator

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("hardlink_audit")

VERSION_FILE_URL = "https://raw.githubusercontent.com/dikoharyadhanto/MO2_Hardlink_Builder/refs/heads/main/version.txt"
NEXUS_MOD_URL = "https://www.nexusmods.com/skyrimspecialedition/mods/172014"
CURRENT_VERSION = "4.0.0"

# Registry file stores profile → build_path mappings
_REGISTRY_FILE = Path(__file__).parent.parent / "standalone_registry.json"


# ---------------------------------------------------------------------------
# Logging setup: called once when the plugin loads
# ---------------------------------------------------------------------------
def _configure_logging():
    """Configures file logging (ARCH-04). Idempotent — safe to call multiple times."""
    root = logging.getLogger()
    if root.handlers:
        return

    log_dir = Path(os.environ.get("LOCALAPPDATA", ".")) / "MO2_Hardlink_Builder" / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "hardlink_builder.log"
    audit_file = log_dir / "deployment_audit.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(fmt)
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    audit = logging.getLogger("hardlink_audit")
    audit_handler = logging.FileHandler(audit_file, encoding="utf-8")
    audit_handler.setFormatter(fmt)
    audit.addHandler(audit_handler)
    audit.propagate = False


try:
    import logging.handlers
    _configure_logging()
except Exception:
    pass


def _flat_manifest_from_layered(layered_manifest, output_path):
    """
    TASK-A02: Derives mapping_manifest.json from LayeredManifest._active_map.
    Called in the INCREMENTAL fast-path to skip build_mapping() entirely.
    Produces a flat dict compatible with legacy reporting and LinkerExecutor.
    Note: only winning-mod entries are included (no conflict data) — flat
    manifest is a reporting artifact; layered manifest is the authority.
    """
    mapping = {}
    for path_key, entry in layered_manifest._active_map.items():
        mapping[path_key] = {
            "source":         entry["source"],
            "mod_origin":     entry.get("mod_origin", ""),
            "is_root":        entry.get("is_root", False),
            "size_bytes":     entry.get("size_bytes", 0),
            "mtime":          entry.get("mtime", 0),
            "preferred_path": entry.get("preferred_path", path_key),
        }
    payload = {
        "version":       3,   # MANIFEST_VERSION from scanner_engine
        "mapping":       mapping,
        "scan_failures": {},
        "folder_states": {},
    }
    output_path = Path(output_path)
    tmp = output_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
    os.replace(str(tmp), str(output_path))
    logger.info(
        "_flat_manifest_from_layered: %d entries derived → %s",
        len(mapping), output_path,
    )


# ---------------------------------------------------------------------------
# SynchronousMessenger: thread-safe Qt dialog prompts from worker threads
# ---------------------------------------------------------------------------
class SynchronousMessenger(QObject):
    request_confirm = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.result = False
        self.cond = QWaitCondition()
        self.mutex = QMutex()

    def ask(self, title: str, message: str) -> bool:
        self.mutex.lock()
        self.request_confirm.emit(title, message)
        self.cond.wait(self.mutex)
        res = self.result
        self.mutex.unlock()
        return res

    def set_result(self, res: bool):
        self.mutex.lock()
        self.result = res
        self.cond.wakeAll()
        self.mutex.unlock()


# ---------------------------------------------------------------------------
# UpdateCheckWorker (FEAT-14)
# ---------------------------------------------------------------------------
class UpdateCheckWorker(QThread):
    update_signal = pyqtSignal(str, str)  # (new_version, nexus_url)

    def __init__(self, current_version: str):
        super().__init__()
        self._current = current_version

    def run(self):
        try:
            response = urllib.request.urlopen(VERSION_FILE_URL, timeout=5)
            remote = response.read().decode("utf-8").strip()
            if self._is_newer(remote, self._current):
                self.update_signal.emit(remote, NEXUS_MOD_URL)
        except Exception:
            pass  # FEAT-14: silent fail on network error

    @staticmethod
    def _is_newer(remote: str, local: str) -> bool:
        try:
            return [int(p) for p in remote.split(".")] > [int(p) for p in local.split(".")]
        except Exception:
            return False


# ---------------------------------------------------------------------------
# CleanWorker (FEAT-06)
# ---------------------------------------------------------------------------
class CleanWorker(QThread):
    progress_signal = pyqtSignal(str)
    bar_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, sa_path, mo2_path, game_path, mods_path, overwrite_path,
                 game_name, profile_name, messenger):
        super().__init__()
        self.sa_path = Path(sa_path)
        self.mo2_path = Path(mo2_path)
        self.game_path = Path(game_path)
        self.mods_path = Path(mods_path)
        self.overwrite_path = Path(overwrite_path)
        self.game_name = game_name
        self.profile_name = profile_name
        self.messenger = messenger
        self._sa_path_str = str(sa_path)
        self._profile_name_str = profile_name

    def _crash_logger_kwargs(self) -> dict:
        return {
            "standalone_path": self._sa_path_str,
            "profile_name": self._profile_name_str,
            "build_config": {"operation": "clean"},
        }

    @crash_safe
    def run(self):
        from ..model.engines.cleaner_engine import CleanerEngine
        from ..model.engines.profile_sync import ProfileSync

        game_profile = get_profile_for_game(self.game_name)
        docs_name = game_profile.docs_name
        appdata_name = game_profile.appdata_name
        ini_prefix = game_profile.ini_prefix

        self.progress_signal.emit(f"[*] Safety check: {clean_path_for_display(self.sa_path)}")

        cleaner = CleanerEngine(
            self.sa_path, self.mo2_path, self.game_path,
            docs_name, appdata_name,
            game_name=self.game_name, profile_name=self.profile_name,
            portable_mode=True, mods_path=self.mods_path, overwrite_path=self.overwrite_path,
        )

        is_safe, msg = cleaner.check_safety()
        if not is_safe:
            self.finished_signal.emit(False, f"Safety Block: {msg}")
            return

        # FEAT-12: sync saves BEFORE deletion
        self.progress_signal.emit("[*] Save Sync: syncing saves to MO2 before clean...")
        try:
            p_sync = ProfileSync(
                self.mo2_path / "profiles" / self.profile_name,
                self.sa_path,
                docs_name=docs_name, appdata_name=appdata_name, ini_prefix=ini_prefix,
                game_name=self.game_name, profile_name=self.profile_name,
                stealth_mode=True,
                uses_plugins_txt=game_profile.uses_plugins_txt,
                uses_bethesda_ini=game_profile.uses_bethesda_ini,
                callback=self.messenger.ask,
                log_callback=self.progress_signal.emit,
            )
            synced = p_sync.sync_saves_to_mo2()
            if synced:
                self.progress_signal.emit("[*] Save sync complete.")
            else:
                self.progress_signal.emit("[*] No saves to sync.")
        except Exception as e:
            self.progress_signal.emit(f"[!] Warning: Save sync failed: {e}")

        self.progress_signal.emit("[*] Cleaning standalone folder...")
        result = cleaner.total_cleanup(progress_callback=self.bar_signal.emit)
        status = result["status"]

        if status == "SKIPPED":
            self.finished_signal.emit(True, "Destination was already empty. Ready for build.")
        elif status == "FINISHED":
            self.finished_signal.emit(True, "Standalone cleaned successfully.")
        else:
            errors_str = "\n".join(f"- {e}" for e in result["errors"][:5])
            if len(result["errors"]) > 5:
                errors_str += f"\n... and {len(result['errors']) - 5} more."
            self.finished_signal.emit(False, f"Cleanup partial failure:\n{errors_str}")


# ---------------------------------------------------------------------------
# BuildWorker (all phases integrated)
# ---------------------------------------------------------------------------
class BuildWorker(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    clean_bar_signal = pyqtSignal(int)
    scan_bar_signal = pyqtSignal(int)
    link_bar_signal = pyqtSignal(int)
    verify_bar_signal = pyqtSignal(int)

    def __init__(self, organizer, sa_path, use_hardlinks, profile_path, profile_name,
                 use_documents_mode, messenger):
        super().__init__()
        self.organizer = organizer
        self.sa_path = Path(sa_path)
        self.use_hardlinks = use_hardlinks
        self.profile_path = Path(profile_path)
        self.profile_name = profile_name
        self.use_documents_mode = use_documents_mode
        self.messenger = messenger
        self._sa_path_str = str(sa_path)

    def _crash_logger_kwargs(self) -> dict:
        return {
            "standalone_path": self._sa_path_str,
            "profile_name": self.profile_name,
            "build_config": {
                "use_hardlinks": self.use_hardlinks,
                "use_documents_mode": self.use_documents_mode,
                "qt_framework": QT_NAME,
            },
        }

    @crash_safe
    def run(self):
        from ..model.engines.scanner_engine import ScannerEngine
        from ..model.engines.linker_executor import LinkerExecutor
        from ..model.engines.cleaner_engine import CleanerEngine
        from ..model.engines.profile_sync import ProfileSync
        from ..model.engines.verification_engine import VerificationEngine, TieredVerificationEngine
        from ..model.engines.diagnostics import EnvironmentSensor
        from ..model.engines.feature_generator import (
            write_launch_instructions, write_steam_appid, wrap_loaders,
        )
        from ..model.state import DeploymentTransactionManager, ManifestDeltaAnalyzer, LayeredManifest

        self.progress_signal.emit(f"[*] Build started using {QT_NAME}...")

        # --- Gather MO2 API info ---
        mo2_path = Path(self.organizer.basePath())
        mods_path = Path(self.organizer.modsPath())
        overwrite_path = Path(self.organizer.overwritePath())
        game = self.organizer.managedGame()
        game_path = Path(game.gameDirectory().absolutePath())
        game_name = game.gameName()
        game_exe = game.binaryName()

        self.progress_signal.emit(f"[*] Game: {game_name} | Profile: {self.profile_name}")

        # ARCH-02: load game profile (no hardcoded strings)
        game_profile = get_profile_for_game(game_name)
        docs_name = game_profile.docs_name
        appdata_name = game_profile.appdata_name
        ini_prefix = game_profile.ini_prefix
        steam_appid = game_profile.steam_appid
        known_loaders = game_profile.known_loaders

        # FEAT-0X: Safety check - Prevent cross-contamination between different games/profiles
        metadata_file = self.sa_path / "standalone_metadata" / "standalone_metadata.json"
        if metadata_file.exists():
            try:
                import json as _json
                with open(metadata_file, "r", encoding="utf-8") as _f:
                    _saved_meta = _json.load(_f)
                
                _saved_game = _saved_meta.get("game_info", {}).get("game_name", "")
                _saved_profile = _saved_meta.get("mo2_info", {}).get("mo2_profile_name", "")
                
                if _saved_game and _saved_profile:
                    if _saved_game != game_name or _saved_profile != self.profile_name:
                        error_msg = (
                            f"Cross-Profile Contamination Risk Detected!\n\n"
                            f"Target Standalone was previously built with:\n"
                            f"  Game: {_saved_game}\n"
                            f"  Profile: {_saved_profile}\n\n"
                            f"Current Active MO2 State:\n"
                            f"  Game: {game_name}\n"
                            f"  Profile: {self.profile_name}\n\n"
                            f"To prevent severe file corruption, the tool refuses to rebuild in this directory. "
                            f"Please select a different standalone output folder or delete the existing one first."
                        )
                        self.progress_signal.emit(f"[!] Safety Abort: Profile Mismatch")
                        self.finished_signal.emit(False, error_msg)
                        return
            except Exception as e:
                self.progress_signal.emit(f"[!] Warning: Failed to read standalone metadata for safety check: {e}")

        # FEAT-01: Pre-flight environment sensing
        self.progress_signal.emit("[*] Stage 0: Pre-flight environment check...")
        sensor = EnvironmentSensor(str(self.sa_path), str(game_path))
        sensor_result = sensor.run_all()
        if sensor_result.has_conflicts:
            for conflict in sensor_result.conflicts:
                self.progress_signal.emit(
                    f"[!] {conflict.conflict_type}: {conflict.description}"
                )
                self.progress_signal.emit(f"    Suggestion: {conflict.retry_suggestion}")
            proceed = self.messenger.ask(
                "Pre-flight Conflict Detected",
                f"{len(sensor_result.conflicts)} environment issue(s) detected before deployment.\n\n"
                + "\n".join(c.description for c in sensor_result.conflicts)
                + "\n\nContinue anyway? (Retry = Yes, Abort = No)",
            )
            if not proceed:
                self.progress_signal.emit("[X] Build aborted by user (pre-flight).")
                self.finished_signal.emit(False, "Build aborted — pre-flight conflict.")
                return

        # ================================================================
        # STAGE 1 — Verification & Strategy
        # Pre-checks, harvest, manifest rotation, preliminary build strategy
        # ================================================================
        self.progress_signal.emit("[*] Stage 1: Verification & strategy...")
        self.clean_bar_signal.emit(5)

        metadata_dir = self.sa_path / "standalone_metadata"
        current_manifest = metadata_dir / "mapping_manifest.json"
        prev_manifest = metadata_dir / "mapping_manifest_prev.json"

        cleaner = CleanerEngine(
            self.sa_path, mo2_path, game_path,
            docs_name, appdata_name,
            game_name=game_name, profile_name=self.profile_name,
            portable_mode=True, mods_path=mods_path, overwrite_path=overwrite_path,
        )
        is_safe, msg = cleaner.check_safety()
        if not is_safe:
            self.finished_signal.emit(False, f"Safety Check Failed: {msg}")
            return

        # Detect build strategy from existing state (no scan needed)
        standalone_has_files = self.sa_path.exists() and any(self.sa_path.iterdir())
        manifest_exists = current_manifest.exists()

        if not standalone_has_files or not manifest_exists:
            build_strategy = "FRESH"
            self.progress_signal.emit("[*] S1: Fresh build detected — standalone is empty or uninitialized.")
        else:
            # Estimate strategy: compare manifest mod count vs current modlist
            # Full delta analysis is done at Stage 3 after the new scan.
            # Here we only need a preliminary FULL/INCREMENTAL split for Stage 2 cleanup ordering.
            try:
                import json as _json
                with open(current_manifest, "r", encoding="utf-8") as _f:
                    _raw = _json.load(_f)
                _old_mapping = _raw.get("mapping", _raw) if isinstance(_raw, dict) else _raw
                _old_mod_set = {v.get("mod_origin", "") for v in _old_mapping.values()}
                _cur_mods = set(self.organizer.modList().allMods()) if self.organizer else set()
                _removed_mods = _old_mod_set - _cur_mods
                _added_mods = _cur_mods - _old_mod_set
                _total = max(len(_old_mod_set), 1)
                _est_ratio = (len(_removed_mods) + len(_added_mods)) / _total
                build_strategy = "FULL_REBUILD" if _est_ratio > game_profile.delta_rebuild_threshold else "INCREMENTAL"
                self.progress_signal.emit(
                    f"[*] S1: Estimated delta {_est_ratio*100:.1f}% → preliminary strategy: {build_strategy}"
                )
            except Exception as e:
                logger.warning("S1 strategy estimation failed: %s — defaulting to INCREMENTAL.", e)
                build_strategy = "INCREMENTAL"

        # FEAT-16: Harvest generated files BEFORE any potential wipe, using current manifest
        harvest_result = cleaner.harvest_generated_files(str(current_manifest))
        if harvest_result["harvested"] > 0:
            self.progress_signal.emit(
                f"[*] S1: Generated files harvested: {harvest_result['harvested']} file(s) → standalone_generated_files"
            )
        else:
            self.progress_signal.emit("[*] S1: No generated files detected.")

        # Manifest rotation: current → prev (saves delta baseline for Stage 3)
        if current_manifest.exists():
            try:
                import shutil as _shutil
                _shutil.move(str(current_manifest), str(prev_manifest))
                logger.info("S1: Manifest rotated → mapping_manifest_prev.json")
            except Exception as e:
                logger.warning("S1: Manifest rotation failed: %s — delta analysis will trigger full rebuild.", e)

        self.clean_bar_signal.emit(30)

        # ================================================================
        # STAGE 2 — Cleanup Decision
        # Acts on S1 strategy. total_cleanup() runs HERE (before scan)
        # so the scan at Stage 3 writes the manifest into a clean directory.
        # ================================================================
        self.progress_signal.emit("[*] Stage 2: Cleanup decision...")

        linker = LinkerExecutor(self.sa_path, game_path, output_dir=metadata_dir,
                                protected_data_prefixes=game_profile.protected_data_subdirs)

        if build_strategy == "FRESH":
            self.progress_signal.emit("[*] S2: Fresh build — no cleanup needed.")

        elif build_strategy == "FULL_REBUILD":
            self.progress_signal.emit("[*] S2: Full rebuild — cleaning standalone folder...")
            result = cleaner.total_cleanup(progress_callback=self.clean_bar_signal.emit)
            if result["status"] == "PARTIAL_FAILURE":
                errors_str = "\n".join(f"- {e}" for e in result["errors"][:5])
                proceed = self.messenger.ask(
                    "Cleanup Integrity Alert",
                    f"Some files could not be deleted (locked/inaccessible).\n\n{errors_str}\n\n"
                    "Continue anyway? Proceeding may cause file mixing.",
                )
                if not proceed:
                    self.finished_signal.emit(False, "Build aborted — incomplete cleanup.")
                    return
                self.progress_signal.emit("[!] S2: Warning — proceeding with potentially mixed files.")
            elif result["status"] == "SKIPPED":
                self.progress_signal.emit("[*] S2: Destination already empty.")
            else:
                self.progress_signal.emit("[*] S2: Standalone cleared.")

        else:  # INCREMENTAL
            # Surgical orphan cleanup deferred to Stage 3 (needs removed_keys from delta analysis)
            self.progress_signal.emit("[*] S2: Incremental — surgical cleanup deferred to Stage 3.")

        self.clean_bar_signal.emit(100)

        # ================================================================
        # STAGE 3 — Scan & Deploy Routing
        # TASK-A02: INCREMENTAL + valid layered_manifest.json → skip legacy
        # build_mapping(), call tri-gate builder directly (V07-FIND-002 fix).
        # FRESH / FULL_REBUILD / schema-mismatch fallback → legacy build_mapping()
        # then build layered manifest for future incremental runs.
        # ================================================================
        self.progress_signal.emit("[*] Stage 3: Scan routing...")
        self.scan_bar_signal.emit(5)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        scanner = ScannerEngine(mods_path, overwrite_path, self.profile_path,
                                output_dir=metadata_dir)

        layered_manifest_file  = metadata_dir / "layered_manifest.json"
        _layered_manifest_new  = None
        _layered_manifest_prev = None
        _action_queue          = None
        _use_incremental_fast_path = False

        # -- Route: try to engage incremental fast-path --
        if build_strategy == "INCREMENTAL" and layered_manifest_file.exists():
            try:
                _layered_manifest_prev = LayeredManifest.load(str(layered_manifest_file))
                _use_incremental_fast_path = True
                self.progress_signal.emit(
                    f"[*] S3: INCREMENTAL (tri-gate) — valid layered manifest found "
                    f"({len(_layered_manifest_prev.mod_index) - 1} mods, "
                    f"{len(_layered_manifest_prev.path_owners)} paths). "
                    "Skipping legacy full scan."
                )
            except (FileNotFoundError, ValueError) as e:
                if "invariant violation" in str(e).lower():
                    # Hard abort — do NOT fall back to full scan on invariant violation.
                    self.progress_signal.emit(
                        f"[!] S3: INVARIANT VIOLATION in stored layered manifest — aborting.\n"
                        f"    Reason: {e}\n"
                        "    Action: Delete the standalone and perform a full rebuild."
                    )
                    self.finished_signal.emit(
                        False,
                        f"Build aborted — manifest invariant violation.\n{e}"
                    )
                    return
                else:
                    # Schema mismatch (TR-03) — fall back to legacy full scan.
                    self.progress_signal.emit(
                        f"[!] S3: Layered manifest schema mismatch ({e}). "
                        "Falling back to legacy full scan for this run."
                    )
                    _layered_manifest_prev = None

        if _use_incremental_fast_path:
            # ---- INCREMENTAL tri-gate path (no build_mapping()) ----
            try:
                _layered_manifest_new = scanner.build_layered_manifest(
                    organizer=self.organizer,
                    prev_manifest=_layered_manifest_prev,
                    progress_callback=self.scan_bar_signal.emit,
                )
                _layered_manifest_new.save(str(layered_manifest_file))
                self.progress_signal.emit(
                    f"[*] S3: Layered manifest saved — "
                    f"{len(_layered_manifest_new.path_owners)} virtual paths."
                )

                # Derive flat manifest from layered manifest (no filesystem scan needed)
                _flat_manifest_from_layered(_layered_manifest_new, scanner.output_manifest)
                self.progress_signal.emit(
                    f"[*] S3: Flat manifest derived from layered manifest "
                    f"({len(_layered_manifest_new._active_map)} entries)."
                )

                # Compute Action Queue (Phase 1: DELETE, Phase 2: LINK)
                _action_queue = _layered_manifest_new.compute_action_queue(_layered_manifest_prev)
                delete_ops = sum(1 for a in _action_queue if a[0] == 'DELETE')
                link_ops   = sum(1 for a in _action_queue if a[0] == 'LINK')
                self.progress_signal.emit(
                    f"[*] S3: Action Queue — {delete_ops} DELETE + {link_ops} LINK ops."
                )

                # Surgical orphan cleanup from Action Queue DELETE ops
                removed_keys = {a[2] for a in _action_queue if a[0] == 'DELETE'}
                if removed_keys:
                    self.progress_signal.emit(
                        f"[*] S3: Surgical orphan cleanup — {len(removed_keys)} removed path(s)..."
                    )
                    linker.clean_orphaned_files(
                        removed_keys=removed_keys,
                        confirm_callback=lambda count: True,
                    )
                else:
                    self.progress_signal.emit("[*] S3: No orphans to remove.")

            except Exception as e:
                logger.error("S3 incremental fast-path failed: %s", e)
                self.progress_signal.emit(
                    f"[!] S3: Incremental fast-path failed ({e}). "
                    "Falling back to legacy linker."
                )
                _action_queue = None

            self.scan_bar_signal.emit(100)

        else:
            # ---- FULL / FRESH / fallback path — legacy build_mapping() ----
            _scan_label = "FRESH" if build_strategy == "FRESH" else "FULL legacy"
            self.progress_signal.emit(f"[*] S3: {_scan_label} scan running...")

            scanner.build_mapping(organizer=self.organizer,
                                  progress_callback=self.scan_bar_signal.emit)
            self.scan_bar_signal.emit(90)
            self.progress_signal.emit(f"[*] S3: Scan complete — {scanner.output_manifest}")

            # Delta analysis: new manifest vs prev (rotated at Stage 1)
            delta_analyzer = ManifestDeltaAnalyzer(
                str(scanner.output_manifest),
                str(prev_manifest) if prev_manifest.exists() else None,
                delta_threshold=game_profile.delta_rebuild_threshold,
            )
            delta = delta_analyzer.analyze()
            removed_keys = delta.get("removed_keys", set())

            self.progress_signal.emit(
                f"[*] S3: Delta {delta['delta_ratio']*100:.1f}% — "
                f"{'FULL' if delta['full_rebuild_required'] else 'INCREMENTAL'} "
                f"(+{delta['added']} / -{delta['removed']} / ={delta['unchanged']} files)"
            )

            if build_strategy == "INCREMENTAL" and removed_keys:
                self.progress_signal.emit(
                    f"[*] S3: Surgical orphan cleanup — {len(removed_keys)} removed file(s)..."
                )
                linker.clean_orphaned_files(
                    removed_keys=removed_keys,
                    confirm_callback=lambda count: True,
                )
            elif build_strategy == "INCREMENTAL":
                self.progress_signal.emit("[*] S3: No orphans to remove (zero-delta).")

            self.scan_bar_signal.emit(100)

            # ================================================================
            # STAGE 3b — Build LayeredManifest from full scan
            # Saves layered_manifest.json for future incremental runs.
            # ================================================================
            self.progress_signal.emit("[*] Stage 3b: Building v3.7 Layered Manifest (full scan)...")

            # Delete stale layered manifest before full/fresh rebuild
            if layered_manifest_file.exists():
                try:
                    layered_manifest_file.unlink()
                    logger.info("S3b: Stale layered_manifest.json deleted (full/fresh rebuild).")
                except Exception as _ue:
                    pass

            try:
                _layered_manifest_new = scanner.build_layered_manifest(
                    organizer=self.organizer,
                    prev_manifest=None,  # full scan — all mods treated as dirty
                    progress_callback=self.scan_bar_signal.emit,
                )
                _layered_manifest_new.save(str(layered_manifest_file))
                self.progress_signal.emit(
                    f"[*] S3b: Layered manifest saved — "
                    f"{len(_layered_manifest_new.path_owners)} virtual paths."
                )

                # Action Queue for full/fresh = all LINKs (no prev manifest)
                _action_queue = _layered_manifest_new.compute_action_queue(None)
                link_ops = sum(1 for a in _action_queue if a[0] == 'LINK')
                self.progress_signal.emit(
                    f"[*] S3b: Action Queue (full) — {link_ops} LINK ops."
                )

            except Exception as e:
                logger.error("S3b layered manifest build failed: %s", e)
                self.progress_signal.emit(
                    f"[!] S3b: Layered manifest build failed ({e}). "
                    "Falling back to legacy linker for this run."
                )
                _action_queue = None

        # ================================================================
        # STAGE 4 — Build & Deploy
        # Base game hardlinks + mod manifest deployment with Inode Fast-Path
        # ================================================================
        self.progress_signal.emit("[*] Stage 4: Deploying files...")
        self.link_bar_signal.emit(5)

        # FEAT-05: Base game hardlinking before mod deployment
        self.progress_signal.emit("[*] S4: Hardlinking base game files...")
        base_mapping = scanner.scan_base_game(game_path)
        deployed_base = linker.deploy_base_game(base_mapping)
        if deployed_base == 0:
            self.progress_signal.emit(f"[*] S4: Base game — All {len(base_mapping)} files skipped (already linked).")
        else:
            self.progress_signal.emit(f"[*] S4: Base game — {deployed_base} files linked (out of {len(base_mapping)} scanned).")

        # FIX-03: Transaction state (resume from checkpoint support)
        tx_manager = DeploymentTransactionManager(str(self.sa_path))

        if _action_queue is not None:
            # ---- v3.7: Action Queue path (INCREMENTAL + tri-gate) ----
            # Phase 1 (DELETE) + Phase 2 (LINK) with zero os.stat in execution.
            tx_manager.begin(str(scanner.output_manifest))
            self.progress_signal.emit("[*] S4: Executing Action Queue (v3.7 phased executor)...")

            aq_result = linker.execute_action_queue(
                action_queue=_action_queue,
                progress_callback=lambda pct: self.link_bar_signal.emit(pct),
                tick_callback=tx_manager.tick,
            )
            tx_manager.complete()

            self.progress_signal.emit(
                f"[*] S4: Action Queue complete \u2014 "
                f"{aq_result['deleted']} deleted, {aq_result['linked']} linked, "
                f"{aq_result['failed']} failed."
            )
            if aq_result['errors']:
                for path_key, err in aq_result['errors'][:5]:
                    self.progress_signal.emit(f"    [!] {path_key}: {err}")
                if len(aq_result['errors']) > 5:
                    self.progress_signal.emit(
                        f"    ... and {len(aq_result['errors']) - 5} more errors (see audit log)."
                    )
        else:
            # ---- Legacy path: FRESH / FULL_REBUILD / S3b fallback ----
            incomplete = tx_manager.get_incomplete_state()
            _start_index = 0
            if incomplete:
                resume = self.messenger.ask(
                    "Incomplete Deployment Detected",
                    f"A previous deployment was interrupted at checkpoint {incomplete.get('checkpoint_index', 0)}.\n\n"
                    "Resume from checkpoint? (No = start fresh)",
                )
                if resume:
                    _start_index = incomplete.get("checkpoint_index", 0)
                    self.progress_signal.emit(f"[*] S4: Resuming from checkpoint {_start_index}.")
                else:
                    self.progress_signal.emit("[*] S4: Starting fresh deploy.")

            tx_manager.begin(str(scanner.output_manifest))

            linker.execute_mapping(
                clean=False,
                confirm_orphan_callback=lambda count: self.messenger.ask(
                    "Orphan Cleanup",
                    f"Found {count} orphaned file(s) not in current manifest.\n"
                    "Delete these orphans?",
                ),
                progress_callback=lambda pct: self.link_bar_signal.emit(pct),
                tick_callback=tx_manager.tick,
                start_index=_start_index,
                paranoid_mode=False,
            )
            tx_manager.complete()

        self.link_bar_signal.emit(95)
        self.progress_signal.emit("[*] S4: Main deployment complete.")

        # TASK-A06: Override pass — standalone_generated_files (runs AFTER main pass so overrides win)
        generated_files_path = mods_path / "standalone_generated_files"
        override_result = linker.deploy_generated_overrides(
            generated_files_path=generated_files_path,
            output_root=self.sa_path,
        )
        if override_result["deployed"] > 0 or override_result["failed"] > 0:
            self.progress_signal.emit(
                f"[*] S4: Override pass — {override_result['deployed']} deployed, "
                f"{override_result['skipped']} skipped (not in allowlist), "
                f"{override_result['failed']} failed."
            )
        else:
            self.progress_signal.emit("[*] S4: Override pass — no standalone_generated_files found.")

        self.link_bar_signal.emit(100)
        self.progress_signal.emit("[*] S4: Deployment complete.")

        # ================================================================
        # STAGE 5 — Post-Build
        # Profile config sync, wrapper generation, metadata, verification
        # ================================================================
        self.progress_signal.emit("[*] Stage 5: Post-build...")
        mo2_standalone_dir = self.profile_path / "standalone_profile"
        mo2_standalone_dir.mkdir(parents=True, exist_ok=True)

        # Patch SkyrimCustom.ini for save redirection
        custom_ini_name = f"{ini_prefix}Custom.ini"
        custom_ini_src = self.profile_path / custom_ini_name
        target_custom = mo2_standalone_dir / custom_ini_name
        content_lines = []
        if custom_ini_src.exists():
            try:
                with open(custom_ini_src, "r", encoding="utf-8-sig", errors="ignore") as f:
                    content_lines = f.readlines()
            except Exception:
                pass
        new_lines = [l for l in content_lines if "slocalsavepath" not in l.lower()]
        if not any("[general]" in l.lower() for l in new_lines):
            new_lines.insert(0, "[General]\n")
        for i, line in enumerate(new_lines):
            if "[general]" in line.lower():
                new_lines.insert(i + 1, "sLocalSavePath=Saves\\\n")
                break
        try:
            with open(target_custom, "w", encoding="utf-8-sig") as f:
                f.writelines(new_lines)
            self.progress_signal.emit(f"   [*] {custom_ini_name} patched.")
        except Exception as e:
            self.progress_signal.emit(f"   [!] Failed to patch {custom_ini_name}: {e}")

        p_sync = ProfileSync(
            self.profile_path, self.sa_path,
            docs_name=docs_name, appdata_name=appdata_name, ini_prefix=ini_prefix,
            game_name=game_name, profile_name=self.profile_name,
            portable_mode=True, stealth_mode=True,
            uses_plugins_txt=game_profile.uses_plugins_txt,
            uses_bethesda_ini=game_profile.uses_bethesda_ini,
            callback=self.messenger.ask, log_callback=self.progress_signal.emit,
        )
        p_sync.deploy_mo2_profile()

        # Feature generation
        self.progress_signal.emit("[*] S5: Generating metadata & wrapper files...")

        # FEAT-09: steam_appid.txt
        write_steam_appid(str(self.sa_path), steam_appid)
        self.progress_signal.emit(f"[*] steam_appid.txt written: {steam_appid}")

        # FEAT-10: EXE wrapping
        if build_strategy != "INCREMENTAL":
            wrap_result = wrap_loaders(
                str(self.sa_path), 
                known_loaders, 
                game_exe,
                is_stealth=True,
                mo2_profile_path=str(self.profile_path),
                docs_name=docs_name,
                appdata_name=appdata_name,
                ini_prefix=ini_prefix,
                uses_plugins_txt=game_profile.uses_plugins_txt,
                uses_bethesda_ini=game_profile.uses_bethesda_ini,
            )
            self.progress_signal.emit(
                f"[*] EXE wrapping: {wrap_result['hijacked']} hijacked, "
                f"{wrap_result['exe_wrappers']} EXE, {wrap_result['bat_wrappers']} .bat."
            )
        else:
            self.progress_signal.emit("[*] S5: EXE wrapping bypassed (Incremental).")
            wrap_result = {"hijacked": 0, "exe_wrappers": 1, "bat_wrappers": 0}

        # FEAT-08: HOW TO LAUNCH.txt
        write_launch_instructions(
            str(self.sa_path), self.profile_name, game_name,
            known_loaders, docs_name=docs_name, use_stealth=True,
        )
        self.progress_signal.emit("[*] HOW TO LAUNCH.txt written.")

        # Write standalone metadata JSON
        metadata = {
            "standalone_info": {
                "standalone_name": self.sa_path.name,
                "standalone_path": str(Path(ensure_long_path(self.sa_path))),
                "build_timestamp": datetime.datetime.now().isoformat(),
                "qt_framework": QT_NAME,
                "wrapper_type": "EXE" if wrap_result["exe_wrappers"] > 0 else "BAT",
            },
            "game_info": {
                "game_name": game_name,
                "game_path": str(Path(ensure_long_path(game_path))),
                "game_executable": game_exe,
            },
            "mo2_info": {
                "mo2_profile_name": self.profile_name,
                "mo2_profile_path": str(Path(ensure_long_path(self.profile_path))),
                "mo2_base_path": str(Path(ensure_long_path(mo2_path))),
                "mo2_mods_path": str(Path(ensure_long_path(mods_path))),
                "mo2_overwrite_path": str(Path(ensure_long_path(overwrite_path))),
            },
            "build_config": {
                "mode": "MO2_Sync",
                "use_hardlinks": self.use_hardlinks,
                "use_stealth": True,
            },
            "source_paths": {
                "save_source": str(Path(ensure_long_path(self.profile_path / "saves"))),
                "config_source": str(Path(ensure_long_path(self.profile_path))),
                "plugins_source": str(Path(ensure_long_path(self.profile_path))),
            },
        }
        with open(metadata_dir / "standalone_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)

        # Post-build tiered verification (FEAT-02: Quick + Sampled auto)
        quick_r = {"checked": 0, "missing": [], "mismatches": []}
        sampled_r = {"checked": 0, "missing": [], "hash_mismatches": []}

        if build_strategy != "INCREMENTAL":
            self.progress_signal.emit("[*] S5: Running post-build verification (Quick + Sampled)...")
            self.verify_bar_signal.emit(5)
            try:
                tiered = TieredVerificationEngine(
                    str(scanner.output_manifest), str(self.sa_path)
                )
                v_results = tiered.run_post_build(progress_callback=self.verify_bar_signal.emit)
                quick_r = v_results["quick"]
                sampled_r = v_results["sampled"]
                self.progress_signal.emit(
                    f"[*] Quick: {quick_r['checked']} checked, "
                    f"{len(quick_r['missing'])} missing, "
                    f"{len(quick_r['mismatches'])} size mismatches."
                )
                self.progress_signal.emit(
                    f"[*] Sampled (5%): {sampled_r['checked']} checked, "
                    f"{len(sampled_r['missing'])} missing, "
                    f"{len(sampled_r['hash_mismatches'])} hash mismatches."
                )
            except Exception as e:
                self.progress_signal.emit(f"[!] Tiered verification issue: {e}")
        else:
            self.progress_signal.emit("[*] S5: Post-build verification bypassed (Incremental fast-path).")
            self.verify_bar_signal.emit(100)

        try:
            report_path = metadata_dir / "execution_report.json"
            output_html = metadata_dir / "build_report.html"
            # Store html path on worker so _on_build_finished can open it
            self._last_report_html = str(output_html)

            v3_results = {
                "missing_files": [{"file": str(p), "mod": "Unknown"} for p in quick_r.get("missing", [])],
                "zero_byte_files": [{"file": str(p), "mod": "Unknown"} for p in quick_r.get("mismatches", [])],
                "wrapper_info": {"type": "EXE" if wrap_result.get("exe_wrappers", 0) > 0 else "BAT"}
            }

            gen = ReportGenerator(
                manifest_path=str(scanner.output_manifest),
                report_path=str(report_path),
                output_html=str(output_html)
            )
            # TASK-A02: Atomic manifest write — write to .tmp, then os.replace() atomically
            tmp_manifest = metadata_dir / "mapping_manifest.json.tmp"
            try:
                import shutil as _shutil2
                _shutil2.copy2(str(scanner.output_manifest), str(tmp_manifest))
                os.replace(str(tmp_manifest), str(scanner.output_manifest))
                logger.info("S5: Atomic manifest write complete.")
            except Exception as _me:
                logger.warning("S5: Atomic manifest swap failed (non-fatal): %s", _me)

            # TASK-A03/A06: pass override results so report knows about override files
            gen.generate(
                verification_results=v3_results,
                show_deployment=True,
                override_results=override_result,
                build_strategy=build_strategy,
            )
            self.progress_signal.emit(f"[*] Build Report generated: {output_html}")
        except Exception as ex:
            self._last_report_html = ""
            self.progress_signal.emit(f"[!] Failed to generate build report: {ex}")

        self.verify_bar_signal.emit(100)

        self.progress_signal.emit("[SUCCESS] Build complete!")
        self.finished_signal.emit(True, "Build completed successfully!")


# ---------------------------------------------------------------------------
# HardlinkBuilderDialog — main window (MVC: orchestrates view panels + workers)
# ---------------------------------------------------------------------------
class HardlinkBuilderDialog(QDialog):
    def __init__(self, organizer: mobase.IOrganizer):
        super().__init__()
        self.organizer = organizer
        self.setWindowTitle("MO2 Hardlink Builder V4b")
        self.setMinimumSize(720, 600)

        self.messenger = SynchronousMessenger()
        self.messenger.request_confirm.connect(self._on_messenger_request)

        self._registry = self._load_registry()
        self._build_worker = None
        self._clean_worker = None

        self._init_ui()

        # FEAT-14: update check on startup
        self._update_worker = UpdateCheckWorker(CURRENT_VERSION)
        self._update_worker.update_signal.connect(self._show_update_notification)
        self._update_worker.start()

        self._populate_profiles()
        self._validate_drives()
        self._check_registry_for_path()

        try:
            prof_path = Path(self.organizer.profile().absolutePath())
            self._validate_profile(prof_path)
        except Exception:
            pass

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # FEAT-14: update banner (hidden by default)
        self.update_banner = QLabel("")
        try:
            self.update_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except AttributeError:
            self.update_banner.setAlignment(Qt.AlignCenter)
        self.update_banner.setStyleSheet(
            "QLabel { background-color: #FFB74D; color: #000; padding: 8px; "
            "border-radius: 4px; } QLabel:hover { background-color: #FFA726; }"
        )
        try:
            self.update_banner.setCursor(Qt.CursorShape.PointingHandCursor)
        except AttributeError:
            self.update_banner.setCursor(Qt.PointingHandCursor)
        self.update_banner.mousePressEvent = lambda e: self._open_update_url()
        self.update_banner.hide()
        layout.addWidget(self.update_banner)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Builder (ARCH-01: view panel)
        self.builder_tab = BuilderTab(organizer=self.organizer)
        self.tabs.addTab(self.builder_tab, "1. Builder")

        # Tab 2: Standalone Manager (ARCH-01: view panel)
        self.manager_tab = ManagerTab()
        self.tabs.addTab(self.manager_tab, "2. Standalone Manager")

        # Connect builder tab signals to controller methods
        bt = self.builder_tab
        bt.btn_browse_dest.clicked.connect(self._browse_dest)
        bt.btn_browse_prof.clicked.connect(self._browse_profile)
        bt.dest_edit.textChanged.connect(self._validate_drives)
        bt.dest_edit.textChanged.connect(self._validate_report_button)
        bt.btn_build.clicked.connect(self._start_build)
        bt.btn_clean_standalone.clicked.connect(self._start_clean)  # FEAT-06
        bt.btn_show_report.clicked.connect(self._open_build_report)  # TASK-A04

        # Connect manager tab signals
        mt = self.manager_tab
        mt.btn_refresh_list.clicked.connect(self._refresh_standalone_list)
        mt.btn_open_folder.clicked.connect(self._open_standalone_folder)
        mt.standalone_list.itemSelectionChanged.connect(self._on_standalone_selected)

        self._populate_standalone_list()

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------
    def _populate_profiles(self):
        current_prof = "Default"
        try:
            current_prof = self.organizer.profile().name()
        except Exception:
            pass

        profiles = []
        for method_name, method_func in [
            ("profileNames", lambda: self.organizer.profileNames()),
            ("profileList", lambda: [p.name() for p in self.organizer.profileList()]),
            ("currentProfileOnly", lambda: [self.organizer.profile().name()]),
        ]:
            try:
                result = method_func()
                if result:
                    profiles = result
                    break
            except Exception:
                pass

        if not profiles:
            profiles = ["Default"]

        bt = self.builder_tab
        bt.profile_box.clear()
        default_idx = 0
        for i, name in enumerate(profiles):
            bt.profile_box.addItem(name)
            if name == current_prof:
                default_idx = i
        bt.profile_box.setCurrentIndex(default_idx)
        bt.profile_box.currentIndexChanged.connect(self._on_profile_changed)

    def _on_profile_changed(self):
        name = self.builder_tab.profile_box.currentText()
        try:
            base = Path(self.organizer.basePath()) / "profiles" / name
            if name == self.organizer.profile().name():
                base = Path(self.organizer.profile().absolutePath())
            self.builder_tab.lbl_prof_path.setText(
                f"<small>Path: {clean_path_for_display(base)}</small>"
            )
            self._validate_profile(base)
        except Exception:
            pass
        self._validate_drives()
        self._check_registry_for_path()

    def _browse_profile(self):
        path = QFileDialog.getExistingDirectory(self, "Select Custom Profile Folder")
        if path:
            folder_name = Path(path).name
            bt = self.builder_tab
            bt.profile_box.addItem(folder_name, path)
            bt.profile_box.setCurrentIndex(bt.profile_box.count() - 1)
            bt.lbl_prof_path.setText(f"<small>Path: {clean_path_for_display(path)}</small>")
            self._validate_profile(Path(path))
            self._validate_drives()

    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, "Select Standalone Destination")
        if path:
            self.builder_tab.dest_edit.setText(path)

    def _get_profile_path(self) -> Path:
        """Resolves the current profile path from combo box."""
        bt = self.builder_tab
        name = bt.profile_box.currentText()
        data = bt.profile_box.currentData()
        if data:
            return Path(data)
        try:
            if name == self.organizer.profile().name():
                return Path(self.organizer.profile().absolutePath())
            return Path(self.organizer.basePath()) / "profiles" / name
        except Exception:
            return Path(self.organizer.basePath()) / "profiles" / name

    def _validate_profile(self, prof_path: Path):
        bt = self.builder_tab
        if not prof_path.exists():
            bt.lbl_prof_status.setText("<b>Profile Error:</b> Path does not exist.")
            bt.lbl_prof_status.setStyleSheet(
                "font-size: 11px; color: #F44336; border: 1px solid #F44336; "
                "padding: 5px; border-radius: 4px;"
            )
            bt.lbl_prof_status.show()
            bt.btn_build.setEnabled(False)
            return

        missing = [f for f in ["modlist.txt"] if not (prof_path / f).exists()]
        if missing:
            bt.lbl_prof_status.setText(
                f"<b>Warning:</b> Missing files: {', '.join(missing)}"
            )
            bt.lbl_prof_status.setStyleSheet(
                "font-size: 11px; color: #FFB74D; border: 1px solid #FFB74D; "
                "padding: 5px; border-radius: 4px;"
            )
            bt.lbl_prof_status.show()
        else:
            bt.lbl_prof_status.hide()
            bt.btn_build.setEnabled(True)

    # ------------------------------------------------------------------
    # UX-01: Cross-drive warning
    # ------------------------------------------------------------------
    def _validate_drives(self):
        bt = self.builder_tab
        dest = bt.dest_edit.text().strip()
        if not dest:
            bt.drive_warning.hide()
            return

        try:
            mods_drive = Path(self.organizer.modsPath()).anchor.lower()
            dest_drive = Path(dest).anchor.lower()
            if mods_drive != dest_drive:
                bt.drive_warning.setText(
                    f"⚠ Cross-drive configuration detected: MO2 mods ({mods_drive.upper()}) vs "
                    f"destination ({dest_drive.upper()}). Hardlinks require the same drive — "
                    "files will be COPIED instead. This increases disk usage and deployment time."
                )
            else:
                bt.drive_warning.hide()
        except Exception:
            bt.drive_warning.hide()

    def _validate_report_button(self):
        bt = self.builder_tab
        dest = bt.dest_edit.text().strip()
        if dest:
            candidate = Path(dest) / "standalone_metadata" / "build_report.html"
            bt.btn_show_report.setEnabled(candidate.exists())
        else:
            bt.btn_show_report.setEnabled(False)

    # ------------------------------------------------------------------
    # Build & Clean actions
    # ------------------------------------------------------------------
    def _start_build(self):
        bt = self.builder_tab
        sa_path = bt.dest_edit.text().strip()
        if not sa_path:
            QMessageBox.warning(self, "Missing Destination",
                                "Please select a standalone destination folder.")
            return

        profile_path = self._get_profile_path()
        profile_name = bt.profile_box.currentText()

        bt.btn_build.setEnabled(False)
        bt.btn_clean_standalone.setEnabled(False)
        for bar in [bt.bar_clean, bt.bar_scan, bt.bar_link, bt.bar_verify]:
            bar.setValue(0)
        bt.log_area.clear()

        self._build_worker = BuildWorker(
            self.organizer, sa_path,
            use_hardlinks=bt.cb_hardlinks.isChecked(),
            profile_path=profile_path,
            profile_name=profile_name,
            use_documents_mode=bt.rb_mode_docs.isChecked(),
            messenger=self.messenger,
        )
        self._build_worker.progress_signal.connect(self._append_log)
        self._build_worker.clean_bar_signal.connect(bt.bar_clean.setValue)
        self._build_worker.scan_bar_signal.connect(bt.bar_scan.setValue)
        self._build_worker.link_bar_signal.connect(bt.bar_link.setValue)
        self._build_worker.verify_bar_signal.connect(bt.bar_verify.setValue)
        self._build_worker.finished_signal.connect(self._on_build_finished)
        self._build_worker.start()

        self._update_registry(profile_name, sa_path)

    def _on_build_finished(self, success: bool, message: str):
        bt = self.builder_tab
        bt.btn_build.setEnabled(True)
        bt.btn_clean_standalone.setEnabled(True)

        # Recover last report path from build worker
        report_html = getattr(self._build_worker, '_last_report_html', '')

        if success:
            bt.btn_show_report.setEnabled(bool(report_html))
            self._refresh_standalone_list()

            # TASK-A04: Post-build prompt (unless suppressed by "Don't show again")
            if bt.cb_show_report_prompt.isChecked() and report_html:
                from ..qt_compat import QCheckBox as _QCB
                prompt = QMessageBox(self)
                prompt.setWindowTitle("Build Complete")
                prompt.setText("Build completed successfully!\n\nWould you like to view the build report?")
                prompt.setIcon(QMessageBox.Icon.Information)
                prompt.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                dont_show = _QCB("Don't show again")
                prompt.setCheckBox(dont_show)
                res = prompt.exec()
                if dont_show.isChecked():
                    bt.cb_show_report_prompt.setChecked(False)
                if res == QMessageBox.StandardButton.Yes:
                    self._open_report_path(report_html)
            else:
                QMessageBox.information(self, "Build Complete", message)
        else:
            if "Crash log:" in message:
                QMessageBox.critical(self, "Build Failed — Crash", message)
            else:
                QMessageBox.warning(self, "Build Failed", message)
        self._append_log(f"\n{'[SUCCESS]' if success else '[FAILED]'} {message}")

    def _open_build_report(self):
        """TASK-A04: Open build report from Show Report button."""
        report_html = getattr(self._build_worker, '_last_report_html', '') if self._build_worker else ''
        if not report_html:
            # Fallback: try to find report in registered standalone path
            bt = self.builder_tab
            dest = bt.dest_edit.text().strip()
            if dest:
                candidate = Path(dest) / "standalone_metadata" / "build_report.html"
                if candidate.exists():
                    report_html = str(candidate)
        self._open_report_path(report_html)

    def _open_report_path(self, path: str):
        """TASK-A04: Open an HTML path in the default browser."""
        if path and Path(path).exists():
            try:
                os.startfile(path)
            except Exception as e:
                QMessageBox.warning(self, "Report Error", f"Could not open report: {e}")
        else:
            QMessageBox.information(self, "Report Not Found",
                                   "Build report not found. Run a build first.")


    def _start_clean(self):
        """FEAT-06: Clean Standalone button — deletes contents, no rebuild."""
        bt = self.builder_tab
        sa_path = bt.dest_edit.text().strip()
        if not sa_path:
            QMessageBox.warning(self, "No Destination", "Please enter a standalone folder path.")
            return

        confirmed = QMessageBox.question(
            self,
            "Clean Standalone",
            f"Delete ALL contents of:\n{sa_path}\n\n"
            "This will NOT trigger a rebuild. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            mo2_path = Path(self.organizer.basePath())
            game_path = Path(self.organizer.managedGame().gameDirectory().absolutePath())
            game_name = self.organizer.managedGame().gameName()
            mods_path = Path(self.organizer.modsPath())
            overwrite_path = Path(self.organizer.overwritePath())
        except Exception as e:
            QMessageBox.critical(self, "MO2 Error", f"Failed to read MO2 info: {e}")
            return

        profile_name = bt.profile_box.currentText()

        bt.btn_build.setEnabled(False)
        bt.btn_clean_standalone.setEnabled(False)
        bt.bar_clean.setValue(0)

        self._clean_worker = CleanWorker(
            sa_path, mo2_path, game_path, mods_path, overwrite_path,
            game_name, profile_name, self.messenger,
        )
        self._clean_worker.progress_signal.connect(self._append_log)
        self._clean_worker.bar_signal.connect(bt.bar_clean.setValue)
        self._clean_worker.finished_signal.connect(self._on_clean_finished)
        self._clean_worker.start()

    def _on_clean_finished(self, success: bool, message: str):
        bt = self.builder_tab
        bt.btn_build.setEnabled(True)
        bt.btn_clean_standalone.setEnabled(True)
        if success:
            QMessageBox.information(self, "Clean Complete", message)
        else:
            QMessageBox.warning(self, "Clean Failed", message)
        self._append_log(f"\n{'[SUCCESS]' if success else '[FAILED]'} {message}")
        self._refresh_standalone_list()

    def _append_log(self, msg: str):
        self.builder_tab.log_area.append(msg)

    # ------------------------------------------------------------------
    # Messenger handler (runs on UI thread)
    # ------------------------------------------------------------------
    def _on_messenger_request(self, title: str, message: str):
        res = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        self.messenger.set_result(res == QMessageBox.StandardButton.Yes)

    # ------------------------------------------------------------------
    # FEAT-14: Update notification banner
    # ------------------------------------------------------------------
    def _show_update_notification(self, new_version: str, url: str):
        self._update_url = url
        self.update_banner.setText(
            f"<b>Update Available!</b> v{new_version} — Click here to download on Nexus."
        )
        self.update_banner.show()

    def _open_update_url(self):
        url = getattr(self, "_update_url", NEXUS_MOD_URL)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------
    def _load_registry(self) -> dict:
        if _REGISTRY_FILE.exists():
            try:
                with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_registry(self):
        try:
            with open(_REGISTRY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, indent=4)
        except Exception as e:
            logger.warning("Registry save failed: %s", e)

    def _update_registry(self, profile_name: str, path: str):
        self._registry[profile_name] = {
            "path": str(Path(path).as_posix()),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_registry()

    def _check_registry_for_path(self):
        name = self.builder_tab.profile_box.currentText()
        if name in self._registry:
            saved = self._registry[name].get("path", "")
            if saved:
                self.builder_tab.dest_edit.setText(saved)
                self._validate_drives()
        else:
            self.builder_tab.dest_edit.setText("")

    # ------------------------------------------------------------------
    # Standalone Manager tab
    # ------------------------------------------------------------------
    def _populate_standalone_list(self):
        mt = self.manager_tab
        mt.standalone_list.clear()
        for profile_name, info in self._registry.items():
            display = f"{profile_name}  [{info.get('timestamp', '')}]"
            mt.standalone_list.addItem(display)

    def _refresh_standalone_list(self):
        self._registry = self._load_registry()
        self._populate_standalone_list()

    def _on_standalone_selected(self):
        mt = self.manager_tab
        items = mt.standalone_list.selectedItems()
        if not items:
            mt.btn_open_folder.setEnabled(False)
            mt.metadata_display.clear()
            return

        mt.btn_open_folder.setEnabled(True)
        profile_name = items[0].text().split("  [")[0]
        info = self._registry.get(profile_name, {})
        path = info.get("path", "")
        metadata_file = Path(path) / "standalone_metadata" / "standalone_metadata.json" if path else None

        if metadata_file and metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                # UX-02: render paths as clickable file:/// links
                html = self._render_metadata_html(meta)
                mt.metadata_display.setHtml(html)
                return
            except Exception as e:
                logger.warning("Failed to load metadata for %s: %s", profile_name, e)

        # Fallback: plain info
        mt.metadata_display.setPlainText(
            f"Profile: {profile_name}\nPath: {path}\nTimestamp: {info.get('timestamp', 'N/A')}"
        )

    def _render_metadata_html(self, meta: dict) -> str:
        """UX-02: Renders metadata with clickable file:/// links."""
        lines = ["<html><body style='font-family:Consolas,monospace;color:#E0E0E0;'>"]

        def _section(title, data):
            lines.append(f"<p><b style='color:#81C784'>{title}</b></p><ul>")
            for k, v in data.items():
                v_str = str(v)
                if v_str.startswith("\\\\?\\"):
                    v_str = v_str[4:]
                if v_str and (v_str.startswith("C:\\") or v_str.startswith("D:\\")
                               or v_str.startswith("E:\\") or ":\\" in v_str):
                    v_html = f"<a href='file:///{v_str.replace(chr(92), chr(47))}' style='color:#64B5F6'>{v_str}</a>"
                else:
                    v_html = v_str
                lines.append(f"<li><b>{k}:</b> {v_html}</li>")
            lines.append("</ul>")

        for section_key, section_data in meta.items():
            if isinstance(section_data, dict):
                _section(section_key.replace("_", " ").title(), section_data)

        lines.append("</body></html>")
        return "".join(lines)

    def _open_standalone_folder(self):
        items = self.manager_tab.standalone_list.selectedItems()
        if not items:
            return
        profile_name = items[0].text().split("  [")[0]
        info = self._registry.get(profile_name, {})
        path = info.get("path", "")
        if path and Path(path).exists():
            try:
                os.startfile(path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open folder: {e}")
        else:
            QMessageBox.warning(self, "Folder Not Found",
                                f"The folder '{path}' does not exist.")
