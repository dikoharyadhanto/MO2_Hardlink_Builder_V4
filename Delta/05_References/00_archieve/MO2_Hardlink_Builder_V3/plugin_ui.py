import os
import sys
import json
import datetime
import traceback
import subprocess
import shutil
import urllib.request
import ctypes
import webbrowser
from pathlib import Path
try:
    import winreg
except ImportError:
    winreg = None

# --- Configuration & Links ---
VERSION_FILE_URL = "https://raw.githubusercontent.com/dikoharyadhanto/MO2_Hardlink_Builder/refs/heads/main/version.txt"
NEXUS_MOD_URL = "https://www.nexusmods.com/skyrimspecialedition/mods/172014"
# ----------------------------

# Try PySide6 first (MO2 2.5+), fallback to PyQt6 or PyQt5
try:
    from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                   QLineEdit, QPushButton, QTextEdit, QFileDialog, 
                                   QMessageBox, QCheckBox, QProgressBar, QComboBox,
                                   QTabWidget, QWidget, QGridLayout, QScrollArea, QFrame, QGroupBox,
                                   QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
                                   QTextBrowser)
    from PySide6.QtCore import Qt, QThread, Signal as pyqtSignal, QObject, QWaitCondition, QMutex
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    QT_NAME = "PySide6"
except ImportError:
    try:
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                     QLineEdit, QPushButton, QTextEdit, QFileDialog, 
                                     QMessageBox, QCheckBox, QProgressBar, QComboBox,
                                     QTabWidget, QWidget, QGridLayout, QScrollArea, QFrame, QGroupBox,
                                     QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
                                     QTextBrowser)
        from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QWaitCondition, QMutex
        from PyQt6.QtGui import QDragEnterEvent, QDropEvent
        QT_NAME = "PyQt6"
    except ImportError:
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                     QLineEdit, QPushButton, QTextEdit, QFileDialog, 
                                     QMessageBox, QCheckBox, QProgressBar, QComboBox,
                                     QTabWidget, QWidget, QGridLayout, QScrollArea, QFrame, QGroupBox,
                                     QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
                                     QTextBrowser)
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QWaitCondition, QMutex
        from PyQt5.QtGui import QDragEnterEvent, QDropEvent
        QT_NAME = "PyQt5"

# Import logic from Scripts folder relative to this file
import mobase

# Initialize engines to None to prevent NameError
ScannerEngine = None
LinkerExecutor = None
CleanerEngine = None
ProfileSync = None
VerificationEngine = None
ReportGenerator = None

# Add Scripts to sys.path
BASE_DIR = Path(__file__).parent
SCRIPTS_DIR = BASE_DIR / "Scripts"
REGISTRY_FILE = BASE_DIR / "standalone_registry.json"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

# Lazy import logic engines with individual safety
try:
    from scanner_engine import ScannerEngine
except ImportError: print("[!] ScannerEngine not found")

try:
    from linker_executor import LinkerExecutor
except ImportError: print("[!] LinkerExecutor not found")

try:
    from cleaner_engine import CleanerEngine
except ImportError: print("[!] CleanerEngine not found")

try:
    from profile_sync import ProfileSync
except ImportError: print("[!] ProfileSync not found")

try:
    from verification_engine import VerificationEngine
except ImportError: print("[!] VerificationEngine not found")

try:
    from report_generator import ReportGenerator
except ImportError: print("[!] ReportGenerator not found")

try:
    from path_utils import ensure_long_path, clean_path_for_display
except ImportError: print("[!] path_utils not found")

try:
    from process_utils import set_priority, set_affinity
except ImportError: 
    print("[!] process_utils not found")
    def set_priority(cpu=True, io=True): pass
    def set_affinity(mask): pass

# --- Hardware Detection Helpers ---
def escape_cs_string(s):
    """Escapes a string for use in a C# verbatim string literal (@"")."""
    if not s: return ""
    return str(s).replace('"', '""')
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

def get_total_ram_gb():
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return round(stat.ullTotalPhys / (1024**3), 2)
    except: return 0.0

def get_windows_documents_path():
    """Robustly retrieves the Windows Documents folder path using Shell API (v3.1.2)."""
    try:
        # CSIDL_PERSONAL = 0x0005 (My Documents)
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
        if buf.value:
            return buf.value
    except: pass
    
    # Fallback 1: Registry (Standard fallback)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            val, _ = winreg.QueryValueEx(key, "Personal")
            return os.path.expandvars(val)
    except: pass

    # Fallback 2: Environment
    return os.path.expanduser("~/Documents")

# --- Custom Widgets ---
class DropLineEdit(QLineEdit):
    def __init__(self, parent=None, organizer=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.organizer = organizer

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = Path(urls[0].toLocalFile())
                if path.is_dir():
                    # Security validation if organizer is available
                    if self.organizer and not self._is_path_safe(path):
                        event.ignore()
                        return
                    self.setText(str(path))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
    
    def _is_path_safe(self, selected_path):
        """Check if path is safe (not in Steam/Game/MO2 folders)"""
        try:
            selected_path = selected_path.resolve()
            game_path = Path(self.organizer.managedGame().gameDirectory().absolutePath()).resolve()
            mo2_path = Path(self.organizer.basePath()).resolve()
            steam_path = game_path.parent.parent if "steamapps" in str(game_path).lower() else None
            
            forbidden_paths = [game_path, mo2_path]
            if steam_path:
                forbidden_paths.append(steam_path)
            
            for forbidden in forbidden_paths:
                if selected_path == forbidden:
                    return False
                try:
                    selected_path.relative_to(forbidden)
                    return False
                except ValueError:
                    pass
                try:
                    forbidden.relative_to(selected_path)
                    return False
                except ValueError:
                    pass
            return True
        except:
            return True  # If validation fails, allow it (fail-safe)

# --- Synchronous Messenger for Threaded UI Prompts ---
class SynchronousMessenger(QObject):
    request_confirm = pyqtSignal(str, str)
    
    def __init__(self):
        super().__init__()
        self.result = False
        self.cond = QWaitCondition()
        self.mutex = QMutex()

    def ask(self, title, message):
        self.mutex.lock()
        self.request_confirm.emit(title, message)
        self.cond.wait(self.mutex)
        res = self.result
        self.mutex.unlock()
        return res

    def set_result(self, res):
        self.mutex.lock()
        self.result = res
        self.cond.wakeAll()
        self.mutex.unlock()

class CleanWorker(QThread):
    progress_signal = pyqtSignal(str)
    bar_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, sa_path, mo2_path, game_path, mods_path, overwrite_path, game_name, profile_name, messenger, cpu_priority=False, io_priority=False, affinity_mask=0):
        super().__init__()
        self.sa_path = Path(sa_path)
        self.mo2_path = Path(mo2_path)
        self.game_path = Path(game_path)
        self.mods_path = Path(mods_path)
        self.overwrite_path = Path(overwrite_path)
        self.game_name = game_name
        self.profile_name = profile_name
        self.messenger = messenger
        self.cpu_priority = cpu_priority
        self.io_priority = io_priority
        self.affinity_mask = affinity_mask

    def run(self):
        try:
            if self.cpu_priority or self.io_priority:
                set_priority(cpu=self.cpu_priority, io=self.io_priority)
                if self.affinity_mask > 0:
                    set_affinity(self.affinity_mask)
                    self.progress_signal.emit(f"[*] Process Optimization Enabled (CPU: {self.cpu_priority}, IO: {self.io_priority}, Affinity: {self.affinity_mask})")
                else:
                    self.progress_signal.emit(f"[*] Process Optimization Enabled (CPU: {self.cpu_priority}, IO: {self.io_priority})")

            self.progress_signal.emit(f"[*] Starting Safety Check for: {clean_path_for_display(self.sa_path)}")
            
            # Mapping for standard Bethesda games
            MAPPINGS = {
                "Skyrim Special Edition": {"docs": "Skyrim Special Edition", "appdata": "Skyrim Special Edition", "ini": "Skyrim"},
                "Skyrim": {"docs": "Skyrim", "appdata": "Skyrim", "ini": "Skyrim"},
                "Fallout 4": {"docs": "Fallout4", "appdata": "Fallout4", "ini": "Fallout4"},
                "Starfield": {"docs": "Starfield", "appdata": "Starfield", "ini": "Starfield"},
            }
            info = MAPPINGS.get(self.game_name, {"docs": self.game_name, "appdata": self.game_name, "ini": self.game_name.split()[0]})
            docs_name = info["docs"]
            appdata_name = info["appdata"]
            ini_prefix = info["ini"]

            # 1. READ METADATA (Optional now, as guard is removed)
            metadata_file = self.sa_path / "standalone_metadata" / "standalone_metadata.json"

            cleaner = None
            if CleanerEngine:
                cleaner = CleanerEngine(
                    self.sa_path, self.mo2_path, self.game_path, 
                    docs_name, appdata_name, 
                    game_name=self.game_name, profile_name=self.profile_name, 
                    portable_mode=True, mods_path=self.mods_path, overwrite_path=self.overwrite_path
                )
                
                is_safe, msg = cleaner.check_safety()
                if not is_safe:
                    self.finished_signal.emit(False, f"Safety Block: {msg}")
                    return

                self.progress_signal.emit("[*] Cleaning Standalone folder...")
            
            # --- SAVE SAFETY SYNC (PROTECTION) ---
            mo2_standalone = self.mo2_path / "profiles" / self.profile_name / "standalone_profile"
            standalone_saves = mo2_standalone / "Saves"
            if standalone_saves.exists():
                save_files = [f for f in standalone_saves.iterdir() if f.is_file() and (f.suffix.lower() == ".ess" or f.suffix.lower() == ".skse")]
                if save_files:
                    self.progress_signal.emit(f"[*] Save Safety: Found {len(save_files)} saves in standalone profile. Exporting to MO2...")
                    if ProfileSync:
                        # Initialize sync in stealth mode to point WRAPPED paths correctly
                        p_sync = ProfileSync(
                            self.mo2_path / "profiles" / self.profile_name, 
                            self.sa_path, 
                            docs_name=docs_name, 
                            appdata_name=appdata_name, 
                            ini_prefix=ini_prefix, 
                            game_name=self.game_name, 
                            profile_name=self.profile_name,
                            stealth_mode=True, # Redirects internal paths
                            callback=self.messenger.ask, 
                            log_callback=self.progress_signal.emit
                        )
                        # Push saves back to MO2 (using the quarantine system built into ProfileSync)
                        p_sync.sync_saves_to_mo2()
                    else:
                        self.progress_signal.emit("[!] Warning: ProfileSync missing. Cannot safety-export saves!")

            # --- BRIDGE CLEANUP (Leftover from previous versions) ---
            bridge_folder = self.sa_path / "standalone_bridge"
            if bridge_folder.exists() and bridge_folder.is_dir():
                self.progress_signal.emit(f"[*] Removing legacy bridge folder: {bridge_folder.name}")
                try:
                    shutil.rmtree(bridge_folder, onerror=self._handle_remove_readonly)
                except Exception as e:
                    self.progress_signal.emit(f"[!] Warning: Failed to remove bridge folder: {e}")
            
            if cleaner:
                result = cleaner.total_cleanup(progress_callback=self.bar_signal.emit)
                status = result["status"]
                if status == "SKIPPED":
                    self.finished_signal.emit(True, "Destination was already empty. Ready for build.")
                elif status == "FINISHED":
                    self.finished_signal.emit(True, "Destination cleared successfully.")
                else:
                    errors_str = "\n".join([f"- {e}" for e in result["errors"][:5]])
                    if len(result["errors"]) > 5:
                        errors_str += f"\n... and {len(result['errors']) - 5} more."
                    self.finished_signal.emit(False, f"Cleanup failed: Some files are locked or inaccessible.\n\nFailed items:\n{errors_str}")
            else:
                self.finished_signal.emit(False, "CleanerEngine not found.")
        except Exception:
            error_msg = traceback.format_exc()
            self.finished_signal.emit(False, f"Error during cleanup:\n{error_msg}")

class BuildWorker(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    
    # Per-stage progress signals
    clean_bar_signal = pyqtSignal(int)
    scan_bar_signal = pyqtSignal(int)
    link_bar_signal = pyqtSignal(int)
    verify_bar_signal = pyqtSignal(int)

    def __init__(self, organizer, sa_path, use_hardlinks, profile_path, profile_name, use_documents_mode, messenger, 
                 cpu_priority=False, io_priority=False, affinity_mask=0,
                 use_mmcss=False, use_ram_trim=False, use_stealth=False):
        super().__init__()
        self.organizer = organizer
        self.sa_path = Path(sa_path)
        self.use_hardlinks = use_hardlinks
        self.profile_path = Path(profile_path)
        self.profile_name = profile_name
        self.use_documents_mode = use_documents_mode
        self.messenger = messenger
        self.cpu_priority = cpu_priority
        self.io_priority = io_priority
        self.affinity_mask = affinity_mask
        self.use_mmcss = use_mmcss
        self.use_ram_trim = use_ram_trim
        self.use_stealth = use_stealth

    def run(self):
        try:
            if self.cpu_priority or self.io_priority:
                set_priority(cpu=self.cpu_priority, io=self.io_priority)
                if self.affinity_mask > 0:
                    set_affinity(self.affinity_mask)
                    self.progress_signal.emit(f"[*] Process Optimization Enabled (CPU: {self.cpu_priority}, IO: {self.io_priority}, Affinity: {self.affinity_mask})")
                else:
                    self.progress_signal.emit(f"[*] Process Optimization Enabled (CPU: {self.cpu_priority}, IO: {self.io_priority})")
            
            self.progress_signal.emit(f"[*] Starting Build using {QT_NAME}...")
            
            # --- MO2 API Integration ---
            mo2_path = Path(self.organizer.basePath())
            mods_path = Path(self.organizer.modsPath())
            overwrite_path = Path(self.organizer.overwritePath())
            
            game = self.organizer.managedGame()
            game_path = Path(game.gameDirectory().absolutePath())
            game_name = game.gameName()
            game_exe = game.binaryName()
            
            self.progress_signal.emit(f"[*] Profile Path: {clean_path_for_display(self.profile_path)}")
            self.progress_signal.emit(f"[*] Detected Game: {game_name} at {clean_path_for_display(game_path)}")

            # Mapping for standard Bethesda games
            MAPPINGS = {
                "Skyrim Special Edition": {"docs": "Skyrim Special Edition", "appdata": "Skyrim Special Edition", "ini": "Skyrim", "appid": "489830"},
                "Skyrim": {"docs": "Skyrim", "appdata": "Skyrim", "ini": "Skyrim", "appid": "72850"},
                "Fallout 4": {"docs": "Fallout4", "appdata": "Fallout4", "ini": "Fallout4", "appid": "377160"},
                "Starfield": {"docs": "Starfield", "appdata": "Starfield", "ini": "Starfield", "appid": "1716740"},
            }
            info = MAPPINGS.get(game_name, {"docs": game_name, "appdata": game_name, "ini": game_name.split()[0], "appid": "0"})

            docs_name = info["docs"]
            appdata_name = info["appdata"]
            ini_prefix = info["ini"]
            game_appid = info["appid"]

            # STAGE 2: CLEAN
            self.progress_signal.emit("[*] Stage 1: Cleaning Standalone folder...")
            self.clean_bar_signal.emit(5)
            
            # --- Isolation Safety Check (OneDrive Detection) ---
            isolation_possible = True
            doc_path_warning = ""
            
            # Use robust path resolution v3.1.2
            expanded_path = get_windows_documents_path()
            user_profile = os.environ.get("USERPROFILE", "C:\\Users")

            if "onedrive" in expanded_path.lower():
                isolation_possible = False
                doc_path_warning = f"OneDrive detected in Document path: {expanded_path}"
            elif not expanded_path.lower().startswith(user_profile.lower()):
                isolation_possible = False
                doc_path_warning = f"Non-standard Document path detected: {expanded_path}"

            use_isolation = True
            shared_mode_backup = False
            if not isolation_possible:
                msg = f"SAFETY ALERT: {doc_path_warning}\n\n" \
                      f"Windows is redirecting your Documents folder. This usually blocks 'Portable Isolation' from working correctly with Steam.\n\n" \
                      f"How would you like to proceed?\n\n" \
                      f"YES: CONTINUE (Shared Mode) - Isolation will be DISABLED. Saves and Configs will be shared with your original Documents folder.\n" \
                      f"NO: ABORT - Stop the build and fix your Document path manually."
                
                if self.messenger.ask("Isolation Warning", msg):
                    use_isolation = False
                    self.progress_signal.emit("[!] USER DECISION: Disabling isolation due to OneDrive/Cloud path.")
                    
                    # Check for existing files in Shared Mode
                    real_docs = Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}"))
                    if real_docs.exists() and any(real_docs.iterdir()):
                        msg_backup = f"Shared Mode Active.\n\n" \
                                     f"Existing files detected in: {clean_path_for_display(real_docs)}\n\n" \
                                     f"Would you like to BACKUP existing files (recommended) or OVERWRITE them?\n\n" \
                                     f"YES: BACKUP (Highly Recommended)\n" \
                                     f"NO: OVERWRITE (No Backup)"
                        shared_mode_backup = self.messenger.ask("Shared Mode Backup", msg_backup)
                        if shared_mode_backup:
                            self.progress_signal.emit("[*] Backup requested for Shared Mode sync.")
                else:
                    self.progress_signal.emit("[X] Build Aborted by User.")
                    self.finished_signal.emit(False, "Build aborted due to isolation incompatibility.")
                    return

            if CleanerEngine:
                clean_engine = CleanerEngine(self.sa_path, mo2_path, game_path, docs_name, appdata_name, game_name=game_name, profile_name=self.profile_name, portable_mode=use_isolation, mods_path=mods_path, overwrite_path=overwrite_path)
                
                # Check for Live MO2 Mode specific handling
                if self.use_stealth:
                    self.progress_signal.emit("[*] Live MO2 Mode detected. Skipping profile/save deployment Stage.")
                
                self.clean_bar_signal.emit(10)
                is_safe, msg = clean_engine.check_safety()
                if not is_safe:
                    self.finished_signal.emit(False, f"Safety Check Failed: {msg}")
                    return

                # 1. READ METADATA FOR SAVE EXPORT
                metadata_file = self.sa_path / "standalone_metadata" / "standalone_metadata.json"
                save_export_destination = None
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            # Read from new metadata structure
                            raw_dest = meta.get("source_paths", {}).get("save_source")
                            # Fallback to old structure for backward compatibility
                            if not raw_dest:
                                raw_dest = meta.get("build_info", {}).get("save_source")
                            
                            if raw_dest:
                                save_export_destination = Path(ensure_long_path(raw_dest))
                    except: pass

                # 2. SAVE EXPORT GUARD (Golden Rule)
                # Check isolated profile inside MO2 (standalone_profile)
                mo2_standalone = self.profile_path / "standalone_profile"
                standalone_saves = mo2_standalone / "Saves"
                if standalone_saves.exists():
                    save_files = [f for f in standalone_saves.iterdir() if f.is_file() and (f.suffix.lower() == ".ess" or f.suffix.lower() == ".skse")]
                    if save_files:
                        if self.messenger.ask("Save Export Guard", f"Found {len(save_files)} saves in isolated standalone profile.\nExport (Backup) to [{self.profile_name}] before cleaning?"):
                            self.progress_signal.emit(f"[*] Exporting isolated saves to MO2 profile...")
                            try:
                                p_sync = ProfileSync(
                                    self.profile_path, self.sa_path,
                                    docs_name=docs_name, appdata_name=appdata_name, ini_prefix=ini_prefix,
                                    game_name=game_name, profile_name=self.profile_name,
                                    stealth_mode=True, callback=self.messenger.ask, log_callback=self.progress_signal.emit
                                )
                                p_sync.sync_saves_to_mo2()
                            except Exception as e:
                                self.progress_signal.emit(f"[!] Warning: Isolated save export failed: {e}")
                
                
                result = clean_engine.total_cleanup(progress_callback=self.clean_bar_signal.emit)
                status = result["status"]
                if status == "PARTIAL_FAILURE":
                    errors_str = "\n".join([f"- {e}" for e in result["errors"][:5]])
                    if len(result["errors"]) > 5:
                        errors_str += f"\n... and {len(result['errors']) - 5} more."
                        
                    msg_fail = "CLEANUP FAILED (PARTIAL)\n\n" \
                               "Some files in the destination are locked or cannot be deleted.\n" \
                               "Proceeding may cause 'File Mixing' (old mods conflicting with new ones).\n\n" \
                               "FAILED ITEMS:\n" + errors_str + "\n\n" \
                               "Do you want to ignore this and TRY TO BUILD REGARDLESS?"
                               
                    if not self.messenger.ask("Cleanup Integrity Alert", msg_fail):
                        self.progress_signal.emit("[X] Build Aborted by User due to incomplete cleanup.")
                        self.finished_signal.emit(False, "Incomplete cleanup")
                        return
                    else:
                        self.progress_signal.emit("[!] Warning: Proceeding with potentially mixed files in destination.")
                elif status == "SKIPPED":
                    self.progress_signal.emit("[*] Destination already empty. Moving to scanning.")
                else:
                    self.progress_signal.emit("[SUCCESS] Destination cleared.")
            else:
                 self.progress_signal.emit("[!] CleanerEngine missing. Skipping clean.")

            # --- BRIDGE CLEANUP (Leftover from previous versions) ---
            bridge_folder = self.sa_path / "standalone_bridge"
            if bridge_folder.exists() and bridge_folder.is_dir():
                self.progress_signal.emit(f"[*] Removing legacy bridge folder: {bridge_folder.name}")
                try:
                    def _force_remove(func, path, excinfo):
                        os.chmod(path, 0o777)
                        func(path)
                    shutil.rmtree(bridge_folder, onerror=_force_remove)
                except Exception as e:
                    self.progress_signal.emit(f"[!] Warning: Failed to remove bridge folder: {e}")

            # STAGE 3: SCAN
            self.progress_signal.emit("[*] Stage 2: Scanning Mods from Profile...")
            self.scan_bar_signal.emit(10)
            metadata_dir = self.sa_path / "standalone_metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            
            if ScannerEngine:
                scanner = ScannerEngine(mods_path, overwrite_path, self.profile_path, output_dir=metadata_dir)
                scanner.build_mapping(progress_callback=self.scan_bar_signal.emit)
            else:
                self.progress_signal.emit("[!] ScannerEngine missing. Build cannot proceed.")
                self.finished_signal.emit(False, "ScannerEngine missing")
                return

            # STAGE 4: LINK
            self.progress_signal.emit("[*] Stage 3: Deploying Files (This may take time)...")
            self.link_bar_signal.emit(5)
            if LinkerExecutor:
                linker = LinkerExecutor(self.sa_path, game_path, output_dir=metadata_dir)
                
                vanilla_mode = 'link' if self.use_hardlinks else 'copy'
                linker.initial_vanilla_clone(mode=vanilla_mode)
                linker.execute_mapping(clean=False, progress_callback=self.link_bar_signal.emit)
            else:
                self.progress_signal.emit("[!] LinkerExecutor missing. Build cannot proceed.")
                self.finished_signal.emit(False, "LinkerExecutor missing")
                return

            # STAGE 5: SYNC
            if not self.use_stealth:
                self.progress_signal.emit("[*] Stage 4: Syncing Profile Configuration...")
                
                # Deploy configuration files (INI, plugins) using ProfileSync
                if ProfileSync:
                    p_sync = ProfileSync(self.profile_path, self.sa_path, docs_name, appdata_name, ini_prefix, game_name=game_name, profile_name=self.profile_name, portable_mode=use_isolation, use_documents_mode=self.use_documents_mode, callback=self.messenger.ask, log_callback=self.progress_signal.emit)
                    
                    # Shared Mode Guard: Backup if requested
                    if not use_isolation and shared_mode_backup:
                        real_docs_path = Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}"))
                        p_sync.backup_shared_docs(real_docs_path)
                    
                    p_sync.deploy_mo2_profile()
                    if use_isolation:
                        p_sync.clean_custom_save_path()
                else:
                    self.progress_signal.emit("[!] ProfileSync missing. Skipping config sync.")
                
                # Initial Save Import removed. Managed by native swap wrapper.
                self.progress_signal.emit("[*] Manual Save Import skipped (Managed by Wrapper).")
            else:
                self.progress_signal.emit("[*] Stage 4: Initializing Isolated Standalone Profile (Live MO2 Mode)...")
                
                # 1. Create Folders
                mo2_standalone = self.profile_path / "standalone_profile"
                standalone_saves = mo2_standalone / "Saves"
                standalone_saves.mkdir(parents=True, exist_ok=True)

                # 2. Patch SkyrimCustom.ini (Mandatory for Save redirection)
                custom_ini_name = f"{ini_prefix}Custom.ini"
                custom_ini_src = self.profile_path / custom_ini_name
                target_custom = mo2_standalone / custom_ini_name
                
                # We prioritize the existing Custom.ini but if it doesn't exist we create a basic one
                content_lines = []
                if custom_ini_src.exists():
                    try:
                        with open(custom_ini_src, 'r', encoding='utf-8-sig', errors='ignore') as f:
                            content_lines = f.readlines()
                    except: pass
                
                # Ensure sLocalSavePath=Saves is in [General]
                new_lines = [l for l in content_lines if "slocalsavepath" not in l.lower()]
                has_general = any("[general]" in l.lower() for l in new_lines)
                if not has_general:
                    new_lines.insert(0, "[General]\n")
                
                for i, line in enumerate(new_lines):
                    if "[general]" in line.lower():
                        new_lines.insert(i + 1, "sLocalSavePath=Saves\\\n")
                        break
                
                try:
                    with open(target_custom, 'w', encoding='utf-8-sig') as f:
                        f.writelines(new_lines)
                    self.progress_signal.emit(f"   [*] {custom_ini_name} patched and stored in standalone profile.")
                except Exception as e:
                    self.progress_signal.emit(f"   [!] Failed to save patched {custom_ini_name}: {e}")

                # Initial Save Import removed. Managed by native swap wrapper.
                self.progress_signal.emit("   [*] Initial save import skipped (Managed by Wrapper).")

                # We still need a dummy p_sync for verification paths later
                if ProfileSync:
                    p_sync = ProfileSync(self.profile_path, self.sa_path, docs_name, appdata_name, ini_prefix, game_name=game_name, profile_name=self.profile_name, portable_mode=use_isolation, stealth_mode=self.use_stealth, callback=self.messenger.ask)
                else: p_sync = None

            # STAGE 6: FINALIZING
            self.progress_signal.emit("[*] Finalizing: Implementing Smart Isolation Wrapper...")
            self.last_hijacked_count, self.last_wrappers_succeeded = implement_isolation_hijack(
                                       self.progress_signal, self.sa_path, game_exe, ini_prefix, docs_name, self.profile_name,
                                       self.cpu_priority, self.io_priority, self.affinity_mask, 
                                       self.use_mmcss, self.use_ram_trim,
                                       use_isolation=use_isolation, use_stealth=self.use_stealth, mo2_profile_path=self.profile_path, appdata_name=appdata_name)
            
            self.progress_signal.emit("[*] Finalizing: Generating Metadata & Instructions...")
            
            # Determine save/config source locations for metadata
            if self.use_stealth:
                # Stealth Mode: The absolute source of truth is the MO2 profile itself
                save_source = str(self.profile_path / "saves")
                config_source = str(self.profile_path)
            elif self.use_documents_mode:
                save_source = str(Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}/Saves")))
                config_source = str(Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")))
            else:
                save_source = str(self.profile_path / "saves")
                config_source = str(self.profile_path)
            
            # Plugins and loadorder ALWAYS come from MO2 profile (not affected by Documents mode)
            plugins_source = str(self.profile_path)
            
            # Extract standalone name from path (last directory name)
            standalone_name = self.sa_path.name
            
            # Determine all source paths
            modlist_source = str(self.profile_path / "modlist.txt")
            loadorder_source = str(self.profile_path / "loadorder.txt")
            
            metadata = {
                "standalone_info": {
                    "standalone_name": standalone_name,
                    "standalone_path": str(Path(ensure_long_path(self.sa_path))),
                    "build_timestamp": datetime.datetime.now().isoformat(),
                    "qt_framework": QT_NAME,
                    "wrapper_type": "EXE (Compiled)" if self.last_wrappers_succeeded > 0 else "BAT (Fallback)"
                },
                "game_info": {
                    "game_name": game_name,
                    "game_path": str(Path(ensure_long_path(game_path))),
                    "game_executable": game_exe
                },
                "mo2_info": {
                    "mo2_profile_name": self.profile_name,
                    "mo2_profile_path": str(Path(ensure_long_path(self.profile_path))),
                    "mo2_base_path": str(Path(ensure_long_path(mo2_path))),
                    "mo2_mods_path": str(Path(ensure_long_path(mods_path))),
                    "mo2_overwrite_path": str(Path(ensure_long_path(overwrite_path)))
                },
                "build_config": {
                    "mode": "MO2_Sync",
                    "use_hardlinks": self.use_hardlinks,
                    "use_stealth": True
                },
                "source_paths": {
                    "save_source": str(Path(ensure_long_path(save_source))),
                    "config_source": str(Path(ensure_long_path(config_source))),
                    "plugins_source": str(Path(ensure_long_path(plugins_source))),
                    "modlist_source": str(Path(ensure_long_path(modlist_source))),
                    "loadorder_source": str(Path(ensure_long_path(loadorder_source)))
                },
                "optimization_settings": {
                    "cpu_priority": self.cpu_priority,
                    "io_priority": self.io_priority,
                    "affinity_mask": self.affinity_mask,
                    "use_mmcss": self.use_mmcss,
                    "use_ram_trim": self.use_ram_trim
                }
            }
            with open(metadata_dir / "standalone_metadata.json", "w", encoding='utf-8') as f:
                json.dump(metadata, f, indent=4)

            with open(self.sa_path / "steam_appid.txt", "w") as f:
                f.write(game_appid)
            
            self.progress_signal.emit("[*] Finalizing: Running Verification...")
            self.verify_bar_signal.emit(10)
            verification_results = {}
            if VerificationEngine:
                try:
                    verifier = VerificationEngine()
                    verification_results = verifier.run_all_checks(
                        manifest_path=scanner.output_manifest,
                        standalone_path=self.sa_path,
                        mo2_profile_path=self.profile_path,
                        appdata_path=p_sync.win_appdata,
                        doc_save_path=p_sync.win_docs,
                        ini_prefix=ini_prefix,
                        run_timestamp=p_sync.run_timestamp,
                        mods_dir=mods_path,
                        use_documents_mode=self.use_documents_mode,
                        stealth_mode=self.use_stealth,
                        progress_callback=self.verify_bar_signal.emit
                    )
                    # Inject wrapper status for the report
                    verification_results["wrapper_info"] = {
                        "type": "EXE" if self.last_wrappers_succeeded > 0 else "BAT",
                        "count": self.last_wrappers_succeeded,
                        "total_hijacked": self.last_hijacked_count
                    }
                except Exception as e:
                    self.progress_signal.emit(f"[!] Verification issue: {e}")
            else:
                 self.progress_signal.emit("[!] VerificationEngine missing.")

            self.progress_signal.emit("[*] Finalizing: Generating HTML Report...")
            if ReportGenerator:
                try:
                    gen = ReportGenerator(
                        manifest_path=str(scanner.output_manifest), 
                        report_path=str(linker.report_file),
                        output_html=str(metadata_dir / "build_report.html")
                    )
                    gen.generate(verification_results)
                    self.verify_bar_signal.emit(100)
                except Exception as e:
                    self.progress_signal.emit(f"[!] Report failed: {e}")
            else:
                self.progress_signal.emit("[!] ReportGenerator missing.")

            self.finished_signal.emit(True, "Build completed successfully!")

        except Exception:
            error_msg = traceback.format_exc()
            self.finished_signal.emit(False, f"Error during build:\n{error_msg}")


def implement_isolation_hijack(progress_signal, sa_path, game_exe, ini_prefix, docs_name, profile_name,
                             cpu_priority=False, io_priority=False, affinity_mask=0,
                             use_mmcss=False, use_ram_trim=False,
                             use_isolation=True, use_stealth=True, mo2_profile_path="", appdata_name=""):
    """Standard hijacking logic from standalone script."""
    potential_targets = [game_exe, f"{Path(game_exe).stem}Launcher.exe"]
    if ini_prefix: potential_targets.append(f"{ini_prefix}Launcher.exe")
    
    # Custom Loaders for various Bethesda games
    common_loaders = [
        "skse64_loader.exe", "f4se_loader.exe", "sfse_loader.exe", 
        "skse_loader.exe", "sksevr_loader.exe", "nvse_loader.exe", 
        "obse_loader.exe", "mgexe.exe", "mwse.exe"
    ]
    potential_targets.extend(common_loaders)
    
    # Game executables to NOT hijack (Main engine files)
    game_executables = [
        game_exe.lower(), 
        f"{Path(game_exe).stem}Launcher.exe".lower(), 
        "launcher.exe",
        "skyrimlauncher.exe",
        "falloutlauncher.exe"
    ]
    
    # Filter targets: Must exist, and not be a protected game engine EXE
    # EXCEPT for loaders - we ALWAYS want to hijack loaders even if they match game_exe
    critical_exes = []
    for t in potential_targets:
        if not t: continue
        low_t = t.lower()
        is_loader = any(l in low_t for l in ["loader", "seve", "mwse", "mgexe"])
        
        # We always want to hijack loaders. 
        # For non-loaders, we only hijack if it's NOT a main game engine file (which are launched BY the loader/wrapper)
        if is_loader or low_t not in game_executables:
            if t not in critical_exes:
                critical_exes.append(t)
    
    # Dynamic C# Compilation Setup
    hijacked_count = 0
    wrappers_succeeded = 0
    csc_path = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if not os.path.exists(csc_path):
        csc_path = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
        
    has_compiler = os.path.exists(csc_path)
    if has_compiler:
        progress_signal.emit(f"    [*] Found C# Compiler: {csc_path}")
    else:
        progress_signal.emit("    [!] Warning: C# Compiler NOT found. Falling back to .bat mode.")

    # Source Template for the Wrapper (Native Swap Approach)
    cs_source_template = r"""
using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Management;
using System.Collections.Generic;
using System.Linq;

class Wrapper {
    [DllImport("ntdll.dll")]
    private static extern int NtSetInformationProcess(IntPtr processHandle, int processInformationClass, ref int processInformation, int processInformationLength);

    [DllImport("psapi.dll")]
    private static extern bool EmptyWorkingSet(IntPtr hProcess);

    private const int ProcessIoPriority = 21;
    
    private const bool USE_CPU_PRIORITY = {cpu_priority};
    private const bool USE_IO_PRIORITY = {io_priority};
    private const long AFFINITY_MASK = {affinity_mask};
    private const bool USE_MMCSS = {use_mmcss};
    private const bool USE_RAM_TRIM = {use_ram_trim};

    private static HashSet<int> optimizedPIDs = new HashSet<int>();

    private static void Log(string message) {
        try {
            File.AppendAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "wrapper_log.txt"), 
                "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "] " + message + Environment.NewLine);
        } catch {}
    }

    private static float GetCPUTemp() {
        try {
            using (var searcher = new ManagementObjectSearcher(@"root\WMI", "SELECT * FROM MSAcpi_ThermalZoneTemperature")) {
                foreach (var obj in searcher.Get()) {
                    double temp = Convert.ToDouble(obj["CurrentTemperature"]);
                    return (float)((temp - 2732.15) / 10.0);
                }
            }
        } catch {}
        return -1;
    }

    private static void ApplyOptimizations(Process p, bool isWrapper) {
        if (p == null || p.HasExited) return;

        bool firstTime = !optimizedPIDs.Contains(p.Id);
        if (firstTime) {
            Log(">>> Applying optimizations to " + p.ProcessName + " (PID: " + p.Id + ")");
            optimizedPIDs.Add(p.Id);
        }

        float temp = GetCPUTemp();
        bool thermalFailsafeTriggered = temp > 90.0f;

        if (USE_CPU_PRIORITY) {
            try { 
                p.PriorityClass = ProcessPriorityClass.High; 
                if (firstTime) Log("    [*] CPU Priority: HIGH (Success)");
            } catch (Exception e) { 
                if (firstTime) Log("    [!] CPU Priority: Failed - " + e.Message); 
            }
        }

        if (USE_IO_PRIORITY) {
            try {
                int ioPriority = 3; // High
                int status = NtSetInformationProcess(p.Handle, ProcessIoPriority, ref ioPriority, 4);
                if (firstTime) Log("    [*] IO Priority: HIGH (Status: " + status + ")");
            } catch (Exception e) { 
                if (firstTime) Log("    [!] IO Priority: Failed - " + e.Message); 
            }
        }

        if (AFFINITY_MASK > 0) {
            try {
                int coreCount = Environment.ProcessorCount;
                int selectedCoreCount = 0;
                for (int i = 0; i < 64; i++) if (((AFFINITY_MASK >> i) & 1) == 1) selectedCoreCount++;

                if (thermalFailsafeTriggered) {
                    if (firstTime) Log("    [!] Thermal Failsafe Triggered (" + temp + "C). Disabling Affinity.");
                    if (coreCount >= 64) p.ProcessorAffinity = (IntPtr)(-1);
                    else p.ProcessorAffinity = new IntPtr((1L << coreCount) - 1);
                } else if (selectedCoreCount < 2) {
                    if (firstTime) Log("    [!] CPU Affinity: Ignored - Less than 2 cores selected for stability.");
                } else {
                    p.ProcessorAffinity = new IntPtr(AFFINITY_MASK);
                    if (firstTime) Log("    [*] CPU Affinity: Set to " + AFFINITY_MASK + " (Success)");
                }
            } catch (Exception e) { 
                if (firstTime) Log("    [!] CPU Affinity: Failed - " + e.Message); 
            }
        }

        if (USE_RAM_TRIM && !isWrapper) {
            try { 
                bool success = EmptyWorkingSet(p.Handle); 
                if (firstTime) Log("    [*] RAM Trimmer: Active (Initial Success: " + success + ")");
            } catch (Exception e) { 
                if (firstTime) Log("    [!] RAM Trimmer: Failed - " + e.Message); 
            }
        }
    }

    private static void DirectoryCopy(string sourceDirName, string destDirName, bool copySubDirs) {
        DirectoryInfo dir = new DirectoryInfo(sourceDirName);
        if (!dir.Exists) return;

        DirectoryInfo[] dirs = dir.GetDirectories();
        if (!Directory.Exists(destDirName)) Directory.CreateDirectory(destDirName);

        FileInfo[] files = dir.GetFiles();
        foreach (FileInfo file in files) {
            string tempPath = Path.Combine(destDirName, file.Name);
            try {
                file.CopyTo(tempPath, true);
            } catch (Exception ex) {
                Log("Warning: Could not copy file " + file.Name + " - " + ex.Message);
            }
        }

        if (copySubDirs) {
            foreach (DirectoryInfo subdir in dirs) {
                string tempPath = Path.Combine(destDirName, subdir.Name);
                DirectoryCopy(subdir.FullName, tempPath, copySubDirs);
            }
        }
    }

    private static void ForceDeleteDirectory(string path) {
        if (!Directory.Exists(path)) return;
        
        DirectoryInfo dir = new DirectoryInfo(path);
        foreach (FileInfo file in dir.GetFiles()) {
            try { file.Delete(); } 
            catch (Exception ex) { Log("Warning: Could not delete file " + file.Name + " - " + ex.Message); }
        }
        foreach (DirectoryInfo subDir in dir.GetDirectories()) {
            ForceDeleteDirectory(subDir.FullName);
        }
        try { Directory.Delete(path, false); } 
        catch (Exception ex) { Log("Warning: Could not delete directory " + dir.Name + " - " + ex.Message); }
    }

    private static void RestoreOriginalFile(string backupPath, string originalPath) {
        if (File.Exists(backupPath)) {
            try {
                if (File.Exists(originalPath)) File.Delete(originalPath);
                File.Move(backupPath, originalPath);
                Log("Restored original file: " + Path.GetFileName(originalPath));
            } catch (Exception e) {
                Log("Error restoring " + originalPath + ": " + e.Message);
            }
        }
    }

    static void Main(string[] args) {
        string exePath = AppDomain.CurrentDomain.BaseDirectory;
        string selfName = AppDomain.CurrentDomain.FriendlyName;
        if (!selfName.EndsWith(".exe")) selfName += ".exe";
        
        string targetName = "_" + selfName.Replace(".exe", "") + "_original.exe";
        string foundTarget = Path.Combine(exePath, targetName);
        
        bool isStealth = {is_stealth};
        bool useIsolation = {use_isolation};
        string mo2ProfilePath = @"{mo2_profile_path}";
        
        string myDocsBase = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        string localAppDataBase = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        
        string realDocsFolder = Path.Combine(myDocsBase, "My Games", "{docs_name}");
        string realLocalFolder = Path.Combine(localAppDataBase, "{appdata_name}");
        
        string backupDocsFolder = realDocsFolder + "_WrapperBackup";
        string backupLocalFolder = realLocalFolder + "_WrapperBackup";

        try {
            Log("=== Starting Native Swap Wrapper ===");
            Log("Self: " + selfName + " | Target: " + targetName);
            
            if (!File.Exists(foundTarget)) {
                Log("ERROR: Could not find original executable: " + targetName);
                return;
            }

            if (isStealth && useIsolation) {
                Log("Applying Native Swap Isolation (Targeted File Swap)...");
                
                string[] appDataFiles = { "plugins.txt", "loadorder.txt", "lockedorder.txt" };
                string[] docFiles = { "{ini_prefix}.ini", "{ini_prefix}Prefs.ini", "{ini_prefix}Custom.ini" };
                
                if (!Directory.Exists(backupDocsFolder)) Directory.CreateDirectory(backupDocsFolder);
                if (!Directory.Exists(backupLocalFolder)) Directory.CreateDirectory(backupLocalFolder);

                // 1. Backup specific original files
                foreach (string f in appDataFiles) {
                    string src = Path.Combine(realLocalFolder, f);
                    string bkp = Path.Combine(backupLocalFolder, f);
                    if (File.Exists(src)) {
                        File.Copy(src, bkp, true);
                    }
                }
                foreach (string f in docFiles) {
                    string src = Path.Combine(realDocsFolder, f);
                    string bkp = Path.Combine(backupDocsFolder, f);
                    if (File.Exists(src)) {
                        File.Copy(src, bkp, true);
                    }
                }
                
                // Backup Saves Directory
                string originalSaves = Path.Combine(realDocsFolder, "Saves");
                string backupSaves = Path.Combine(backupDocsFolder, "Saves");
                if (Directory.Exists(originalSaves)) {
                    DirectoryCopy(originalSaves, backupSaves, true);
                    ForceDeleteDirectory(originalSaves); // Clear for MO2 saves
                }

                // 2. Inject MO2 Files into Native Environment
                Log("Injecting MO2 Profile into live environment...");
                foreach (string f in appDataFiles) {
                    string src = Path.Combine(mo2ProfilePath, f);
                    if (File.Exists(src)) File.Copy(src, Path.Combine(realLocalFolder, f), true);
                }
                
                foreach (string f in docFiles) {
                    string src = Path.Combine(mo2ProfilePath, f);
                    if (File.Exists(src)) {
                        string targetCustom = Path.Combine(realDocsFolder, f);
                        
                        // Patch Saves natively if Custom.ini
                        if (f.Equals("{ini_prefix}Custom.ini", StringComparison.OrdinalIgnoreCase)) {
                            List<string> processedLines = new List<string>();
                            bool generalAdded = false;
                            string[] lines = File.ReadAllLines(src);
                            
                            foreach (string line in lines) {
                                string trimmed = line.Trim();
                                if (trimmed.StartsWith("sLocalSavePath", StringComparison.OrdinalIgnoreCase)) continue;
                                processedLines.Add(line);
                                if (trimmed.Equals("[General]", StringComparison.OrdinalIgnoreCase) && !generalAdded) {
                                    processedLines.Add("sLocalSavePath=Saves\\");
                                    generalAdded = true;
                                }
                            }
                            if (!generalAdded) {
                                processedLines.Insert(0, "[General]");
                                processedLines.Insert(1, "sLocalSavePath=Saves\\");
                            }
                            File.WriteAllLines(targetCustom, processedLines, new System.Text.UTF8Encoding(true));
                        } else {
                            File.Copy(src, targetCustom, true);
                        }
                    }
                }

                // Inject Saves
                string mo2Saves = Path.Combine(mo2ProfilePath, "saves");
                if (!Directory.Exists(originalSaves)) Directory.CreateDirectory(originalSaves);
                if (Directory.Exists(mo2Saves)) DirectoryCopy(mo2Saves, originalSaves, true);
                
                Log("   [*] Targeted File Swap Setup Complete.");
            }

            // Launch Target NATIVELY without Environment Override
            ProcessStartInfo startInfo = new ProcessStartInfo(foundTarget);
            if (args.Length > 0) startInfo.Arguments = "\"" + string.Join("\" \"", args) + "\"";
            startInfo.UseShellExecute = false;
            startInfo.WorkingDirectory = exePath; 
            
            Log("Launching target...");
            Process pWrapper = Process.Start(startInfo);
            if (pWrapper == null) {
                Log("ERROR: Process.Start returned null.");
                return;
            }

            Log("Process started. PID: " + pWrapper.Id);
            bool isLoader = selfName.ToLower().Contains("loader") || selfName.ToLower().Contains("launcher");

            List<Process> trackedProcesses = new List<Process> { pWrapper };

            string gameStem = "{game_name}";
            string[] fallbackStrings = { "SkyrimSE", "Skyrim", "Fallout4", "Starfield", "SkyrimVR", "Fallout4VR" };

            Log("Monitoring loop started...");
            DateTime startTime = DateTime.Now;
            bool gameFound = false;
            
            while (true) {
                try {
                    if (isLoader && !gameFound) {
                        List<string> searchNames = new List<string> { gameStem };
                        searchNames.AddRange(fallbackStrings);

                        foreach (var name in searchNames.Distinct()) {
                            if (string.IsNullOrEmpty(name)) continue;
                            try {
                                var foundGames = Process.GetProcessesByName(name).Where(g => !g.HasExited);
                                foreach (var g in foundGames) {
                                    if (!trackedProcesses.Any(tp => tp.Id == g.Id)) {
                                        Log("Discovered game process: " + g.ProcessName + " (PID: " + g.Id + ")");
                                        trackedProcesses.Add(g);
                                        gameFound = true;
                                    }
                                }
                            } catch {}
                        }
                    }

                    foreach (var p in trackedProcesses.ToList()) {
                        try {
                            if (!p.HasExited) ApplyOptimizations(p, p.Id == pWrapper.Id);
                        } catch {}
                    }
                } catch (Exception loopEx) {
                    Log("Loop error: " + loopEx.Message);
                }
                
                bool anyRunning = trackedProcesses.Any(tp => !tp.HasExited);
                double elapsed = (DateTime.Now - startTime).TotalSeconds;

                if (!anyRunning) {
                    if (isLoader && !gameFound && elapsed < 120) { } else { break; }
                }

                int sleepTime = (!gameFound && elapsed < 120) ? 5000 : 15000;
                System.Threading.Thread.Sleep(sleepTime);
                
                var exited = trackedProcesses.Where(tp => tp.HasExited).ToList();
                foreach (var ex in exited) {
                    optimizedPIDs.Remove(ex.Id);
                    trackedProcesses.Remove(ex);
                }
            }
            Log("All tracked processes exited.");
        } catch (Exception e) {
            Log("FATAL ERROR: " + e.Message);
        } finally {
            if (isStealth && useIsolation) {
                Log("Syncing output back to MO2 and Restoring Backups...");
                try {
                    // Sync Phase: Copy modifications back
                    string[] appDataFiles = { "plugins.txt", "loadorder.txt", "lockedorder.txt" };
                    string[] docFiles = { "{ini_prefix}.ini", "{ini_prefix}Prefs.ini", "{ini_prefix}Custom.ini" };
                    
                    // AppDataFiles (plugins, loadorder) and DocFiles (INIs) are STRICTLY one-way (MO2 -> Live). DO NOT sync back to MO2.

                    string targetSaves = Path.Combine(realDocsFolder, "Saves");
                    string mo2Saves = Path.Combine(mo2ProfilePath, "saves");
                    
                    if (Directory.Exists(targetSaves)) DirectoryCopy(targetSaves, mo2Saves, true);
                    // Explicitly removed SKSE sync per user request to avoid locked log files.

                    Log("Sync Phase Complete. Restoring original files...");
                    
                    // Restore Phase: Delete MO2 files and restore original specific files
                    foreach (string f in appDataFiles) {
                        string activePath = Path.Combine(realLocalFolder, f);
                        string bkpPath = Path.Combine(backupLocalFolder, f);
                        if (File.Exists(activePath)) File.Delete(activePath);
                        RestoreOriginalFile(bkpPath, activePath);
                    }
                    
                    foreach (string f in docFiles) {
                        string activePath = Path.Combine(realDocsFolder, f);
                        string bkpPath = Path.Combine(backupDocsFolder, f);
                        if (File.Exists(activePath)) File.Delete(activePath);
                        RestoreOriginalFile(bkpPath, activePath);
                    }

                    // Restore Saves
                    string backupSaves = Path.Combine(backupDocsFolder, "Saves");
                    if (Directory.Exists(targetSaves)) ForceDeleteDirectory(targetSaves); // Remove MO2 saves from live dir
                    if (Directory.Exists(backupSaves)) {
                        DirectoryCopy(backupSaves, targetSaves, true);
                        ForceDeleteDirectory(backupSaves);
                    }
                    
                    // Cleanup Backup Directories if empty
                    try { if (Directory.GetFiles(backupDocsFolder).Length == 0 && Directory.GetDirectories(backupDocsFolder).Length == 0) Directory.Delete(backupDocsFolder); } catch {}
                    try { if (Directory.GetFiles(backupLocalFolder).Length == 0 && Directory.GetDirectories(backupLocalFolder).Length == 0) Directory.Delete(backupLocalFolder); } catch {}

                    
                } catch (Exception syncEx) {
                    Log("Error during final Sync/Restore Phase: " + syncEx.Message);
                }
            }
        }
    }
}
    """ \
    .replace("{cpu_priority}", "true" if cpu_priority else "false") \
    .replace("{io_priority}", "true" if io_priority else "false") \
    .replace("{affinity_mask}", str(affinity_mask)) \
    .replace("{use_mmcss}", "true" if use_mmcss else "false") \
    .replace("{use_ram_trim}", "true" if use_ram_trim else "false") \
    .replace("{use_isolation}", "true" if use_isolation else "false") \
    .replace("{is_stealth}", "true" if use_stealth else "false") \
    .replace("{mo2_profile_path}", escape_cs_string(str(mo2_profile_path).replace("\\\\?\\", ""))) \
    .replace("{docs_name}", escape_cs_string(docs_name)) \
    .replace("{appdata_name}", escape_cs_string(appdata_name or docs_name)) \
    .replace("{ini_prefix}", escape_cs_string(ini_prefix)) \
    .replace("{game_name}", escape_cs_string(Path(game_exe).stem))


    for target in critical_exes:
        target_path = sa_path / target
        original_name = f"_{target.replace('.exe', '')}_original.exe"
        original_path = sa_path / original_name
        
        # Scenario A: Target exists, Original does NOT (Fresh Hijack)
        if target_path.exists() and not original_path.exists():
            try:
                target_path.rename(original_path)
                hijacked_count += 1
                try: subprocess.run(['attrib', '+h', str(original_path)], check=True)
                except: pass
            except Exception as e:
                progress_signal.emit(f"    [!] Failed to hijack {target}: {e}")
                continue

        # Scenario B: Original exists (Already Hijacked or Re-Optimization)
        # We don't need to rename anything, just ensure we (re)deploy the wrapper
        if original_path.exists():
            if not target_path.exists() or target_path.suffix.lower() == ".bat":
                 # Target is missing or is just a .bat from previous fail, we can proceed to wrap
                 pass
            hijacked_count += 1 # Still count it as being in an isolated state
        else:
            # If neither exists, skip this target
            if not target_path.exists():
                continue

        # Deploy Wrapper via Dynamic Compilation
        try:
            if has_compiler:
                source_file = sa_path / f"{target}_source.cs"
                with open(source_file, "w", encoding='utf-8') as f:
                    f.write(cs_source_template)
                
                # Compile (Winexe = no console window)
                standard_target_path = str(target_path).replace('\\\\?\\', '')
                standard_source_path = str(source_file).replace('\\\\?\\', '')
                cmd = [
                    csc_path, 
                    "/target:winexe", 
                    "/r:System.Management.dll",
                    f"/out:{standard_target_path}", 
                    standard_source_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                if result.returncode == 0 and target_path.exists():
                    progress_signal.emit(f"    [*] Compiled & Hijacked {target}")
                    wrappers_succeeded += 1
                    try: source_file.unlink() # Cleanup source
                    except: pass
                    
                    # Cleanup old .bat if it exists (successful upgrade to EXE)
                    bat_path = target_path.with_suffix(".bat")
                    if bat_path.exists():
                        try: bat_path.unlink()
                        except: pass
                else:
                    progress_signal.emit(f"    [!] Compiler Error for {target}. Falling back to .bat.")
                    deploy_bat_fallback(progress_signal, target_path)
            else:
                deploy_bat_fallback(progress_signal, target_path)
        except Exception as e:
             progress_signal.emit(f"    [!] Failed to wrap {target}: {e}")

    # --- GENERATE LAUNCH INSTRUCTIONS ---
    progress_signal.emit("[*] Generating Launch Instructions...")
    try:
        # Detect which loader to point to
        main_loader = next((t for t in critical_exes if "loader" in t.lower()), critical_exes[0] if critical_exes else "the original loader")
        
        # Determine extension based on success
        loader_ext = ".exe"
        if wrappers_succeeded == 0:
            loader_ext = ".bat"
            
        loader_final = main_loader.replace(".exe", loader_ext)
        
        if use_stealth:
            isolation_msg = f"- Use {loader_final} to launch with Live MO2 Redirection."
            data_loc = f"Saves & Configs: DIRECT LINK to MO2 Profile ({profile_name})"
        else:
            isolation_msg = f"- Use {loader_final} to keep your saves/settings in the '_standalone' folder."
            data_loc = f"Saves & Configs: _standalone\\Documents\\My Games\\{docs_name}"

        launch_info = [
            "=== HOW TO LAUNCH YOUR STANDALONE GAME ===",
            "",
            f"To play with this isolated profile, ALWAYS use:",
            f"-> {loader_final}",
            "",
            "--- WHY ARE FILES RENAMED? ---",
            "To ensure total isolation, original executables have been renamed",
            "with a '_' prefix (e.g. _skse64_loader_original.exe) and hidden.",
            "",
            "IMPORTANT:",
            f"- DO NOT launch via the '_' prefixed files. They bypass isolation!",
            isolation_msg,
            "",
            "--- DATA LOCATION ---",
            data_loc,
            "",
            f"Build Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Profile: {profile_name}"
        ]
        if use_stealth:
            launch_info.insert(15, f"MO2 Profile Path: {mo2_profile_path}")
        
        with open(sa_path / "HOW TO LAUNCH.txt", "w", encoding='utf-8') as f:
            f.write("\n".join(launch_info))
        progress_signal.emit(f"[SUCCESS] Instructions generated: HOW TO LAUNCH.txt")
    except Exception as e:
        progress_signal.emit(f"[!] Warning: Could not generate launch instructions: {e}")

    progress_signal.emit(f"[SUCCESS] Multi-Hijack complete. {hijacked_count} executables isolated ({wrappers_succeeded} EXE wrappers).")
    return hijacked_count, wrappers_succeeded

def deploy_bat_fallback(progress_signal, target_path):
    bat_path = target_path.with_suffix(".bat")
    with open(bat_path, "w") as f:
        f.write("@echo off\n")
        f.write("echo [!] Falling back to .bat mode. The .bat mode does NOT support the Native Swap feature.\n")
        f.write("echo Launching isolated game...\n")
        f.write(f"start \"\" \"%~dp0_{target_path.stem}_original.exe\" %*\n")
    progress_signal.emit(f"    -> Deployed barebones .bat fallback for {target_path.name}")

# Workers classes removed (SaveExportWorker, SaveImportWorker)

# Re-optimize/Re-wrap Worker - Updates wrappers for an existing build
class ReWrapWorker(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, sa_path, game_exe, ini_prefix, docs_name, profile_name, cpu_priority, io_priority, affinity_mask, 
                 use_mmcss, use_ram_trim, implement_hijack_func, 
                 use_isolation=True, use_stealth=False, mo2_profile_path="", appdata_name=""):
        super().__init__()
        self.sa_path = Path(sa_path)
        self.game_exe = game_exe
        self.ini_prefix = ini_prefix
        self.docs_name = docs_name
        self.profile_name = profile_name
        self.cpu_priority = cpu_priority
        self.io_priority = io_priority
        self.affinity_mask = affinity_mask
        self.use_mmcss = use_mmcss
        self.use_ram_trim = use_ram_trim
        self.implement_hijack_func = implement_hijack_func
        self.use_isolation = use_isolation
        self.use_stealth = use_stealth
        self.mo2_profile_path = mo2_profile_path
        self.appdata_name = appdata_name

    def run(self):
        try:
            self.progress_signal.emit("[*] Re-optimizing Standalone Wrappers...")
            self.implement_hijack_func(self.progress_signal, self.sa_path, self.game_exe, self.ini_prefix, self.docs_name, self.profile_name,
                                       self.cpu_priority, self.io_priority, self.affinity_mask,
                                       self.use_mmcss, self.use_ram_trim,
                                       use_isolation=self.use_isolation, use_stealth=self.use_stealth,
                                       mo2_profile_path=self.mo2_profile_path, appdata_name=self.appdata_name)
            
            # Update metadata file
            metadata_file = self.sa_path / "standalone_metadata" / "standalone_metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r", encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    metadata["optimization_settings"] = {
                        "cpu_priority": self.cpu_priority,
                        "io_priority": self.io_priority,
                        "affinity_mask": self.affinity_mask,
                        "use_mmcss": self.use_mmcss,
                        "use_ram_trim": self.use_ram_trim
                    }
                    
                    # Also update build_config to reflect enforced Live MO2 Mode
                    if "build_config" not in metadata:
                        metadata["build_config"] = {}
                    metadata["build_config"]["use_stealth"] = self.use_stealth
                    metadata["build_config"]["mode"] = "MO2_Sync" # Standardize
                    
                    with open(metadata_file, "w", encoding='utf-8') as f:
                        json.dump(metadata, f, indent=4)
                    self.progress_signal.emit("[*] Metadata updated with new optimization settings.")
                except Exception as e:
                    self.progress_signal.emit(f"[!] Warning: Could not update metadata JSON: {e}")

            self.finished_signal.emit(True, "Optimizer settings updated successfully.")
        except Exception:
            error_msg = traceback.format_exc()
            self.finished_signal.emit(False, f"Error during re-optimization:\n{error_msg}")

# --- Update Check Logic ---
class UpdateCheckWorker(QThread):
    update_signal = pyqtSignal(str, str) # version, url

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version
        self.version_url = VERSION_FILE_URL
        self.nexus_url = NEXUS_MOD_URL

    def run(self):
        try:
            # Short timeout to prevent blocking
            response = urllib.request.urlopen(self.version_url, timeout=5)
            remote_version = response.read().decode('utf-8').strip()
            
            if self._is_newer(remote_version, self.current_version):
                self.update_signal.emit(remote_version, self.nexus_url)
        except:
            pass # Silent fail for network issues

    def _is_newer(self, remote, local):
        try:
            r_parts = [int(p) for p in remote.split('.')]
            l_parts = [int(p) for p in local.split('.')]
            return r_parts > l_parts
        except:
            return False

class HardlinkBuilderDialog(QDialog):
    def __init__(self, organizer: mobase.IOrganizer):
        super().__init__()
        self.organizer = organizer
        self.setWindowTitle("MO2 Hardlink Builder")
        self.setMinimumSize(700, 550)
        
        # New Synchronous Messenger
        self.messenger = SynchronousMessenger()
        self.messenger.request_confirm.connect(self.on_messenger_request)
        
        self.cpu_count = os.cpu_count() or 64
        self.system_ram_gb = get_total_ram_gb()
        
        self.last_confirmed_mode = "stealth"
        self.init_ui()
        
        # Start Update Check
        self.version_str = "3.2.0"
        self.update_worker = UpdateCheckWorker(self.version_str)
        self.update_worker.update_signal.connect(self.show_update_notification)
        self.update_worker.start()
        
        self.validate_drives()
        
        # Initial profile validation
        try:
            prof_path = Path(self.organizer.profile().absolutePath())
            self.validate_profile(prof_path)
        except: pass

        # Diagnostic Logging for MO2 API
        print(f"[DEBUG] Organizer type: {type(self.organizer)}")
        try:
            members = dir(self.organizer)
            print(f"[DEBUG] Organizer members: {members}")
            if 'profileNames' in members:
                print("[DEBUG] profileNames found in organizer members.")
            else:
                print("[DEBUG] profileNames NOT found in organizer members.")
        except Exception as e:
            print(f"[DEBUG] Error listing organizer members: {e}")

        # Load build registry
        self.registry = self._load_registry()
        
        # Initial auto-fill if registry has entry for current profile
        self._check_registry_for_path()

    def _load_registry(self):
        """Loads the profile -> build_path mapping from JSON."""
        if REGISTRY_FILE.exists():
            try:
                with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Registry load error: {e}")
        return {}

    def _save_registry(self):
         """Saves the current registry to JSON."""
         try:
             with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
                 json.dump(self.registry, f, indent=4)
         except Exception as e:
             print(f"[!] Registry save error: {e}")

    def _update_registry(self, profile_name, path):
        """Records a successful build deployment."""
        path = str(Path(path).as_posix()) # Normalize path
        self.registry[profile_name] = {
            "path": path,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_registry()

    def _remove_from_registry(self, profile_name):
        """Removes a profile from the registry (e.g., after total cleanup)."""
        if profile_name in self.registry:
            del self.registry[profile_name]
            self._save_registry()

    def _check_registry_for_path(self):
        """Auto-fills the destination field if a registry entry exists for the current profile."""
        profile_name = self.profile_box.currentText()
        if profile_name in self.registry:
            saved_path = self.registry[profile_name].get("path")
            if saved_path:
                self.dest_edit.setText(saved_path)
                self.validate_drives()
        else:
            # If not in registry and we just switched, we clear it to satisfy the "keep empty" requirement
            self.dest_edit.setText("")

    def on_messenger_request(self, title, message):
        res = QMessageBox.question(self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self.messenger.set_result(res == QMessageBox.StandardButton.Yes)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Update Notification Banner (Hidden by default)
        self.update_banner = QLabel("")
        # Fix for PyQt6 alignment compatibility
        align_center = getattr(Qt, 'AlignCenter', None) or getattr(Qt.AlignmentFlag, 'AlignCenter', None)
        if align_center: self.update_banner.setAlignment(align_center)
        self.update_banner.setStyleSheet("""
            QLabel {
                background-color: #FFB74D;
                color: #000;
                padding: 8px;
                border: none;
                border-radius: 4px;
            }
            QLabel:hover { background-color: #FFA726; }
        """)
        # Fix for PyQt6 compatibility
        cursor = getattr(Qt, 'PointingHandCursor', None) or getattr(Qt.CursorShape, 'PointingHandCursor', None)
        if cursor: self.update_banner.setCursor(cursor)
        
        # Make QLabel clickable
        self.update_banner.mousePressEvent = lambda e: self.open_update_url()
        self.update_banner.hide()
        layout.addWidget(self.update_banner)

        # --- MAIN UI TABS ---
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # TAB 1: BUILDER
        self.tab_builder = QWidget()
        self.tabs.addTab(self.tab_builder, "1. Builder")
        builder_layout = QVBoxLayout(self.tab_builder)
        builder_layout.setSpacing(10)

        # Profile Selection Row
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("<b>MO2 Profile:</b>"))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(200)
        self._populate_profiles()
        self.profile_box.currentIndexChanged.connect(self.profile_changed)
        profile_layout.addWidget(self.profile_box)
        
        btn_browse_prof = QPushButton("Browse...")
        btn_browse_prof.clicked.connect(self.browse_profile)
        profile_layout.addWidget(btn_browse_prof)
        builder_layout.addLayout(profile_layout)

        # Game Info
        game = self.organizer.managedGame().gameName()
        self.lbl_game = QLabel(f"<span style='font-size: 14px; color: #81C784;'><b>Target Game:</b> {game}</span>")
        builder_layout.addWidget(self.lbl_game)

        # Profile Path
        self.lbl_prof_path = QLabel(f"<small>Path: {clean_path_for_display(self.organizer.profile().absolutePath())}</small>")
        self.lbl_prof_path.setStyleSheet("color: #AAA;")
        builder_layout.addWidget(self.lbl_prof_path)

        # Profile Status
        self.lbl_prof_status = QLabel("")
        self.lbl_prof_status.setWordWrap(True)
        self.lbl_prof_status.setStyleSheet("font-size: 11px; padding: 5px; border-radius: 4px;")
        self.lbl_prof_status.hide()
        builder_layout.addWidget(self.lbl_prof_status)

        # Destination Group
        dest_group = QVBoxLayout()
        dest_group.addWidget(QLabel("<b>Standalone Destination Folder:</b>"))
        dest_input_layout = QHBoxLayout()
        self.dest_edit = DropLineEdit(organizer=self.organizer)
        self.dest_edit.setPlaceholderText("Select or Drag & Drop Folder here...")
        self.dest_edit.textChanged.connect(self.validate_drives)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_dest)
        btn_browse.setStyleSheet("height: 30px; padding: 5px;")
        dest_input_layout.addWidget(self.dest_edit)
        dest_input_layout.addWidget(btn_browse)
        dest_group.addLayout(dest_input_layout)
        self.drive_warning = QLabel("")
        self.drive_warning.setWordWrap(True)
        self.drive_warning.setStyleSheet("font-size: 11px; color: #FFB74D; border: 1px solid #FFB74D; padding: 5px; border-radius: 4px;")
        self.drive_warning.hide()
        dest_group.addWidget(self.drive_warning)
        builder_layout.addLayout(dest_group)

        # Options (Hardlinks, Clean, Documents)
        options_row1 = QHBoxLayout()
        self.cb_hardlinks = QCheckBox("Use Hardlinks for Vanilla Files (Recommended)")
        self.cb_hardlinks.setChecked(True)
        self.btn_clear = QPushButton("Clear Destination")
        self.btn_clear.clicked.connect(self.clear_dest)
        self.btn_clear.setStyleSheet("background-color: #D32F2F; color: white; border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 2px 10px;")
        options_row1.addWidget(self.cb_hardlinks)
        options_row1.addStretch()
        options_row1.addWidget(self.btn_clear)
        builder_layout.addLayout(options_row1)

        # Save & Configuration Mode: Enforced to MO2 Live Sync (Live MO2 Mode)
        # Save & Configuration Mode: Enforced to MO2 Live Sync (Live MO2 Mode)
        # We create dummy radio buttons (hidden) to maintain compatibility with existing logic
        self.rb_mode_isolated = QRadioButton("Isolated")
        self.rb_mode_docs = QRadioButton("Documents")
        self.rb_mode_stealth = QRadioButton("Stealth (Live MO2)")
        self.rb_mode_stealth.setChecked(True)
        # We don't add them to the layout, effectively keeping them hidden/removed from UI
        # But they exist as attributes so .isChecked() works.


        # TAB 2: TWEAKS & OPTIMIZATION
        self.tab_tweaks = QWidget()
        self.tabs.addTab(self.tab_tweaks, "2. Tweaks & Optimization")
        tweaks_layout = QVBoxLayout(self.tab_tweaks)
        tweaks_layout.setContentsMargins(15, 15, 15, 15)
        tweaks_layout.setSpacing(15)

        # 1. GENERAL OPTIMIZATIONS
        gen_group = QGroupBox("General Process Optimizations")
        gen_layout = QGridLayout()
        gen_layout.setSpacing(10)
        
        self.cb_cpu_priority = QCheckBox("High CPU Priority")
        self.cb_cpu_priority.setChecked(False)
        self.cb_cpu_priority.stateChanged.connect(self.validate_optimization_settings)
        if self.cpu_count < 4:
            self.cb_cpu_priority.setEnabled(False)
            self.cb_cpu_priority.setToolTip("DISABLED: Requires at least 4 logical processors for system safety.")
        else:
            self.cb_cpu_priority.setToolTip("Sets the game process to High CPU priority.\nImproves frame consistency and responsiveness.")
        
        self.cb_io_priority = QCheckBox("High I/O Priority")
        self.cb_io_priority.setChecked(False)
        self.cb_io_priority.stateChanged.connect(self.validate_optimization_settings)
        self.cb_io_priority.setToolTip("Sets the game process to High I/O priority.\nReduces micro-stutters during cell/texture streaming.")

        self.cb_mmcss = QCheckBox("Enable MMCSS (Games)")
        self.cb_mmcss.setChecked(False)
        self.cb_mmcss.stateChanged.connect(self.validate_optimization_settings)
        if self.cpu_count < 8:
            self.cb_mmcss.setEnabled(False)
            self.cb_mmcss.setToolTip(f"DISABLED: Requires at least 8 logical processors (Detected: {self.cpu_count}).")
        else:
            self.cb_mmcss.setToolTip("Registers the game with Microsoft's Multimedia Class Scheduler.\nEnsures game threads are prioritized over background tasks.")
        
        self.cb_ram_trim = QCheckBox("Trim Background RAM")
        self.cb_ram_trim.stateChanged.connect(self.validate_optimization_settings)
        self.cb_ram_trim.setToolTip("Attempts to clear unused memory from other background applications right before the game starts.\nEnsures a clean slate for the game's initial memory allocation.\n\n[IMPORTANT] An SSD is highly recommended to prevent disk hitching during paging.")
        
        gen_layout.addWidget(self.cb_cpu_priority, 0, 0)
        gen_layout.addWidget(self.cb_io_priority, 0, 1)
        gen_layout.addWidget(self.cb_mmcss, 1, 0)
        gen_layout.addWidget(self.cb_ram_trim, 1, 1)
        gen_group.setLayout(gen_layout)
        gen_group.setMinimumHeight(100)
        tweaks_layout.addWidget(gen_group)

        # 2. ADVANCED CPU AFFINITY
        aff_group = QGroupBox("Advanced CPU Affinity Control")
        aff_layout = QVBoxLayout()
        aff_layout.setSpacing(8)

        self.cb_affinity_optimizer = QCheckBox("Enable CPU Affinity Optimizer")
        self.cb_affinity_optimizer.setStyleSheet("font-weight: bold;")
        self.cb_affinity_optimizer.setChecked(False) # Default unchecked as requested
        self.cb_affinity_optimizer.setToolTip("Disable to let Windows handle core allocation normally.\nEnable to manually restrict the game to specific cores.")
        self.cb_affinity_optimizer.stateChanged.connect(self.on_affinity_optimizer_changed)
        aff_layout.addWidget(self.cb_affinity_optimizer)

        # Labels and Selection Buttons Row
        aff_btns_row = QHBoxLayout()
        lbl_affinity = QLabel("Select Logical Processors for Game Threads:")
        lbl_affinity.setStyleSheet("color: #AAA; font-size: 10px;")
        aff_btns_row.addWidget(lbl_affinity)
        
        aff_btns_row.addStretch()
        
        self.btn_affinity_all = QPushButton("Select All")
        self.btn_affinity_all.clicked.connect(lambda: self._set_all_affinity(True))
        self.btn_affinity_none = QPushButton("None")
        self.btn_affinity_none.clicked.connect(lambda: self._set_all_affinity(False))
        
        btn_style = "height: 20px; font-size: 10px; padding: 0 8px; margin: 0;"
        self.btn_affinity_all.setStyleSheet(btn_style)
        self.btn_affinity_none.setStyleSheet(btn_style)
        
        aff_btns_row.addWidget(self.btn_affinity_all)
        aff_btns_row.addWidget(self.btn_affinity_none)
        aff_layout.addLayout(aff_btns_row)
        
        affinity_scroll = QScrollArea()
        affinity_scroll.setFixedHeight(120)
        affinity_scroll.setWidgetResizable(True)
        affinity_scroll.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #0A0A0A; }")
        
        affinity_container = QWidget()
        affinity_container.setStyleSheet("background-color: transparent;")
        self.affinity_grid_layout = QGridLayout(affinity_container)
        self.affinity_grid_layout.setSpacing(4)
        self.affinity_checkboxes = []
        for i in range(64):
            cb = QCheckBox(f"{i}")
            cb.setStyleSheet("color: #DDD; font-size: 9px; padding: 1px;")
            cb.setChecked(True) # State when optimizer is enabled
            if i < 2:
                cb.setEnabled(False)
                cb.setChecked(False)
                cb.setToolTip("Reserved for System Tasks")
            elif i >= self.cpu_count:
                cb.setEnabled(False)
                cb.setChecked(False)
                cb.setToolTip("Hardware not present")
            
            self.affinity_checkboxes.append(cb)
            self.affinity_grid_layout.addWidget(cb, i // 8, i % 8)
        
        affinity_scroll.setWidget(affinity_container)
        self.affinity_scroll_area = affinity_scroll
        aff_layout.addWidget(affinity_scroll)

        # (Buttons moved above scroll area)
        aff_group.setLayout(aff_layout)
        aff_group.setMinimumHeight(200)
        tweaks_layout.addWidget(aff_group)

        # 3. APPLY BUTTON
        self.btn_reoptimize = QPushButton("⚡ APPLY OPTIMIZATION SETTINGS")
        self.btn_reoptimize.clicked.connect(self.reoptimize_wrappers)
        self.btn_reoptimize.setStyleSheet("""
            QPushButton { 
                background-color: #673AB7; color: white; font-weight: bold; height: 38px; border-radius: 4px; 
                margin-top: 5px; margin-bottom: 2px;
            }
            QPushButton:hover { background-color: #7E57C2; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        tweaks_layout.addWidget(self.btn_reoptimize)

        self.btn_reset_defaults = QPushButton("↺ Reset to Windows Defaults")
        self.btn_reset_defaults.clicked.connect(self.reset_optimization_defaults)
        self.btn_reset_defaults.setStyleSheet("""
            QPushButton { 
                background-color: #333; color: #AAA; font-size: 11px; height: 28px; border: 1px solid #444; border-radius: 4px;
                margin-bottom: 5px;
            }
            QPushButton:hover { background-color: #444; color: white; border: 1px solid #555; }
        """)
        tweaks_layout.addWidget(self.btn_reset_defaults)

        tweaks_layout.addStretch()

        # Ensure correct initial UI state
        self.on_affinity_optimizer_changed()
        self.on_cpu_priority_changed()

        # TAB 3: STANDALONE MANAGER
        self.tab_manager = QWidget()
        self.tabs.addTab(self.tab_manager, "3. Standalone Manager")
        manager_layout = QHBoxLayout(self.tab_manager)
        manager_layout.setContentsMargins(15, 15, 15, 15)
        manager_layout.setSpacing(15)

        # Left Panel: Standalone List
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        
        list_label = QLabel("<b>Registered Standalone Builds:</b>")
        left_panel.addWidget(list_label)
        
        self.standalone_list = QListWidget()
        self.standalone_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2A2A2A;
            }
            QListWidget::item:selected {
                background-color: #673AB7;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #2A2A2A;
            }
        """)
        self.standalone_list.itemSelectionChanged.connect(self.on_standalone_selected)
        left_panel.addWidget(self.standalone_list)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh_list = QPushButton("🔄 Refresh List")
        self.btn_refresh_list.clicked.connect(self.refresh_standalone_list)
        self.btn_refresh_list.setStyleSheet("background-color: #1565C0; color: white; height: 32px;")
        
        self.btn_open_folder = QPushButton("📁 Open Folder")
        self.btn_open_folder.clicked.connect(self.open_standalone_folder)
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.setStyleSheet("background-color: #2E7D32; color: white; height: 32px;")
        
        btn_layout.addWidget(self.btn_refresh_list)
        btn_layout.addWidget(self.btn_open_folder)
        left_panel.addLayout(btn_layout)
        
        # Right Panel: Metadata Display
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)
        
        info_label = QLabel("<b>Build Information:</b>")
        right_panel.addWidget(info_label)
        
        self.metadata_display = QTextBrowser()
        self.metadata_display.setReadOnly(True)
        self.metadata_display.setOpenExternalLinks(True)  # Enable clickable links
        self.metadata_display.setStyleSheet("""
            QTextBrowser {
                background-color: #121212;
                color: #E0E0E0;
                font-family: 'Consolas', monospace;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        self.metadata_display.setPlaceholderText("Select a standalone build to view details...")
        right_panel.addWidget(self.metadata_display)
        
        # Add panels to layout (40/60 split)
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setMinimumWidth(300)
        left_widget.setMaximumWidth(400)
        
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        
        manager_layout.addWidget(left_widget)
        manager_layout.addWidget(right_widget)
        
        # Load initial data
        self._populate_standalone_list()

        # Progress Area
        progress_layout = QVBoxLayout()
        bar_style = """
            QProgressBar { border: 1px solid #333; border-radius: 5px; text-align: center; height: 12px; background: #222; font-size: 10px; }
            QProgressBar::chunk { background-color: #388E3C; }
        """
        
        self.lbl_clean = QLabel("Stage 1: Cleanup")
        self.bar_clean = QProgressBar()
        self.bar_clean.setStyleSheet(bar_style)
        progress_layout.addWidget(self.lbl_clean)
        progress_layout.addWidget(self.bar_clean)

        self.lbl_scan = QLabel("Stage 2: Scanning")
        self.bar_scan = QProgressBar()
        self.bar_scan.setStyleSheet(bar_style)
        progress_layout.addWidget(self.lbl_scan)
        progress_layout.addWidget(self.bar_scan)

        self.lbl_link = QLabel("Stage 3: Deployment")
        self.bar_link = QProgressBar()
        self.bar_link.setStyleSheet(bar_style)
        progress_layout.addWidget(self.lbl_link)
        progress_layout.addWidget(self.bar_link)

        self.lbl_verify = QLabel("Stage 4: Verification")
        self.bar_verify = QProgressBar()
        self.bar_verify.setStyleSheet(bar_style)
        progress_layout.addWidget(self.lbl_verify)
        progress_layout.addWidget(self.bar_verify)

        builder_layout.addLayout(progress_layout)

        # Log Area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #121212; color: #E0E0E0; font-family: 'Consolas', monospace; border: 1px solid #333;")
        builder_layout.addWidget(self.log_area)

        # Action Button
        self.btn_build = QPushButton("BUILD STANDALONE")
        self.btn_build.clicked.connect(self.start_build)
        self.btn_build.setStyleSheet("""
            QPushButton {
                background-color: #388E3C; 
                color: white; 
                font-weight: bold; 
                height: 50px; 
                font-size: 16px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #43A047; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        builder_layout.addWidget(self.btn_build)
        
        footer_layout = QHBoxLayout()
        lbl_qt = QLabel(f"<small>Framework: {QT_NAME} | Deployment Engine v2.1.0</small>")
        lbl_qt.setStyleSheet("color: #777;")
        footer_layout.addStretch()
        footer_layout.addWidget(lbl_qt)
        builder_layout.addLayout(footer_layout)

        self.setLayout(layout)

    def _populate_profiles(self):
        current_prof = "Default"
        try:
            current_prof = self.organizer.profile().name()
        except: pass

        profiles = []
        # Tiered approach for MO2 API compatibility
        methods_to_try = [
            ("profileNames", lambda: self.organizer.profileNames()),
            ("profileList", lambda: [p.name() for p in self.organizer.profileList()]),
            ("currentProfileOnly", lambda: [self.organizer.profile().name()])
        ]

        for method_name, method_func in methods_to_try:
            try:
                print(f"[*] Attempting profile listing via: {method_name}")
                profiles = method_func()
                if profiles:
                    print(f"[SUCCESS] Found profiles via {method_name}")
                    break
            except Exception as e:
                print(f"[!] {method_name} failed: {e}")

        if not profiles:
            profiles = ["Default"] # Absolute fallback

        self.profile_box.clear()
        
        default_index = 0
        for i, name in enumerate(profiles):
            self.profile_box.addItem(name)
            if name == current_prof:
                default_index = i
        
        self.profile_box.setCurrentIndex(default_index)

    def profile_changed(self):
        name = self.profile_box.currentText()
        try:
            base_prof_path = Path(self.organizer.basePath()) / "profiles" / name
            if name == self.organizer.profile().name():
                base_prof_path = Path(self.organizer.profile().absolutePath())
            
            self.lbl_prof_path.setText(f"<small>Path: {clean_path_for_display(base_prof_path)}</small>")
            self.validate_profile(base_prof_path)
            self.validate_drives()
            
            # Smart Auto-fill Destination
            self._check_registry_for_path()
        except: pass

    def browse_profile(self):
        path = QFileDialog.getExistingDirectory(self, "Select Custom Profile Folder")
        if path:
            folder_name = Path(path).name
            self.profile_box.addItem(folder_name, path)
            self.profile_box.setCurrentIndex(self.profile_box.count() - 1)
            self.lbl_prof_path.setText(f"<small>Path: {clean_path_for_display(path)}</small>")
            self.validate_profile(Path(path))
            self.validate_drives()

    def _get_game_info(self):
        """Get game-specific naming info (ini prefix, etc.)"""
        game_name = self.organizer.managedGame().gameName()
        MAPPINGS = {
            "Skyrim Special Edition": {"ini": "Skyrim"},
            "Skyrim": {"ini": "Skyrim"},
            "Fallout 4": {"ini": "Fallout4"},
            "Starfield": {"ini": "Starfield"},
        }
        info = MAPPINGS.get(game_name, {"ini": game_name.split()[0]})
        return info

    def validate_profile(self, prof_path):
        """Validate profile files and update UI accordingly."""
        prof_path = Path(ensure_long_path(prof_path))
        if not prof_path.exists():
            self.lbl_prof_status.setText("❌ <b>Profile Error:</b> Path does not exist.")
            self.lbl_prof_status.setStyleSheet("font-size: 11px; color: #F44336; border: 1px solid #F44336; padding: 5px; border-radius: 4px;")
            self.lbl_prof_status.show()
            self.btn_build.setEnabled(False)
            return

        # Get game-specific ini prefix
        game_info = self._get_game_info()
        ini_prefix = game_info["ini"]
        
        # Determine which location to check based on Documents mode
        use_documents = self.rb_mode_docs.isChecked() if self.rb_mode_docs else False
        
        if use_documents:
            # Check in Windows Documents folder
            game_name = self.organizer.managedGame().gameName()
            MAPPINGS = {
                "Skyrim Special Edition": "Skyrim Special Edition",
                "Skyrim": "Skyrim",
                "Fallout 4": "Fallout4",
                "Starfield": "Starfield",
            }
            docs_name = MAPPINGS.get(game_name, game_name)
            check_path = Path(get_windows_documents_path()) / "My Games" / docs_name
            location_label = "Documents Folder"
        else:
            # Check in profile folder
            check_path = prof_path
            location_label = "Profile Folder"

        # Required files (blocks build)
        required = ["modlist.txt"]  # Always required from profile
        
        # Configuration files to check in the appropriate location
        config_files = [
            f"{ini_prefix}.ini",
            f"{ini_prefix}Prefs.ini"
        ]
        
        # Plugin files to check
        plugin_files = [
            "loadorder.txt",
            "plugins.txt"
        ]

        # Always check modlist.txt in profile folder
        missing_required = [f for f in required if not (prof_path / f).exists()]
        
        # Check config and plugin files in the appropriate location
        if use_documents:
            # In Documents mode, check config files in Documents, plugins in AppData
            missing_config = [f for f in config_files if not (check_path / f).exists()]
            # Plugins are in AppData/Local
            appdata_path = Path(os.environ['LOCALAPPDATA']) / docs_name
            missing_plugins = [f for f in plugin_files if not (appdata_path / f).exists()]
            missing_optional = missing_config + missing_plugins
        else:
            # In Profile mode, check everything in profile folder
            optional = plugin_files + config_files
            missing_optional = [f for f in optional if not (prof_path / f).exists()]

        if missing_required:
            self.lbl_prof_status.setText(f"❌ <b>Profile Invalid:</b> Missing critical file(s): {', '.join(missing_required)}")
            self.lbl_prof_status.setStyleSheet("font-size: 11px; color: #F44336; border: 1px solid #F44336; padding: 5px; border-radius: 4px;")
            self.lbl_prof_status.show()
            self.btn_build.setEnabled(False)
        elif missing_optional:
            self.lbl_prof_status.setText(f"⚠️ <b>Warning ({location_label}):</b> Missing optional file(s): {', '.join(missing_optional)}")
            self.lbl_prof_status.setStyleSheet("font-size: 11px; color: #FFB74D; border: 1px solid #FFB74D; padding: 5px; border-radius: 4px;")
            self.lbl_prof_status.show()
            self.btn_build.setEnabled(True)
        else:
            self.lbl_prof_status.setText(f"✅ <b>Valid ({location_label}):</b> All required files found.")
            self.lbl_prof_status.setStyleSheet("font-size: 11px; color: #81C784; border: 1px solid #81C784; padding: 5px; border-radius: 4px;")
            self.lbl_prof_status.show()
            self.btn_build.setEnabled(True)
    
    def on_cpu_priority_changed(self):
        """Validate optimization settings and enable/disable apply button."""
        self.validate_optimization_settings()
    
    def validate_optimization_settings(self):
        """Enable/disable optimization button based on whether any checkbox is checked."""
        # Check if any optimization checkbox is checked
        any_checked = (
            self.cb_cpu_priority.isChecked() or
            self.cb_io_priority.isChecked() or
            self.cb_mmcss.isChecked() or
            self.cb_ram_trim.isChecked() or
            self.cb_affinity_optimizer.isChecked()
        )
        
        # Enable button only if at least one checkbox is checked
        if hasattr(self, 'btn_reoptimize'):
            self.btn_reoptimize.setEnabled(any_checked)

    def on_affinity_optimizer_changed(self):
        """Toggle affinity grid based on the master checkbox."""
        state = self.cb_affinity_optimizer.isChecked()
        
        # Enable/Disable the scroll area containing the grid
        self.affinity_scroll_area.setEnabled(state)
        
        # Enable/Disable the helper buttons
        self.btn_affinity_all.setEnabled(state)
        self.btn_affinity_none.setEnabled(state)

        if state:
            # Enabled: Force disable CPU 0 and 1, and any cores beyond hardware limit
            for i, cb in enumerate(self.affinity_checkboxes):
                if i < 2 or i >= self.cpu_count:
                    cb.setChecked(False)
                    cb.setEnabled(False)
                else:
                    cb.setEnabled(True)
        else:
            # Disabled: Check all active cores (Windows Default)
            for i, cb in enumerate(self.affinity_checkboxes):
                if i < self.cpu_count:
                    cb.setChecked(True)
                    cb.setEnabled(True)
                else:
                    cb.setChecked(False)
                    cb.setEnabled(False)
        
        # Validate optimization settings to enable/disable apply button
        self.validate_optimization_settings()

    def _set_all_affinity(self, state):
        """Helper to mass toggle affinity checkboxes (only for active, non-reserved cores)"""
        for i, cb in enumerate(self.affinity_checkboxes):
            if i >= 2 and i < self.cpu_count:
                cb.setChecked(state)

    def _load_standalone_registry(self):
        """Load and parse standalone_registry.json"""
        try:
            print(f"[DEBUG] Loading registry from: {REGISTRY_FILE}")
            print(f"[DEBUG] Registry file exists: {REGISTRY_FILE.exists()}")
            
            if not REGISTRY_FILE.exists():
                print("[DEBUG] Registry file does not exist")
                return {}
            
            with open(REGISTRY_FILE, 'r') as f:
                data = json.load(f)
                print(f"[DEBUG] Registry data loaded: {data}")
                return data
        except Exception as e:
            print(f"[DEBUG] Failed to load registry: {e}")
            traceback.print_exc()
            return {}

    def _populate_standalone_list(self):
        """Populate the standalone list from registry"""
        self.standalone_list.clear()
        self.metadata_display.clear()
        self.btn_open_folder.setEnabled(False)
        
        registry = self._load_standalone_registry()
        print(f"[DEBUG] Registry loaded: {registry}")
        
        if not registry:
            self.standalone_list.addItem("No standalone builds found.")
            print("[DEBUG] Registry is empty, showing 'No standalone builds found.'")
            return
        
        item_count = 0
        for profile_name, data in registry.items():
            path = data.get("path", "")
            print(f"[DEBUG] Processing profile: {profile_name}, path: {path}")
            
            if not path:
                print(f"[DEBUG] Skipping {profile_name} - no path")
                continue
            
            # Try to read metadata to get standalone folder name
            try:
                metadata_file = Path(path) / "standalone_metadata" / "standalone_metadata.json"
                print(f"[DEBUG] Looking for metadata at: {metadata_file}")
                
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        # Get standalone folder name from metadata
                        standalone_name = metadata.get("standalone_info", {}).get("standalone_name", "")
                        if not standalone_name:
                            # Fallback to folder name from path
                            standalone_name = Path(path).name
                        print(f"[DEBUG] Found standalone name: {standalone_name}")
                else:
                    # Fallback to folder name from path
                    standalone_name = Path(path).name
                    print(f"[DEBUG] Metadata file not found, using folder name: {standalone_name}")
            except Exception as e:
                # Fallback to folder name from path
                standalone_name = Path(path).name
                print(f"[DEBUG] Error reading metadata: {e}, using folder name: {standalone_name}")
            
            # Create list item with format: FolderName (ProfileName)
            item_text = f"{standalone_name} ({profile_name})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, {"profile": profile_name, "path": path})
            self.standalone_list.addItem(item)
            item_count += 1
            print(f"[DEBUG] Added item: {item_text}")
        
        print(f"[DEBUG] Total items added: {item_count}")

    def on_standalone_selected(self):
        """Handle standalone build selection"""
        selected_items = self.standalone_list.selectedItems()
        if not selected_items:
            self.metadata_display.clear()
            self.btn_open_folder.setEnabled(False)
            return
        
        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        path = data.get("path", "")
        if not path:
            return
        
        # Enable open folder button
        self.btn_open_folder.setEnabled(True)
        
        # Load and display metadata
        try:
            metadata_file = Path(path) / "standalone_metadata" / "standalone_metadata.json"
            if not metadata_file.exists():
                self.metadata_display.setHtml(f"<p style='color: #F44336;'>Metadata file not found at:<br>{metadata_file}</p>")
                return
            
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Helper function to clean paths and create clickable links
            def make_path_link(path_str):
                if not path_str or path_str == "N/A":
                    return None
                clean = clean_path_for_display(path_str)
                # Convert to file:/// URL for clickable link
                file_url = Path(path_str).as_uri()
                return f'<a href="{file_url}" style="color: #81C784; text-decoration: none;">{clean}</a>'
            
            # Helper to add field only if value exists
            def add_field(label, value, is_path=False):
                if value is None or value == "":
                    return ""
                if is_path:
                    link = make_path_link(value)
                    if link:
                        return f"<tr><td style='color: #AAA; padding-right: 20px;'>{label}</td><td>{link}</td></tr>"
                    return ""
                return f"<tr><td style='color: #AAA; padding-right: 20px;'>{label}</td><td style='color: #E0E0E0;'>{value}</td></tr>"
            
            # Format metadata as HTML
            html = []
            html.append("<html><body style='font-family: Consolas, monospace; background-color: #121212; color: #E0E0E0;'>")
            
            # Header
            html.append("<div style='border-bottom: 2px solid #673AB7; padding-bottom: 10px; margin-bottom: 20px;'>")
            html.append("<h2 style='color: #81C784; margin: 0;'>STANDALONE BUILD INFORMATION</h2>")
            html.append("</div>")
            
            # Standalone Info
            standalone_info = metadata.get("standalone_info", {})
            if standalone_info:
                html.append("<h3 style='color: #FFB74D; margin-top: 20px; margin-bottom: 10px;'>📦 STANDALONE INFORMATION</h3>")
                html.append("<table cellspacing='0' cellpadding='5'>")
                html.append(add_field("Name", standalone_info.get("standalone_name")))
                html.append(add_field("Path", standalone_info.get("standalone_path"), is_path=True))
                html.append(add_field("Build Date", standalone_info.get("build_timestamp")))
                html.append(add_field("Qt Framework", standalone_info.get("qt_framework")))
                html.append(add_field("Wrapper Type", standalone_info.get("wrapper_type")))
                html.append("</table>")
            
            # Game Info
            game_info = metadata.get("game_info", {})
            if game_info:
                html.append("<h3 style='color: #FFB74D; margin-top: 20px; margin-bottom: 10px;'>🎮 GAME INFORMATION</h3>")
                html.append("<table cellspacing='0' cellpadding='5'>")
                html.append(add_field("Game Name", game_info.get("game_name")))
                html.append(add_field("Game Path", game_info.get("game_path"), is_path=True))
                html.append(add_field("Executable", game_info.get("game_executable")))
                html.append("</table>")
            
            # MO2 Info
            mo2_info = metadata.get("mo2_info", {})
            if mo2_info:
                html.append("<h3 style='color: #FFB74D; margin-top: 20px; margin-bottom: 10px;'>🔧 MO2 INFORMATION</h3>")
                html.append("<table cellspacing='0' cellpadding='5'>")
                html.append(add_field("Profile Name", mo2_info.get("mo2_profile_name")))
                html.append(add_field("Profile Path", mo2_info.get("mo2_profile_path"), is_path=True))
                html.append(add_field("MO2 Base Path", mo2_info.get("mo2_base_path"), is_path=True))
                html.append(add_field("Mods Path", mo2_info.get("mo2_mods_path"), is_path=True))
                html.append(add_field("Overwrite Path", mo2_info.get("mo2_overwrite_path"), is_path=True))
                html.append("</table>")
            
            # Build Config section excluded as per user request
            
            # Source Paths
            source_paths = metadata.get("source_paths", {})
            if source_paths:
                html.append("<h3 style='color: #FFB74D; margin-top: 20px; margin-bottom: 10px;'>📂 SOURCE PATHS</h3>")
                html.append("<table cellspacing='0' cellpadding='5'>")
                html.append(add_field("Save Source", source_paths.get("save_source"), is_path=True))
                html.append(add_field("Config Source", source_paths.get("config_source"), is_path=True))
                html.append(add_field("Plugins Source", source_paths.get("plugins_source"), is_path=True))
                html.append(add_field("Modlist Source", source_paths.get("modlist_source"), is_path=True))
                html.append(add_field("Load Order Source", source_paths.get("loadorder_source"), is_path=True))
                html.append("</table>")
            
            # Optimization Settings
            opt_settings = metadata.get("optimization_settings", {})
            if opt_settings:
                html.append("<h3 style='color: #FFB74D; margin-top: 20px; margin-bottom: 10px;'>⚡ OPTIMIZATION SETTINGS</h3>")
                html.append("<table cellspacing='0' cellpadding='5'>")
                
                # Helper to convert boolean to Yes/No
                def bool_to_yesno(value):
                    if isinstance(value, bool):
                        return "Yes" if value else "No"
                    return str(value)
                
                html.append(add_field("CPU Priority", bool_to_yesno(opt_settings.get("cpu_priority", False))))
                html.append(add_field("I/O Priority", bool_to_yesno(opt_settings.get("io_priority", False))))
                html.append(add_field("MMCSS Enabled", bool_to_yesno(opt_settings.get("use_mmcss", False))))
                html.append(add_field("RAM Trim", bool_to_yesno(opt_settings.get("use_ram_trim", False))))
                
                # CPU Affinity: Show "Yes" if tweaked (not all cores), "No" if all cores active (default)
                affinity_mask = opt_settings.get("affinity_mask", 0)
                if affinity_mask == 0:
                    # 0 means all cores active (Windows default)
                    html.append(add_field("CPU Affinity", "No"))
                else:
                    # Non-zero means affinity is tweaked
                    html.append(add_field("CPU Affinity", "Yes"))
                
                html.append("</table>")
            
            html.append("</body></html>")
            
            self.metadata_display.setHtml("".join(html))
            
        except Exception as e:
            self.metadata_display.setHtml(f"<p style='color: #F44336;'>Error loading metadata:<br>{str(e)}</p>")

    def refresh_standalone_list(self):
        """Refresh the standalone list"""
        self._populate_standalone_list()

    def open_standalone_folder(self):
        """Open the selected standalone folder in Explorer"""
        selected_items = self.standalone_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        path = data.get("path", "")
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Folder Not Found", f"The standalone folder does not exist:\n{path}")
            return
        
        try:
            webbrowser.open(str(Path(path)))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open folder:\n{str(e)}")

    def reset_optimization_defaults(self):
        """Reverts all optimizations to Windows defaults and re-wraps."""
        # 1. Reset UI State
        self.cb_cpu_priority.setChecked(False)
        self.cb_io_priority.setChecked(False)
        self.cb_mmcss.setChecked(False)
        self.cb_ram_trim.setChecked(False)
        self.cb_affinity_optimizer.setChecked(False) # Triggers on_affinity_optimizer_changed -> Resets grid
        
        # 2. Re-apply (Wipe optimizations from wrappers)
        self.reoptimize_wrappers(skip_warning=True)

    def reoptimize_wrappers(self, skip_warning=False):
        """Updates wrappers for an existing standalone folder without rebuilding."""
        dest = ensure_long_path(self.dest_edit.text().strip())
        if not dest:
            QMessageBox.warning(self, "Missing Destination", "Select a standalone folder first.")
            return

        # Protection Check
        if (Path(dest) / ".mo2_protected").exists():
            QMessageBox.critical(self, "Build Protected", 
                                "This folder is currently LINKED to the MO2 Hardlink Updater.\n\n"
                                "You cannot change optimization settings while it is protected.\n"
                                "Please 'Unlink' it via the Updater tool first.")
            return
        
        # Read existing metadata
        metadata_file = Path(dest) / "standalone_metadata" / "standalone_metadata.json"
        if not metadata_file.exists():
            QMessageBox.critical(self, "Error", "No metadata found in this folder. Is it a standalone build?")
            return

        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            game_exe = meta.get("game_info", {}).get("game_executable")
            game_name = meta.get("game_info", {}).get("game_name")
            
            MAPPINGS = {
                "Skyrim Special Edition": {"docs": "Skyrim Special Edition", "ini": "Skyrim"},
                "Skyrim": {"docs": "Skyrim", "ini": "Skyrim"},
                "Fallout 4": {"docs": "Fallout4", "ini": "Fallout4"},
                "Starfield": {"docs": "Starfield", "ini": "Starfield"},
            }
            info = MAPPINGS.get(game_name, {"docs": game_name, "ini": game_name.split()[0]})
            docs_name = info["docs"]
            ini_prefix = info["ini"]

            cpu_priority = self.cb_cpu_priority.isChecked()
            io_priority = self.cb_io_priority.isChecked()
            affinity_mask, core_count = self._get_affinity_mask()
            
            # If the optimizer is disabled, we pass mask 0 so Windows uses defaults
            if not self.cb_affinity_optimizer.isChecked():
                affinity_mask = 0
                core_count = self.cpu_count
            use_mmcss = self.cb_mmcss.isChecked()
            use_ram_trim = self.cb_ram_trim.isChecked()

            # Warning Prompt
            if not skip_warning:
                msg = "⚡ <b>WARNING</b>\n\n" \
                      "Incorrect optimization configurations may cause game instability or crashes.\n\n" \
                      "Are you sure you want to apply these optimization settings to your standalone build?"
                
                res = QMessageBox.warning(self, "Warning", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                
                if res == QMessageBox.StandardButton.No:
                    self.log("[X] Optimization update canceled by user.")
                    # Reset logic: all checkboxes become uncheck except affinity
                    self.cb_cpu_priority.setChecked(False)
                    self.cb_io_priority.setChecked(False)
                    self.cb_mmcss.setChecked(False)
                    self.cb_ram_trim.setChecked(False)
                    self.cb_affinity_optimizer.setChecked(False) # This will trigger on_affinity_optimizer_changed which resets affinity to all checked
                    return

            # Safety Check: At least 2 cores if affinity is being set and optimizer is enabled
            if self.cb_affinity_optimizer.isChecked() and core_count < 2:
                QMessageBox.warning(self, "Safety Warning", 
                                    "You must select at least <b>2 CPU cores</b> for the affinity setting.\n\n"
                                    "Selecting zero or only 1 core can cause the game to freeze or crash during startup.")
                return

            self.btn_reoptimize.setEnabled(False)
            self.log_area.append(f"[*] Starting Re-Optimization for: {clean_path_for_display(dest)}")
            
            profile_name = meta.get("mo2_info", {}).get("mo2_profile_name", "Unknown")
            mo2_profile_path = meta.get("mo2_info", {}).get("mo2_profile_path", "")
            use_isolation = True # Enforced for v3.0 Live MO2 Mode consistency
            use_stealth = True   # Enforced for v3.0 Live MO2 Mode consistency
            appdata_name = meta.get("game_info", {}).get("game_name", "") # Fallback

            self.re_worker = ReWrapWorker(
                dest, game_exe, ini_prefix, docs_name, profile_name,
                cpu_priority, io_priority, affinity_mask,
                use_mmcss, use_ram_trim,
                implement_isolation_hijack,
                use_isolation=use_isolation, use_stealth=use_stealth,
                mo2_profile_path=mo2_profile_path, appdata_name=appdata_name
            )
            self.re_worker.progress_signal.connect(self.log)
            self.re_worker.finished_signal.connect(self.on_reoptimize_finished)
            self.re_worker.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read metadata: {e}")

    def on_reoptimize_finished(self, success, message):
        self.btn_reoptimize.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
            self.log("[SUCCESS] Optimizer settings updated.")
        else:
            QMessageBox.critical(self, "Failed", message)
            self.log(f"[!] Re-optimization failed: {message}")

    def validate_drives(self):
        dest_text = self.dest_edit.text().strip()
        if not dest_text:
            self.drive_warning.hide()
            return

        try:
            # Normalize all drives using ensure_long_path so prefixes match
            dest_drive = Path(ensure_long_path(dest_text)).anchor.lower()
            
            game_path = self.organizer.managedGame().gameDirectory().absolutePath()
            game_drive = Path(ensure_long_path(game_path)).anchor.lower()
            
            mods_path = self.organizer.modsPath()
            mods_drive = Path(ensure_long_path(mods_path)).anchor.lower()
            
            prof_path_text = self.lbl_prof_path.text().replace("<small>Path: ", "").replace("</small>", "")
            prof_drive = Path(ensure_long_path(prof_path_text)).anchor.lower()

            # Helper for display: Strip \\?\ if present
            def clean_drv(d): return d.replace("\\\\?\\", "").upper()

            warnings = []
            if dest_drive != game_drive: 
                warnings.append(f"• <b>Game Drive mismatch:</b> {clean_drv(dest_drive)} vs {clean_drv(game_drive)}")
            if dest_drive != mods_drive: 
                warnings.append(f"• <b>Mods Drive mismatch:</b> {clean_drv(dest_drive)} vs {clean_drv(mods_drive)}")
            if dest_drive != prof_drive: 
                warnings.append(f"• <b>Profile Drive mismatch:</b> {clean_drv(dest_drive)} vs {clean_drv(prof_drive)}")

            if warnings:
                self.drive_warning.setText("⚠️ <b>Drive Warning:</b> (Performance/Space impact)<br/>" + "<br/>".join(warnings))
                self.drive_warning.show()
            else:
                self.drive_warning.hide()
        except:
            self.drive_warning.hide()
        
        pass 

    def validate_save_buttons(self):
        """Dummy method for v3.1+ compatibility with legacy calls"""
        pass

    def clear_dest(self):
        dest = ensure_long_path(self.dest_edit.text())
        if not dest: return
        
        if QMessageBox.question(self, "Clear Folder", f"WIPE everything in {clean_path_for_display(dest)}?\n\nThis will remove all files in the target folder.", 
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        self.btn_build.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.log_area.clear()
        self.bar_clean.setValue(0)
        
        # Collect required paths
        mo2_path = Path(self.organizer.basePath())
        game_path = Path(self.organizer.managedGame().gameDirectory().absolutePath())
        mods_path = Path(self.organizer.modsPath())
        overwrite_path = Path(self.organizer.overwritePath())
        game_name = self.organizer.managedGame().gameName()
        profile_name = self.profile_box.currentText()
        cpu_priority = self.cb_cpu_priority.isChecked()
        io_priority = self.cb_io_priority.isChecked()
        affinity_mask, core_count = self._get_affinity_mask()

        self.clean_worker = CleanWorker(dest, mo2_path, game_path, mods_path, overwrite_path, game_name, profile_name, self.messenger, cpu_priority, io_priority, affinity_mask)
        self.clean_worker.progress_signal.connect(self.log)
        self.clean_worker.bar_signal.connect(self.bar_clean.setValue)
        self.clean_worker.finished_signal.connect(self.on_clean_finished)
        self.clean_worker.start()

    def on_clean_finished(self, success, message):
        self.btn_build.setEnabled(True)
        self.btn_clear.setEnabled(True)
        if success:
            # Cleanup success! Remove from registry
            prof_name = self.profile_box.currentText()
            self._remove_from_registry(prof_name)
            
            QMessageBox.information(self, "Cleanup Success", message)
        else:
            QMessageBox.critical(self, "Cleanup Failed", message)
    
    def show_update_notification(self, version, url):
        self.update_banner.setText(f"🚀 <b>New Version Available: v{version}</b> - Click to visit Nexus")
        self.update_banner.show()
        self.update_url = url

    def open_update_url(self):
        import webbrowser
        webbrowser.open(self.update_url)

    def browse_dest(self):
        path = QFileDialog.getExistingDirectory(self, "Select Standalone Destination")
        if path:
            # selected_path already uses ensure_long_path
            selected_path = Path(ensure_long_path(path)).resolve()
            
            # Get forbidden paths and NORMALIZE them with ensure_long_path
            game_raw = self.organizer.managedGame().gameDirectory().absolutePath()
            game_path = Path(ensure_long_path(game_raw)).resolve()
            
            mo2_raw = self.organizer.basePath()
            mo2_path = Path(ensure_long_path(mo2_raw)).resolve()
            
            # Check if Steam folder (parent of game folder)
            steam_path = None
            if "steamapps" in str(game_path).lower():
                steam_path = game_path.parent.parent
            
            # Security validation
            forbidden_paths = [game_path, mo2_path]
            if steam_path:
                forbidden_paths.append(steam_path)
            
            # Check if selected path is forbidden or is a parent/child of forbidden paths
            for forbidden in forbidden_paths:
                # Both paths are now normalized with \\?\ if on Windows
                if selected_path == forbidden:
                    QMessageBox.critical(
                        self,
                        "Forbidden Location",
                        f"❌ Cannot use this location as standalone destination:\n\n"
                        f"Selected: {clean_path_for_display(selected_path)}\n\n"
                        f"This is a protected system folder. Please choose a different location."
                    )
                    return
                
                # Check if selected path is INSIDE a forbidden path
                try:
                    selected_path.relative_to(forbidden)
                    QMessageBox.critical(
                        self,
                        "Forbidden Location",
                        f"❌ Cannot create standalone inside a protected folder:\n\n"
                        f"Selected: {clean_path_for_display(selected_path)}\n"
                        f"Protected: {clean_path_for_display(forbidden)}\n\n"
                        f"Please choose a location outside of Steam, Game, or MO2 folders."
                    )
                    return
                except ValueError:
                    pass
                
                # Check if forbidden path is INSIDE selected path (Parent check)
                try:
                    forbidden.relative_to(selected_path)
                    QMessageBox.critical(
                        self,
                        "Forbidden Location",
                        f"❌ Cannot use a parent folder of protected locations:\n\n"
                        f"Selected: {clean_path_for_display(selected_path)}\n"
                        f"Contains: {clean_path_for_display(forbidden)}\n\n"
                        f"Please choose a different location."
                    )
                    return
                except ValueError:
                    pass
            
            # If we passed security checks, update UI
            self.dest_edit.setText(path)
            self.validate_drives()

    def log(self, text):
        self.log_area.append(text)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def start_build(self):
        dest = ensure_long_path(self.dest_edit.text())
        if not dest:
            QMessageBox.warning(self, "Missing Destination", "Please specify a destination folder.")
            return

        # Display clean path to user, but use long path internally
        display_path = clean_path_for_display(dest)
        if not QMessageBox.question(self, "Confirm Build", f"Start deployment to:\n{display_path}?\n\nTarget will be CLEANED.") == QMessageBox.StandardButton.Yes:
            return

        affinity_mask, core_count = self._get_affinity_mask()
        
        # If optimizer is off, mask is 0
        if not self.cb_affinity_optimizer.isChecked():
            affinity_mask = 0
            core_count = self.cpu_count

        # Safety Check: At least 2 cores if affinity is being set and optimizer enabled
        if self.cb_affinity_optimizer.isChecked() and core_count < 2:
            QMessageBox.warning(self, "Safety Warning", 
                                "You must select at least <b>2 CPU cores</b> for the affinity setting.\n\n"
                                "Selecting zero or only 1 core can cause the game to freeze or crash during startup.")
            return

        self.btn_build.setEnabled(False)
        self.btn_build.setText("BUILDING STANDALONE...")
        self.btn_clear.setEnabled(False)
        self.log_area.clear()
        
        # Reset bars
        self.bar_clean.setValue(0)
        self.bar_scan.setValue(0)
        self.bar_link.setValue(0)
        self.bar_verify.setValue(0)
        
        prof_path = self.lbl_prof_path.text().replace("<small>Path: ", "").replace("</small>", "")
        prof_name = self.profile_box.currentText()
        use_documents = False # Forced False for MO2 Sync Mode
        use_stealth = True   # Forced True for MO2 Sync Mode
        cpu_priority = self.cb_cpu_priority.isChecked()
        io_priority = self.cb_io_priority.isChecked()
        use_mmcss = self.cb_mmcss.isChecked()
        use_ram_trim = self.cb_ram_trim.isChecked()
        
        self.worker = BuildWorker(self.organizer, dest, self.cb_hardlinks.isChecked(), prof_path, prof_name, use_documents, self.messenger, 
                                  cpu_priority, io_priority, affinity_mask, use_mmcss, use_ram_trim, use_stealth)
        
        # Connect signals
        self.worker.progress_signal.connect(self.log)
        self.worker.clean_bar_signal.connect(self.bar_clean.setValue)
        self.worker.scan_bar_signal.connect(self.bar_scan.setValue)
        self.worker.link_bar_signal.connect(self.bar_link.setValue)
        self.worker.verify_bar_signal.connect(self.bar_verify.setValue)
        self.worker.finished_signal.connect(self.on_finished)
        
        self.worker.start()

    def _get_affinity_mask(self):
        """Generates a 64-bit mask based on checkbox states and returns the mask and count of selected cores."""
        mask = 0
        count = 0
        
        # We now return the mask based on checkbox states regardless of CPU Priority
        # The caller (start_build or reoptimize_wrappers) handles if the optimizer is disabled.
        for i, cb in enumerate(self.affinity_checkboxes):
            if cb.isChecked():
                mask |= (1 << i)
                count += 1
        return mask, count

    def on_finished(self, success, message):
        self.btn_build.setEnabled(True)
        self.btn_build.setText("BUILD STANDALONE")
        self.btn_clear.setEnabled(True)
        
        # Re-validate save buttons (NOT NEEDED in v3.1+)
        # self.validate_save_buttons()
        
        if success:
            # Success! Update the registry
            prof_name = self.profile_box.currentText()
            self._update_registry(prof_name, self.dest_edit.text())
            
            # Auto-refresh Tab 3 standalone list
            self.refresh_standalone_list()
            
            QMessageBox.information(self, "Build Success", message)
            report_path = Path(self.dest_edit.text()) / "standalone_metadata" / "build_report.html"
            if report_path.exists():
                if QMessageBox.question(self, "Open Report", "Build finished! Open the HTML report?") == QMessageBox.StandardButton.Yes:
                    import webbrowser
                    webbrowser.open(report_path.as_uri())
        else:
            QMessageBox.critical(self, "Build Failed", message)
