import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .path_utils import ensure_long_path
from .state_manager import ConflictManager, ModlistSnapshot, hash_modlist

logger = logging.getLogger(__name__)

# Version written into every manifest. ARCH-03: mismatch on load forces fresh scan.
MANIFEST_VERSION = 3

# Subtree cache schema version stored in each mod's Layer A entry.
# Mismatch causes the mod to fall back to the full fingerprint path.
DIR_INDEX_VERSION = 1

# Default maximum directory depth to track in dir_index per mod.
# Acts as a cache policy default; deeper mutations are caught via dirty-parent propagation.
MAX_SUBTREE_DEPTH = 2


class ScannerEngine:
    def __init__(self, mods_dir, overwrite_dir, profile_dir, output_dir=None):
        self.mods_dir = Path(ensure_long_path(mods_dir))
        self.overwrite_dir = Path(ensure_long_path(overwrite_dir))
        self.profile_path = Path(ensure_long_path(profile_dir))
        self.modlist_txt = self.profile_path / "modlist.txt"

        if output_dir:
            self.metadata_dir = Path(output_dir)
        else:
            raise ValueError("output_dir must be provided to ScannerEngine")

        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.output_manifest = self.metadata_dir / "mapping_manifest.json"

        self.blacklist_files = [
            "meta.ini", "mo2_separator.txt", "thumbs.db", "desktop.ini",
            "readme.txt", "credits.txt", "changelog.txt", "license.txt",
            "readme.md", "credits.md", "changelog.md",
        ]
        self.blacklist_dirs = [
            ".hidden", "fomod", "readmes", "readme", "docs", "documents",
            "credits", "changelog", "licenses", "rootbuilder", "backup",
        ]
        self.blacklist_extensions = [".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"]
        self.critical_extensions = [
            ".esp", ".esm", ".esl", ".bsa", ".ba2", ".nif", ".dds",
            ".hkx", ".fuz", ".wav", ".swf", ".tri", ".seq",
        ]

        self.failed_mods: dict = {}
        self.conflict_manager = ConflictManager(self.metadata_dir)

    # ------------------------------------------------------------------
    # FIX-01: Load order from mobase API — no heuristic fallback allowed
    # ------------------------------------------------------------------
    def _get_active_mods(self, organizer=None):
        """
        Returns active mod names in priority order (low→high).

        If an organizer is supplied the mobase modList() API is used exclusively.
        If no organizer is supplied this raises RuntimeError("API Link Failure") —
        there is NO silent fallback to keyword guessing.
        """
        if organizer is None:
            # TOOL_FAULT: mobase IOrganizer not provided — cannot resolve load order via API
            raise RuntimeError(
                "API Link Failure: mobase organizer not provided to ScannerEngine. "
                "Cannot determine load order without the MO2 API."
            )

        try:
            mod_list = organizer.modList()
            profile = organizer.profile()
            active_mods = []

            # MO2 API uses allModsByProfilePriority to get priority ordered list
            if hasattr(mod_list, 'allModsByProfilePriority'):
                all_mods = mod_list.allModsByProfilePriority(profile)
            else:
                all_mods = mod_list.allMods()

            for name in all_mods:
                # state flag 0x02 = active
                if mod_list.state(name) & 0x02:
                    active_mods.append(name)
            logger.info("mobase API returned %d active mods.", len(active_mods))
            return active_mods
        except Exception as e:
            # TOOL_FAULT: mobase API call failed at runtime
            raise RuntimeError(f"API Link Failure: mobase modList() call failed — {e}") from e

    # TASK-A01: Directories excluded from ALL traversals (exact case-insensitive name match).
    # "backup_old" does NOT match "backup" — exact equality only.
    _EXCLUDED_DIRS = {"logs", "backup"}
    # TASK-A01: File extensions excluded from ALL traversals.
    _EXCLUDED_EXTENSIONS = {".log"}

    def _scan_folder(self, folder_path, mod_name, mapping_table):
        try:
            for root, dirs, files in os.walk(folder_path):
                # TASK-A01: Prune excluded dirs + existing blacklist in one pass.
                # Using exact name equality (lower()) — partial substrings like "backup_old" pass through.
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in self.blacklist_dirs
                    and d.lower() not in self._EXCLUDED_DIRS
                ]

                for file_name in files:
                    ext = Path(file_name).suffix.lower()

                    # TASK-A01: Skip .log files and existing blacklisted files/extensions
                    if (file_name.lower() in self.blacklist_files
                            or ext in self.blacklist_extensions
                            or ext in self._EXCLUDED_EXTENSIONS):
                        continue

                    try:
                        full_source = Path(root) / file_name
                        rel_path = full_source.relative_to(folder_path)
                        parts = rel_path.parts

                        if parts[0].lower() == "root":
                            target_path = Path(*parts[1:])
                            is_root = True
                        elif parts[0].lower() == "data":
                            target_path = rel_path
                            is_root = False
                        else:
                            target_path = Path("Data") / rel_path
                            is_root = False

                        target_key = str(target_path).lower().replace("\\", "/")

                        self.conflict_manager.register_file(str(target_path), mod_name)

                        try:
                            stat = full_source.stat()
                        except Exception:
                            stat = None

                        mapping_table[target_key] = {
                            "source": str(full_source),
                            "mod_origin": mod_name,
                            "is_root": is_root,
                            "size_bytes": stat.st_size if stat else 0,
                            "mtime": stat.st_mtime if stat else 0,
                            "preferred_path": str(target_path),
                        }
                    except (PermissionError, OSError) as e:
                        if mod_name not in self.failed_mods:
                            self.failed_mods[mod_name] = []
                        self.failed_mods[mod_name].append(f"File Access Error: {file_name} ({e})")
        except Exception as e:
            if mod_name not in self.failed_mods:
                self.failed_mods[mod_name] = []
            self.failed_mods[mod_name].append(f"Scan Error: {e}")

    def build_mapping(self, organizer=None, progress_callback=None):
        """
        Scans all active mods and writes mapping_manifest.json.
        organizer must be supplied — FIX-01 enforces API-based load order.
        """
        active_mods = self._get_active_mods(organizer)
        mapping_table: dict = {}
        folder_states: dict = {}

        logger.info("Scanning %d mods in profile: %s", len(active_mods), self.profile_path.name)
        total = len(active_mods)

        for i, mod_name in enumerate(active_mods):
            mod_folder = self.mods_dir / mod_name
            if mod_folder.exists():
                try:
                    folder_states[mod_name] = mod_folder.stat().st_mtime
                except Exception:
                    folder_states[mod_name] = 0

                self._scan_folder(mod_folder, mod_name, mapping_table)

            if progress_callback:
                progress_callback(int(((i + 1) / total) * 100))

        if self.overwrite_dir.exists():
            logger.info("Scanning Overwrite folder (Ghost Mods)...")
            self._scan_folder(self.overwrite_dir, "Overwrite", mapping_table)

        # ARCH-03: version field in manifest
        output_data = {
            "version": MANIFEST_VERSION,
            "mapping": mapping_table,
            "scan_failures": self.failed_mods,
            "folder_states": folder_states,
        }

        with open(self.output_manifest, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)

        self.conflict_manager.save()

        try:
            snapshot = ModlistSnapshot(self.profile_path)
            snapshot.save_snapshot(self.metadata_dir / "modlist_reference.txt")
        except Exception:
            pass

        logger.info("Manifest & Metadata saved to: %s", self.metadata_dir)

    # ------------------------------------------------------------------
    # FEAT-05: Scan base game files (executables, DLLs, root assets)
    # ------------------------------------------------------------------
    def scan_base_game(self, game_path):
        """
        Scans the base game directory for executables, DLLs, vanilla Data/ assets,
        and root-level files. Skips mods/ and _commonredist/ subdirectories.
        Returns a dict mapping rel_path -> {source, size_bytes, mtime}.
        """
        game_path = Path(ensure_long_path(game_path))
        if not game_path.exists():
            logger.warning("Base game path does not exist: %s", game_path)
            return {}

        # Base-game scan exclusions: static base dirs + TASK-A01 shared exclusion set
        excluded_dirs = {"mods", "_commonredist"} | self._EXCLUDED_DIRS
        base_mapping: dict = {}

        logger.info("Scanning base game directory: %s", game_path)

        try:
            for item in game_path.iterdir():
                lower_name = item.name.lower()

                if item.is_dir() and lower_name in excluded_dirs:
                    continue

                if item.is_file():
                    # TASK-A01: skip .log files at root level
                    if item.suffix.lower() in self._EXCLUDED_EXTENSIONS:
                        continue
                    try:
                        stat = item.stat()
                        base_mapping[item.name] = {
                            "source": str(item),
                            "size_bytes": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    except (PermissionError, OSError) as e:
                        logger.warning("Cannot stat base game file %s: %s", item.name, e)

                elif item.is_dir() and lower_name not in excluded_dirs:
                    # Recurse into subdirs (e.g. Data/, DotNetRuntime)
                    for sub_item in item.rglob("*"):
                        if not sub_item.is_file():
                            continue
                        # TASK-A01: prune any sub-path that passes through an excluded dir
                        if any(p.lower() in self._EXCLUDED_DIRS for p in sub_item.parts):
                            continue
                        # TASK-A01: skip .log files in subdirs
                        if sub_item.suffix.lower() in self._EXCLUDED_EXTENSIONS:
                            continue
                        if True:
                            try:
                                rel = sub_item.relative_to(game_path)
                                stat = sub_item.stat()
                                base_mapping[str(rel)] = {
                                    "source": str(sub_item),
                                    "size_bytes": stat.st_size,
                                    "mtime": stat.st_mtime,
                                }
                            except (PermissionError, OSError) as e:
                                logger.warning("Cannot stat base game file %s: %s", sub_item, e)
        except Exception as e:
            logger.error("Base game scan failed: %s", e)

        logger.info("Base game scan complete: %d files found.", len(base_mapping))
        return base_mapping

    # ==================================================================
    # v3.7 — Tri-Gate Dirty Detection + Layered Manifest Builder
    # ==================================================================

    def _gate2_compute_fingerprint(self, folder: Path) -> tuple:
        """
        Single-pass walk: counts deployable files AND computes a metadata fingerprint.
        Fingerprint = SHA-256 of sorted "path_key|mtime|size" lines.

        PERFORMANCE NOTE — ANT Safety Exception (CDC-IMPL-002-v0.7 DEC-003):
        This is a full metadata traversal — O(N) stat calls where N is the number
        of deployable files in the mod folder. This is a correctness-over-speed
        tradeoff. The prior _count_deployable_files() performed the same O(N)
        os.walk; this method replaces it without adding an extra filesystem pass.
        Gate 2 cost is O(mods × files) across the full modlist.

        Returns: (file_count: int, fingerprint_hex: str)
        """
        import hashlib
        entries = []
        try:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in self.blacklist_dirs
                    and d.lower() not in self._EXCLUDED_DIRS
                ]
                for fn in files:
                    ext = Path(fn).suffix.lower()
                    if (fn.lower() in self.blacklist_files
                            or ext in self.blacklist_extensions
                            or ext in self._EXCLUDED_EXTENSIONS):
                        continue
                    full = Path(root) / fn
                    try:
                        st = full.stat()
                        # Apply same path transformation as _gate3_scan_mod so that
                        # the fingerprint format matches what is stored in Layer A.
                        rel_path = full.relative_to(folder)
                        parts = rel_path.parts
                        if parts[0].lower() == "root":
                            target_path = Path(*parts[1:])
                        elif parts[0].lower() == "data":
                            target_path = rel_path
                        else:
                            target_path = Path("Data") / rel_path
                        target_key = str(target_path).lower().replace("\\", "/")
                        entries.append(f"{target_key}|{st.st_mtime:.3f}|{st.st_size}")
                    except OSError:
                        entries.append(f"ERR|ERR|ERR")
        except Exception:
            pass
        entries.sort()
        fingerprint = hashlib.sha256("\n".join(entries).encode()).hexdigest()
        return len(entries), fingerprint

    def _gate2_mod_dirty(
        self,
        mod_name: str,
        mod_folder: Path,
        layer_a_entry: dict,
        precomputed_subtrees: "set | None" = None,
    ) -> bool:
        """
        Gate 2: Mod Dirty Flag check.
        Returns True if the mod has changed since it was last scanned, False if clean.

        Check order:
          1. mod root directory mtime (fast, always checked first)
          2. meta.ini mtime (fast)
          3a. Subtree dirty detection via dir_index (O(tracked_dirs) stat calls)
              — used when a valid dir_index is present in the Layer A entry.
          3b. Full metadata fingerprint fallback (O(N) traversal)
              — used when dir_index is absent, wrong version, or returns ambiguous state.
        """
        try:
            # Signal 1: root directory mtime
            root_stat = mod_folder.stat()
            if abs(root_stat.st_mtime - layer_a_entry.get("root_mtime", 0)) > 0.01:
                logger.debug("Gate2 DIRTY (root_mtime): %s", mod_name)
                return True

            # Signal 2: meta.ini mtime
            meta_ini = mod_folder / "meta.ini"
            cur_meta_mtime = meta_ini.stat().st_mtime if meta_ini.exists() else 0.0
            if abs(cur_meta_mtime - layer_a_entry.get("meta_mtime", 0)) > 0.01:
                logger.debug("Gate2 DIRTY (meta_mtime): %s", mod_name)
                return True

            # Signal 3: subtree dirty detection (preferred path)
            dir_index = layer_a_entry.get("dir_index")
            if dir_index is not None and layer_a_entry.get("dir_index_version") == DIR_INDEX_VERSION:
                # Reuse subtrees precomputed in build_layered_manifest when available
                # to avoid a second round of directory stat calls for the same mod.
                dirty_subtrees = (
                    precomputed_subtrees
                    if precomputed_subtrees is not None
                    else self._compute_dirty_subtrees(mod_folder, dir_index)
                )
                if dirty_subtrees:
                    logger.debug("Gate2 DIRTY (subtree %s): %s", sorted(dirty_subtrees)[:3], mod_name)
                    return True
                logger.debug("Gate2 CLEAN (subtree cache): %s", mod_name)
                return False

            # Signal 3 fallback: full metadata fingerprint (no valid dir_index)
            cur_file_count, cur_fingerprint = self._gate2_compute_fingerprint(mod_folder)

            if cur_file_count != layer_a_entry.get("file_count", -1):
                logger.debug(
                    "Gate2 DIRTY (file_count %d vs %d): %s",
                    cur_file_count, layer_a_entry.get("file_count", -1), mod_name,
                )
                return True

            if cur_fingerprint != layer_a_entry.get("file_fingerprint", ""):
                logger.debug("Gate2 DIRTY (file_fingerprint): %s", mod_name)
                return True

        except Exception as e:
            logger.warning("Gate2 error for %s: %s — marking dirty.", mod_name, e)
            return True

        return False

    def _build_dir_index(self, mod_folder: Path, files_map: dict) -> dict:
        """
        Builds a dir_index from an already-scanned files_map.
        Tracks ALL ancestor directories using the physical source path of each file
        relative to mod_folder. This correctly handles Root/, Data/, and other source
        layouts because it follows where files actually live on disk, not their virtual
        target keys.
        Each entry: {mtime: float, file_count: int}

        Keys are lowercase forward-slash relative paths from mod_folder.
        The empty string "" represents the mod root itself.
        MAX_SUBTREE_DEPTH controls partial-rescan scope, not index coverage.
        """
        tracked_dirs: set[str] = {""}
        source_rel_paths: list[str] = []

        for entry in files_map.values():
            raw_source = entry.get("source", "")
            if not raw_source:
                continue
            try:
                rel = Path(raw_source).relative_to(mod_folder)
            except ValueError:
                continue
            rel_lower = str(rel).lower().replace("\\", "/")
            source_rel_paths.append(rel_lower)
            parts = rel_lower.split("/")
            for depth in range(1, len(parts)):
                tracked_dirs.add("/".join(parts[:depth]))

        dir_index: dict = {}
        for rel_dir in tracked_dirs:
            abs_dir = mod_folder / Path(*rel_dir.split("/")) if rel_dir else mod_folder
            try:
                mtime = abs_dir.stat().st_mtime
            except OSError:
                continue
            if rel_dir:
                prefix = rel_dir + "/"
                count = sum(1 for r in source_rel_paths if r.startswith(prefix))
            else:
                count = len(source_rel_paths)
            dir_index[rel_dir] = {"mtime": mtime, "file_count": count}

        return dir_index

    def _compute_dirty_subtrees(
        self,
        mod_folder: Path,
        dir_index: dict,
    ) -> set:
        """
        Compares the stored dir_index against current filesystem state.
        Returns the set of dirty subtree keys (relative dir paths).

        Dirty rules:
        - Directory mtime changed → that subtree is dirty.
        - Directory no longer exists → that subtree and its nearest tracked parent are dirty.
        - Any dirty subtree also propagates to its parent if the parent is tracked.
        Empty set means all tracked subtrees are clean.
        """
        dirty: set[str] = set()

        def _mark_with_parent(rel_dir: str) -> None:
            dirty.add(rel_dir)
            # Propagate dirty upward to nearest tracked parent
            if rel_dir:
                parent_parts = rel_dir.rsplit("/", 1)
                parent = parent_parts[0] if len(parent_parts) > 1 else ""
                if parent in dir_index:
                    dirty.add(parent)

        for rel_dir, entry in dir_index.items():
            if not isinstance(entry, dict):
                # Corrupt or unexpected entry type — treat as dirty rather than crash
                _mark_with_parent(rel_dir)
                continue
            abs_dir = mod_folder / Path(*rel_dir.split("/")) if rel_dir else mod_folder
            try:
                current_mtime = abs_dir.stat().st_mtime
            except OSError:
                # Directory removed or inaccessible → dirty
                _mark_with_parent(rel_dir)
                continue

            stored_mtime = entry.get("mtime", 0.0)
            if abs(current_mtime - stored_mtime) > 0.01:
                _mark_with_parent(rel_dir)

        return dirty

    def _gate3_scan_mod_partial(
        self,
        mod_name: str,
        mod_folder: Path,
        prev_entry: dict,
        dirty_subtrees: set,
    ) -> dict:
        """
        Partial Gate 3 scan: re-scans only dirty subtrees and reuses clean file entries
        from prev_entry. Returns a complete updated Layer A entry with a fresh dir_index.

        If the root ("") is dirty the entire mod must be rescanned — delegates to
        _gate3_scan_mod() for a full scan.
        """
        if "" in dirty_subtrees:
            return self._gate3_scan_mod(mod_name, mod_folder)

        # Start from prior file entries; remove then re-add files under dirty subtrees
        files_map: dict = dict(prev_entry.get("files", {}))

        # Precompute mod_folder as a lowercase/forward-slash string for source comparison
        mod_folder_lower = str(mod_folder).lower().replace("\\", "/").rstrip("/") + "/"

        for dirty_rel in dirty_subtrees:
            # Build the canonical lowercase source prefix for this dirty subtree so that
            # stale file entries can be matched by physical source path regardless of
            # whether their virtual target key contains the layout prefix (Root/, Data/, etc.)
            dirty_src_prefix = mod_folder_lower + dirty_rel + "/"

            # Remove stale entries whose physical source is under the dirty directory
            for k in list(files_map):
                src = str(files_map[k].get("source", "")).lower().replace("\\", "/")
                if src.startswith(dirty_src_prefix):
                    del files_map[k]

            # Rescan the actual directory; resolve to real filesystem case so that
            # source paths produced by os.walk match those from a full _gate3_scan_mod
            # (Windows NTFS preserves case; os.walk inherits the case of the path passed in)
            dirty_abs = mod_folder / Path(*dirty_rel.split("/"))
            if not dirty_abs.exists():
                continue
            try:
                dirty_abs = dirty_abs.resolve()
            except Exception:
                pass
            for root, dirs, files_list in os.walk(dirty_abs):
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in self.blacklist_dirs
                    and d.lower() not in self._EXCLUDED_DIRS
                ]
                for file_name in files_list:
                    ext = Path(file_name).suffix.lower()
                    if (file_name.lower() in self.blacklist_files
                            or ext in self.blacklist_extensions
                            or ext in self._EXCLUDED_EXTENSIONS):
                        continue
                    try:
                        full_source = Path(root) / file_name
                        rel_path = full_source.relative_to(mod_folder)
                        parts = rel_path.parts
                        if parts[0].lower() == "root":
                            target_path = Path(*parts[1:])
                            is_root = True
                        elif parts[0].lower() == "data":
                            target_path = rel_path
                            is_root = False
                        else:
                            target_path = Path("Data") / rel_path
                            is_root = False
                        target_key = str(target_path).lower().replace("\\", "/")
                        try:
                            stat = full_source.stat()
                            size_b = stat.st_size
                            mtime = stat.st_mtime
                        except Exception:
                            size_b = 0
                            mtime = 0.0
                        files_map[target_key] = {
                            "size_bytes": size_b,
                            "mtime": mtime,
                            "source": str(full_source),
                            "preferred_path": str(target_path),
                            "is_root": is_root,
                        }
                    except (PermissionError, OSError) as e:
                        logger.warning("Partial Gate3 scan error for %s in %s: %s", file_name, mod_name, e)

        # Recompute root and meta mtimes from filesystem
        root_mtime = 0.0
        meta_mtime = 0.0
        try:
            root_mtime = mod_folder.stat().st_mtime
        except Exception:
            pass
        meta_ini = mod_folder / "meta.ini"
        if meta_ini.exists():
            try:
                meta_mtime = meta_ini.stat().st_mtime
            except Exception:
                pass

        # Recompute fingerprint for the full updated files_map
        import hashlib as _hashlib
        _fp_entries = sorted(
            f"{k}|{v.get('mtime', 0):.3f}|{v.get('size_bytes', 0)}"
            for k, v in files_map.items()
        )
        file_fingerprint = _hashlib.sha256("\n".join(_fp_entries).encode()).hexdigest()

        # Rebuild dir_index over the merged files_map
        new_dir_index = self._build_dir_index(mod_folder, files_map)

        return {
            "files": files_map,
            "root_mtime": root_mtime,
            "meta_mtime": meta_mtime,
            "file_count": len(files_map),
            "file_fingerprint": file_fingerprint,
            "dir_index": new_dir_index,
            "dir_index_version": DIR_INDEX_VERSION,
        }

    def _gate3_scan_mod(
        self,
        mod_name: str,
        mod_folder: Path,
    ) -> dict:
        """
        Gate 3: Selective Stat.
        Performs a full os.scandir traversal scoped exclusively to mod_folder.
        Returns a Layer A entry dict:
          {
            'files':      {rel_key: {size_bytes, mtime, source, preferred_path, is_root}},
            'root_mtime': float,
            'meta_mtime': float,
            'file_count': int,
          }
        """
        files_map: dict = {}
        root_mtime = 0.0
        meta_mtime = 0.0

        try:
            root_stat = mod_folder.stat()
            root_mtime = root_stat.st_mtime
        except Exception:
            pass

        meta_ini = mod_folder / "meta.ini"
        if meta_ini.exists():
            try:
                meta_mtime = meta_ini.stat().st_mtime
            except Exception:
                pass

        for root, dirs, files_list in os.walk(mod_folder):
            dirs[:] = [
                d for d in dirs
                if d.lower() not in self.blacklist_dirs
                and d.lower() not in self._EXCLUDED_DIRS
            ]
            for file_name in files_list:
                ext = Path(file_name).suffix.lower()
                if (file_name.lower() in self.blacklist_files
                        or ext in self.blacklist_extensions
                        or ext in self._EXCLUDED_EXTENSIONS):
                    continue
                try:
                    full_source = Path(root) / file_name
                    rel_path = full_source.relative_to(mod_folder)
                    parts = rel_path.parts

                    if parts[0].lower() == "root":
                        target_path = Path(*parts[1:])
                        is_root = True
                    elif parts[0].lower() == "data":
                        target_path = rel_path
                        is_root = False
                    else:
                        target_path = Path("Data") / rel_path
                        is_root = False

                    target_key = str(target_path).lower().replace("\\", "/")

                    try:
                        stat = full_source.stat()
                        size_b = stat.st_size
                        mtime  = stat.st_mtime
                    except Exception:
                        size_b = 0
                        mtime  = 0.0

                    files_map[target_key] = {
                        "size_bytes":     size_b,
                        "mtime":          mtime,
                        "source":         str(full_source),
                        "preferred_path": str(target_path),
                        "is_root":        is_root,
                    }
                except (PermissionError, OSError) as e:
                    logger.warning(
                        "Gate3 scan error for %s in %s: %s", file_name, mod_name, e
                    )

        # Compute file_fingerprint from scanned data so Gate 2 can compare on next run.
        # Uses the same format as _gate2_compute_fingerprint for consistency.
        import hashlib as _hashlib
        _fp_entries = sorted(
            f"{k}|{v.get('mtime', 0):.3f}|{v.get('size_bytes', 0)}"
            for k, v in files_map.items()
        )
        file_fingerprint = _hashlib.sha256("\n".join(_fp_entries).encode()).hexdigest()

        # Build subtree cache for use by subsequent Gate 2 dirty-detection checks.
        dir_index = self._build_dir_index(mod_folder, files_map)

        return {
            "files":              files_map,
            "root_mtime":         root_mtime,
            "meta_mtime":         meta_mtime,
            "file_count":         len(files_map),
            "file_fingerprint":   file_fingerprint,
            "dir_index":          dir_index,
            "dir_index_version":  DIR_INDEX_VERSION,
        }

    def build_layered_manifest(
        self,
        organizer=None,
        prev_manifest=None,
        progress_callback=None,
        max_workers: int = 4,
    ):
        """
        v3.7 Main entry point: Event-Driven Incremental build using tri-gate detection.

        Returns a LayeredManifest fully populated in RAM (Layer A + B).
        Does NOT write to disk — caller is responsible for calling manifest.save().

        Args:
            organizer:         MO2 IOrganizer (required for load order).
            prev_manifest:     LayeredManifest from the previous build (or None for fresh).
                               If None — full scan of all mods.
            progress_callback: Optional callable(pct: int).
            max_workers:       Threads for Gate 3 parallel scanning.

        Raises:
            RuntimeError: If the load order cannot be determined (FIX-01).
        """
        from ..state import LayeredManifest

        t_total_start = time.perf_counter()

        active_mods = self._get_active_mods(organizer)   # FIX-01: API-only
        total = len(active_mods)
        load_order = active_mods  # low→high priority order

        # ---- Gate 1: Topology gate — modlist.txt hash ----
        t_gate1_start = time.perf_counter()
        current_modlist_hash = hash_modlist(self.modlist_txt)
        prev_modlist_hash = ""
        if prev_manifest is not None:
            prev_modlist_hash = prev_manifest.mod_index.get(
                "__meta__", {}
            ).get("modlist_hash", "")

        load_order_changed = (current_modlist_hash != prev_modlist_hash)
        t_gate1_end = time.perf_counter()
        if load_order_changed:
            logger.info(
                "Gate1 HIT: modlist.txt hash changed — full Layer B recompute queued after scan. "
                "[%.3fs]", t_gate1_end - t_gate1_start,
            )
        else:
            logger.info("Gate1 PASS: modlist.txt unchanged. [%.3fs]", t_gate1_end - t_gate1_start)

        # ---- Build new Layer A (mod_index) ----
        new_manifest = LayeredManifest()

        # Preserve meta hash in a pseudo-entry so we can compare on next run
        new_manifest.mod_index["__meta__"] = {
            "modlist_hash": current_modlist_hash,
            "files": {},
            "root_mtime": 0.0,
            "meta_mtime": 0.0,
            "file_count": 0,
        }

        # dirty_mods entries: (mod_name, mod_folder, dirty_subtrees | None)
        # dirty_subtrees=None → full Gate 3 scan required (fresh build or no dir_index)
        # dirty_subtrees=set  → partial Gate 3 scan possible if root ("") not in set
        dirty_mods: list = []
        clean_mods: list = []

        t_gate2_start = time.perf_counter()
        for i, mod_name in enumerate(active_mods):
            mod_folder = self.mods_dir / mod_name
            if not mod_folder.exists():
                continue

            if prev_manifest is None:
                # Fresh build — all mods are dirty by definition; no dir_index yet
                dirty_mods.append((mod_name, mod_folder, None))
            else:
                prev_entry = prev_manifest.mod_index.get(mod_name)
                if prev_entry is None:
                    dirty_mods.append((mod_name, mod_folder, None))
                else:
                    # Compute dirty subtrees before calling _gate2_mod_dirty so that we can
                    # route partial Gate 3 scans without a second round of stat calls.
                    dir_index = prev_entry.get("dir_index")
                    subtrees: set | None = None
                    if (dir_index is not None
                            and prev_entry.get("dir_index_version") == DIR_INDEX_VERSION):
                        subtrees = self._compute_dirty_subtrees(mod_folder, dir_index)
                    if self._gate2_mod_dirty(
                        mod_name, mod_folder, prev_entry,
                        precomputed_subtrees=subtrees,
                    ):
                        dirty_mods.append((mod_name, mod_folder, subtrees))
                    else:
                        clean_mods.append(mod_name)
                        new_manifest.mod_index[mod_name] = prev_entry

            if progress_callback:
                progress_callback(int(((i + 1) / total) * 30))  # 0–30% = gate scan

        t_gate2_end = time.perf_counter()
        logger.info(
            "Gate2 complete: %d dirty / %d clean. [%.3fs]",
            len(dirty_mods), len(clean_mods), t_gate2_end - t_gate2_start,
        )

        # ---- Gate 3: Parallel selective stat for dirty mods ----
        t_gate3_start = time.perf_counter()
        gate3_total = len(dirty_mods)
        completed   = 0

        def _scan_and_store(item):
            mod_name, mod_folder, dirty_subtrees = item
            if (dirty_subtrees is not None
                    and "" not in dirty_subtrees
                    and prev_manifest is not None):
                prev_e = prev_manifest.mod_index.get(mod_name)
                if prev_e is not None:
                    return mod_name, self._gate3_scan_mod_partial(
                        mod_name, mod_folder, prev_e, dirty_subtrees
                    )
            return mod_name, self._gate3_scan_mod(mod_name, mod_folder)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_scan_and_store, item): item for item in dirty_mods}
            for future in as_completed(futures):
                try:
                    mod_name, entry = future.result()
                    new_manifest.mod_index[mod_name] = entry
                    # Also register with conflict manager for legacy compatibility
                    for path_key in entry["files"]:
                        self.conflict_manager.register_file(path_key, mod_name)
                except Exception as e:
                    item = futures[future]
                    logger.error("Gate3 scan failed for %s: %s", item[0], e)

                completed += 1
                if progress_callback:
                    pct = 30 + int((completed / max(gate3_total, 1)) * 50)  # 30–80%
                    progress_callback(pct)

        t_gate3_end = time.perf_counter()
        logger.info(
            "Gate3 complete: %d mods scanned. [%.3fs]",
            gate3_total, t_gate3_end - t_gate3_start,
        )

        # Scan Overwrite folder (always treated as dirty — Ghost Mods may change any time)
        if self.overwrite_dir.exists():
            logger.info("Scanning Overwrite folder (Ghost Mods)...")
            ow_entry = self._gate3_scan_mod("Overwrite", self.overwrite_dir)
            new_manifest.mod_index["Overwrite"] = ow_entry
            for path_key in ow_entry["files"]:
                self.conflict_manager.register_file(path_key, "Overwrite")

        # ---- Rebuild / recompute Layer B ----
        t_layer_b_start = time.perf_counter()
        if load_order_changed or prev_manifest is None:
            # Full RAM recompute of Layer B — no filesystem touch
            new_manifest.full_recompute_layer_b(load_order)
        else:
            # Incremental Layer B: carry over unchanged paths, update dirty ones
            # Start from previous Layer B and apply only the changes from dirty mods.
            new_manifest.path_owners = dict(prev_manifest.path_owners)

            # Remove all entries that belonged to now-dirty mods
            dirty_mod_names = {m for m, _mf, _ds in dirty_mods}
            paths_to_rebuild = set()
            for path_key, owners in list(new_manifest.path_owners.items()):
                if any(o in dirty_mod_names for o in owners):
                    paths_to_rebuild.add(path_key)

            # Re-insert files from dirty mods into the correct stack positions
            priority = {mod: idx for idx, mod in enumerate(load_order)}
            for path_key in paths_to_rebuild:
                # Collect all current providers from full new mod_index
                providers = [
                    mod for mod, entry in new_manifest.mod_index.items()
                    if mod != "__meta__" and path_key in entry.get("files", {})
                ]
                sorted_owners = sorted(
                    providers,
                    key=lambda m: priority.get(m, -1),
                    reverse=True,
                )
                if sorted_owners:
                    new_manifest.path_owners[path_key] = sorted_owners
                else:
                    new_manifest.path_owners.pop(path_key, None)

            # Remove paths that are no longer provided by anyone
            for mod_name, _mf, _ds in dirty_mods:
                # If a dirty mod was re-scanned and no longer provides a path,
                # clean up orphaned entries in path_owners
                new_files = set(new_manifest.mod_index.get(mod_name, {}).get("files", {}).keys())
                old_files = set(prev_manifest.mod_index.get(mod_name, {}).get("files", {}).keys())
                removed_paths = old_files - new_files
                for path_key in removed_paths:
                    stack = new_manifest.path_owners.get(path_key, [])
                    if mod_name in stack:
                        stack.remove(mod_name)
                    if not stack:
                        new_manifest.path_owners.pop(path_key, None)

            # TASK-A01: Second pass — insert new virtual paths introduced by dirty mods
            # that were absent from prev Layer B (V07-FIND-001 fix).
            new_paths_added = 0
            for mod_name_d, _mf, _ds in dirty_mods:
                dirty_entry = new_manifest.mod_index.get(mod_name_d, {})
                for path_key in dirty_entry.get("files", {}):
                    if path_key not in new_manifest.path_owners:
                        # Collect all current providers for this new path
                        providers = [
                            m for m, e in new_manifest.mod_index.items()
                            if m != "__meta__" and path_key in e.get("files", {})
                        ]
                        sorted_owners = sorted(
                            providers,
                            key=lambda m: priority.get(m, -1),
                            reverse=True,
                        )
                        if sorted_owners:
                            new_manifest.path_owners[path_key] = sorted_owners
                            new_paths_added += 1

            if new_paths_added:
                logger.info(
                    "TASK-A01: %d new virtual path(s) inserted from dirty mods into Layer B.",
                    new_paths_added,
                )

            new_manifest._rebuild_active_map()
            logger.info(
                "Incremental Layer B update complete: %d paths rebuilt, %d paths carried over.",
                len(paths_to_rebuild),
                len(new_manifest.path_owners) - len(paths_to_rebuild),
            )

        t_layer_b_end = time.perf_counter()
        logger.info("Layer B rebuild complete. [%.3fs]", t_layer_b_end - t_layer_b_start)

        if progress_callback:
            progress_callback(95)

        t_save_start = time.perf_counter()
        self.conflict_manager.save()
        t_save_end = time.perf_counter()
        logger.info("Manifest save complete. [%.3fs]", t_save_end - t_save_start)

        # Persist modlist snapshot for reference (non-critical)
        try:
            snapshot = ModlistSnapshot(self.profile_path)
            snapshot.save_snapshot(self.metadata_dir / "modlist_reference.txt")
        except Exception:
            pass

        if progress_callback:
            progress_callback(100)

        t_total_end = time.perf_counter()
        logger.info(
            "build_layered_manifest complete: %d mods, %d virtual paths. "
            "Total [%.3fs] | Gate1 [%.3fs] | Gate2 [%.3fs] | Gate3 [%.3fs] | LayerB [%.3fs] | Save [%.3fs]",
            len(new_manifest.mod_index) - 1,  # subtract __meta__
            len(new_manifest.path_owners),
            t_total_end - t_total_start,
            t_gate1_end - t_gate1_start,
            t_gate2_end - t_gate2_start,
            t_gate3_end - t_gate3_start,
            t_layer_b_end - t_layer_b_start,
            t_save_end - t_save_start,
        )
        return new_manifest
