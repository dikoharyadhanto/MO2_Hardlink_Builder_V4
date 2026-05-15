# ANT TEST STRATEGY — 002-v0.5
**Project:** MO2 Hardlink Builder V4b
**Task:** Verification of v0.5 Refinements
**Status:** COMPLETED (ALL TESTS PASSED)

## 1. Testing Objective
To verify that all refinements defined in `ANT-WO-002-v0.5.md` have been successfully implemented by the CDC without introducing regressions. This includes verifying the Tiered Dual-Logic Incremental engine, atomic manifest updates, strict allowlist overrides, reporting causality, and true transactional save syncing.

## 2. Test Environment
*   **Dataset:** Active MO2 modlist containing a minimum of 1,000 files to ensure measurable relative performance.
*   **Target Build Directory:** Standard Standalone output folder.
*   **Dummy Exclusions:** Create `Logs/`, `Backup/` (testing case-insensitivity), and `backup_old/` (testing exact-match isolation). Add `.log` files randomly.
*   **Dummy Saves:** Place `TEST_SAVE.ess` in the global `Documents\My Games\[Game]\Saves` folder to test wrapper transactional synchronization.

## 3. Execution Phases

### Phase 1: Strict Exclusions & Allowlist Inclusions
1. Inject the dummy exclusion files/folders (`Logs/`, `Backup/`, `backup_old/`) into an active mod.
2. Ensure `standalone_generated_files` is *disabled* in MO2. Add two files inside it: `engine.dll` (allowed extension) and `debug.log` (blacklisted extension).
3. Run a Fresh Build.
4. **Pass Condition (Exclusions):** Verify `Logs/`, `Backup/`, and `.log` files are completely missing from the Standalone folder. Verify `backup_old/` *was* deployed (proving exact-match logic).
5. **Pass Condition (Allowlist Inclusions):** Verify `engine.dll` was deployed from the disabled folder, but `debug.log` was excluded.
6. **Pass Condition (Report Visibility):** Verify the HTML report explicitly lists `engine.dll` under a tag stating "Included via override".

### Phase 2: Tiered Incremental Logic & Atomic Manifest
1. Run a Fresh Build (≥1000 files) and record the base execution time.
2. **Sub-Test A (Tier 1 Speed):** Run an Incremental Build with zero changes.
3. **Pass Condition (Speed):** Execution time must be ≤10% of the Fresh Build time.
4. **Sub-Test B (Tier 2 Safeguard):** Enable "Paranoid Mode". Spoof a file's `mtime` without changing its size. Run Incremental Build.
5. **Pass Condition (Paranoid Mode):** Verify the system catches the mismatch via Hash check and rebuilds the file, bypassing the Tier 2 skip.
6. **Pass Condition (Report Causality):** Verify the `report.html` separates "Unchanged", "Excluded", and "Failed", and includes reason tags (e.g., `Excluded (rule: exact dir match)`).
7. **Pass Condition (Atomic Manifest):** During a build, verify `manifest.json.tmp` is created and only swapped to `manifest.json` after completion.

### Phase 3: UI & UX Verification
1. Open the application GUI.
2. **Pass Condition (UI):** Locate and click the "Show Report" button in the Standalone Manager Tab. Verify it opens the HTML report.
3. Run a minimal build.
4. **Pass Condition (UX):** A post-build prompt must appear asking to view the report. Verify the presence of a "Don't show again" toggle.
5. **Pass Condition (UX Config):** Enable the toggle, run another build, and verify the prompt is successfully suppressed.

### Phase 4: Transactional Wrapper Verification
1. Place `TEST_SAVE.ess` in the global `Documents\My Games\[Game]\Saves` directory.
2. Launch the standalone game via the wrapper. Create a new save (`NEW_STANDALONE_SAVE.ess`), then exit.
3. **Pass Condition (Pre-Launch Backup):** Verify `TEST_SAVE.ess` was safely backed up before launch and restored after exit.
4. **Pass Condition (Transactional Sync):** Verify `NEW_STANDALONE_SAVE.ess` was synced to MO2 and deleted from global `Documents`.
5. **Pass Condition (Failure Simulation):** Simulate a mid-sync failure (e.g., abruptly kill the wrapper process while it is copying the save back to MO2). Verify that the global save in `Documents` is *not* deleted, proving the atomic swap logic functions correctly as a fail-safe.
