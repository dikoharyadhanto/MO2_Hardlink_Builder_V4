# ANT WORK ORDER — 005-v3.7
**Project:** MO2 Hardlink Builder V4b
**Task:** Event-Driven Incremental Build Architecture Refactoring
**Status:** PENDING IMPLEMENTATION

## 1. Executive Summary
Following the strategic review of the incremental build process (CSO-MO2HLB4B-20260505), the current file-level verification logic has been identified as a systemic bottleneck (I/O "stat storm"). This Work Order directs the CDC to fundamentally re-architect the incremental engine into an **Event-Driven State Machine**. 

The goal is to shift computational overhead from disk I/O to memory (RAM) by implementing a multi-layered manifest, a tri-gate change detection system, and an idempotent action queue. This architecture must provide $O(1)$ lookup for fallback ownership and eliminate unnecessary filesystem traversal, transforming the system into a production-grade state diff engine.

## 2. Implementation Directives

### TASK-A01: Multi-Layered Manifest (Engine State)
**Target Component:** Manifest Generator & Data Models (`manifest.json` / state memory)
*   **Active Structure:** The manifest must be loaded into RAM as an active structure, not just a passive JSON dump.
*   **Layer A (Mod-to-Files):** Maintain a mapping of `Mod Name -> [Files]`, including `size` and `mtime` for rapid mod invalidation.
*   **Layer B (Virtual Path-to-Owners Stack):** Implement a dictionary mapping every virtual deployment path to a **Stack/Array of Mod Owners**, strictly ordered by Load Order priority (e.g., `{"textures/armor.dds": ["Mod_HD", "Mod_Base"]}`).
*   **Stack Maintenance Rules:** When a mod changes during incremental build, the stack MUST be explicitly updated:
    *   If a file is added: Insert the mod into the stack at the correct index based on load order priority.
    *   If a file is removed: Remove the mod from the stack.
    *   If a file is modified: Ensure the mod's position remains correctly sorted.
*   **Invariant Check:** The top of the stack must always represent the current active owner. The system MUST perform an invariant check (`top_of_stack == active_owner`). If this fails, abort the build and flag an error to prevent silent ownership corruption.

### TASK-A02: Explicit Load Order Change Handling
**Target Component:** Incremental Entry Point / Load Order Validator
*   **Stable Mode:** If the `modlist.txt` (load order) is unchanged, proceed with standard incremental processing.
*   **Changed Mode (Global Recompute):** If the load order has changed, the system MUST fallback to a **Full Ownership Recompute** in RAM. This operation is restricted to memory updates on the `Virtual Path-to-Owners Stack` and must not touch the filesystem. Do not attempt a "semi-incremental" approach when the load order shifts.

### TASK-A03: Tri-Gate Change Detection
**Target Component:** Scanner / Change Detector
*   **Gate 1 (Topology Gate):** Validate `modlist.txt` hash. If changed, trigger global RAM recompute (TASK-A02).
*   **Gate 2 (Mod Dirty Flag):** Check the mod's root folder `mtime`, `meta.ini` `mtime`, the total `file_count` of the mod directory, **AND** a lightweight sampling fingerprint (e.g., checking mtime/size of 1-3 deep files or a fast rolling checksum). If none of these have changed compared to the manifest, skip the mod entirely. This prevents false negatives when files are modified in-place without altering directory mtime.
*   **Gate 3 (Selective Stat):** Only if a mod fails Gate 1 or Gate 2, perform a multi-threaded `os.scandir` limited exclusively to that specific mod to collect updated `size + mtime` data for the manifest.

### TASK-A04: Idempotent Action Queue Execution
**Target Component:** Linker Executor (`linker_executor.py`)
*   **No Verification at Execution:** The executor must consume the diffs between the old manifest and new RAM state to generate an **Absolute Action Queue** (e.g., `DELETE path`, `LINK source -> target`).
*   **Strict Execution Ordering:** To prevent race conditions, the execution MUST be phased. Phase 1: Execute all `DELETE` operations. Phase 2: Execute all `LINK` operations. Do not interleave deletes and links.
*   **Idempotency Guarantee:** Execute the queue blindly (Force Overwrite) without checking inodes or file existence. The operations must be deterministic so that executing the queue twice yields the exact same state without side effects.
*   **Error Logging:** If a file is locked or in use, log the OS error without halting parallel execution threads.

## 3. Acceptance Criteria
1. The `manifest.json` correctly saves and restores the Two-Way Map (Layer A and Layer B).
2. Deleting or disabling a higher-priority mod correctly pops it from the `Virtual Path-to-Owners Stack` in $O(1)$ time, automatically reassigning the file to the next fallback mod in the stack.
3. Modifying a file deep within a mod without changing the root folder `mtime` is successfully detected via the `file_count` or `meta.ini` check (Gate 2 resilience).
4. Changing the MO2 load order triggers a purely RAM-based full ownership recompute without rescanning unchanged physical files.
5. The execution phase performs zero `os.stat` or inode verification calls, exclusively processing the Action Queue deterministically.
