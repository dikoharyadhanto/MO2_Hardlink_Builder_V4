import fnmatch
import json
import logging
import os
import shutil
import stat
from pathlib import Path

from .path_utils import ensure_long_path

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("hardlink_audit")

# Tool-written artifacts — never included in the harvest pass
HARVEST_EXCLUSIONS_EXACT = {
    "standalone_metadata",
    "_wrapper_state.json",
    "how to launch.txt",
    "steam_appid.txt",
    ".deployment_state",
    "wrapper_log.txt",
    "standalone_bridge",
    "standalone_generated_files",
}
HARVEST_EXCLUSIONS_PATTERNS = [
    "crash_log_*.txt",
    "_*_original.exe",
    "*.bat",
    "*_launcher_src.cs",
    "*.pdb",
]


class CleanerEngine:
    def __init__(self, sa_path, mo2_path, steam_path=None,
                 docs_name="Skyrim Special Edition", appdata_name="Skyrim Special Edition",
                 game_name="Skyrim SE", profile_name="Default",
                 portable_mode=True, mods_path=None, overwrite_path=None):
        self.sa_path = Path(ensure_long_path(Path(sa_path).resolve()))
        self.mo2_path = Path(ensure_long_path(Path(mo2_path).resolve()))
        self.steam_path = Path(ensure_long_path(Path(steam_path).resolve())) if steam_path else None
        self.mods_path = Path(ensure_long_path(Path(mods_path).resolve())) if mods_path else None
        self.overwrite_path = Path(ensure_long_path(Path(overwrite_path).resolve())) if overwrite_path else None
        self.portable_mode = portable_mode
        self.profile_name = profile_name

        self.backup_root = (
            Path(os.environ["LOCALAPPDATA"])
            / "MO2_Hardlink_Builder"
            / game_name
            / profile_name
            / "Backups"
        )
        if not self.portable_mode:
            self.backup_root.mkdir(parents=True, exist_ok=True)

        self.win_docs = Path(ensure_long_path(os.path.expanduser(f"~/Documents/My Games/{docs_name}")))
        self.win_appdata = Path(ensure_long_path(os.environ["LOCALAPPDATA"])) / appdata_name
        self.win_roaming = Path(ensure_long_path(os.environ["APPDATA"])) / appdata_name

    def is_inside(self, child, parent) -> bool:
        try:
            child_p = Path(child).resolve()
            parent_p = Path(parent).resolve()
            return parent_p in child_p.parents or child_p == parent_p
        except Exception:
            return False

    def check_safety(self) -> tuple:
        """Returns (bool, message). False = blocked."""
        if self.is_inside(self.sa_path, self.mo2_path):
            return False, "FORBIDDEN: Standalone folder cannot be INSIDE or IS the MO2 folder!"
        if self.is_inside(self.mo2_path, self.sa_path):
            return False, "FORBIDDEN: You cannot select a parent folder of MO2 as the destination!"

        if self.mods_path and self.is_inside(self.sa_path, self.mods_path):
            return False, "FORBIDDEN: Standalone folder cannot be INSIDE your MO2 Mods folder!"
        if self.overwrite_path and self.is_inside(self.sa_path, self.overwrite_path):
            return False, "FORBIDDEN: Standalone folder cannot be INSIDE your MO2 Overwrite folder!"

        if self.steam_path:
            if self.is_inside(self.sa_path, self.steam_path):
                return False, "FORBIDDEN: Standalone folder cannot be INSIDE your Original Game folder!"
            if self.is_inside(self.steam_path, self.sa_path):
                return False, "FORBIDDEN: You cannot select a parent of your Game installation as the destination!"

        standalone_markers = ["standalone_metadata"]
        is_standalone = any((self.sa_path / m).exists() for m in standalone_markers)

        if (self.sa_path / ".mo2_protected").exists():
            return False, "PROTECTED FOLDER: Unlink via the Updater tool before cleaning."

        if not is_standalone:
            steam_indicators = ["steam.exe", "Steam.dll", "steam_api64.dll"]
            if any((self.sa_path / s).exists() for s in steam_indicators):
                return False, "FORBIDDEN: This folder contains Steam system files. Cleaning blocked for safety."

        return True, "Safe"

    def clean_mo2_standalone_profile(self, progress_callback=None):
        mo2_standalone = self.mo2_path / "profiles" / self.profile_name / "standalone_profile"
        if mo2_standalone.exists() and mo2_standalone.is_dir():
            logger.info("Cleaning persistent standalone profile: %s", mo2_standalone)
            try:
                shutil.rmtree(mo2_standalone, onerror=self._handle_remove_readonly)
                if progress_callback:
                    progress_callback(100)
                return True, ""
            except Exception as e:
                logger.error("Could not remove standalone_profile: %s", e)
                return False, str(e)
        return True, ""

    def total_cleanup(self, progress_callback=None) -> dict:
        """
        Full cleanup of standalone directory.
        Returns {"status": "SKIPPED"|"FINISHED"|"PARTIAL_FAILURE", "errors": []}.
        Every deletion is logged; errors are never silently swallowed.
        """
        logger.info("Cleaning standalone directory: %s", self.sa_path)
        errors = []

        try:
            items = list(self.sa_path.iterdir())
        except Exception as e:
            logger.error("Could not list directory: %s", e)
            return {"status": "PARTIAL_FAILURE", "errors": [f"Root Directory: {e}"]}

        total = len(items)
        if total == 0:
            logger.info("Folder already empty — skipping cleanup.")
            self.clean_mo2_standalone_profile()
            if progress_callback:
                progress_callback(100)
            return {"status": "SKIPPED", "errors": []}

        for i, item in enumerate(items):
            try:
                if item.is_symlink() or os.path.islink(item) or self._is_junction(item):
                    item.unlink()
                    logger.debug("Removed junction/symlink: %s", item.name)
                elif item.is_dir():
                    shutil.rmtree(item, onerror=self._handle_remove_readonly)
                    logger.debug("Removed directory: %s", item.name)
                else:
                    try:
                        item.unlink()
                    except PermissionError:
                        os.chmod(item, stat.S_IWRITE)
                        item.unlink()
                    logger.debug("Removed file: %s", item.name)
            except Exception as e:
                err_msg = f"{item.name}: {e}"
                logger.error("Cleanup failed: %s", err_msg)
                errors.append(err_msg)

            if progress_callback:
                progress_callback(int(((i + 1) / total) * 85))

        # Remove hidden bridge folder if leftover
        bridge_folder = self.sa_path / "standalone_bridge"
        if bridge_folder.exists() and bridge_folder.is_dir():
            logger.info("Removing legacy bridge folder: %s", bridge_folder.name)
            try:
                shutil.rmtree(bridge_folder, onerror=self._handle_remove_readonly)
            except Exception as e:
                logger.error("Could not remove standalone_bridge: %s", e)
                errors.append(f"standalone_bridge: {e}")

        success, err = self.clean_mo2_standalone_profile()
        if not success:
            errors.append(f"MO2 persistent profile: {err}")

        if progress_callback:
            progress_callback(100)

        if errors:
            logger.warning("Cleanup finished with %d locked/inaccessible items.", len(errors))
            return {"status": "PARTIAL_FAILURE", "errors": errors}

        logger.info("Cleanup complete.")
        return {"status": "FINISHED", "errors": []}

    def harvest_generated_files(self, manifest_path) -> dict:
        """
        Identifies files in standalone that were generated DURING GAMEPLAY (not deployed by
        this tool) and copies them to <mods_path>/standalone_generated_files before cleanup.

        Primary gate — link count (st_nlink):
            Any file deployed by this builder (mod hardlink OR base game hardlink) has
            st_nlink > 1 on NTFS because both the source and the standalone share the same
            inode. Files generated during gameplay (FNIS output, JContainers, SKSE logs,
            Bodyslide meshes, NetScriptFramework crash logs) are freshly written by the
            game/SKSE and have st_nlink == 1 — they exist only in the standalone directory.
            This eliminates all false positives for vanilla Data/ assets without walking the
            game directory.

        Secondary gate — manifest path check:
            Cross-drive deployments fall back to shutil.copy2() (st_nlink == 1). The manifest
            path check prevents those from being incorrectly harvested.

        Edge cases:
        - mods_path absent → WARNING + return, no abort
        - manifest absent → link count gate still applies; no secondary gate
        - copy failure → WARNING per file, harvest continues
        - standalone_generated_files exists → merge, no wipe
        - empty harvest → return without creating mod folder
        - directories → skipped (files only)
        """
        if self.mods_path is None or not self.mods_path.exists():
            logger.warning(
                "harvest_generated_files: mods_path absent (%s) — skipping harvest.",
                self.mods_path,
            )
            return {"harvested": 0}

        # Build set of rel_path_lower strings from previous manifest (path-presence gate)
        manifest_paths = set()
        manifest_path_obj = Path(manifest_path)
        if manifest_path_obj.exists():
            try:
                with open(manifest_path_obj, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                mapping = raw.get("mapping", raw) if isinstance(raw, dict) else raw
                for rel_key in mapping.keys():
                    manifest_paths.add(rel_key.lower().replace("\\", "/"))
            except Exception as e:
                logger.warning("harvest_generated_files: failed to load manifest: %s", e)
        else:
            logger.info(
                "harvest_generated_files: manifest not found — link count gate only (no secondary gate)."
            )

        # Walk standalone and classify files
        harvest_list = []  # list of (full_path: Path, rel_path: Path)
        for root, dirs, files in os.walk(self.sa_path):
            root_path = Path(root)
            try:
                root_rel = root_path.relative_to(self.sa_path)
            except ValueError:
                continue

            if not root_rel.parts:
                # At standalone root: prune excluded top-level dirs before recursion
                dirs[:] = [d for d in dirs if d.lower() not in HARVEST_EXCLUSIONS_EXACT]
            elif root_rel.parts[0].lower() in HARVEST_EXCLUSIONS_EXACT:
                # Inside excluded dir — defensive guard (pruning above should prevent this)
                dirs.clear()
                continue

            for file_name in files:
                name_lower = file_name.lower()

                if name_lower in HARVEST_EXCLUSIONS_EXACT:
                    continue
                if any(fnmatch.fnmatch(name_lower, pat) for pat in HARVEST_EXCLUSIONS_PATTERNS):
                    continue

                full_path = root_path / file_name
                try:
                    rel_path = full_path.relative_to(self.sa_path)
                except ValueError:
                    continue

                # PRIMARY GATE: hardlinked files (mod or base game) have st_nlink > 1 on NTFS.
                # Gameplay-generated files are freshly written by the game → st_nlink == 1.
                try:
                    if full_path.stat().st_nlink > 1:
                        continue  # builder-deployed hardlink — never harvest
                except OSError:
                    pass  # stat failed — fall through to secondary check

                # SECONDARY GATE: cross-drive copies have st_nlink == 1 but are in manifest.
                rel_key = str(rel_path).lower().replace("\\", "/")
                if rel_key in manifest_paths:
                    continue  # builder-deployed via copy — skip

                harvest_list.append((full_path, rel_path))

        if not harvest_list:
            logger.info("harvest_generated_files: no generated files detected.")
            return {"harvested": 0}

        mod_root = self.mods_path / "standalone_generated_files"
        harvested = 0

        for full_path, rel_path in harvest_list:
            parts = rel_path.parts
            if parts and parts[0].lower() == "data":
                # Data/ subdir → strip "Data/" prefix (MO2 mod root convention)
                dest_rel = Path(*parts[1:]) if len(parts) > 1 else Path(full_path.name)
                dest = mod_root / dest_rel
            else:
                # Standalone root or non-Data subdir → under root/
                dest = mod_root / "root" / rel_path

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    str(ensure_long_path(full_path)),
                    str(ensure_long_path(dest)),
                )
                audit_logger.info(
                    "HARVEST | %s → %s", rel_path, dest.relative_to(self.mods_path)
                )
                harvested += 1
            except Exception as e:
                logger.warning(
                    "harvest_generated_files: copy failed for %s: %s", rel_path, e
                )

        logger.info(
            "Harvest complete: %d file(s) → standalone_generated_files.", harvested
        )
        return {"harvested": harvested}

    def _is_junction(self, path) -> bool:
        try:
            if os.name != "nt":
                return False
            return bool(os.path.islink(path) or (os.stat(path).st_file_attributes & 0x400))
        except Exception:
            return False

    def _handle_remove_readonly(self, func, path, excinfo):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            if os.path.isdir(path):
                try:
                    os.rmdir(path)
                except Exception:
                    raise e
            else:
                raise e
