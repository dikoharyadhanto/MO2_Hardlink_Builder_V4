import hashlib
import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Version written into every new conflict cache. A mismatch on load forces a full rebuild.
CACHE_VERSION = 2


class ModlistSnapshot:
    """Reads, saves, and diffs modlist.txt."""

    def __init__(self, profile_path=None, custom_file_path=None):
        if custom_file_path:
            self.modlist_path = Path(custom_file_path)
            self.profile_path = self.modlist_path.parent
        elif profile_path:
            self.profile_path = Path(profile_path)
            self.modlist_path = self.profile_path / "modlist.txt"
        else:
            raise ValueError("Must provide either profile_path or custom_file_path")

    def get_active_mods(self):
        """Returns active mod names in load order (bottom of list = highest priority)."""
        if not self.modlist_path.exists():
            return []

        active_mods = []
        try:
            with open(self.modlist_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()

            processed_lines = [line.strip() for line in lines if line.strip()]

            for line in reversed(processed_lines):
                if line.startswith("+"):
                    active_mods.append(line[1:])

        except Exception as e:
            logger.error("Error reading modlist: %s", e)

        return active_mods

    def save_snapshot(self, output_path):
        """Saves a raw copy of modlist.txt."""
        if self.modlist_path.exists():
            try:
                shutil.copy2(self.modlist_path, output_path)
            except Exception as e:
                logger.warning("Failed to save modlist snapshot: %s", e)

    @staticmethod
    def diff(old_list, new_list):
        old_set = set(old_list)
        new_set = set(new_list)

        added = new_set - old_set
        removed = old_set - new_set
        unchanged = old_set & new_set

        old_common = [m for m in old_list if m in unchanged]
        new_common = [m for m in new_list if m in unchanged]

        return {
            "added": list(added),
            "removed": list(removed),
            "reordered": old_common != new_common,
            "unchanged": list(unchanged),
            "new_order": new_list,
        }


class ConflictManager:
    """
    Manages conflict_cache.json.
    Maps: file_path -> list of mod names that provide that file.
    Validates the cache version on load and rebuilds if corrupt or outdated.
    """

    def __init__(self, metadata_path):
        self.cache_file = Path(metadata_path) / "conflict_cache.json"
        self.mapping: dict = {}

    def load(self):
        if not self.cache_file.exists():
            return

        raw = None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning("Conflict cache corrupt (%s) — rebuilding from scratch.", e)
            self.mapping = {}
            return

        if not isinstance(raw, dict):
            logger.warning("Conflict cache has unexpected format — rebuilding.")
            self.mapping = {}
            return

        stored_version = raw.get("version")
        if stored_version != CACHE_VERSION:
            logger.warning(
                "Conflict cache version mismatch (stored=%s, expected=%s) — rebuilding.",
                stored_version,
                CACHE_VERSION,
            )
            self.mapping = {}
            return

        self.mapping = raw.get("data", {})
        logger.debug("Conflict cache loaded: %d entries.", len(self.mapping))

    def save(self):
        try:
            payload = {"version": CACHE_VERSION, "data": self.mapping}
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error("Failed to save conflict cache: %s", e)

    def register_file(self, rel_path: str, mod_name: str):
        key = rel_path.lower().replace("\\", "/")
        if key not in self.mapping:
            self.mapping[key] = []
        if mod_name not in self.mapping[key]:
            self.mapping[key].append(mod_name)

    def remove_mod(self, mod_name: str):
        empty_keys = [k for k, mods in self.mapping.items() if mod_name in mods]
        for k in empty_keys:
            self.mapping[k].remove(mod_name)
            if not self.mapping[k]:
                del self.mapping[k]

    def get_winner_fast(self, rel_path: str, mod_indices: dict):
        key = rel_path.lower().replace("\\", "/")
        providers = self.mapping.get(key, [])
        if not providers:
            return None

        best_mod = None
        best_prio = -1
        for mod in providers:
            prio = mod_indices.get(mod, -1)
            if prio > best_prio:
                best_prio = prio
                best_mod = mod
        return best_mod


def hash_modlist(modlist_path) -> str:
    """
    Returns the SHA-256 hex digest of modlist.txt, or empty string on error.
    Used by Gate 1 (Topology Gate) to detect load-order changes without
    a line-by-line parse.
    """
    h = hashlib.sha256()
    try:
        with open(modlist_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.warning("hash_modlist: could not hash %s: %s", modlist_path, e)
        return ""


class OwnerStackManager:
    """
    Manages Layer B (path_owners) mutations on a LayeredManifest in RAM.

    Requires a valid load_order_dict at construction time. Every priority lookup
    uses this dict — no defaults or fallbacks are permitted.

    Contract:
      load_order_dict: {mod_name: int}
        Maps every mod name to its load-order priority index.
        Higher index == higher priority (wins conflicts).
        Stack index 0 == winning owner (highest priority).

    Callers must call update_load_order() before issuing push/reorder calls
    if the active load order changes mid-session.
    """

    def __init__(self, manifest, load_order_dict: dict):
        """
        Args:
            manifest:         LayeredManifest instance (from model.state).
            load_order_dict:  {mod_name: priority_index} — REQUIRED, never None.
                              Raises TypeError if None is passed.
        """
        if load_order_dict is None:
            raise TypeError(
                "OwnerStackManager: load_order_dict must not be None. "
                "Inject a valid {mod_name: priority_index} mapping from the caller."
            )
        self._manifest = manifest
        self._priority: dict = load_order_dict  # mod_name -> int index

    # ------------------------------------------------------------------
    # Load-order update (call when active load order changes mid-session)
    # ------------------------------------------------------------------
    def update_load_order(self, load_order_dict: dict) -> None:
        """
        Replaces the internal priority dict with a new one.
        Must be called before any push_owner / reorder_stack call whenever
        the active load order has changed.

        Args:
            load_order_dict: {mod_name: priority_index}, never None.
        """
        if load_order_dict is None:
            raise TypeError(
                "update_load_order: load_order_dict must not be None."
            )
        self._priority = load_order_dict
        logger.debug(
            "OwnerStackManager: priority dict updated (%d entries).",
            len(self._priority),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def push_owner(self, path_key: str, mod_name: str) -> None:
        """
        Inserts mod_name into the owner stack for path_key at the correct
        position based on the injected load_order_dict.

        Priority is looked up for EVERY stack member from self._priority —
        no dummy values, no stale comparisons.

        If mod_name is already in the stack it is first removed to prevent
        duplicates, then re-inserted at the deterministically correct position.

        Args:
            path_key:  Normalised virtual path key (lower, forward-slash).
            mod_name:  Name of the mod to push.

        Raises:
            KeyError: If mod_name is not in the injected load_order_dict.
                      This is intentional: a mod with unknown priority must
                      never be silently inserted at a wrong position.
        """
        new_prio = self._lookup_priority(mod_name)  # raises KeyError if absent

        stack = self._manifest.path_owners.setdefault(path_key, [])

        # Remove existing entry to prevent duplicates
        if mod_name in stack:
            stack.remove(mod_name)

        # Insert before the first entry with a STRICTLY lower priority.
        # All lookups use self._priority — no fallback to 0.
        inserted = False
        for i, existing_mod in enumerate(stack):
            existing_prio = self._lookup_priority(existing_mod)
            if new_prio > existing_prio:
                stack.insert(i, mod_name)
                inserted = True
                break
        if not inserted:
            stack.append(mod_name)

        self._sync_active_map_for(path_key)
        logger.debug("push_owner: %s → stack[%s] = %s", mod_name, path_key, stack)

    def pop_owner(self, path_key: str, mod_name: str) -> str | None:
        """
        Removes mod_name from the owner stack for path_key.

        If mod_name is not present, this is a no-op.
        If the stack becomes empty the path_key is deleted from both
        path_owners and _active_map.

        Returns the new active owner (stack[0]) or None if stack is empty.
        """
        stack = self._manifest.path_owners.get(path_key)
        if stack is None:
            logger.debug(
                "pop_owner: path_key '%s' not in path_owners — no-op.", path_key
            )
            return None

        if mod_name not in stack:
            logger.debug(
                "pop_owner: mod '%s' not in stack for '%s' — no-op.",
                mod_name, path_key,
            )
            return stack[0] if stack else None

        stack.remove(mod_name)
        logger.debug("pop_owner: removed '%s' from stack[%s].", mod_name, path_key)

        if not stack:
            del self._manifest.path_owners[path_key]
            self._manifest._active_map.pop(path_key, None)
            logger.debug("pop_owner: stack empty for '%s' — path removed.", path_key)
            return None

        self._sync_active_map_for(path_key)
        new_owner = stack[0]
        logger.debug(
            "pop_owner: '%s' → new active owner for '%s'.", new_owner, path_key
        )
        return new_owner

    def reorder_stack(self, path_key: str) -> None:
        """
        Re-sorts the owner stack for path_key using the injected priority dict.
        Signature no longer takes a load_order list — the dict is injected at
        construction and updated via update_load_order() as needed.

        Called after a targeted incremental update where only a subset of
        paths need re-sorting. For a global load-order change use
        LayeredManifest.full_recompute_layer_b() instead.
        """
        stack = self._manifest.path_owners.get(path_key)
        if not stack:
            return

        stack.sort(key=lambda m: self._priority.get(m, -1), reverse=True)
        self._sync_active_map_for(path_key)
        logger.debug("reorder_stack: '%s' re-sorted → %s", path_key, stack)

    def verify_invariant(self) -> set:
        """
        Checks that path_owners[key][0] == the mod that actually provides
        that file in Layer A for every entry in path_owners.

        Returns:
            Set of path_keys with invariant violations.
            Empty set → manifest is consistent.

        Callers MUST abort the build on a non-empty result — the manifest is corrupt.
        """
        return self._manifest._check_invariant()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _lookup_priority(self, mod_name: str) -> int:
        """
        Returns the load-order priority index for mod_name from the injected dict.

        Raises:
            KeyError: if mod_name is not in the dict — the caller passed a stale
                      or incomplete load_order_dict. No silent fallback is permitted.
        """
        if mod_name not in self._priority:
            raise KeyError(
                f"OwnerStackManager._lookup_priority: mod '{mod_name}' is not in "
                f"the injected load_order_dict. Ensure the dict is current before "
                f"calling push_owner / reorder_stack."
            )
        return self._priority[mod_name]

    def _sync_active_map_for(self, path_key: str) -> None:
        """Updates _active_map for a single path_key without a full rebuild."""
        stack = self._manifest.path_owners.get(path_key)
        if not stack:
            self._manifest._active_map.pop(path_key, None)
            return
        winning_mod = stack[0]
        mod_entry = self._manifest.mod_index.get(winning_mod, {})
        file_entry = mod_entry.get("files", {}).get(path_key)
        if file_entry:
            self._manifest._active_map[path_key] = dict(file_entry, mod_origin=winning_mod)
        else:
            logger.warning(
                "_sync_active_map_for: top owner '%s' has no Layer A entry for '%s'.",
                winning_mod, path_key,
            )
            self._manifest._active_map.pop(path_key, None)


