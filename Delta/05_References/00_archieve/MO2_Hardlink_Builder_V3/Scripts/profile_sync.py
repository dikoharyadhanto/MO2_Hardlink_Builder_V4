import os
import shutil
from pathlib import Path
from datetime import datetime
from path_utils import ensure_long_path

class ProfileSync:
    def __init__(
        self, profile_dir, sa_path, 
        docs_name="Skyrim Special Edition", 
        appdata_name="Skyrim Special Edition", 
        ini_prefix="Skyrim", 
        game_name="Skyrim SE", 
        profile_name="Default", 
        portable_mode=True, 
        use_documents_mode=False, 
        stealth_mode=False,
        callback=None, 
        log_callback=None
    ):
        self.profile_dir = Path(ensure_long_path(Path(profile_dir).resolve()))
        self.profile_name = profile_name # Used for backup labels/paths
        self.sa_path = Path(ensure_long_path(Path(sa_path).resolve()))
        self.ini_prefix = ini_prefix
        self.portable_mode = portable_mode
        self.stealth_mode = stealth_mode
        self.use_documents_mode = use_documents_mode  # If True, source config/saves from Windows Documents instead of profile
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.callback = callback # Optional function for UI prompts/messages (returns bool)
        self.log_callback = log_callback # Optional function for progress logging
        
        # Source Locations (where to get files FROM)
        if self.use_documents_mode:
            # Use Windows Documents folder as source for INI files only
            self.source_docs = Path(ensure_long_path(Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")).resolve()))
        else:
            # Use MO2 profile folder as source
            self.source_docs = self.profile_dir
        
        # Plugins and loadorder ALWAYS come from profile (not affected by Documents mode)
        self.source_appdata = self.profile_dir
        
        # Target Locations (where to deploy files TO in standalone)
        if self.stealth_mode:
            # Redirect to isolated profile inside MO2
            iso_profile = self.profile_dir / "standalone_profile"
            self.win_docs = iso_profile
            self.win_appdata = iso_profile / "AppData" / "Local"
            self.win_roaming = iso_profile / "AppData" / "Roaming"
        elif self.portable_mode:
            self.win_docs = self.sa_path / "_standalone" / "Documents" / "My Games" / docs_name
            self.win_appdata = self.sa_path / "_standalone" / "AppData" / "Local" / appdata_name
            self.win_roaming = self.sa_path / "_standalone" / "AppData" / "Roaming" / appdata_name
        else:
            self.win_docs = Path(ensure_long_path(Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")).resolve()))
            self.win_appdata = Path(ensure_long_path(Path(os.environ['LOCALAPPDATA']).resolve())) / appdata_name
            self.win_roaming = Path(ensure_long_path(Path(os.environ['APPDATA']).resolve())) / appdata_name
        
        # Ensure directories exist
        if self.stealth_mode or self.portable_mode:
            self.win_docs.mkdir(parents=True, exist_ok=True)
            self.win_appdata.mkdir(parents=True, exist_ok=True)
            self.win_roaming.mkdir(parents=True, exist_ok=True)
        
        self.backup_root = Path(os.environ['LOCALAPPDATA']) / "MO2_Hardlink_Builder" / game_name / profile_name / "Backups"

    def backup_shared_docs(self, target_dir):
        """Creates a timestamped backup of the real Documents folder if it exists."""
        if not target_dir.exists():
            return None
            
        backup_path = self.backup_root / f"Shared_Docs_Backup_{self.run_timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        if self.log_callback:
            self.log_callback(f"[*] Creating safety backup for Shared Mode: {backup_path.name}")
            
        for item in target_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, backup_path / item.name)
            elif item.is_dir() and item.name.lower() != "saves":
                try: shutil.copytree(item, backup_path / item.name)
                except: pass
        
        save_dir = target_dir / "Saves"
        if save_dir.exists():
            backup_saves = backup_path / "Saves"
            backup_saves.mkdir(parents=True, exist_ok=True)
            for s in save_dir.iterdir():
                if s.is_file():
                    shutil.copy2(s, backup_saves / s.name)
                    
        return backup_path

    def _safe_copy(self, src, dst):
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True
        return False

    def _process_sync(self, src_dir, dst_dir, quarantine_base_name, action_label):
        if not src_dir.exists():
            return False

        all_files = [item for item in src_dir.iterdir() if item.is_file()]
        if not all_files:
            return False

        dst_dir.mkdir(parents=True, exist_ok=True)
        
        conflicts = []
        new_files = []
        
        for item in all_files:
            target_path = dst_dir / item.name
            if target_path.exists():
                conflicts.append(item)
            else:
                new_files.append(item)

        # Descriptive message from EXE Standalone logic
        overwrite = True
        quarantine_dir = None
        if conflicts:
            msg = f"Conflict detected for {len(conflicts)} save files in destination ({action_label}).\n\n" \
                  f"Overwrite existing files?\n\n" \
                  f"YES: Overwrite them.\n" \
                  f"NO: Move to quarantine folder '{quarantine_base_name}' instead."
            
            if self.callback:
                overwrite = self.callback("Save Conflict", msg)
            
            if not overwrite:
                # Quarantine if not overwriting
                quarantine_dir = dst_dir / f"{quarantine_base_name}_{self.run_timestamp}"
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                if self.log_callback:
                    self.log_callback(f"[*] Conflict mode: Moving {len(conflicts)} files to quarantine folder...")

        # Process new files
        import time
        for i, item in enumerate(new_files):
            if self.log_callback and i % 5 == 0:
                self.log_callback(f"[*] Processing: {item.name}")
            
            success = False
            for retry in range(3):
                try:
                    shutil.copy2(item, dst_dir / item.name)
                    success = True
                    break
                except PermissionError:
                    if self.log_callback:
                        self.log_callback(f"[!] Warning: File locked, retrying ({retry+1}/3): {item.name}")
                    time.sleep(1)
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"[!] Error processing: {item.name} - {e}")
                    break
            
            if not success and self.log_callback:
                self.log_callback(f"[!] FAILED to process (Skipping): {item.name}")
            
        # Process conflicts
        for i, item in enumerate(conflicts):
            dst_file = dst_dir / item.name
            target = dst_file if overwrite else (quarantine_dir / item.name)
            op_label = "Overwrite" if overwrite else "Quarantine"
            
            success = False
            for retry in range(3):
                try:
                    if overwrite:
                        if self.log_callback and i % 5 == 0:
                            self.log_callback(f"[*] {op_label}: {item.name}")
                        shutil.copy2(item, dst_file)
                    else:
                        if self.log_callback and i % 5 == 0:
                            self.log_callback(f"[*] {op_label}: {item.name}")
                        try:
                            shutil.move(str(item), str(target))
                        except Exception:
                            shutil.copy2(item, target)
                    
                    success = True
                    break
                except PermissionError:
                    if self.log_callback:
                        self.log_callback(f"[!] Warning: File locked, retrying ({retry+1}/3): {item.name}")
                    time.sleep(1)
                except Exception as e:
                    if self.log_callback:
                        self.log_callback(f"[!] Error during {op_label}: {item.name} - {e}")
                    break
            
            if not success and self.log_callback:
                self.log_callback(f"[!] FAILED to {op_label} (Skipping): {item.name}")
        
        if self.log_callback:
            self.log_callback(f"[SUCCESS] Sync complete: {len(all_files)} files processed.")
        return True

    def sync_saves_to_mo2(self):
        win_saves = self.win_docs / "Saves"
        mo2_saves = self.profile_dir / "saves"
        return self._process_sync(win_saves, mo2_saves, "Standalone_Export_save", "Standalone -> MO2")

    def push_saves_to_docs(self):
        # Source: Use Documents folder if in Documents mode, otherwise use profile folder
        if self.use_documents_mode:
            source_saves = self.source_docs / "Saves"
        else:
            source_saves = self.profile_dir / "saves"
        
        win_saves = self.win_docs / "Saves"
        action_label = "Documents -> Standalone" if self.use_documents_mode else "MO2 -> Standalone"
        return self._process_sync(source_saves, win_saves, "MO2_import_save", action_label)

    def clean_custom_save_path(self):
        custom_ini = self.win_docs / f"{self.ini_prefix}Custom.ini"
        
        lines = []
        if custom_ini.exists():
            try:
                with open(custom_ini, 'r', encoding='utf-8-sig', errors='ignore') as f:
                    lines = f.readlines()
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"[ERROR] Failed to read custom ini: {e}")

        new_lines = []
        general_found = False
        save_path_found = False

        for line in lines:
            trimmed = line.strip()
            if trimmed.lower() == "[general]":
                general_found = True
                new_lines.append(line)
                if not save_path_found: # Only add if not already added
                    new_lines.append("sLocalSavePath=Saves\\\n")
                    save_path_found = True
                continue
            if trimmed.lower().startswith("slocalsavepath"):
                if save_path_found: # If we already added it after [General], skip this existing one
                    continue
                # If [General] was not found yet, or sLocalSavePath was before [General],
                # we'll handle adding it correctly later. For now, just mark it found.
                save_path_found = True
                continue # Skip adding the old sLocalSavePath line
            new_lines.append(line)

        if not general_found:
            # If [General] was never found, add it at the top
            new_lines.insert(0, "[General]\n")
            new_lines.insert(1, "sLocalSavePath=Saves\\\n")
        elif not save_path_found:
            # If [General] was found, but sLocalSavePath was not added (meaning it wasn't present
            # or was removed by the loop logic), insert it after the [General] line.
            for i, line in enumerate(new_lines):
                if line.strip().lower() == "[general]":
                    new_lines.insert(i + 1, "sLocalSavePath=Saves\\\n")
                    break

        try:
            with open(custom_ini, 'w', encoding='utf-8-sig') as f:
                f.writelines(new_lines)
            
            if self.log_callback:
                self.log_callback(f"[*] Forced relative save path secured: {custom_ini.name}")
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"[ERROR] Failed to clean/write custom ini: {e}")
            else:
                print(f"[ERROR] Failed to clean custom ini: {e}")

