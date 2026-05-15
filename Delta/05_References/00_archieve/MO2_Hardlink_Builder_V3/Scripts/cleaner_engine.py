import os
import shutil
import stat
from pathlib import Path
from path_utils import ensure_long_path

class CleanerEngine:
    def __init__(self, sa_path, mo2_path, steam_path=None, docs_name="Skyrim Special Edition", appdata_name="Skyrim Special Edition", game_name="Skyrim SE", profile_name="Default", portable_mode=True, mods_path=None, overwrite_path=None):
        self.sa_path = Path(ensure_long_path(Path(sa_path).resolve()))
        self.mo2_path = Path(ensure_long_path(Path(mo2_path).resolve()))
        self.steam_path = Path(ensure_long_path(Path(steam_path).resolve())) if steam_path else None
        self.mods_path = Path(ensure_long_path(Path(mods_path).resolve())) if mods_path else None
        self.overwrite_path = Path(ensure_long_path(Path(overwrite_path).resolve())) if overwrite_path else None
        self.portable_mode = portable_mode
        self.profile_name = profile_name
        
        # New Dynamic Backup Path in LocalAppData
        self.backup_root = Path(os.environ['LOCALAPPDATA']) / "MO2_Hardlink_Builder" / game_name / profile_name / "Backups"
        
        # Only ensure backup directory if NOT in portable mode (safety)
        if not self.portable_mode:
            self.backup_root.mkdir(parents=True, exist_ok=True)
        
        self.win_docs = Path(ensure_long_path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")))
        self.win_appdata = Path(ensure_long_path(os.environ['LOCALAPPDATA'])) / appdata_name
        self.win_roaming = Path(ensure_long_path(os.environ['APPDATA'])) / appdata_name

    def is_inside(self, child, parent):
        """Checks if a path is inside another path."""
        try:
            child_p = Path(child).resolve()
            parent_p = Path(parent).resolve()
            return parent_p in child_p.parents or child_p == parent_p
        except:
            return False

    def check_safety(self):
        """Checks for safety before proceeding. Returns (bool, message)."""
        # 1. Check if the target folder is the MO2 folder or its parent (or nested)
        if self.is_inside(self.sa_path, self.mo2_path):
            return False, "FORBIDDEN: Standalone folder cannot be INSIDE or IS the MO2 folder!"
        if self.is_inside(self.mo2_path, self.sa_path):
            return False, "FORBIDDEN: You cannot select a parent folder of MO2 as the Standalone destination!"
        
        # 1b. Extra checks for Nolvus/relocated mods
        if self.mods_path and self.is_inside(self.sa_path, self.mods_path):
             return False, "FORBIDDEN: Standalone folder cannot be INSIDE your MO2 Mods folder!"
        if self.overwrite_path and self.is_inside(self.sa_path, self.overwrite_path):
             return False, "FORBIDDEN: Standalone folder cannot be INSIDE your MO2 Overwrite folder!"
        
        # 2. Check if the target folder is the Steam installation folder (or nested/parent)
        if self.steam_path:
            if self.is_inside(self.sa_path, self.steam_path):
                return False, "FORBIDDEN: Standalone folder cannot be INSIDE or IS your Original Game folder!"
            if self.is_inside(self.steam_path, self.sa_path):
                return False, "FORBIDDEN: You cannot select a parent folder of your Game installation (like Steam root) as the Standalone destination!"

        # 3. Standalone Identity Check
        standalone_markers = ["standalone_metadata"]
        is_standalone = any((self.sa_path / m).exists() for m in standalone_markers)

        # 4. PROTECTED FOLDER CHECK (New)
        if (self.sa_path / ".mo2_protected").exists():
            return False, "PROTECTED FOLDER: This folder is managed by the MO2 Hardlink Updater. Please 'Unlink' it via the Updater tool before cleaning or rebuilding."

        # 5. Extra Protection: Check if it looks like a Steam folder
        if not is_standalone:
            steam_indicators = ["steam.exe", "Steam.dll", "steam_api64.dll"]
            if any((self.sa_path / indicator).exists() for indicator in steam_indicators):
                 return False, "FORBIDDEN FOLDER! This folder contains Steam system files. Cleaning is blocked for your safety."

        return True, "Safe"

    def restore_profiles(self):
        print(f"[*] Restoring original profile data from: {self.backup_root}")
        
        # Restore Documents
        doc_backup = self.backup_root / "Documents"
        if doc_backup.exists():
            for ini in doc_backup.iterdir():
                if ini.is_file():
                    dst = self.win_docs / ini.name
                    shutil.copy2(ini, dst)
            
        # Restore AppData
        app_backup = self.backup_root / "AppData"
        if app_backup.exists():
            if self.win_appdata.exists():
                shutil.rmtree(self.win_appdata, onerror=self._handle_remove_readonly)
            shutil.copytree(app_backup, self.win_appdata)

    def clean_mo2_standalone_profile(self, progress_callback=None):
        """Removes the isolated standalone_profile folder from the MO2 profile."""
        mo2_standalone = self.mo2_path / "profiles" / self.profile_name / "standalone_profile"
        if mo2_standalone.exists() and mo2_standalone.is_dir():
            print(f"[*] CLEANING PERSISTENT STANDALONE PROFILE: {mo2_standalone}")
            try:
                shutil.rmtree(mo2_standalone, onerror=self._handle_remove_readonly)
                if progress_callback: progress_callback(100)
                return True, ""
            except Exception as e:
                err = str(e)
                print(f"  [Failed] Could not remove standalone_profile: {err}")
                return False, err
        return True, ""

    def total_cleanup(self, progress_callback=None):
        """
        Performs a full cleanup and returns a status dict.
        Returns: {"status": "SKIPPED"|"FINISHED"|"PARTIAL_FAILURE", "errors": []}
        """
        print(f"[*] CLEANING STANDALONE DIRECTORY: {self.sa_path}")
        errors = []

        # 1. Count items in main standalone folder
        try:
            items = list(self.sa_path.iterdir())
        except Exception as e:
            print(f"  [Error] Could not list directory: {e}")
            return {"status": "PARTIAL_FAILURE", "errors": [f"Root Directory: {str(e)}"]}
            
        total = len(items)
        if total == 0:
            print("  [*] Folder is already empty. Skipping cleanup.")
            # Still clean MO2 profile if it exists
            self.clean_mo2_standalone_profile()
            if progress_callback: progress_callback(100)
            return {"status": "SKIPPED", "errors": []}

        # 2. Wipe all contents of the standalone folder FIRST
        # This prevents dangling junctions when we delete the source profile folder
        for i, item in enumerate(items):
            try:
                # Junction/Symlink Detection (Crucial for Windows)
                if item.is_symlink() or os.path.islink(item) or self._is_junction(item):
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, onerror=self._handle_remove_readonly)
                else:
                    # Regular file
                    try:
                        item.unlink()
                    except PermissionError:
                        os.chmod(item, stat.S_IWRITE)
                        item.unlink()
            except Exception as e:
                err_msg = f"{item.name}: {str(e)}"
                print(f"  [Failed] {err_msg}")
                errors.append(err_msg)
            
            if progress_callback:
                percent = int(((i + 1) / total) * 85) # Leave room for bridge and MO2 profile cleanup
                progress_callback(percent)

        # 2b. Explicitly check for hidden/leftover bridge folders (standalone_bridge)
        bridge_folder = self.sa_path / "standalone_bridge"
        if bridge_folder.exists() and bridge_folder.is_dir():
            print(f"[*] CLEANING HIDDEN BRIDGE: {bridge_folder}")
            try:
                shutil.rmtree(bridge_folder, onerror=self._handle_remove_readonly)
            except Exception as e:
                print(f"  [Failed] Could not remove standalone_bridge: {e}")
                errors.append(f"standalone_bridge: {str(e)}")

        # 3. Clean the isolated profile in MO2
        success, err = self.clean_mo2_standalone_profile()
        if not success:
            errors.append(f"MO2 persistent profile: {err}")

        if progress_callback: progress_callback(100)

        if errors:
            print(f"  [!] Cleanup finished with {len(errors)} locked or inaccessible items.")
            return {"status": "PARTIAL_FAILURE", "errors": errors}
        
        print("  [SUCCESS] Cleanup complete.")
        return {"status": "FINISHED", "errors": []}

    def _is_junction(self, path):
        """Checks if a path is a Windows Junction or Symlink."""
        try:
            if os.name != 'nt': return False
            return bool(os.path.islink(path) or (os.stat(path).st_file_attributes & 0x400))
        except:
            return False

    def _handle_remove_readonly(self, func, path, excinfo):
        """Error handler for shutil.rmtree to handle read-only files and junctions."""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            # If it's a directory and failed to remove, it might be a junction that shutil.rmtree missed
            if os.path.isdir(path):
                try:
                    os.rmdir(path)
                except:
                    raise e
            else:
                raise e

