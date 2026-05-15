# ANT TEST STRATEGY — 002-v0.4
**Project:** MO2 Hardlink Builder V4b
**Task:** Vanilla Asset Starvation Fix
**Status:** PENDING EXECUTION

## 1. Testing Objective
To definitively prove that removing `"data"` from the `ScannerEngine`'s exclusion list resolves the asset starvation crash, ensuring all vanilla ESMs and BSAs are successfully hardlinked into the Standalone environment before MO2 mods are overlaid.

## 2. Test Environment
*   **Target Directory:** `F:\Skyrim_Standalone`
*   **Comparison Directory:** `F:\Skyrim_Standalone_V3`
*   **Base Game Directory:** Real Skyrim Special Edition folder.

## 3. Execution Phases

### Phase 1: Pre-Implementation Verification (Baseline)
1. Verify the current crash state in V4 by checking the BSA count:
    *   `Get-ChildItem -Path "F:\Skyrim_Standalone\Data" -Filter "*.bsa" | Measure-Object` -> Should yield 472.
2. Confirm that `F:\Skyrim_Standalone\Data\Skyrim.esm` is missing.

### Phase 2: Post-Implementation Verification (File Sync)
1. Implement TASK-A01 in `scanner_engine.py` (change `excluded_dirs = {"data", "mods", "_commonredist"}` to `{"mods", "_commonredist"}`).
2. Execute a Full Rebuild of the Hardlink Builder.
3. Count the BSAs in the target directory:
    *   `Get-ChildItem -Path "F:\Skyrim_Standalone\Data" -Filter "*.bsa" | Measure-Object` -> Must yield 565 (matching V3).
4. Verify the existence of `F:\Skyrim_Standalone\Data\Skyrim.esm` and `Skyrim - Interface.bsa`.

### Phase 3: Runtime Stability
1. Launch `_skse64_loader_original.exe` (or let the wrapper handle it) from the newly built Standalone directory.
2. Observe the startup sequence.
3. **Pass Condition:** The game successfully bypasses the `0x00` memory read violation and reaches the Main Menu.
4. **Fail Condition:** The game still crashes at startup, indicating secondary starvation or other structural issues.
