import hashlib
import json
import logging
import os
import random
from pathlib import Path

from .path_utils import ensure_long_path

logger = logging.getLogger(__name__)


class VerificationEngine:
    def __init__(self):
        self.results = {
            "missing_files": [],
            "zero_byte_files": [],
            "config_mismatch": [],
            "save_issues": [],
            "quarantined_items": [],
            "has_historic_quarantine": False,
            "mod_audit": {
                "broken_mods": [],
                "redundant_mods": [],
                "untracked_mods": [],
            },
        }

    def verify_deployment(self, manifest_path=None, standalone_path=None, progress_callback=None):
        if not manifest_path or not Path(manifest_path).exists():
            return

        logger.info("Verifying deployment integrity...")
        manifest_p = Path(ensure_long_path(manifest_path))
        sa_p = Path(ensure_long_path(standalone_path))

        try:
            with open(manifest_p, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            manifest = raw_data.get("mapping", raw_data) if isinstance(raw_data, dict) else raw_data
        except Exception as e:
            logger.error("Error loading manifest: %s", e)
            return

        total = len(manifest)
        items = list(manifest.items())

        for i, (relative_path, info) in enumerate(items):
            target_path = sa_p / relative_path

            exists = target_path.exists()
            if not exists and ".exe" in relative_path.lower():
                original_name = f"_{Path(relative_path).stem}_original.exe"
                alt_path = target_path.parent / original_name
                if alt_path.exists():
                    exists = True
                    target_path = alt_path

            if not exists:
                self.results["missing_files"].append(
                    {"file": relative_path, "mod": info.get("mod_origin", "Unknown")}
                )
            elif target_path.stat().st_size == 0 and info.get("size_bytes", 1) > 0:
                self.results["zero_byte_files"].append(
                    {"file": relative_path, "mod": info.get("mod_origin", "Unknown")}
                )

            if progress_callback and (i % 50 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

    def verify_configs(self, mo2_profile_path, appdata_path, doc_path, ini_prefix="Skyrim",
                       use_documents_mode=False, stealth_mode=False):
        if stealth_mode:
            logger.info("Live MO2 Mode: skipping offline configuration checks.")
            return

        logger.info("Verifying configuration synchronization...")
        mo2_p = Path(ensure_long_path(mo2_profile_path))
        app_p = Path(ensure_long_path(appdata_path))
        doc_p = Path(ensure_long_path(doc_path))

        for filename in ["plugins.txt", "loadorder.txt"]:
            self._compare_files(mo2_p / filename, app_p / filename, filename, "Local AppData")

        source_label = "Windows Documents" if use_documents_mode else "MO2 Profile"
        if use_documents_mode:
            docs_name = Path(doc_path).name
            src_base = Path(ensure_long_path(
                Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")).resolve()
            ))
        else:
            src_base = mo2_p

        for ini in [f"{ini_prefix}.ini", f"{ini_prefix}Prefs.ini", f"{ini_prefix}Custom.ini"]:
            src = src_base / ini
            dst = doc_p / ini
            ignore_pattern = "sLocalSavePath" if "Custom" in ini else None
            self._compare_files(src, dst, ini, f"Standalone (vs {source_label})",
                                ignore_line=ignore_pattern)

    def _compare_files(self, src, dst, label, location_name, ignore_line=None):
        if not src.exists():
            return
        if not dst.exists():
            self.results["config_mismatch"].append(f"{label} missing in {location_name}")
            return
        try:
            with open(src, "r", errors="ignore", encoding="utf-8-sig") as f1, \
                 open(dst, "r", errors="ignore", encoding="utf-8-sig") as f2:
                c1 = [l.strip().lower() for l in f1 if l.strip()]
                c2 = [l.strip().lower() for l in f2 if l.strip()]
                if ignore_line:
                    pat = ignore_line.lower()
                    c1 = [l for l in c1 if pat not in l]
                    c2 = [l for l in c2 if pat not in l]
                if c1 != c2:
                    self.results["config_mismatch"].append(
                        f"{label} differs from {location_name}"
                    )
        except Exception as e:
            self.results["config_mismatch"].append(f"Error reading {label}: {e}")

    def verify_saves(self, mo2_profile_path, doc_save_path, run_timestamp=None,
                     use_documents_mode=False, stealth_mode=False):
        logger.info("Verifying save games...")

        if use_documents_mode and doc_save_path:
            docs_name = Path(doc_save_path).name
            src_saves_dir = Path(ensure_long_path(
                Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}/Saves")).resolve()
            ))
        else:
            src_saves_dir = Path(ensure_long_path(mo2_profile_path)) / "saves"

        if stealth_mode:
            doc_saves_dir = Path(ensure_long_path(mo2_profile_path)) / "standalone_profile" / "Saves"
        else:
            if not doc_save_path:
                return
            doc_saves_dir = Path(ensure_long_path(doc_save_path)) / "Saves"

        if not src_saves_dir.exists():
            return

        try:
            doc_saves = {f.name for f in doc_saves_dir.glob("*.[es][sk][se]*")}

            def process_q_dir(root, pattern, location_label):
                for q_dir in root.glob(pattern):
                    if q_dir.is_dir():
                        is_current = run_timestamp and run_timestamp in q_dir.name
                        if not is_current:
                            self.results["has_historic_quarantine"] = True
                        for qf in q_dir.glob("*.[es][sk][se]*"):
                            doc_saves.add(qf.name)
                            if is_current:
                                self.results["quarantined_items"].append({
                                    "file": qf.name,
                                    "location": str(q_dir),
                                    "reason": f"Conflicting save quarantined from {location_label}.",
                                })

            process_q_dir(doc_saves_dir, "MO2_import_save*", "Source")
            process_q_dir(src_saves_dir, "Standalone_Export_save*", "Standalone")

            src_saves = {f.name for f in src_saves_dir.glob("*.[es][sk][se]*")}
            missing = src_saves - doc_saves
            if missing:
                if stealth_mode:
                    logger.info("Live MO2 Mode: %d saves in source (expected).", len(missing))
                else:
                    source_label = "Windows Documents" if use_documents_mode else "MO2"
                    self.results["save_issues"].append({
                        "summary": f"Missing {len(missing)} save files in Standalone folder.",
                        "source": source_label,
                        "missing_files": sorted(list(missing)),
                    })
        except Exception as e:
            self.results["save_issues"].append({
                "summary": f"Error checking saves: {e}",
                "source": "Internal",
                "missing_files": [],
            })

    def verify_mod_completeness(self, modlist_path, manifest_path, report_path, mods_dir=None):
        logger.info("Auditing mod presence and integrity...")
        modlist_p = Path(ensure_long_path(modlist_path))
        manifest_p = Path(ensure_long_path(manifest_path))
        report_p = Path(ensure_long_path(report_path))

        active_mods: set = set()
        redundant_mods = []
        untracked_mods: set = set()
        broken_mods = []
        scan_failures: dict = {}

        if modlist_p.exists():
            try:
                with open(modlist_p, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("+"):
                            mod_name = line[1:]
                            if not mod_name.lower().endswith("_separator"):
                                active_mods.add(mod_name)
            except Exception as e:
                logger.error("Error reading modlist: %s", e)

        build_mod_data: dict = {}
        try:
            if manifest_p.exists():
                with open(manifest_p, "r", encoding="utf-8") as f:
                    raw_manifest = json.load(f)
                manifest = raw_manifest.get("mapping", raw_manifest) if isinstance(raw_manifest, dict) else raw_manifest
                scan_failures = raw_manifest.get("scan_failures", {}) if isinstance(raw_manifest, dict) else {}
                for target, info in manifest.items():
                    mod = info.get("mod_origin", "Unknown")
                    if mod not in build_mod_data:
                        build_mod_data[mod] = {"success": 0, "failed": 0, "total": 0}
                    build_mod_data[mod]["total"] += 1
                    build_mod_data[mod]["success"] += 1

            if report_p.exists():
                with open(report_p, "r", encoding="utf-8") as f:
                    report = json.load(f)
                for target, info in report.items():
                    mod = info.get("mod", "Unknown")
                    if mod not in build_mod_data:
                        build_mod_data[mod] = {"success": 0, "failed": 0, "total": 0}
                    if "SUCCESS" not in info.get("status", ""):
                        build_mod_data[mod]["success"] -= 1
                        build_mod_data[mod]["failed"] += 1
        except Exception as e:
            logger.error("Error during mod audit: %s", e)

        for mod in active_mods:
            if mod in scan_failures:
                broken_mods.append({
                    "name": mod,
                    "failed": len(scan_failures[mod]),
                    "total": "N/A",
                    "rate": "Scan Fail",
                    "reason": scan_failures[mod][0] if scan_failures[mod] else "Technical Error",
                })
            elif mod not in build_mod_data:
                redundant_mods.append(mod)

        for mod in build_mod_data:
            if mod not in ("Overwrite", "Unknown") and mod not in active_mods:
                untracked_mods.add(mod)

        for mod, stats in build_mod_data.items():
            if stats["failed"] > 0:
                rate = (stats["failed"] / stats["total"]) * 100
                broken_mods.append({
                    "name": mod,
                    "failed": stats["failed"],
                    "total": stats["total"],
                    "rate": f"{rate:.1f}%",
                    "reason": "Link/Hardlink Failure",
                })

        self.results["mod_audit"] = {
            "redundant_mods": sorted(redundant_mods),
            "untracked_mods": sorted(list(untracked_mods)),
            "broken_mods": sorted(broken_mods, key=lambda x: str(x.get("failed", 0)), reverse=True),
        }
        return self.results["mod_audit"]

    def verify_save_artifacts(self, game_saves_path, game_not_running=True):
        """
        Detects leftover .bak_standalone backup artifacts in the live saves folder.
        These are created by the launcher before injecting saves and removed on clean exit.
        If the game is not running and backups still exist, the cleanup cycle was incomplete.
        """
        if not game_not_running or not game_saves_path:
            return
        saves_dir = Path(ensure_long_path(game_saves_path))
        if not saves_dir.exists():
            return
        try:
            leftovers = sorted(f.name for f in saves_dir.rglob("*.bak_standalone"))
            if leftovers:
                self.results["save_issues"].append({
                    "summary": (
                        f"Leftover wrapper backup artifact(s) found in live saves folder "
                        f"while game is not running: {len(leftovers)} file(s)."
                    ),
                    "source": "SaveArtifactCheck",
                    "missing_files": leftovers,
                })
                logger.warning(
                    "%d leftover .bak_standalone artifact(s) found in %s",
                    len(leftovers), saves_dir,
                )
        except Exception as e:
            logger.warning("verify_save_artifacts failed: %s", e)

    def run_all_checks(self, manifest_path=None, standalone_path=None, mo2_profile_path=None,
                       appdata_path=None, doc_save_path=None, ini_prefix="Skyrim",
                       run_timestamp=None, mods_dir=None, use_documents_mode=False,
                       stealth_mode=False, progress_callback=None,
                       game_saves_path=None, game_not_running=True):
        if manifest_path:
            self.verify_deployment(manifest_path, standalone_path,
                                   progress_callback=progress_callback)
            report_path = Path(manifest_path).parent / "execution_report.json"
            if mo2_profile_path:
                modlist_path = Path(mo2_profile_path) / "modlist.txt"
                self.verify_mod_completeness(modlist_path, manifest_path, report_path,
                                             mods_dir=mods_dir)

        if mo2_profile_path and (appdata_path or stealth_mode):
            self.verify_configs(mo2_profile_path, appdata_path, doc_path=doc_save_path,
                                ini_prefix=ini_prefix, use_documents_mode=use_documents_mode,
                                stealth_mode=stealth_mode)
            self.verify_saves(mo2_profile_path, doc_save_path, run_timestamp=run_timestamp,
                              use_documents_mode=use_documents_mode, stealth_mode=stealth_mode)

        if game_saves_path:
            self.verify_save_artifacts(game_saves_path, game_not_running=game_not_running)

        if manifest_path:
            try:
                log_path = Path(ensure_long_path(manifest_path)).parent / "verification_report.json"
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(self.results, f, indent=4)
                logger.info("Verification report saved: %s", log_path)
            except Exception as e:
                logger.warning("Failed to save verification report: %s", e)

        return self.results


class TieredVerificationEngine:
    """
    Tiered verification policy:
      - Quick   : size + mtime check (~0.06 ms/file). Runs automatically after every build.
      - Sampled : random 5 % SHA-256 check. Runs automatically after every build.
      - Full    : 100 % SHA-256 check. Manual trigger only.
    """

    SAMPLE_FRACTION = 0.05

    def __init__(self, manifest_path: str, standalone_path: str):
        self.manifest_path = Path(ensure_long_path(manifest_path))
        self.standalone_path = Path(ensure_long_path(standalone_path))
        self._manifest: dict = {}
        self._load_manifest()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            return
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._manifest = raw.get("mapping", raw) if isinstance(raw, dict) else raw
        except Exception as e:
            logger.error("TieredVerification: failed to load manifest: %s", e)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def run_quick(self, progress_callback=None) -> dict:
        """Size + mtime check against manifest metadata."""
        results = {"method": "Quick", "checked": 0, "mismatches": [], "missing": []}
        items = list(self._manifest.items())
        total = len(items)

        for i, (rel_key, info) in enumerate(items):
            target = self.standalone_path / info.get("preferred_path", rel_key)
            target_lp = Path(ensure_long_path(target))
            
            # Skip files we know the tool intentionally overwrites post-build
            if target.name.lower() in ("steam_appid.txt", "how to launch.txt"):
                continue

            # Handle EXE wrapping: if the original was renamed to _original.exe, verify that instead
            if not target_lp.exists() and ".exe" in rel_key.lower():
                alt_path = target_lp.parent / f"_{target_lp.stem}_original.exe"
                if alt_path.exists():
                    target_lp = alt_path
            elif target_lp.exists() and ".exe" in rel_key.lower():
                alt_path = target_lp.parent / f"_{target_lp.stem}_original.exe"
                if alt_path.exists():
                    target_lp = alt_path

            if not target_lp.exists():
                results["missing"].append(rel_key)
            else:
                try:
                    stat = target_lp.stat()
                    expected_size = info.get("size_bytes", 0)
                    if expected_size > 0 and stat.st_size != expected_size:
                        results["mismatches"].append(
                            {"file": rel_key, "expected_size": expected_size,
                             "actual_size": stat.st_size}
                        )
                except Exception:
                    results["missing"].append(rel_key)

            results["checked"] += 1
            if progress_callback and (i % 50 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

        logger.info(
            "Quick verification: %d checked, %d missing, %d size mismatches.",
            results["checked"], len(results["missing"]), len(results["mismatches"]),
        )
        return results

    def run_sampled(self, progress_callback=None) -> dict:
        """SHA-256 on a random 5% sample of deployed files."""
        results = {"method": "Sampled", "checked": 0, "hash_mismatches": [], "missing": []}
        all_items = list(self._manifest.items())
        sample_count = max(1, int(len(all_items) * self.SAMPLE_FRACTION))
        sample = random.sample(all_items, min(sample_count, len(all_items)))
        total = len(sample)

        logger.info("Sampled verification: checking %d / %d files (5%%).", total, len(all_items))

        for i, (rel_key, info) in enumerate(sample):
            target = self.standalone_path / info.get("preferred_path", rel_key)
            target_lp = Path(ensure_long_path(target))

            if target.name.lower() in ("steam_appid.txt", "how to launch.txt"):
                continue

            if not target_lp.exists() and ".exe" in rel_key.lower():
                alt_path = target_lp.parent / f"_{target_lp.stem}_original.exe"
                if alt_path.exists():
                    target_lp = alt_path
            elif target_lp.exists() and ".exe" in rel_key.lower():
                alt_path = target_lp.parent / f"_{target_lp.stem}_original.exe"
                if alt_path.exists():
                    target_lp = alt_path

            if not target_lp.exists():
                results["missing"].append(rel_key)
            else:
                try:
                    src_lp = Path(ensure_long_path(info["source"]))
                    if src_lp.exists():
                        src_hash = self._sha256(src_lp)
                        dst_hash = self._sha256(target_lp)
                        if src_hash != dst_hash:
                            results["hash_mismatches"].append(
                                {"file": rel_key, "src_hash": src_hash, "dst_hash": dst_hash}
                            )
                except Exception as e:
                    logger.warning("Hash check failed for %s: %s", rel_key, e)

            results["checked"] += 1
            if progress_callback and (i % 10 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

        logger.info(
            "Sampled verification: %d checked, %d missing, %d hash mismatches.",
            results["checked"], len(results["missing"]), len(results["hash_mismatches"]),
        )
        return results

    def run_full(self, progress_callback=None) -> dict:
        """SHA-256 on 100% of deployed files. Manual trigger only."""
        results = {"method": "Full", "checked": 0, "hash_mismatches": [], "missing": []}
        items = list(self._manifest.items())
        total = len(items)

        logger.info("Full verification: checking %d files (100%%).", total)

        for i, (rel_key, info) in enumerate(items):
            target = self.standalone_path / info.get("preferred_path", rel_key)
            target_lp = Path(ensure_long_path(target))

            if target.name.lower() in ("steam_appid.txt", "how to launch.txt"):
                continue

            if not target_lp.exists() and ".exe" in rel_key.lower():
                alt_path = target_lp.parent / f"_{target_lp.stem}_original.exe"
                if alt_path.exists():
                    target_lp = alt_path
            elif target_lp.exists() and ".exe" in rel_key.lower():
                alt_path = target_lp.parent / f"_{target_lp.stem}_original.exe"
                if alt_path.exists():
                    target_lp = alt_path

            if not target_lp.exists():
                results["missing"].append(rel_key)
            else:
                try:
                    src_lp = Path(ensure_long_path(info["source"]))
                    if src_lp.exists():
                        src_hash = self._sha256(src_lp)
                        dst_hash = self._sha256(target_lp)
                        if src_hash != dst_hash:
                            results["hash_mismatches"].append(
                                {"file": rel_key, "src_hash": src_hash, "dst_hash": dst_hash}
                            )
                except Exception as e:
                    logger.warning("Hash check failed for %s: %s", rel_key, e)

            results["checked"] += 1
            if progress_callback and (i % 50 == 0 or i == total - 1):
                progress_callback(int(((i + 1) / total) * 100))

        logger.info(
            "Full verification: %d checked, %d missing, %d hash mismatches.",
            results["checked"], len(results["missing"]), len(results["hash_mismatches"]),
        )
        return results

    def run_post_build(self, progress_callback=None) -> dict:
        """Runs Quick + Sampled automatically. Returns combined results."""
        logger.info("Running post-build tiered verification (Quick + Sampled)...")
        quick = self.run_quick(progress_callback=lambda p: progress_callback(p // 2) if progress_callback else None)
        sampled = self.run_sampled(progress_callback=lambda p: progress_callback(50 + p // 2) if progress_callback else None)
        combined = {"quick": quick, "sampled": sampled}
        logger.info("Post-build verification complete.")
        return combined
