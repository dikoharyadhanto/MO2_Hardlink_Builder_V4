import os
import sys
import json
import shutil
from pathlib import Path
from path_utils import ensure_long_path

class LinkerExecutor:
    def __init__(self, standalone_path, original_game_path, output_dir=None):
        if not output_dir:
            raise ValueError("output_dir must be provided to LinkerExecutor")
            
        self.standalone_path = Path(ensure_long_path(standalone_path))
        self.game_path = Path(ensure_long_path(original_game_path))
        
        # The passed output_dir IS the metadata directory (from plugin_ui)
        self.metadata_dir = Path(output_dir)
        self.output_dir = self.metadata_dir # Alias for clarity if needed
        
        self.manifest_file = self.metadata_dir / "mapping_manifest.json"
        self.report_file = self.metadata_dir / "execution_report.json"
        self.broken_mods_log = self.metadata_dir / "brokenmods_logs.txt"

    def _recursive_vanilla_deploy(self, src_root, dst_root, mode='copy'):
        for item in src_root.iterdir():
            if item.name.lower() == '_commonredist': 
                continue
            target = dst_root / item.name
            if item.is_dir():
                target.mkdir(exist_ok=True)
                self._recursive_vanilla_deploy(item, target, mode)
            else:
                if not target.exists():
                    if mode == 'link':
                        try:
                            os.link(item, target)
                        except OSError:
                            # Fallback to copy if hardlink fails
                            shutil.copy2(item, target)
                    else:
                        shutil.copy2(item, target)

    def initial_vanilla_clone(self, mode='copy'):
        print(f"[*] Cloning vanilla files (mode: {mode})...")
        self._recursive_vanilla_deploy(self.game_path, self.standalone_path, mode)

    def clean_orphaned_files(self):
        if not self.manifest_file.exists():
            return

        with open(self.manifest_file, 'r') as f:
            manifest = json.load(f)
        
        manifest_targets = {k.lower().replace("\\", "/") for k in manifest.keys()}
        protected_prefixes = ['data/skyrim', 'data/fallout', 'data/starfield', 'data/oblivion', 'data/update']
        protected_extensions = ['.exe', '.dll', '.bsa', '.esm', '.ba2'] 

        for root, dirs, files in os.walk(self.standalone_path):
            for file_name in files:
                full_path = Path(root) / file_name
                rel_path = full_path.relative_to(self.standalone_path)
                rel_key = str(rel_path).lower().replace("\\", "/")

                is_protected = False
                if any(rel_key.startswith(p) for p in protected_prefixes): is_protected = True
                if rel_key.count('/') == 0 and any(rel_key.endswith(ext) for ext in protected_extensions): is_protected = True
                if rel_key.endswith('.bsa'): is_protected = True
                
                if rel_key not in manifest_targets and not is_protected:
                    try:
                        os.remove(full_path)
                    except:
                        pass

    def execute_mapping(self, clean=False, progress_callback=None):
        if clean:
            self.clean_orphaned_files()

        if not self.manifest_file.exists():
            return

        # Initialize/Clear Broken Mods Log
        with open(self.broken_mods_log, "w", encoding="utf-8") as log:
            log.write(f"BROKEN MODS LOG - {Path(self.broken_mods_log).stem.replace('_', ' ').upper()}\n")
            log.write(f"Build Timestamp: {os.path.getmtime(self.manifest_file)}\n")
            log.write("="*80 + "\n\n")

        with open(self.manifest_file, 'r') as f:
            raw_manifest = json.load(f)
            if isinstance(raw_manifest, dict) and "mapping" in raw_manifest:
                manifest = raw_manifest["mapping"]
                
                # Log Scan Failures if present
                if "scan_failures" in raw_manifest:
                    scan_fails = raw_manifest["scan_failures"]
                    if scan_fails:
                        with open(self.broken_mods_log, "a", encoding="utf-8") as log:
                            log.write("[SCAN FAILURES] The following mods were skipped due to structural issues:\n")
                            for mod, reasons in scan_fails.items():
                                log.write(f"Mod: {mod}\n")
                                for r in reasons:
                                    log.write(f"    - {r}\n")
                            log.write("-" * 80 + "\n\n")
            else:
                manifest = raw_manifest

        total = len(manifest)
        print(f"[*] Deploying {total} files to standalone...")
        report = {}

        for i, (target_key, info) in enumerate(manifest.items()):
            source_path = Path(ensure_long_path(info['source']))
            # Use preferred_path (original casing) for physical deployment
            target_rel_path = info.get('preferred_path', target_key)
            target_full_path = self.standalone_path / target_rel_path
            
            try:
                if target_full_path.exists():
                    if target_full_path.is_file() or target_full_path.is_symlink():
                        os.remove(target_full_path)
                    elif target_full_path.is_dir():
                        shutil.rmtree(target_full_path)

                target_full_path.parent.mkdir(parents=True, exist_ok=True)

                method = "unknown"
                try:
                    # Try Hardlink first if on the same drive
                    if source_path.anchor.lower() == self.standalone_path.anchor.lower():
                        try:
                            os.link(source_path, target_full_path)
                            method = "hardlink"
                        except OSError:
                            # Fallback to Copy if hardlink fails (e.g. cross-vol, path limit, or file in use)
                            shutil.copy2(source_path, target_full_path)
                            method = "copy"
                    else:
                        # Different drives: Copy is the only option
                        shutil.copy2(source_path, target_full_path)
                        method = "copy"

                    report[target_rel_path] = {"status": "SUCCESS", "method": method, "mod": info['mod_origin']}
                except Exception as e:
                    # Both Hardlink and Copy failed (or some other error during the process)
                    error_msg = str(e)
                    report[target_rel_path] = {"status": "FAILED", "error": error_msg, "mod": info['mod_origin']}
                    
                    # Log to brokenmods_logs.txt
                    with open(self.broken_mods_log, "a", encoding="utf-8") as log:
                        log.write(f"[DEPLOYMENT FAILURE] Mod: {info['mod_origin']}\n")
                        log.write(f"    File: {target_rel_path}\n")
                        log.write(f"    Error: {error_msg}\n")
                        log.write("-" * 40 + "\n")
            except Exception as e:
                # Capture errors during os.remove or directory creation
                error_msg = str(e)
                report[target_rel_path] = {"status": "FAILED", "error": error_msg, "mod": info['mod_origin']}
                with open(self.broken_mods_log, "a", encoding="utf-8") as log:
                    log.write(f"[PRE-DEPLOYMENT FAILURE] Mod: {info['mod_origin']}\n")
                    log.write(f"    File: {target_rel_path}\n")
                    log.write(f"    Error: {error_msg}\n")
                    log.write("-" * 40 + "\n")
            
            if progress_callback and (i % 50 == 0 or i == total - 1):
                percent = int(((i + 1) / total) * 100)
                progress_callback(percent)

        with open(self.report_file, 'w') as f:
            json.dump(report, f, indent=4)
            
        # === COPY METADATA ===
        try:
            target_meta = self.standalone_path / "standalone_metadata"
            
            # Smart Check: If we are already writing to the target metadata folder, DO NOT DELETE IT!
            if self.metadata_dir.resolve() == target_meta.resolve():
                print(f"[*] Metadata is already in place at: {target_meta}")
            else:
                if target_meta.exists():
                    shutil.rmtree(target_meta)
                shutil.copytree(self.metadata_dir, target_meta)
                print(f"[*] Metadata copied to: {target_meta}")
        except Exception as e:
            print(f"[!] Warning: Failed to copy metadata: {e}")
