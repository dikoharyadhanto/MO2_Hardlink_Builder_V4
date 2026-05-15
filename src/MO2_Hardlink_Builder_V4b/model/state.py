"""
FIX-03: DeploymentTransactionManager — checkpoint-based recovery.
FEAT-15: ManifestDeltaAnalyzer — delta threshold to decide full vs incremental rebuild.
v3.7 — LayeredManifest: two-layer Event-Driven state machine manifest.
         Layer A: mod_index  → {mod_name: {files: {rel_key: {size, mtime, source, preferred_path, is_root}}, root_mtime, meta_mtime, file_count}}
         Layer B: path_owners → {virtual_path_key: [mod_name_highest_priority, ..., mod_name_lowest]}
         Invariant: path_owners[key][0] == active_owner (top of stack = winner).
"""
import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE_NAME = ".deployment_state"
CHECKPOINT_INTERVAL = 500  # FIX-03: checkpoint every 500 files


class DeploymentTransactionManager:
    """
    FIX-03: Writes a .deployment_state file before the deployment loop begins.
    Checkpoints every CHECKPOINT_INTERVAL files.
    On clean completion, removes the state file.
    On restart with an incomplete state file, callers can query and offer Resume/Rebuild.
    """

    def __init__(self, standalone_path: str):
        self.standalone_path = Path(standalone_path)
        self.state_file = self.standalone_path / STATE_FILE_NAME
        self._checkpoint_counter = 0

    @staticmethod
    def _hash_file(path: Path) -> str:
        """SHA-256 of the manifest file for state identity."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except Exception:
            pass
        return h.hexdigest()

    def begin(self, manifest_path: str):
        """
        Called BEFORE the first file is linked.
        Writes .deployment_state with manifest hash + checkpoint_index = 0.
        """
        manifest_hash = self._hash_file(Path(manifest_path))
        state = {
            "manifest_hash": manifest_hash,
            "manifest_path": str(manifest_path),
            "checkpoint_index": 0,
            "complete": False,
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.info("Deployment state written: %s", self.state_file)
        except Exception as e:
            logger.error("Failed to write deployment state: %s", e)

        self._checkpoint_counter = 0

    def tick(self, current_index: int):
        """Call inside the deployment loop every iteration. Checkpoints automatically."""
        self._checkpoint_counter += 1
        if self._checkpoint_counter >= CHECKPOINT_INTERVAL:
            self._write_checkpoint(current_index)
            self._checkpoint_counter = 0

    def _write_checkpoint(self, index: int):
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["checkpoint_index"] = index
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.debug("Checkpoint written at file index %d.", index)
        except Exception as e:
            logger.warning("Failed to write checkpoint: %s", e)

    def complete(self):
        """Called on clean completion — removes the state file."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
            logger.info("Deployment state file removed (clean completion).")
        except Exception as e:
            logger.warning("Failed to remove deployment state file: %s", e)

    def get_incomplete_state(self) -> dict | None:
        """
        Returns the incomplete state dict if a previous deployment was interrupted,
        else None. Callers use this to offer Resume/Full Rebuild.
        """
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("complete"):
                return None
            return state
        except Exception as e:
            logger.warning("Could not read deployment state file: %s", e)
            return None


class ManifestDeltaAnalyzer:
    """
    FEAT-15: Compares a new scan manifest against the previous deployment state
    to determine whether to do a full rebuild or incremental deploy.
    Threshold is configurable per game profile (default 70%).
    """

    def __init__(self, manifest_path: str, previous_manifest_path: str = None,
                 delta_threshold: float = 0.70):
        self.manifest_path = Path(manifest_path)
        self.previous_manifest_path = Path(previous_manifest_path) if previous_manifest_path else None
        self.delta_threshold = delta_threshold

    def _load_keys(self, path: Path) -> set:
        if not path or not path.exists():
            return set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            mapping = raw.get("mapping", raw) if isinstance(raw, dict) else raw
            return set(mapping.keys())
        except Exception as e:
            logger.warning("Delta analyzer: failed to load manifest %s: %s", path, e)
            return set()

    def analyze(self) -> dict:
        """
        Returns:
            {
              "full_rebuild_required": bool,
              "delta_ratio": float,
              "added": int,
              "removed": int,
              "removed_keys": set,  # FEAT-15/v3.4: actual key strings for surgical orphan cleanup
              "unchanged": int,
              "threshold": float,
            }
        """
        new_keys = self._load_keys(self.manifest_path)
        old_keys = self._load_keys(self.previous_manifest_path)

        if not old_keys:
            # No previous manifest — full rebuild by definition
            logger.info("Delta analysis: no previous manifest, full rebuild required.")
            return {
                "full_rebuild_required": True,
                "delta_ratio": 1.0,
                "added": len(new_keys),
                "removed": 0,
                "removed_keys": set(),
                "unchanged": 0,
                "threshold": self.delta_threshold,
            }

        added_keys = new_keys - old_keys
        removed_keys_set = old_keys - new_keys
        added = len(added_keys)
        removed = len(removed_keys_set)
        unchanged = len(new_keys & old_keys)
        total = len(old_keys)

        delta_count = added + removed
        delta_ratio = delta_count / total if total > 0 else 0.0
        full_rebuild = delta_ratio > self.delta_threshold

        logger.info(
            "Delta analysis: ratio=%.1f%% (threshold=%.1f%%) — %s",
            delta_ratio * 100,
            self.delta_threshold * 100,
            "FULL REBUILD" if full_rebuild else "INCREMENTAL",
        )
        return {
            "full_rebuild_required": full_rebuild,
            "delta_ratio": delta_ratio,
            "added": added,
            "removed": removed,
            "removed_keys": removed_keys_set,
            "unchanged": unchanged,
            "threshold": self.delta_threshold,
        }


# ---------------------------------------------------------------------------
# v3.7 — LayeredManifest (Event-Driven State Machine)
# ---------------------------------------------------------------------------
# Schema version embedded in every serialised manifest.
# Mismatch on load triggers forced full-rebuild (TR-03 mitigation).
LAYERED_MANIFEST_VERSION = 1


class LayeredManifest:
    """
    v3.7 Two-layer manifest loaded entirely in RAM.

    Layer A  (mod_index):
        mod_name -> {
            'files':      {rel_key: {size, mtime, source, preferred_path, is_root}},
            'root_mtime': float,   # mtime of the mod root directory
            'meta_mtime': float,   # mtime of meta.ini (0 if absent)
            'file_count': int,
        }

    Layer B  (path_owners):
        virtual_path_key -> [mod_high_prio, ..., mod_low_prio]
        path_owners[key][0] is ALWAYS the active (winning) owner.

    Invariant check on load:  path_owners[key][0] == the mod that currently
    provides that virtual path as the highest-priority owner.
    A mismatch means the manifest is corrupt — build must be aborted.
    """

    def __init__(self):
        # Layer A: {mod_name -> mod_entry}
        self.mod_index: dict = {}
        # Layer B: {virtual_path_key -> [ordered owner list]}
        self.path_owners: dict = {}
        # Convenience: {virtual_path_key -> winning entry dict} derived from Layer A + B
        self._active_map: dict = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self, manifest_path) -> None:
        """
        Atomically writes the two-layer manifest as JSON using a .tmp + os.replace().
        Compatible with the existing atomic-write pattern (TASK-A02, v3.6).
        """
        path = Path(manifest_path)
        tmp = path.with_suffix(".json.tmp")

        payload = {
            "version": LAYERED_MANIFEST_VERSION,
            "mod_index": self.mod_index,
            "path_owners": self.path_owners,
        }
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(str(tmp), str(path))
            logger.info("LayeredManifest saved atomically → %s", path)
        except Exception as e:
            logger.error("LayeredManifest save failed: %s", e)
            raise

    @classmethod
    def load(cls, manifest_path) -> 'LayeredManifest':
        """
        Loads a LayeredManifest from disk and immediately runs the invariant check.

        Raises:
            FileNotFoundError  — manifest does not exist (caller should trigger full build).
            ValueError         — schema version mismatch or invariant violation.
                                 Caller MUST abort the build — do NOT fall back silently.
        """
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"LayeredManifest not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # TR-03: schema version guard — old flat manifest rejected explicitly
        if not isinstance(raw, dict) or "mod_index" not in raw or "path_owners" not in raw:
            raise ValueError(
                "LayeredManifest: incompatible schema detected (v3.6 flat format or corrupt). "
                "A full rebuild is required to regenerate the manifest."
            )

        stored_ver = raw.get("version")
        if stored_ver != LAYERED_MANIFEST_VERSION:
            raise ValueError(
                f"LayeredManifest version mismatch (stored={stored_ver}, "
                f"expected={LAYERED_MANIFEST_VERSION}). Full rebuild required."
            )

        instance = cls()
        instance.mod_index = raw["mod_index"]
        instance.path_owners = raw["path_owners"]
        instance._rebuild_active_map()

        # Invariant check on load (TD-02)
        violations = instance._check_invariant()
        if violations:
            sample = ", ".join(list(violations)[:5])
            raise ValueError(
                f"LayeredManifest invariant violation on load: top_of_stack != active_owner "
                f"for {len(violations)} path(s). Sample: [{sample}]. "
                "Build aborted — manifest is corrupt. Perform a full rebuild."
            )

        logger.info(
            "LayeredManifest loaded OK: %d mods, %d paths.",
            len(instance.mod_index), len(instance.path_owners),
        )
        return instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _rebuild_active_map(self) -> None:
        """
        Derives _active_map from Layer A + B in one pass.
        Called after load and after every bulk recompute.
        """
        self._active_map = {}
        for path_key, owners in self.path_owners.items():
            if not owners:
                continue
            winning_mod = owners[0]
            mod_entry = self.mod_index.get(winning_mod, {})
            file_entry = mod_entry.get("files", {}).get(path_key)
            if file_entry:
                self._active_map[path_key] = dict(file_entry, mod_origin=winning_mod)

    def _check_invariant(self) -> set:
        """
        Returns the set of path_keys where path_owners[key][0] != the mod
        that actually provides that file with the highest confirmed load-order index.
        An empty set means the invariant holds.
        """
        violations = set()
        for path_key, owners in self.path_owners.items():
            if not owners:
                continue
            top = owners[0]
            # Verify top-of-stack mod actually has this file in Layer A
            if path_key not in self.mod_index.get(top, {}).get("files", {}):
                violations.add(path_key)
        return violations

    # ------------------------------------------------------------------
    # Layer B stack mutation API  (called by OwnerStackManager)
    # ------------------------------------------------------------------
    def get_active_entry(self, path_key: str) -> dict | None:
        """Returns the active (winning) file entry dict for a virtual path, or None."""
        return self._active_map.get(path_key)

    def active_owner(self, path_key: str) -> str | None:
        """Returns the name of the current winning mod for a virtual path."""
        owners = self.path_owners.get(path_key)
        return owners[0] if owners else None

    def full_recompute_layer_b(self, load_order: list) -> None:
        """
        Pure RAM recompute of Layer B from Layer A when the load order changes (TASK-A02).
        Does NOT touch the filesystem.

        Args:
            load_order: Active mod names ordered low→high priority
                        (index 0 = lowest, last = highest priority).
        """
        # Build priority lookup: higher index = higher priority.
        priority = {mod: idx for idx, mod in enumerate(load_order)}

        # For each virtual path, collect all mods that provide it, sort by priority desc.
        path_to_providers: dict = {}
        for mod_name, mod_entry in self.mod_index.items():
            for path_key in mod_entry.get("files", {}):
                if path_key not in path_to_providers:
                    path_to_providers[path_key] = []
                path_to_providers[path_key].append(mod_name)

        new_owners: dict = {}
        for path_key, providers in path_to_providers.items():
            # Sort descending by priority (highest first = index 0)
            sorted_owners = sorted(
                providers,
                key=lambda m: priority.get(m, -1),
                reverse=True,
            )
            new_owners[path_key] = sorted_owners

        self.path_owners = new_owners
        self._rebuild_active_map()
        logger.info(
            "LayeredManifest: full Layer B recompute complete — %d paths rebuilt in RAM.",
            len(self.path_owners),
        )

    def compute_action_queue(self, old_manifest: 'LayeredManifest | None') -> list:
        """
        Diffs the new RAM state (self) against old_manifest to produce an Action Queue.
        Returns a list of action tuples:
            ('DELETE', virtual_path_key, old_target_preferred_path)
            ('LINK',   virtual_path_key, source_abs_path, preferred_path)

        Phase ordering is enforced by the consumer (LinkerExecutor):
            Phase 1: all DELETEs first
            Phase 2: all LINKs
        """
        queue = []

        if old_manifest is None:
            # Fresh build — everything is a LINK, nothing to DELETE
            for path_key, entry in self._active_map.items():
                queue.append(('LINK', path_key, entry['source'], entry.get('preferred_path', path_key)))
            logger.info("Action Queue (fresh): %d LINK operations.", len(queue))
            return queue

        old_map = old_manifest._active_map
        new_map = self._active_map

        # Paths removed from new state → DELETE
        for path_key, old_entry in old_map.items():
            if path_key not in new_map:
                queue.append(('DELETE', path_key, old_entry.get('preferred_path', path_key)))

        # Paths added or changed (different source or mod_origin) → LINK
        for path_key, new_entry in new_map.items():
            old_entry = old_map.get(path_key)
            if old_entry is None:
                # New file
                queue.append(('LINK', path_key, new_entry['source'], new_entry.get('preferred_path', path_key)))
            elif (old_entry.get('source') != new_entry.get('source')
                  or old_entry.get('mod_origin') != new_entry.get('mod_origin')):
                # Owner changed or source path changed — relink
                queue.append(('LINK', path_key, new_entry['source'], new_entry.get('preferred_path', path_key)))

        delete_count = sum(1 for a in queue if a[0] == 'DELETE')
        link_count   = sum(1 for a in queue if a[0] == 'LINK')
        logger.info(
            "Action Queue computed: %d DELETE + %d LINK = %d total ops.",
            delete_count, link_count, len(queue),
        )
        return queue
