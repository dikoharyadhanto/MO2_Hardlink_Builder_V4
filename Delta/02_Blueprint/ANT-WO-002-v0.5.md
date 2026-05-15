# ANT WORK ORDER — 002-v0.5
**Project:** MO2 Hardlink Builder V4b
**Task:** Post-v0.4 Director Feedback Implementation & Refinement
**Status:** PENDING IMPLEMENTATION

## 1. Executive Summary
Following the Director's manual testing of v0.4 (DIR-STR-002-v0.5), several refinements, bug fixes, and usability improvements have been requested. These include updating exclusion lists for logs and backups, optimizing the incremental build process to actually save time, updating the UI and reporting structure, and addressing logic gaps in the C# wrapper's handling of save files and configuration backups. Additionally, the standalone generated files need to be forcibly hardlinked even if disabled in MO2.

This Work Order defines the tasks for the CDC to implement these corrections and enhancements.

## 2. Implementation Directives

### TASK-A01: Hardlink Exclusion Expansion
**Target Component:** `ScannerEngine` / Exclusion Logic
*   **Logs:** Explicitly skip any files with the `.log` extension and any directory named `Logs` during the scan and hardlink process.
*   **Backups:** Explicitly skip any directory named `backup` during the scan and hardlink process.
*   **Matching Rules:** Exclusion matching must be an **exact directory name match only** (not a partial substring like `backup_old`) and strictly **case-insensitive** (e.g., `logs`, `LOGS`, `Backup`).

### TASK-A02: Incremental Build Optimization (Dual-Logic Verification)
**Target Component:** Incremental Build Pipeline & Manifest Generator (`builder_core.py` / `linker_executor.py` / `manifest.json`)
*   **Analysis & Refactor:** The current incremental build process is executing a "Full Verification" (hashing) for every file, causing it to take as much time as a fresh build. This is an architectural inefficiency.
*   **Optimization (Dual-Logic):** Implement a bifurcated verification logic based on deployment type:
    1.  **Tier 1 (Hardlinked - Fast Path):** Use the file's Inode (`st_ino`). If `Target_Inode == Source_Inode`, treat as unchanged and skip instantly.
    2.  **Tier 2 (Size + mtime Fallback):** If Inode mismatches, check Size + Modified Time (`mtime`). If both match exactly, treat as unchanged. *Safeguard:* Provide an optional "Paranoid Mode" toggle that disables Tier 2, forcing Hash validation if Inode mismatches, to prevent false positives from spoofed mtimes.
    3.  **Tier 3 (Hash/Rebuild Escalation):** If Size or mtime differs, escalate immediately. For hardlinks, immediately delete target and rebuild the link.
*   **Manifest Persistence (Atomic):** Manifest updates must be atomic and durable. Write the updated state to a `manifest.json.tmp` file and perform an OS-level atomic swap replacing the old manifest only after a successful full pass, preventing manifest drift during crashes.

### TASK-A03: Reporting Enhancements
**Target Component:** HTML Report Generator (`report_generator.py` or equivalent)
*   **Categorization & Causality:** Separate files into distinct categories to prevent semantic overloading ("Failed", "Unchanged", "Excluded"). Furthermore, attach causality tags to these entries for diagnostic visibility (e.g., `Excluded (rule: .log)` or `Failed (stage: permission denied)`).

### TASK-A04: UI & UX Improvements
**Target Component:** GUI / Main Application Window
*   **Show Report Button:** Add a "Show Report" button within the Standalone Manager Tab that opens the `report.html` in the user's default web browser.
*   **Post-Build Prompt:** Implement a confirmation dialog/message box that appears immediately after the build process completes, asking the user: "Do you want to view the build report?". Provide a "Don't show again" toggle or configuration setting to prevent interrupt friction for batch-automation users.

### TASK-A05: C# Wrapper Logic Refinement
**Target Component:** C# Standalone Wrapper
*   **Pre-Launch Backup Clarification/Fix:** Ensure the wrapper explicitly backs up any existing `plugins.txt`, `loadorder.txt`, and save files in the global `AppData` and `Documents` game folders *before* copying the fresh files from the MO2 payload. This prevents data loss of the user's global state.
*   **Post-Exit Save Cleanup:** Update the wrapper to sync localized saves from `Documents` back to MO2 using a true transactional model (e.g., copy to a staging temp folder in MO2 -> verify checksum/integrity -> perform atomic swap using Windows API `MoveFileEx` -> finally delete the source from global `Documents`). This prevents partial corruption during crashes.

### TASK-A06: Forcing Standalone Generated Files
**Target Component:** Deployment Engine
*   **Override MO2 State:** Update the logic to automatically detect and hardlink the contents of `standalone_generated_files` after the main overwrite phase. This is an **intentional divergence** from MO2 semantics. To prevent "ghost behavior", this override must be explicitly flagged in the HTML report summary count (e.g., "X files included via override").
*   **Precedence Rule & Scope Limit (Allowlist):** Forced inclusion overrides general exclusion rules, but must operate on a strict **allowlist** basis. Only explicitly defined runtime file extensions (e.g., `.dll`, `.exe`, `.ini`, `.json`, `.txt`) within `standalone_generated_files` are permitted, rather than relying on a blacklist.

## 3. Acceptance Criteria
1. No `.log` files, `Logs` folders, or `backup` folders are present in the final standalone directory.
2. Incremental builds of an unchanged dataset (minimum 1,000 files) execute in ≤10% of the time required for a fresh build on the same machine/dataset.
3. The HTML report cleanly separates "Unchanged" and "Excluded" files from "Failed" files.
4. The GUI features a working "Show Report" button and prompts the user after a build.
5. The C# wrapper safely backs up existing global files before deployment, and cleans up generated saves from the global `Documents` folder after syncing them back to MO2.
6. Files within `standalone_generated_files` are successfully hardlinked into the standalone build regardless of their MO2 checkbox status.
