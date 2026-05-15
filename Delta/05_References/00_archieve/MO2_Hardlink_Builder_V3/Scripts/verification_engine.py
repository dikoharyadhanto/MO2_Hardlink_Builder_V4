import os
import json
import filecmp
from pathlib import Path
from path_utils import ensure_long_path

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
                "untracked_mods": []
            }
        }

    def verify_deployment(self, manifest_path=None, standalone_path=None, progress_callback=None):
        """Checks if files in manifest exist in standalone path."""
        if not manifest_path or not Path(manifest_path).exists():
            return
            
        print("[*] Verifying Deployment Integrity...")
        manifest_p = Path(ensure_long_path(manifest_path))
        sa_p = Path(ensure_long_path(standalone_path))

        try:
            with open(manifest_p, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                # Handle new nested structure or old flat structure
                if isinstance(raw_data, dict) and "mapping" in raw_data:
                    manifest = raw_data["mapping"]
                else:
                    manifest = raw_data
        except Exception as e:
            print(f"[!] Error loading manifest: {e}")
            return

        total = len(manifest)
        items = list(manifest.items())

        for i, (relative_path, info) in enumerate(items):
            target_path = sa_p / relative_path
            
            # Check for Hijacked original if not found as is
            exists = target_path.exists()
            if not exists and (relative_path.lower().endswith(".exe") or ".exe" in relative_path.lower()):
                # Potential hijacked file
                original_name = f"_{Path(relative_path).stem}_original.exe"
                alt_path = target_path.parent / original_name
                if alt_path.exists():
                    exists = True
                    target_path = alt_path # Use the original for size check
            
            if not exists:
                self.results["missing_files"].append({
                    "file": relative_path,
                    "mod": info.get('mod_origin', 'Unknown')
                })
            elif target_path.stat().st_size == 0 and info.get('size_bytes', 1) > 0:
                 self.results["zero_byte_files"].append({
                    "file": relative_path,
                    "mod": info.get('mod_origin', 'Unknown')
                })
            
            if progress_callback and (i % 50 == 0 or i == total - 1):
                percent = int(((i + 1) / total) * 100)
                progress_callback(percent)

    def verify_configs(self, mo2_profile_path, appdata_path, doc_path, ini_prefix="Skyrim", use_documents_mode=False, stealth_mode=False):
        """Compares plugins, loadorder, and INIs. Skips checks if in stealth mode."""
        if stealth_mode:
            print("[*] Live MO2 Mode detected: Skipping offline configuration checks (handled at runtime).")
            return

        print("[*] Verifying Configuration Synchronization...")
        mo2_p = Path(ensure_long_path(mo2_profile_path))
        app_p = Path(ensure_long_path(appdata_path))
        doc_p = Path(ensure_long_path(doc_path))

        # 1. Text Configs (AppData)
        for filename in ["plugins.txt", "loadorder.txt"]:
            src = mo2_p / filename
            dst = app_p / filename
            self._compare_files(src, dst, filename, "Local AppData")

        # 2. INI Files (Documents)
        # Source of truth depends on use_documents_mode
        source_label = "Windows Documents" if use_documents_mode else "MO2 Profile"
        if use_documents_mode:
            real_doc_path = Path(ensure_long_path(Path(os.path.expanduser(f"~/Documents/My Games/{Path(doc_path).name}")).resolve()))
            src_base = real_doc_path
        else:
            src_base = mo2_p

        for ini in [f"{ini_prefix}.ini", f"{ini_prefix}Prefs.ini", f"{ini_prefix}Custom.ini"]:
            src = src_base / ini
            dst = doc_p / ini
            
            # Special handling for Custom.ini to ignore sLocalSavePath
            ignore_pattern = "sLocalSavePath" if "Custom" in ini else None
            self._compare_files(src, dst, ini, f"Standalone (vs {source_label})", ignore_line=ignore_pattern)

    def _compare_files(self, src, dst, label, location_name, ignore_line=None):
        """Helper to compare file contents."""
        if not src.exists():
            return
        
        if not dst.exists():
            self.results["config_mismatch"].append(f"{label} missing in {location_name}")
            return

        try:
            with open(src, 'r', errors='ignore', encoding='utf-8-sig') as f1, \
                 open(dst, 'r', errors='ignore', encoding='utf-8-sig') as f2:
                
                c1 = [l.strip().lower() for l in f1.readlines() if l.strip()]
                c2 = [l.strip().lower() for l in f2.readlines() if l.strip()]
                
                if ignore_line:
                    pattern = ignore_line.lower()
                    c1 = [l for l in c1 if pattern not in l]
                    c2 = [l for l in c2 if pattern not in l]

                if c1 != c2:
                    self.results["config_mismatch"].append(f"{label} differs from {location_name}")
        except Exception as e:
            self.results["config_mismatch"].append(f"Error reading {label}: {str(e)}")

    def verify_saves(self, mo2_profile_path, doc_save_path, run_timestamp=None, use_documents_mode=False, stealth_mode=False):
        """Checks if all saves are synchronized, including timestamped quarantine folders."""
        print("[*] Verifying Save Games...")
        
        # 1. Determine Source (Where we expect saves to come from)
        if use_documents_mode and doc_save_path:
            docs_name = Path(doc_save_path).name
            src_saves_dir = Path(ensure_long_path(Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}/Saves")).resolve()))
        else:
            src_saves_dir = Path(ensure_long_path(mo2_profile_path)) / "saves"
            
        # 2. Determine Target (Where the standalone actually writes saves)
        if stealth_mode:
            doc_saves_dir = Path(ensure_long_path(mo2_profile_path)) / "standalone_profile" / "Saves"
        else:
            if not doc_save_path: return # Safety
            doc_saves_dir = Path(ensure_long_path(doc_save_path)) / "Saves"

        if not src_saves_dir.exists():
            return

        try:
            # 1. Map existing saves in destination (Root + All Quarantines)
            doc_saves = {f.name for f in doc_saves_dir.glob("*.[es][sk][se]*")}
            
            # Helper to process quarantine folders
            def process_q_dir(root, pattern, location_label, is_current=False):
                for q_dir in root.glob(pattern):
                    if q_dir.is_dir():
                        # If we have a run_timestamp, check if this is the "current" one
                        is_this_current = (run_timestamp and run_timestamp in q_dir.name)
                        
                        if not is_this_current:
                            self.results["has_historic_quarantine"] = True
                        
                        q_files = [f.name for f in q_dir.glob("*.[es][sk][se]*")]
                        for qf in q_files:
                            doc_saves.add(qf)
                            # Only report the "latest" (current run) in the detailed list
                            if is_this_current:
                                self.results["quarantined_items"].append({
                                    "file": qf,
                                    "location": str(q_dir),
                                    "reason": f"Newer/Conflicting save from {location_label} moved to current quarantine."
                                })
                                
            process_q_dir(doc_saves_dir, "MO2_import_save*", "Source")
            process_q_dir(src_saves_dir, "Standalone_Export_save*", "Standalone")

            # 2. Compare against Source
            src_saves = {f.name for f in src_saves_dir.glob("*.[es][sk][se]*")}
            
            missing = src_saves - doc_saves
            if missing:
                if stealth_mode:
                    # In Live MO2 Mode, we don't expect files in the standalone profile yet
                    print(f"    [*] Live MO2 Mode: {len(missing)} saves remain in source (Expected).")
                else:
                    source_label = "Windows Documents" if use_documents_mode else "MO2"
                    self.results["save_issues"].append({
                        "summary": f"Missing {len(missing)} save files in Standalone folder.",
                        "source": source_label,
                        "missing_files": sorted(list(missing))
                    })
                    for m in sorted(list(missing))[:5]:
                        print(f"    [-] Missing: {m}")
            
        except Exception as e:
            self.results["save_issues"].append({"summary": f"Error checking saves: {str(e)}", "source": "Internal", "missing_files": []})

    def verify_mod_completeness(self, modlist_path, manifest_path, report_path, mods_dir=None):
        """Cross-references MO2 modlist with build outputs to find redundant or broken mods."""
        print("[*] Auditing Mod Presence and Integrity...")
        modlist_p = Path(ensure_long_path(modlist_path))
        manifest_p = Path(ensure_long_path(manifest_path))
        report_p = Path(ensure_long_path(report_path))
        mods_base = Path(ensure_long_path(mods_dir)) if mods_dir else None

        active_mods = set()
        redundant_mods = []
        untracked_mods = set()
        broken_mods = []
        scan_failures = {}
        
        # 1. Parse modlist.txt for active mods
        if modlist_p.exists():
            try:
                with open(modlist_p, 'r', encoding='utf-8-sig') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('+'):
                            mod_name = line[1:]
                            if mod_name.lower().endswith("_separator"):
                                continue
                            active_mods.add(mod_name)
            except Exception as e:
                print(f"[!] Error reading modlist: {e}")

        # 2. Analyze Manifest & Report
        build_mod_data = {} 
        
        try:
            if manifest_p.exists():
                with open(manifest_p, 'r', encoding='utf-8') as f:
                    raw_manifest = json.load(f)
                    if isinstance(raw_manifest, dict) and "mapping" in raw_manifest:
                        manifest = raw_manifest["mapping"]
                        scan_failures = raw_manifest.get("scan_failures", {})
                    else:
                        manifest = raw_manifest
                        
                    for target, info in manifest.items():
                        mod = info.get('mod_origin', 'Unknown')
                        if mod not in build_mod_data:
                            build_mod_data[mod] = {"success": 0, "failed": 0, "total": 0}
                        build_mod_data[mod]["total"] += 1
                        build_mod_data[mod]["success"] += 1

            if report_p.exists():
                with open(report_p, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                    for target, info in report.items():
                        mod = info.get('mod', 'Unknown')
                        if mod not in build_mod_data:
                            build_mod_data[mod] = {"success": 0, "failed": 0, "total": 0}
                        
                        # Update stats from report (override manifest success assumptions)
                        if "SUCCESS" in info.get('status', ''):
                            pass # Already counted in manifest scan
                        else:
                            build_mod_data[mod]["success"] -= 1
                            build_mod_data[mod]["failed"] += 1
        except Exception as e:
            print(f"[!] Error during mod audit: {e}")

        # 3. Categorize results
        # A. Detect Redundant vs Broken Mods
        for mod in active_mods:
            if mod in scan_failures:
                # Mod had technical failures during scanning
                broken_mods.append({
                    "name": mod,
                    "failed": len(scan_failures[mod]),
                    "total": "N/A",
                    "rate": "Scan Fail",
                    "reason": scan_failures[mod][0] if scan_failures[mod] else "Technical Error"
                })
            elif mod not in build_mod_data:
                # Mod is missing from build. Likely Redundant (separator/readme)
                redundant_mods.append(mod)

        # B. Detect Untracked Mods
        for mod in build_mod_data.keys():
            if mod != "Overwrite" and mod != "Unknown" and mod not in active_mods:
                untracked_mods.add(mod)

        # C. Detect Broken Mods (Any link failure)
        for mod, stats in build_mod_data.items():
            if stats["failed"] > 0:
                failure_rate = (stats["failed"] / stats["total"]) * 100
                broken_mods.append({
                    "name": mod,
                    "failed": stats["failed"],
                    "total": stats["total"],
                    "rate": f"{failure_rate:.1f}%",
                    "reason": "Link/Hardlink Failure"
                })

        self.results["mod_audit"] = {
            "redundant_mods": sorted(redundant_mods),
            "untracked_mods": sorted(list(untracked_mods)),
            "broken_mods": sorted(broken_mods, key=lambda x: str(x.get('failed', 0)), reverse=True)
        }

        return self.results["mod_audit"]

    def run_all_checks(self, manifest_path=None, standalone_path=None, mo2_profile_path=None, appdata_path=None, doc_save_path=None, ini_prefix="Skyrim", run_timestamp=None, mods_dir=None, use_documents_mode=False, stealth_mode=False, progress_callback=None):
        if manifest_path:
            self.verify_deployment(manifest_path, standalone_path, progress_callback=progress_callback)
            
            # If we have manifest, we likely have the report next to it
            report_path = Path(manifest_path).parent / "execution_report.json"
            if mo2_profile_path:
                modlist_path = Path(mo2_profile_path) / "modlist.txt"
                self.verify_mod_completeness(modlist_path, manifest_path, report_path, mods_dir=mods_dir)
            
        if mo2_profile_path and (appdata_path or stealth_mode):
            self.verify_configs(mo2_profile_path, appdata_path, doc_path=doc_save_path, ini_prefix=ini_prefix, use_documents_mode=use_documents_mode, stealth_mode=stealth_mode)
            self.verify_saves(mo2_profile_path, doc_save_path, run_timestamp=run_timestamp, use_documents_mode=use_documents_mode, stealth_mode=stealth_mode)
        
        # 4. Save results to persistent log in metadata folder
        if manifest_path:
            try:
                manifest_p = Path(ensure_long_path(manifest_path))
                log_path = manifest_p.parent / "verification_report.json"
                with open(log_path, 'w', encoding='utf-8') as f:
                    json.dump(self.results, f, indent=4)
                print(f"[SUCCESS] Deep verification report saved to: {log_path}")
            except Exception as e:
                print(f"[!] Warning: Failed to save verification report: {e}")

        return self.results
