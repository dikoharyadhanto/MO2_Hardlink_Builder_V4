import os
import sys
import json
from pathlib import Path
from path_utils import ensure_long_path
from state_manager import ConflictManager, ModlistSnapshot

class ScannerEngine:
    def __init__(self, mods_dir, overwrite_dir, profile_dir, output_dir=None):
        self.mods_dir = Path(ensure_long_path(mods_dir))
        self.overwrite_dir = Path(ensure_long_path(overwrite_dir))
        self.profile_path = Path(ensure_long_path(profile_dir))
        self.modlist_txt = self.profile_path / "modlist.txt"
        
        # Determine Base Path
        if output_dir:
            self.metadata_dir = Path(output_dir)
        else:
            raise ValueError("output_dir must be provided to ScannerEngine")
            
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.output_manifest = self.metadata_dir / "mapping_manifest.json"
        
        self.blacklist_files = [
            'meta.ini', 'mo2_separator.txt', 'thumbs.db', 'desktop.ini',
            'readme.txt', 'credits.txt', 'changelog.txt', 'license.txt',
            'readme.md', 'credits.md', 'changelog.md'
        ]
        self.blacklist_dirs = [
            '.hidden', 'fomod', 'readmes', 'readme', 'docs', 'documents', 
            'credits', 'changelog', 'licenses', 'rootbuilder', 'backup'
        ]
            
        self.blacklist_extensions = ['.pdf', '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt']
        
        self.critical_extensions = [
            '.esp', '.esm', '.esl', '.bsa', '.ba2', '.nif', '.dds', 
            '.hkx', '.fuz', '.wav', '.swf', '.tri', '.seq'
        ]
        
        self.failed_mods = {}
        
        # Initialize Conflict Manager
        self.conflict_manager = ConflictManager(self.metadata_dir)

    def _get_active_mods(self):
        # ... (remains same) ...
        # Copied from viewing file to ensure Context match
        if not self.modlist_txt.exists():
            return []

        active_mods = []
        try:
            with open(self.modlist_txt, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
            
            processed_lines = []
            for line in lines:
                line = line.strip()
                if line.startswith('+') or line.startswith('*DLC:') or line.startswith('*Creation Club:'):
                    processed_lines.append(line)

            if not processed_lines:
                return []

            core_keywords = ["dlc:", "base game", "creation club:"]
            core_positions = []
            for i, line in enumerate(processed_lines):
                low_line = line.lower()
                if any(k in low_line for k in core_keywords):
                    core_positions.append(i)
            
            is_reversed = True 
            if core_positions:
                avg_pos = sum(core_positions) / len(core_positions)
                if avg_pos > (len(processed_lines) / 2):
                    is_reversed = False
            
            if is_reversed:
                for line in processed_lines:
                    if line.startswith('+'):
                        active_mods.append(line[1:])
            else:
                for line in reversed(processed_lines):
                    if line.startswith('+'):
                        active_mods.append(line[1:])
        except Exception as e:
            print(f"[!] Error reading modlist.txt: {e}")

        return active_mods

    def _scan_folder(self, folder_path, mod_name, mapping_table):
        try:
            for root, dirs, files in os.walk(folder_path):
                dirs[:] = [d for d in dirs if d.lower() not in self.blacklist_dirs]

                for file_name in files:
                    ext = Path(file_name).suffix.lower()
                    
                    if file_name.lower() in self.blacklist_files or ext in self.blacklist_extensions:
                        continue

                    try:
                        full_source = Path(root) / file_name
                        rel_path = full_source.relative_to(folder_path)
                        parts = rel_path.parts
                        
                        if parts[0].lower() == 'root':
                            target_path = Path(*parts[1:])
                            is_root = True
                        elif parts[0].lower() == 'data':
                            target_path = rel_path
                            is_root = False
                        else:
                            target_path = Path("Data") / rel_path
                            is_root = False
                        
                        target_key = str(target_path).lower().replace("\\", "/")
                        
                        # === CONFLICT REGISTRATION ===
                        self.conflict_manager.register_file(str(target_path), mod_name)
                        
                        try: stat = full_source.stat()
                        except: stat = None

                        mapping_table[target_key] = {
                            "source": str(full_source),
                            "mod_origin": mod_name,
                            "is_root": is_root,
                            "size_bytes": stat.st_size if stat else 0,
                            "mtime": stat.st_mtime if stat else 0,
                            "preferred_path": str(target_path)
                        }
                    except (PermissionError, OSError) as e:
                        if mod_name not in self.failed_mods: self.failed_mods[mod_name] = []
                        self.failed_mods[mod_name].append(f"File Access Error: {file_name} ({str(e)})")
        except Exception as e:
            if mod_name not in self.failed_mods: self.failed_mods[mod_name] = []
            self.failed_mods[mod_name].append(f"Scan Error: {str(e)}")

    def build_mapping(self, progress_callback=None):
        active_mods = self._get_active_mods()
        mapping_table = {}
        folder_states = {}
        
        print(f"[*] Scanning {len(active_mods)} mods in profile: {self.profile_path.name}")
        total = len(active_mods)
        
        for i, mod_name in enumerate(active_mods):
            mod_folder = self.mods_dir / mod_name
            if mod_folder.exists():
                try: folder_states[mod_name] = mod_folder.stat().st_mtime
                except: folder_states[mod_name] = 0
                
                # Check timestamps for cache? No, Builder always full scans.
                # But we populate the conflict manager.
                
                self._scan_folder(mod_folder, mod_name, mapping_table)
            
            if progress_callback:
                percent = int(((i + 1) / total) * 100)
                progress_callback(percent)

        if self.overwrite_dir.exists():
            print(f"[*] Scanning Overwrite folder (Ghost Mods)...")
            self._scan_folder(self.overwrite_dir, "Overwrite", mapping_table)

        # Build final output object including failures
        output_data = {
            "mapping": mapping_table,
            "scan_failures": self.failed_mods,
            "folder_states": folder_states
        }

        with open(self.output_manifest, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4)
            
        # === SAVE METADATA ===
        self.conflict_manager.save()
        
        # Save Modlist Snapshot
        try:
            snapshot = ModlistSnapshot(self.profile_path)
            snapshot.save_snapshot(self.metadata_dir / "modlist_reference.txt")
        except: pass
        
        print(f"[*] Manifest & Metadata saved.")
