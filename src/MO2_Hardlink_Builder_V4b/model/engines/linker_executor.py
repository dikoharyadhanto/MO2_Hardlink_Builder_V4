import json
import logging
import os
import shutil
from pathlib import Path

from .path_utils import ensure_long_path
from .scanner_engine import MANIFEST_VERSION

logger = logging.getLogger(__name__)

# Separate audit logger for every file-level deployment action
audit_logger = logging.getLogger("hardlink_audit")


class LinkerExecutor:
    def __init__(self, standalone_path, original_game_path, output_dir=None,
                 protected_data_prefixes: list = None):
        if not output_dir:
            raise ValueError("output_dir must be provided to LinkerExecutor")

        self.standalone_path = Path(ensure_long_path(standalone_path))
        self.game_path = Path(ensure_long_path(original_game_path))
        self.metadata_dir = Path(output_dir)

        self.manifest_file = self.metadata_dir / "mapping_manifest.json"
        self.report_file = self.metadata_dir / "execution_report.json"
        self.broken_mods_log = self.metadata_dir / "brokenmods_logs.txt"

        # DEFECT-02: injected per-game protected prefixes; fallback is the single game-agnostic entry
        self._protected_data_prefixes = protected_data_prefixes if protected_data_prefixes is not None else ["data/update"]

    # ------------------------------------------------------------------
    # FIX-02: Hardlink helper with mandatory inode validation
    # ------------------------------------------------------------------
    def _hardlink_verified(self, source: Path, target: Path) -> str:
        """
        Creates a hardlink from source to target and verifies via inode match.
        Returns 'hardlink' on success.
        On inode mismatch (pseudo-hardlink): deletes target, falls back to copy,
        returns 'copy_fallback_pseudo'.
        On any OSError: falls back to copy, returns 'copy_fallback_oserror'.
        NEVER silent — every fallback is logged to the audit trail.
        """
        src_lp = Path(ensure_long_path(source))
        dst_lp = Path(ensure_long_path(target))

        try:
            os.link(src_lp, dst_lp)
            # Inode validation — FIX-02
            src_ino = src_lp.stat().st_ino
            dst_ino = dst_lp.stat().st_ino
            if src_ino == dst_ino:
                audit_logger.info("HARDLINK OK | inode=%d | %s", src_ino, target)
                return "hardlink"
            else:
                # Pseudo-hardlink detected (FAT32, cross-volume, AV interference)
                dst_lp.unlink(missing_ok=True)
                audit_logger.warning(
                    "PSEUDO-HARDLINK DETECTED | src_ino=%d dst_ino=%d | %s "
                    "| target deleted, falling back to copy",
                    src_ino, dst_ino, target,
                )
                shutil.copy2(src_lp, dst_lp)
                return "copy_fallback_pseudo"
        except OSError as e:
            audit_logger.warning(
                "HARDLINK FAILED (OSError: %s) | %s | falling back to copy", e, target
            )
            shutil.copy2(src_lp, dst_lp)
            return "copy_fallback_oserror"

    # ------------------------------------------------------------------
    # FEAT-05: Deploy base game files with inode-verified hardlinks
    # ------------------------------------------------------------------
    def deploy_base_game(self, base_mapping: dict, progress_callback=None) -> int:
        """
        Hardlinks base game files (from scan_base_game output) into the standalone root.
        Skips files that already exist at the target.
        Returns the number of files actually deployed (not skipped).
        """
        if not base_mapping:
            logger.info("No base game mapping provided — skipping base game deploy.")
            return 0

        total = len(base_mapping)
        logger.info("Deploying %d base game files to standalone...", total)
        deployed_count = 0

        for i, (rel_path, info) in enumerate(base_mapping.items()):
            source = Path(ensure_long_path(info["source"]))
            target = Path(ensure_long_path(self.standalone_path / rel_path))

            if target.exists():
                # Already present (e.g. incremental run)
                continue

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.anchor.lower() == self.standalone_path.anchor.lower():
                    method = self._hardlink_verified(source, target)
                else:
                    shutil.copy2(Path(ensure_long_path(source)), target)
                    method = "copy_cross_drive"
                    audit_logger.info("BASE GAME COPY (cross-drive) | %s", rel_path)

                logger.debug("Base game %s: %s", method, rel_path)
                deployed_count += 1
            except Exception as e:
                logger.error("Base game deploy failed for %s: %s", rel_path, e)
                audit_logger.error("BASE GAME FAIL | %s | %s", rel_path, e)

            if progress_callback and (i % 50 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

        logger.info("Base game deploy complete. %d linked, %d skipped.", deployed_count, total - deployed_count)
        return deployed_count

    # ------------------------------------------------------------------
    # FIX-05: Orphan cleanup — preview + confirm before any deletion
    # ------------------------------------------------------------------
    def get_orphan_list(self, manifest_keys: set) -> list:
        """
        Returns list of Path objects in standalone that are not in manifest_keys
        and are not in protected categories.
        """
        protected_prefixes = self._protected_data_prefixes
        protected_extensions = {".exe", ".dll", ".bsa", ".esm", ".ba2"}
        orphans = []

        for root, _dirs, files in os.walk(self.standalone_path):
            for file_name in files:
                full_path = Path(root) / file_name
                try:
                    rel_path = full_path.relative_to(self.standalone_path)
                except ValueError:
                    continue
                rel_key = str(rel_path).lower().replace("\\", "/")

                is_protected = (
                    any(rel_key.startswith(p) for p in protected_prefixes)
                    or (rel_key.count("/") == 0 and Path(rel_key).suffix in protected_extensions)
                    or rel_key.endswith(".bsa")
                )

                if rel_key not in manifest_keys and not is_protected:
                    orphans.append(full_path)

        return orphans

    def clean_orphaned_files(self, removed_keys: set = None, confirm_callback=None):
        """
        FIX-05: Collects orphan list, calls confirm_callback(count) for user confirmation,
        then deletes. Every deletion is logged. Errors are logged, never silently skipped.

        FEAT-15/v3.4 — Surgical mode: if removed_keys is provided, bypass the recursive
        os.walk entirely and delete only those specific target files.

        confirm_callback(count) -> bool: True = proceed, False = abort.
        If no callback provided this method is a no-op (no silent deletion).
        """
        # --- FEAT-15/v3.4: Surgical orphan cleanup (delta-driven) ---
        if removed_keys is not None:
            if not removed_keys:
                logger.info("Surgical orphan cleanup: no removed keys — nothing to delete.")
                return

            if confirm_callback is not None and not confirm_callback(len(removed_keys)):
                logger.info("Surgical orphan cleanup cancelled by user (%d files).", len(removed_keys))
                return

            deleted = 0
            for key in removed_keys:
                target_full_path = self.standalone_path / key
                if target_full_path.exists():
                    try:
                        os.remove(target_full_path)
                        audit_logger.info("SURGICAL ORPHAN DELETED | %s", key)
                        deleted += 1
                    except Exception as e:
                        audit_logger.error("SURGICAL ORPHAN DELETE FAILED | %s | %s", key, e)
                        logger.error("Failed to delete surgical orphan %s: %s", key, e)

            logger.info("Surgical orphan cleanup complete: %d of %d files deleted.", deleted, len(removed_keys))
            return

        # --- Legacy mode: recursive walk (FIX-05 preserved) ---
        if not self.manifest_file.exists():
            return

        if confirm_callback is None:
            logger.warning(
                "clean_orphaned_files called without confirm_callback — "
                "no files deleted (FIX-05 safety guard)."
            )
            return

        try:
            with open(self.manifest_file, "r") as f:
                raw = json.load(f)
            manifest = raw.get("mapping", raw) if isinstance(raw, dict) else raw
            manifest_keys = {k.lower().replace("\\", "/") for k in manifest.keys()}
        except Exception as e:
            logger.error("Failed to load manifest for orphan cleanup: %s", e)
            return

        orphans = self.get_orphan_list(manifest_keys)
        if not orphans:
            logger.info("Orphan cleanup: no orphaned files found.")
            return

        # FIX-05: Show preview count and require user confirmation
        if not confirm_callback(len(orphans)):
            logger.info("Orphan cleanup cancelled by user (%d files).", len(orphans))
            return

        deleted = 0
        for path in orphans:
            try:
                os.remove(path)
                audit_logger.info("ORPHAN DELETED | %s", path)
                deleted += 1
            except Exception as e:
                audit_logger.error("ORPHAN DELETE FAILED | %s | %s", path, e)
                logger.error("Failed to delete orphan %s: %s", path, e)

        logger.info("Orphan cleanup complete: %d of %d files deleted.", deleted, len(orphans))

    # ------------------------------------------------------------------
    # Core deployment loop (V3 preserved — FIX-02 + v3.4 Inode Fast-Path + v3.6 Tier 2/3)
    # ----------------------------------------------------------------
    def execute_mapping(self, clean=False, confirm_orphan_callback=None, progress_callback=None,
                        tick_callback=None, start_index=0, paranoid_mode=False):
        if clean:
            self.clean_orphaned_files(confirm_callback=confirm_orphan_callback)

        if not self.manifest_file.exists():
            logger.error("Manifest not found: %s", self.manifest_file)
            return

        # ARCH-03: validate manifest version on load
        with open(self.manifest_file, "r") as f:
            raw_manifest = json.load(f)

        if isinstance(raw_manifest, dict) and "version" in raw_manifest:
            if raw_manifest["version"] != MANIFEST_VERSION:
                raise ValueError(
                    f"Manifest version mismatch (stored={raw_manifest['version']}, "
                    f"expected={MANIFEST_VERSION}). Force fresh scan required."
                )

        with open(self.broken_mods_log, "w", encoding="utf-8") as log:
            log.write("BROKEN MODS LOG\n")
            log.write("=" * 80 + "\n\n")

        if isinstance(raw_manifest, dict) and "mapping" in raw_manifest:
            manifest = raw_manifest["mapping"]
            scan_fails = raw_manifest.get("scan_failures", {})
            if scan_fails:
                with open(self.broken_mods_log, "a", encoding="utf-8") as log:
                    log.write("[SCAN FAILURES]\n")
                    for mod, reasons in scan_fails.items():
                        log.write(f"Mod: {mod}\n")
                        for r in reasons:
                            log.write(f"    - {r}\n")
                    log.write("-" * 80 + "\n\n")
        else:
            manifest = raw_manifest

        total = len(manifest)
        logger.info("Deploying %d files to standalone...", total)
        report = {}

        for i, (target_key, info) in enumerate(manifest.items()):
            if i < start_index:
                continue

            source_path = Path(ensure_long_path(info["source"]))
            target_rel_path = info.get("preferred_path", target_key)
            target_full_path = Path(ensure_long_path(self.standalone_path / target_rel_path))

            # FEAT-15/v3.4: Tier 1 — Inode Fast-Path
            # Skip if target is already the correct hardlink (same inode == same physical data).
            if target_full_path.exists() and target_full_path.is_file():
                try:
                    target_stat = target_full_path.stat()
                    source_stat = source_path.stat()

                    if target_stat.st_ino == source_stat.st_ino:
                        # Tier 1 HIT: inodes match — definitely the same hardlink
                        report[target_rel_path] = {
                            "status": "SKIPPED_UNCHANGED",
                            "category": "Unchanged",
                            "reason": "Tier 1 (inode match)",
                            "mod": info["mod_origin"],
                        }
                        if tick_callback:
                            tick_callback(i)
                        if progress_callback and (i % 50 == 0 or i == total - 1):
                            progress_callback(int(((i + 1) / total) * 100))
                        continue

                    # Tier 2 — Size + mtime fast-path (only when paranoid_mode is OFF)
                    # If paranoid_mode=True we skip Tier 2 and escalate straight to Tier 3.
                    if not paranoid_mode:
                        if (target_stat.st_size == source_stat.st_size
                                and abs(target_stat.st_mtime - source_stat.st_mtime) < 0.01):
                            # Tier 2 HIT: size + mtime match — treat as unchanged (fast heuristic)
                            report[target_rel_path] = {
                                "status": "SKIPPED_UNCHANGED",
                                "category": "Unchanged",
                                "reason": "Tier 2 (size+mtime match)",
                                "mod": info["mod_origin"],
                            }
                            if tick_callback:
                                tick_callback(i)
                            if progress_callback and (i % 50 == 0 or i == total - 1):
                                progress_callback(int(((i + 1) / total) * 100))
                            continue

                    # Tier 3 ESCALATION: inode mismatch + (Tier 2 miss OR paranoid_mode)
                    # Fall through to os.remove() + _hardlink_verified() below.
                    audit_logger.info(
                        "TIER3 ESCALATE | reason=%s | %s",
                        "paranoid_mode" if paranoid_mode else "size/mtime mismatch",
                        target_rel_path,
                    )

                except OSError:
                    pass  # Stat failed — fall through to normal relink

            try:
                if target_full_path.exists():
                    if target_full_path.is_file() or target_full_path.is_symlink():
                        os.remove(target_full_path)
                    elif target_full_path.is_dir():
                        shutil.rmtree(target_full_path)

                target_full_path.parent.mkdir(parents=True, exist_ok=True)

                # FIX-02: use verified hardlink helper — never silent
                if source_path.anchor.lower() == self.standalone_path.anchor.lower():
                    method = self._hardlink_verified(source_path, target_full_path)
                else:
                    shutil.copy2(Path(ensure_long_path(source_path)), target_full_path)
                    method = "copy_cross_drive"
                    audit_logger.info("CROSS-DRIVE COPY | %s", target_rel_path)

                report[target_rel_path] = {
                    "status": "SUCCESS",
                    "method": method,
                    "mod": info["mod_origin"],
                }

            except Exception as e:
                error_msg = str(e)
                report[target_rel_path] = {
                    "status": "FAILED",
                    "error": error_msg,
                    "mod": info.get("mod_origin", "Unknown"),
                }
                with open(self.broken_mods_log, "a", encoding="utf-8") as log:
                    log.write(f"[DEPLOYMENT FAILURE] Mod: {info.get('mod_origin', 'Unknown')}\n")
                    log.write(f"    File: {target_rel_path}\n")
                    log.write(f"    Error: {error_msg}\n")
                    log.write("-" * 40 + "\n")
                audit_logger.error("DEPLOY FAIL | %s | %s", target_rel_path, error_msg)

            # FIX-03: checkpoint tick on every deployed file
            if tick_callback:
                tick_callback(i)

            # Granular progress — every 50 files (FEAT-07 preserved from V3)
            if progress_callback and (i % 50 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

        with open(self.report_file, "w") as f:
            json.dump(report, f, indent=4)

        # Copy metadata alongside standalone
        try:
            target_meta = self.standalone_path / "standalone_metadata"
            is_same = False
            if target_meta.exists() and self.metadata_dir.exists():
                try:
                    is_same = target_meta.samefile(self.metadata_dir)
                except Exception:
                    is_same = self.metadata_dir.resolve() == target_meta.resolve()

            if is_same:
                logger.info("Metadata already in place at: %s", target_meta)
            else:
                if target_meta.exists():
                    shutil.rmtree(target_meta)
                shutil.copytree(self.metadata_dir, target_meta)
                logger.info("Metadata copied to: %s", target_meta)
        except Exception as e:
            logger.warning("Failed to copy metadata: %s", e)

    # ------------------------------------------------------------------
    # v3.7 TASK-A04: Action Queue Executor (Event-Driven phased execution)
    # ------------------------------------------------------------------
    def execute_action_queue(
        self,
        action_queue: list,
        progress_callback=None,
        tick_callback=None,
    ) -> dict:
        """
        v3.7: Executes an Action Queue produced by LayeredManifest.compute_action_queue().

        Execution is strictly phased (TD-05):
          Phase 1: All DELETE operations  (unlink existing targets)
          Phase 2: All LINK operations    (force-overwrite hardlinks)

        Idempotency guarantee (TD-06):
          - DELETE: target.unlink(missing_ok=True) — safe if already absent.
          - LINK:   target unlinked via missing_ok=True, then _hardlink_verified().
                    Executing the same LINK twice on NTFS is a no-op (same inode).

        Path 2 Safety Exception — Bounded inode verification (CDC-IMPL-002-v0.7 DEC-004):
          _hardlink_verified() performs 2 stat calls per LINK (src + dst inode) to
          detect pseudo-hardlinks and log fallbacks. This is intentional CON-007
          Level 1 compliance — every hardlink-to-copy fallback must be logged.
          The v0.6 "zero stat" claim was incorrect and is removed here.

        Locked-file OS errors are logged and counted but do NOT halt execution.

        Args:
            action_queue:      List of tuples from compute_action_queue().
                               ('DELETE', path_key, preferred_path)
                               ('LINK',   path_key, source, preferred_path)
            progress_callback: Optional callable(pct: int).
            tick_callback:     Optional callable(index: int) — compatible with
                               DeploymentTransactionManager.tick().

        Returns:
            {
                'deleted':  int,
                'linked':   int,
                'failed':   int,
                'errors':   [(path_key, error_str), ...],
            }
        """
        result = {'deleted': 0, 'linked': 0, 'failed': 0, 'errors': []}
        report = {}

        if not action_queue:
            logger.info("execute_action_queue: empty queue — nothing to do.")
            return result

        # Split queue into phases
        deletes = [a for a in action_queue if a[0] == 'DELETE']
        links   = [a for a in action_queue if a[0] == 'LINK']

        total_ops = len(deletes) + len(links)
        op_index  = 0

        logger.info(
            "execute_action_queue: Phase 1=%d DELETE, Phase 2=%d LINK.",
            len(deletes), len(links),
        )

        # ---- Phase 1: DELETE ----
        for action in deletes:
            _, path_key, preferred_path = action
            target_full = Path(ensure_long_path(self.standalone_path / preferred_path))
            try:
                target_full.unlink(missing_ok=True)
                audit_logger.info("AQ DELETE | %s", preferred_path)
                result['deleted'] += 1
                report[preferred_path] = {
                    "status": "DELETED",
                    "method": "unlink",
                    "mod": "Action Queue (v3.7)",
                }
            except OSError as e:
                # File is locked or inaccessible — log, do not halt
                err = f"DELETE OSError: {e}"
                audit_logger.error("AQ DELETE FAIL | %s | %s", preferred_path, e)
                logger.error("execute_action_queue: DELETE failed for %s: %s", preferred_path, e)
                result['failed'] += 1
                result['errors'].append((path_key, err))

            op_index += 1
            if tick_callback:
                tick_callback(op_index)
            if progress_callback and (op_index % 50 == 0 or op_index == total_ops):
                progress_callback(int((op_index / total_ops) * 100))

        # ---- Phase 2: LINK ----
        for action in links:
            _, path_key, source, preferred_path = action
            source_path  = Path(ensure_long_path(source))
            target_full  = Path(ensure_long_path(self.standalone_path / preferred_path))

            try:
                target_full.parent.mkdir(parents=True, exist_ok=True)

                # Force-overwrite: unlink existing target without pre-check stat (DEC-005).
                # unlink(missing_ok=True) is a no-op when the target is absent.
                target_full.unlink(missing_ok=True)

                # Create hardlink (cross-drive falls back to copy — FIX-02 preserved)
                if source_path.anchor.lower() == self.standalone_path.anchor.lower():
                    method = self._hardlink_verified(source_path, target_full)
                else:
                    shutil.copy2(Path(ensure_long_path(source_path)), target_full)
                    method = "copy_cross_drive"
                    audit_logger.info("AQ LINK (cross-drive copy) | %s", preferred_path)

                audit_logger.info("AQ LINK %s | %s", method, preferred_path)
                result['linked'] += 1
                report[preferred_path] = {
                    "status": "SUCCESS",
                    "method": method,
                    "mod": "Action Queue (v3.7)",
                }

            except OSError as e:
                # File is locked — log without raising (per WO: log OS error, don't halt threads)
                err = f"LINK OSError: {e}"
                audit_logger.error("AQ LINK FAIL | %s | %s", preferred_path, e)
                logger.error("execute_action_queue: LINK failed for %s: %s", preferred_path, e)
                result['failed'] += 1
                result['errors'].append((path_key, err))
            except Exception as e:
                err = f"LINK Exception: {e}"
                audit_logger.error("AQ LINK FAIL (exc) | %s | %s", preferred_path, e)
                logger.error("execute_action_queue: LINK exception for %s: %s", preferred_path, e)
                result['failed'] += 1
                result['errors'].append((path_key, err))

            op_index += 1
            if tick_callback:
                tick_callback(op_index)
            if progress_callback and (op_index % 50 == 0 or op_index == total_ops):
                progress_callback(int((op_index / total_ops) * 100))

        logger.info(
            "execute_action_queue complete: %d deleted, %d linked, %d failed.",
            result['deleted'], result['linked'], result['failed'],
        )
        
        try:
            with open(self.report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4)
        except Exception as e:
            logger.error("Failed to write execution report for Action Queue: %s", e)

        return result

    # ------------------------------------------------------------------
    # TASK-A06: Force-deploy standalone_generated_files regardless of MO2 state
    # ------------------------------------------------------------------
    # Allowlist: only these extensions are permitted through the override.
    # .log is deliberately NOT included (it is also excluded by TASK-A01).
    _OVERRIDE_ALLOWLIST = {".dll", ".exe", ".ini", ".json", ".txt"}

    def deploy_generated_overrides(
        self,
        generated_files_path: Path,
        output_root: Path,
        progress_callback=None,
    ) -> dict:
        """
        TASK-A06: Hardlinks all allowlisted files from standalone_generated_files into
        the standalone build, regardless of MO2 checkbox state.
        Returns a summary dict: {deployed: int, skipped: int, failed: int, files: list}
        """
        result = {"deployed": 0, "skipped": 0, "failed": 0, "files": []}

        if not generated_files_path or not generated_files_path.exists():
            logger.warning(
                "TASK-A06: standalone_generated_files path not found: %s — skipping override pass.",
                generated_files_path,
            )
            return result

        logger.info("TASK-A06: Override pass — scanning: %s", generated_files_path)
        candidate_files = list(generated_files_path.rglob("*"))
        total = sum(1 for f in candidate_files if f.is_file())

        for i, src in enumerate(candidate_files):
            if not src.is_file():
                continue

            ext = src.suffix.lower()
            if ext not in self._OVERRIDE_ALLOWLIST:
                # Not in allowlist — skip silently
                audit_logger.info("OVERRIDE SKIP (not in allowlist) | %s", src.name)
                result["skipped"] += 1
                continue

            rel = src.relative_to(generated_files_path)
            target = Path(ensure_long_path(output_root / rel))

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()

                if src.anchor.lower() == output_root.anchor.lower():
                    method = self._hardlink_verified(src, target)
                else:
                    shutil.copy2(Path(ensure_long_path(src)), target)
                    method = "copy_cross_drive"

                audit_logger.info("OVERRIDE DEPLOY | %s | %s | method=%s", rel, src.name, method)
                result["deployed"] += 1
                result["files"].append({
                    "path": str(rel),
                    "status": "SUCCESS",
                    "category": "Override",
                    "reason": "Included via override (standalone_generated_files)",
                    "method": method,
                    "mod": "standalone_generated_files",
                })
            except Exception as e:
                audit_logger.error("OVERRIDE FAIL | %s | %s", rel, e)
                logger.error("TASK-A06: Override deploy failed for %s: %s", rel, e)
                result["failed"] += 1
                result["files"].append({
                    "path": str(rel),
                    "status": "FAILED",
                    "category": "Failed",
                    "reason": f"Failed (stage: override hardlink — {e})",
                    "mod": "standalone_generated_files",
                })

            if progress_callback and (i % 10 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

        logger.info(
            "TASK-A06: Override pass complete — deployed=%d skipped=%d failed=%d",
            result["deployed"], result["skipped"], result["failed"],
        )
        return result
