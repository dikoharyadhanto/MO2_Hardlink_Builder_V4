# CDC-WALK-002-v0.3 — Pre-Implementation Walkthrough: True Incremental Updates (Delta Execution)

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.3.md` + `ANT-STR-002-v0.3.md`
> **Status**: Implementation complete — approved by ANT with Q-01/Q-02/Q-03 resolutions applied.

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Walkthrough (WALK) |
| **Version** | v0.3 |
| **Status** | **IMPL COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.3.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.3.md` |

---

## 2. Task Interpretation

### What I understand must be implemented:

V4 currently performs Delta Analysis via `ManifestDeltaAnalyzer` (FEAT-15) in `deployment_controller.py` lines 399–415 but **discards the result entirely**. Regardless of whether the analyzer says "incremental deploy", the controller:

1. **Always wipes the standalone folder** via `cleaner.total_cleanup()` in Stage 1 (line 367).
2. **Always runs `execute_mapping()` with `clean=False`**, forcing every file through `os.remove()` + `_hardlink_verified()` unconditionally (linker_executor.py lines 249–264).
3. **Never performs orphan cleanup**, since `clean=False` is hardcoded and the old `clean_orphaned_files()` requires a slow recursive `os.walk`.

### The fix (per ANT-WO-002-v0.3):

1. **Inode Fast-Path** in `LinkerExecutor.execute_mapping()`: Before the destructive `os.remove()` + relink cycle, check if the existing target file already shares the same `st_ino` as the source. If yes → skip instantly with `SKIPPED_UNCHANGED` status.
2. **Surgical Orphan Cleanup** in `LinkerExecutor.clean_orphaned_files()`: Accept an explicit `removed_keys` set (from `ManifestDeltaAnalyzer`) instead of doing a full `os.walk`. Delete only those specific target files.
3. **Controller Wiring** in `BuildWorker.run()`: Route the delta analysis result into the deployment flow. When `full_rebuild_required` is `False`, skip the full wipe and instead surgically delete only the `removed_keys` orphans before entering the Inode Fast-Path deployment loop.

---

## 3. Proposed Approach

### 3.1 ManifestDeltaAnalyzer — Return `removed_keys` (model/state.py)

**Current**: `analyze()` returns `added`, `removed`, `unchanged` as integer counts only.
**Change**: Add `removed_keys` to the return dict — the actual set of key strings (`old_keys - new_keys`).

```python
# In analyze() return dict, add:
"removed_keys": old_keys - new_keys,
```

**Rationale**: The removed key set is already computed (line 163: `removed = len(old_keys - new_keys)`) but only its `len()` is stored. Returning the set itself costs zero extra computation and enables Task 2 without a second manifest load.

### 3.2 LinkerExecutor — Inode Fast-Path (model/engines/linker_executor.py)

**Location**: `execute_mapping()` main loop (line 249), **before** the destructive `os.remove()` call.

**Guard logic** (inserted at the top of the `for` body, after `target_full_path` is resolved):

```python
# FEAT-15: Inode Fast-Path — skip if target already points to same inode
if target_full_path.exists() and target_full_path.is_file():
    try:
        if target_full_path.stat().st_ino == source_path.stat().st_ino:
            report[target_rel_path] = {
                "status": "SKIPPED_UNCHANGED",
                "mod": info["mod_origin"],
            }
            if tick_callback:
                tick_callback(i)
            continue
    except OSError:
        pass  # Stat failed — fall through to normal relink
```

**Key design decisions**:
- The `OSError` catch is intentional: if the file is locked or inaccessible, we fall through to the normal destructive path which has its own error handling.
- `st_ino` comparison works on NTFS (Windows) because NTFS tracks inode-equivalent index numbers. A matching inode means the target is literally the same hardlink — no relink needed.
- This guard is **always active**, not gated by `full_rebuild_required`. Even on a full rebuild, skipping unchanged files is pure performance gain with zero correctness risk. The only case where the inode matches but the file is wrong would be a filesystem corruption scenario, which is beyond our scope.

### 3.3 LinkerExecutor — Surgical Orphan Cleanup (model/engines/linker_executor.py)

**Current signature**: `clean_orphaned_files(self, confirm_callback=None)` — loads manifest, calls `get_orphan_list()` (full `os.walk`), confirms, deletes.

**New overloaded behavior**: Add `removed_keys: set = None` parameter.

```python
def clean_orphaned_files(self, removed_keys: set = None, confirm_callback=None):
```

**Logic branch**:
- If `removed_keys` is provided (surgical mode): iterate directly over `removed_keys`, construct `target_full_path`, `os.remove()` if exists, log to `audit_logger`. Skip the `get_orphan_list()` walk entirely.
- If `removed_keys` is `None` (legacy mode): fall through to the existing recursive walk + confirm behavior (preserving backward compat).

This dual-mode approach ensures:
1. The new incremental path is fast (no `os.walk`, no manifest re-parse).
2. The old `clean=True` code path remains functional if ever re-enabled.
3. No signature-breaking change — existing callers pass `removed_keys=None` implicitly.

### 3.4 DeploymentController — Wiring the Delta Branch (controller/deployment_controller.py)

**Current flow** (BuildWorker.run(), lines 308–466):
```
Stage 1: Always cleaner.total_cleanup() → wipes everything
Stage 2: Scan
FEAT-15: Delta analysis (result logged but ignored)
Stage 3: Deploy with clean=False → brute-force relink of everything
```

**New flow**:
```
Stage 1: Conditional
  - If clean_deploy OR delta["full_rebuild_required"]: cleaner.total_cleanup() (full wipe)
  - Else: SKIP wipe entirely
Stage 2: Scan (unchanged)
FEAT-15: Delta analysis → extract removed_keys
Stage 3: Deploy
  - If NOT full rebuild AND removed_keys exist: linker.clean_orphaned_files(removed_keys, auto-confirm)
  - execute_mapping(clean=False, ...) → Inode Fast-Path handles the rest
```

**Critical restructuring**: The delta analysis currently runs **after** Stage 1 (the full wipe) and **after** Stage 2 (scan). This ordering is correct — we need the **new** manifest from Stage 2 to compare against the previous one. The key change is that Stage 1 must **not** wipe the standalone folder when we're doing an incremental build.

**Implementation detail**: We need to move the `total_cleanup()` call to **after** the delta analysis, or gate it with a flag. The cleanest approach:

1. **Before Stage 2 (Scan)**: Check if a `mapping_manifest_prev.json` exists. If yes, we *might* be incremental — do NOT wipe yet.
2. **After FEAT-15 delta analysis**: If `full_rebuild_required` → do `total_cleanup()` now. If incremental → skip wipe, do surgical cleanup only.

> [!WARNING]
> **Stage 1 reordering is the most architecturally significant change.** The current flow wipes the standalone directory before scanning, which means on a full rebuild, the scan starts from a clean slate. For incremental builds, we must preserve the existing standalone directory so that the Inode Fast-Path can compare inodes. This means Stage 1 cleanup is **deferred** until after delta analysis, and only triggered for full rebuilds.

**Proposed code structure** (simplified):

```python
# Stage 2: Scan (moved before conditional cleanup)
scanner = ScannerEngine(...)
scanner.build_mapping(...)

# FEAT-15: Delta analysis
delta = delta_analyzer.analyze()
is_full_rebuild = delta["full_rebuild_required"]

# Stage 1 (deferred): Conditional cleanup
if is_full_rebuild:
    cleaner.total_cleanup(...)
else:
    removed_keys = delta.get("removed_keys", set())
    if removed_keys:
        linker.clean_orphaned_files(removed_keys=removed_keys, confirm_callback=lambda count: True)

# Stage 3: Deploy (Inode Fast-Path is always active)
linker.execute_mapping(clean=False, ...)
```

---

## 4. Files to Create/Modify

| File | Action | Purpose |
| :--- | :--- | :--- |
| `model/state.py` | MODIFY | Add `removed_keys` set to `ManifestDeltaAnalyzer.analyze()` return dict |
| `model/engines/linker_executor.py` | MODIFY | Task 1: Inode Fast-Path guard in `execute_mapping()`. Task 2: Add `removed_keys` param to `clean_orphaned_files()` for surgical mode |
| `controller/deployment_controller.py` | MODIFY | Task 3: Wire delta branch — defer Stage 1 cleanup, route `removed_keys` to surgical orphan cleanup, let Inode Fast-Path handle unchanged files |

**All changes are within `03_Build/`.** No new files created, no packages added, no signature-breaking changes.

---

## 5. Dependencies

**None.** All changes use standard Python (`os.stat`, `os.remove`, `pathlib.Path`). No new packages or version changes required.

---

## 6. Flags / Risks

| # | Risk | Severity | Mitigation |
| :--- | :--- | :--- | :--- |
| F-01 | **Stage 1 reordering could leave stale state if scan fails mid-way.** If `ScannerEngine.build_mapping()` throws before delta analysis, the standalone folder is not cleaned and contains files from the previous build. | Medium | The existing `DeploymentTransactionManager` already handles incomplete states. If scan fails, the build worker emits an error and the user retries. On retry, the delta analysis will correctly detect the state. Additionally, the FEAT-16 `harvest_generated_files` call (line 358) needs to run before a potential wipe — currently it does, and this is preserved. |
| F-02 | **Inode comparison on FAT32/exFAT.** `st_ino` on FAT32 may return 0 or inconsistent values, causing false-positive skips. | Low | The existing `_hardlink_verified()` already detects pseudo-hardlinks on non-NTFS via inode mismatch (line 53-58). Additionally, FAT32 doesn't support hardlinks at all, so the builder would have fallen back to copy mode long before this point. The pre-flight `EnvironmentSensor` (line 289) warns about cross-volume mismatches. |
| F-03 | **`removed_keys` set could be large.** If a user removes 10,000 mods, the set could be very large. | None | Iterating a 10,000-element set and calling `os.remove()` per item is still orders of magnitude faster than a recursive `os.walk()` over the entire standalone directory. Memory impact is negligible (each key is ~50-100 bytes). |
| F-04 | **Race condition: file removed between `exists()` check and `stat()`.** In the Inode Fast-Path, the file could be deleted between the `exists()` check and `stat()` call. | None | The `OSError` catch wrapping the `stat()` calls handles this gracefully — falls through to the normal relink path. |
| F-05 | **Previous manifest (`mapping_manifest_prev.json`) must exist for incremental to work.** Currently, the controller references `prev_manifest` at line 400, but I don't see where `mapping_manifest_prev.json` is created/rotated. | Medium | **Requires investigation.** If the scanner or controller doesn't rotate `mapping_manifest.json` → `mapping_manifest_prev.json` after each build, then `ManifestDeltaAnalyzer` will always see no previous manifest → always full rebuild. This may already be handled elsewhere, but I need to verify before implementing. If not handled, I'll add a manifest rotation step after `scanner.build_mapping()`. |

---

## 7. Success Indicator Mapping

| WO Indicator | STR Test | Implementation Point |
| :--- | :--- | :--- |
| **SI-01**: Zero-delta deploy < 5 seconds, all files `SKIPPED_UNCHANGED` | STR-INC-02 | Inode Fast-Path guard in `execute_mapping()` — `st_ino` match → skip with `SKIPPED_UNCHANGED` status |
| **SI-02**: Removing files + incremental deploy deletes orphans without full rebuild | STR-INC-03 | `clean_orphaned_files(removed_keys=...)` surgical mode + delta branch wiring in controller |
| **SI-03**: Adding new files + incremental deploy hardlinks ONLY new files | STR-INC-03 | Inode Fast-Path skips existing files (inode match), only new files (no existing target) go through `_hardlink_verified()` |

---

*Implementation complete. See `CDC-IMPL-002-v0.3.md` for the full implementation log.*
