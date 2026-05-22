import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from .path_utils import ensure_long_path

logger = logging.getLogger(__name__)


class ProfileSync:
    def __init__(
        self,
        profile_dir,
        sa_path,
        docs_name="Skyrim Special Edition",
        appdata_name="Skyrim Special Edition",
        ini_prefix="Skyrim",
        game_name="Skyrim SE",
        profile_name="Default",
        portable_mode=True,
        use_documents_mode=False,
        stealth_mode=False,
        uses_plugins_txt=True,
        uses_bethesda_ini=True,
        callback=None,
        log_callback=None,
    ):
        self.profile_dir = Path(ensure_long_path(Path(profile_dir).resolve()))
        self.profile_name = profile_name
        self.sa_path = Path(ensure_long_path(Path(sa_path).resolve()))
        self.ini_prefix = ini_prefix
        self.portable_mode = portable_mode
        self.stealth_mode = stealth_mode
        self.use_documents_mode = use_documents_mode
        self.uses_plugins_txt = uses_plugins_txt
        self.uses_bethesda_ini = uses_bethesda_ini
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.callback = callback
        self.log_callback = log_callback

        if self.use_documents_mode:
            self.source_docs = Path(
                ensure_long_path(
                    Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")).resolve()
                )
            )
        else:
            self.source_docs = self.profile_dir

        self.source_appdata = self.profile_dir

        if self.stealth_mode:
            iso_profile = self.profile_dir / "standalone_profile"
            self.win_docs = iso_profile
            self.win_appdata = iso_profile / "AppData" / "Local" / appdata_name
            self.win_roaming = iso_profile / "AppData" / "Roaming" / appdata_name
        elif self.portable_mode:
            self.win_docs = self.sa_path / "_standalone" / "Documents" / "My Games" / docs_name
            self.win_appdata = self.sa_path / "_standalone" / "AppData" / "Local" / appdata_name
            self.win_roaming = self.sa_path / "_standalone" / "AppData" / "Roaming" / appdata_name
        else:
            self.win_docs = Path(
                ensure_long_path(
                    Path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")).resolve()
                )
            )
            self.win_appdata = (
                Path(ensure_long_path(Path(os.environ["LOCALAPPDATA"]).resolve())) / appdata_name
            )
            self.win_roaming = (
                Path(ensure_long_path(Path(os.environ["APPDATA"]).resolve())) / appdata_name
            )

        if self.stealth_mode or self.portable_mode:
            self.win_docs.mkdir(parents=True, exist_ok=True)
            self.win_appdata.mkdir(parents=True, exist_ok=True)
            self.win_roaming.mkdir(parents=True, exist_ok=True)

        self.backup_root = (
            Path(os.environ["LOCALAPPDATA"])
            / "MO2_Hardlink_Builder"
            / game_name
            / profile_name
            / "Backups"
        )

    def backup_shared_docs(self, target_dir):
        if not target_dir.exists():
            return None

        backup_path = self.backup_root / f"Shared_Docs_Backup_{self.run_timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        if self.log_callback:
            self.log_callback(f"[*] Creating safety backup: {backup_path.name}")

        for item in target_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, backup_path / item.name)
            elif item.is_dir() and item.name.lower() != "saves":
                try:
                    shutil.copytree(item, backup_path / item.name)
                except Exception:
                    pass

        save_dir = target_dir / "Saves"
        if save_dir.exists():
            backup_saves = backup_path / "Saves"
            backup_saves.mkdir(parents=True, exist_ok=True)
            for s in save_dir.iterdir():
                if s.is_file():
                    shutil.copy2(s, backup_saves / s.name)

        return backup_path

    def _safe_copy(self, src: Path, dst: Path) -> bool:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return True
        return False

    def _process_sync(self, src_dir: Path, dst_dir: Path, quarantine_base_name: str, action_label: str):
        """
        Syncs files from src_dir → dst_dir.

        Conflicting files are always moved to a timestamped quarantine folder.
        There is no overwrite option — this prevents any silent data loss.
        New (non-conflicting) files are copied normally.
        """
        if not src_dir.exists():
            return False

        all_files = [item for item in src_dir.iterdir() if item.is_file()]
        if not all_files:
            return False

        dst_dir.mkdir(parents=True, exist_ok=True)

        conflicts = []
        new_files = []

        for item in all_files:
            if (dst_dir / item.name).exists():
                conflicts.append(item)
            else:
                new_files.append(item)

        # Always quarantine conflicts rather than overwriting
        quarantine_dir = None
        if conflicts:
            quarantine_dir = dst_dir / f"{quarantine_base_name}_{self.run_timestamp}"
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            if self.log_callback:
                self.log_callback(
                    f"[*] Save Quarantine: {len(conflicts)} conflict(s) → {quarantine_dir.name}"
                )
            logger.info(
                "Save quarantine: %d file(s) quarantined to %s",
                len(conflicts), quarantine_dir.name,
            )

        # Process new files
        for i, item in enumerate(new_files):
            if self.log_callback and i % 5 == 0:
                self.log_callback(f"[*] Syncing: {item.name}")
            for retry in range(3):
                try:
                    shutil.copy2(item, dst_dir / item.name)
                    break
                except PermissionError:
                    if self.log_callback:
                        self.log_callback(f"[!] File locked, retrying ({retry+1}/3): {item.name}")
                    time.sleep(1)
                except Exception as e:
                    logger.error("Error copying %s: %s", item.name, e)
                    break

        # Process conflicts → quarantine
        for i, item in enumerate(conflicts):
            if self.log_callback and i % 5 == 0:
                self.log_callback(f"[*] Quarantine: {item.name}")
            for retry in range(3):
                try:
                    shutil.move(str(item), str(quarantine_dir / item.name))
                    break
                except PermissionError:
                    if self.log_callback:
                        self.log_callback(f"[!] File locked, retrying ({retry+1}/3): {item.name}")
                    time.sleep(1)
                except Exception as e:
                    try:
                        shutil.copy2(item, quarantine_dir / item.name)
                    except Exception:
                        pass
                    logger.error("Error quarantining %s: %s", item.name, e)
                    break

        synced_count = len(new_files)
        quarantined_count = len(conflicts)
        if self.log_callback:
            self.log_callback(
                f"[SUCCESS] Sync complete ({action_label}): "
                f"{synced_count} synced, {quarantined_count} quarantined."
            )
        logger.info(
            "Sync complete (%s): %d synced, %d quarantined.",
            action_label, synced_count, quarantined_count,
        )
        return True

    def sync_saves_to_mo2(self):
        win_saves = self.win_docs / "Saves"
        mo2_saves = self.profile_dir / "saves"
        return self._process_sync(win_saves, mo2_saves, "Standalone_Export_save", "Standalone → MO2")

    def push_saves_to_docs(self):
        if self.use_documents_mode:
            source_saves = self.source_docs / "Saves"
        else:
            source_saves = self.profile_dir / "saves"

        win_saves = self.win_docs / "Saves"
        action_label = "Documents → Standalone" if self.use_documents_mode else "MO2 → Standalone"
        return self._process_sync(source_saves, win_saves, "MO2_import_save", action_label)

    def deploy_mo2_profile(self):
        """Deploys INI files, plugins.txt and loadorder.txt to standalone paths."""
        logger.info("Deploying MO2 profile configuration to standalone...")

        # INI files — only for Bethesda-style games
        if self.uses_bethesda_ini:
            for ini in [f"{self.ini_prefix}.ini", f"{self.ini_prefix}Prefs.ini", f"{self.ini_prefix}Custom.ini"]:
                src = self.source_docs / ini
                if src.exists():
                    self._safe_copy(src, self.win_docs / ini)
                    logger.debug("Deployed: %s", ini)
        else:
            logger.debug("deploy_mo2_profile: INI patching skipped (uses_bethesda_ini=False).")

        # plugins.txt + loadorder.txt — only for games that use plugin load order
        if self.uses_plugins_txt:
            for fname in ["plugins.txt", "loadorder.txt"]:
                src = self.profile_dir / fname
                if src.exists():
                    self._safe_copy(src, self.win_appdata / fname)
                    logger.debug("Deployed: %s", fname)
        else:
            logger.debug("deploy_mo2_profile: plugins.txt injection skipped (uses_plugins_txt=False).")

        logger.info("Profile configuration deployed.")

    def clean_custom_save_path(self):
        """Ensures the CustomINI has sLocalSavePath=Saves\\. Skipped for non-Bethesda games."""
        if not self.uses_bethesda_ini:
            logger.debug("clean_custom_save_path: skipped (uses_bethesda_ini=False).")
            return

        custom_ini = self.win_docs / f"{self.ini_prefix}Custom.ini"

        lines = []
        if custom_ini.exists():
            try:
                with open(custom_ini, "r", encoding="utf-8-sig", errors="ignore") as f:
                    lines = f.readlines()
            except Exception as e:
                logger.error("Failed to read custom ini: %s", e)

        new_lines = []
        general_found = False
        save_path_written = False

        for line in lines:
            trimmed = line.strip()
            if trimmed.lower() == "[general]":
                general_found = True
                new_lines.append(line)
                if not save_path_written:
                    new_lines.append("sLocalSavePath=Saves\\\n")
                    save_path_written = True
                continue
            if trimmed.lower().startswith("slocalsavepath"):
                if save_path_written:
                    continue
                save_path_written = True
                continue
            new_lines.append(line)

        if not general_found:
            new_lines.insert(0, "[General]\n")
            new_lines.insert(1, "sLocalSavePath=Saves\\\n")
        elif not save_path_written:
            for i, line in enumerate(new_lines):
                if line.strip().lower() == "[general]":
                    new_lines.insert(i + 1, "sLocalSavePath=Saves\\\n")
                    break

        try:
            with open(custom_ini, "w", encoding="utf-8-sig") as f:
                f.writelines(new_lines)
            if self.log_callback:
                self.log_callback(f"[*] Relative save path secured: {custom_ini.name}")
            logger.info("Custom ini save path cleaned: %s", custom_ini)
        except Exception as e:
            logger.error("Failed to write custom ini: %s", e)
