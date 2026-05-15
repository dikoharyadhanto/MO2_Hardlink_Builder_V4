# ANT-WO-005-v3.4 — Work Order: True Incremental Updates (Delta Execution)

> [!IMPORTANT]
> **Logic Dependencies**: `GMN-PRD-005-v3.3`, `FEAT-15` (ManifestDeltaAnalyzer)
> **Context**: V4 currently performs Delta Analysis but discards the result, falling back to the legacy V3 brute-force deployment loop. `LinkerExecutor` rewrites every hardlink from scratch, and orphan cleanup is permanently disabled (`clean=False`), causing removed mods to linger forever. This Work Order implements true Inode-skipping incremental updates.

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Work Order (WO) |
| **Version** | v3.4 |
| **Issued By** | ANT — Technical Foreman |
| **Issued To** | CDC — Lead Developer (Claude Code) |
| **Status** | Implementation-Ready |

---

## 2. Root Cause & Solution

### Problem
1. `deployment_controller.py` evaluates `delta["full_rebuild_required"]` but does not alter execution parameters based on it.
2. `LinkerExecutor.execute_mapping()` unconditionally calls `os.remove()` and `_hardlink_verified()` on every file in the manifest.
3. Orphan cleanup requires a slow, recursive directory walk and is currently hard-disabled.

### Solution
1. **Inode Fast-Path:** `LinkerExecutor` must check if the target already exists and shares the exact `st_ino` (inode) as the source. If yes, it skips the expensive filesystem operation instantly.
2. **Surgical Orphan Cleanup:** Instead of a recursive walk, `clean_orphaned_files` should accept the exact list of removed files (calculated by `ManifestDeltaAnalyzer`) and explicitly delete only those targets.
3. **Controller Wiring:** Route the Delta analyzer's output into the deployment loop. If `full_rebuild_required` is `False`, execute surgical orphan cleanup and let the Inode Fast-Path skip unchanged files.

---

## 3. Implementation Task

### Task 1: Update LinkerExecutor (model/engines/linker_executor.py)

1. **Implement Inode Fast-Path in `execute_mapping()`:**
   Before the `try` block that removes the existing target (`target_full_path`), add a guard:
   ```python
   if target_full_path.exists() and target_full_path.is_file():
       try:
           # If inodes match, the hardlink is already perfectly valid. Skip it.
           if target_full_path.stat().st_ino == source_path.stat().st_ino:
               report[target_rel_path] = {"status": "SKIPPED_UNCHANGED", "mod": info["mod_origin"]}
               if tick_callback: tick_callback(i)
               continue
       except OSError:
           pass
   ```

2. **Rewrite `clean_orphaned_files()` for Surgical Deletion:**
   Modify the signature to accept an explicit list of paths to remove:
   `def clean_orphaned_files(self, removed_keys: set, confirm_callback=None)`
   Bypass the recursive `get_orphan_list()` walk entirely. Just iterate over `removed_keys`, construct the `target_full_path`, and `os.remove()` it if it exists. Log deletions to `audit_logger`.

### Task 2: Update DeploymentController (controller/deployment_controller.py)

1. **Extract `removed_keys`:** 
   Update `ManifestDeltaAnalyzer.analyze()` to return the `removed` set in its output dictionary (e.g., `delta["removed_keys"]`).
   
2. **Wire the Delta Branch (`_deploy_worker`):**
   ```python
   is_full_rebuild = clean_deploy or delta["full_rebuild_required"]
   
   if is_full_rebuild:
       # Existing Stage 1 logic: wipe the whole standalone_path
   else:
       # True Incremental: Surgically delete only removed orphans
       removed = delta.get("removed_keys", set())
       if removed:
           linker.clean_orphaned_files(removed, confirm_callback=lambda count: True) # Auto-confirm surgical delta deletes
   ```

3. **Pass `clean=False`:**
   Leave `clean=False` in `execute_mapping()` so it does not attempt the old recursive cleanup, as we already handled orphans surgically.

---

## 4. Success Indicators

| # | Indicator | Test |
| :--- | :--- | :--- |
| SI-01 | A zero-delta deploy (deploying twice with no changes) takes < 5 seconds and logs `SKIPPED_UNCHANGED` for all files. | STR-INC-02 |
| SI-02 | Removing files from MO2 and deploying incrementally successfully deletes the orphans without a full rebuild. | STR-INC-03 |
| SI-03 | Adding new files and deploying incrementally correctly hardlinks ONLY the new files while skipping the rest. | STR-INC-03 |

---

*End of WO*
