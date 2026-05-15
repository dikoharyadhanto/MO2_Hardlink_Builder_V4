# ANT WORK ORDER — 002-v0.4
**Project:** MO2 Hardlink Builder V4b
**Task:** Vanilla Asset Starvation Fix (Base Game Hardlink Correction)
**Status:** PENDING IMPLEMENTATION

## 1. Executive Summary
During the V4 refactoring process, a flawed instruction in the blueprint (`V3_UPDATE_GUIDANCE.md` - FEAT-05) directed the `ScannerEngine` to explicitly exclude the base game's `Data/` directory when performing the initial "Base Game Hardlinking" phase. 

This exclusion resulted in the Standalone environment completely missing all vanilla master files (`Skyrim.esm`, `Update.esm`, etc.) and critical archives (`Skyrim - Interface.bsa`, `Skyrim - Meshes0.bsa`, and Creation Club content). Without these core assets, the game engine experiences severe asset starvation and throws an `EXCEPTION_ACCESS_VIOLATION` (0x00) crash at the Main Menu when components like `CommunityShaders.dll` or `SKSEMenuFramework` attempt to render UI elements.

This Work Order directs the correction of `scanner_engine.py` to restore the legacy V3 behavior, where the vanilla `Data` directory is correctly hardlinked as the foundation before MO2 mods are deployed over it.

## 2. Root Cause Analysis
*   **V3 Legacy Behavior:** The V3 `LinkerExecutor._recursive_vanilla_deploy()` method iterated over the entire base game directory, skipping only `_commonredist`. It successfully hardlinked the vanilla `Data/` folder.
*   **V4 Architectural Defect:** In V4's `model/engines/scanner_engine.py`, the `scan_base_game()` method contains:
    `excluded_dirs = {"data", "mods", "_commonredist"}`
*   **Impact:** By skipping `"data"`, 93 critical `.bsa` and `.esm` files were missing from the Standalone `Data` folder.

## 3. Implementation Directives

### TASK-A01: Correct Base Game Exclusion Logic
**Target File:** `model/engines/scanner_engine.py`
**Method:** `scan_base_game()`
*   Remove `"data"` from the `excluded_dirs` set.
*   The set should now read: `excluded_dirs = {"mods", "_commonredist"}`
*   Ensure that the recursive scanner correctly traverses the vanilla `Data/` folder and registers its contents in `base_mapping`.

### TASK-A02: Conflict Resolution Validation (LinkerExecutor)
**Target File:** `model/engines/linker_executor.py` (Verification Only)
*   Verify that `LinkerExecutor.execute_mapping()` correctly deletes target files before hardlinking. Since base game files are deployed first, any MO2 mod that overwrites a vanilla file (e.g., an SKSE script or a replaced mesh) must successfully delete the base game hardlink and replace it with the mod's hardlink.

## 4. Acceptance Criteria
1. The standalone `Data` directory must contain the exact same number of vanilla `.bsa` and `.esm` files as the real game directory (e.g., 565 BSAs).
2. The Standalone game must launch and reach the Main Menu without the previous `0x00` rendering crash.
