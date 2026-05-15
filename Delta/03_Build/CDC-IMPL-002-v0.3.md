# CDC-IMPL-002-v0.3 — Implementation Log: True Incremental Updates (Delta Execution)

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.3.md`
> **Build Output:** `03_Build/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Log (IMPL) |
| **Version** | v0.3 |
| **Status** | **COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.3.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.3.md` |
| **Walkthrough Ref** | `CDC-WALK-002-v0.3.md` |

---

## 2. Scope of Change

**Three file modifications** — all within `03_Build/MO2_Hardlink_Builder_V4b/`:

### 2.1 What Changes

| Region | Current Behavior | New Behavior |
| :--- | :--- | :--- |
| `state.py` — `ManifestDeltaAnalyzer.analyze()` | Returns `removed` as integer count only | Additionally returns `removed_keys` as the actual `set` of removed key strings |
| `linker_executor.py` — `execute_mapping()` main loop | Unconditionally calls `os.remove()` + `_hardlink_verified()` on every file | Inode Fast-Path guard: if `target.stat().st_ino == source.stat().st_ino`, skip with `SKIPPED_UNCHANGED` |
| `linker_executor.py` — `clean_orphaned_files()` | Loads manifest + recursive `os.walk` via `get_orphan_list()` | Accepts optional `removed_keys: set` param for surgical mode (direct iteration, no walk) |
| `deployment_controller.py` — `BuildWorker.run()` Stage 1 & 3 | Always wipes standalone via `total_cleanup()`, delta result logged but ignored | Defers cleanup until after delta analysis. Full rebuild → wipe. Incremental → surgical orphan cleanup only |
| `deployment_controller.py` — Manifest rotation | `mapping_manifest.json` overwritten on each scan, no previous state preserved | `shutil.move()` rotates `mapping_manifest.json` → `mapping_manifest_prev.json` before scan |
| `deployment_controller.py` — FEAT-11 Save Export Guard | Runs unconditionally before every build | Only runs inside `is_full_rebuild` branch (saves are safe during incremental) |

### 2.2 What Does NOT Change

- `ScannerEngine`, `VerificationEngine`, `ProfileSync` — untouched
- `feature_generator.py` (C# wrapper) — untouched
- `CleanerEngine.total_cleanup()` — called conditionally, not modified
- `DeploymentTransactionManager` — untouched
- All existing FIX-01 through FIX-05 invariants preserved
- `get_orphan_list()` — preserved as legacy fallback, not deleted
- FEAT-16 `harvest_generated_files` — preserved, runs on every deploy (per ANT directive)

---

## 3. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **Inode Fast-Path is always active, not gated by `is_full_rebuild`** | Even on a full rebuild (after `total_cleanup()`), the Fast-Path has zero cost: `target_full_path.exists()` returns `False` for all files (directory was wiped), so the guard is a no-op. On incremental builds, it provides the core performance gain. No branching complexity needed. |
| TD-02 | **`removed_keys_set` stored as a separate variable, not reusing `removed`** | Preserving `added` and `removed` as integer counts avoids breaking the logging contract at line 175. The set is an additive return, not a replacement. |
| TD-03 | **Manifest rotation via `shutil.move()` not `shutil.copy2()`** | `move()` is atomic on the same filesystem (NTFS rename). `copy2()` would leave the old manifest in place, causing the scanner to overwrite it and corrupt the delta baseline. If `move()` fails (permissions, cross-device), the `except` clause logs a warning and delta analysis falls through to "no previous manifest → full rebuild" — safe degradation. |
| TD-04 | **Surgical cleanup auto-confirms via `lambda count: True`** | The removed_keys set comes from the delta analyzer's exact set comparison — it is mathematically precise. There is no user judgment needed ("should I delete these orphans?"). The FIX-05 confirm callback is preserved for the legacy recursive walk path where orphan identification is heuristic-based. |
| TD-05 | **Progress callback preserved inside Inode Fast-Path skip** | Without this, the progress bar would stall during zero-delta deploys (all files skipped). The `continue` statement includes both `tick_callback` and `progress_callback` to maintain UI responsiveness. |
| TD-06 | **FEAT-16 harvest runs before manifest rotation** | Harvest needs the current `mapping_manifest.json` to identify which files in the standalone are "generated" (not in manifest). After rotation, the manifest becomes `_prev.json` and a new one doesn't exist yet. Harvest must run first. |

---

## 4. Files Modified

| File Path | Action | Purpose |
| :--- | :--- | :--- |
| `model/state.py` | MODIFY | Return `removed_keys` set from `ManifestDeltaAnalyzer.analyze()` — both return paths (no-previous + normal) |
| `model/engines/linker_executor.py` | MODIFY | Inode Fast-Path in `execute_mapping()` (line 278–292) + surgical `clean_orphaned_files(removed_keys=...)` (line 147–181) |
| `controller/deployment_controller.py` | MODIFY | Manifest rotation (line 340–349), delta branch wiring (line 377–447), FEAT-11 gating inside `is_full_rebuild` (line 384–415) |

**Total files modified: 3**

---

## 5. STR Mapping

| STR ID | Scenario | Implementation Point |
| :--- | :--- | :--- |
| STR-INC-01 | Baseline Full Build (Control) | Preserved — full rebuild path unchanged when `delta["full_rebuild_required"]` is True. `total_cleanup()` runs, then full `execute_mapping()` with Inode Fast-Path (no-op since directory was wiped) |
| STR-INC-02 | Zero-Delta Incremental Build | Inode Fast-Path: `st_ino` match → `SKIPPED_UNCHANGED` for all files, execution < 2 seconds. No orphan cleanup (empty `removed_keys`) |
| STR-INC-03 | Add + Remove Files | Surgical orphan cleanup deletes exactly the `removed_keys` files. Inode Fast-Path skips all unchanged files. Only new files (no existing target) go through `_hardlink_verified()` |
| STR-INC-04 | Priority / Content Change | Inode Fast-Path detects `st_ino` mismatch (different source file → different inode) → falls through to normal `os.remove()` + `_hardlink_verified()` relink |

---

## 6. Phase Status

| Phase | Status | Notes |
| :--- | :--- | :--- |
| Pre-Implementation Walkthrough | `[x] Complete` | `CDC-WALK-002-v0.3.md` submitted |
| ANT/Director Approval | `[x] Approved` | Q-01/Q-02/Q-03 resolved by ANT |
| Implementation | `[x] Complete` | 3 files modified — `state.py`, `linker_executor.py`, `deployment_controller.py` |
| Handoff to ANT QA | `[x] READY` | — |

---

## 7. Technical Debt & Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | `mapping_manifest_prev.json` accumulates indefinitely. Only the most recent previous manifest is needed, but the file is never deleted. | None | The `shutil.move()` overwrites `_prev.json` each time — only one previous manifest exists at any time. |
| TR-02 | `st_ino` comparison on network drives (SMB/NFS) may return inconsistent values. | Low | The pre-flight `EnvironmentSensor` already warns about non-local paths. Network drives typically don't support hardlinks anyway, so the builder would use `copy_cross_drive` mode. |
| TR-03 | If `ScannerEngine.build_mapping()` fails after manifest rotation, the old `mapping_manifest.json` is gone (moved to `_prev.json`) and the new one wasn't written. | Low | On next run, `_prev.json` exists but `mapping_manifest.json` doesn't → delta analysis returns "no previous manifest → full rebuild". The user gets a clean rebuild, which is the correct recovery behavior. |
| TR-04 | `import shutil as _shutil` inside the function body (line 345) duplicates the module-level `import shutil` in `linker_executor.py`. | None | `deployment_controller.py` does not have a module-level `shutil` import. The local import is intentional to avoid adding a new module-level dependency to the controller. |
| TR-05 | **[HOTFIX]** Stage reordering regression: `total_cleanup()` destroys `standalone_metadata/` (including the freshly-written manifest) after scan. Caused silent zero-mod deploy + crash at Stage 5. | **Critical** | **Fixed:** Manifest content is read into memory before `total_cleanup()`, then `metadata_dir` is recreated and manifest is restored after wipe. Applied during v3.5 QA cycle. |

---

*Implementation complete (with TR-05 hotfix). ANT: proceed to run `ANT-STR-002-v0.3.md` (STR-INC-01 through STR-INC-04) against the modified codebase.*
