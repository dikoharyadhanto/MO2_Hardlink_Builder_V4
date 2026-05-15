# ANT-STR-002-v0.2 — Test Strategy: Wrapper Redirection Fix

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.2`
> **Context**: Validates that the C# Wrapper physically copies `AppData` configuration (`plugins.txt`, `loadorder.txt`) to the real `%LOCALAPPDATA%` instead of relying on environment variable injection, which games like Skyrim bypass via `SHGetFolderPath`.

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Strategic Test Plan (STR) |
| **Version** | v0.2 |
| **Issued By** | ANT — Technical Foreman |
| **Execution** | Automated (`test_wrapper.py`) |
| **Status** | **PASSED (Golden Pass Issued)** |

---

## 2. Test Cases

### STR-WRAP-01: AppData Physical Injection (Success Path)

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Create a dummy `plugins.txt` inside `%LOCALAPPDATA%\Skyrim Special Edition\` (e.g., `*Skyrim.esm`). | Baseline established. |
| 2 | Ensure the MO2 profile has a distinct `plugins.txt` (e.g., `*Skyrim.esm`, `*MyMod.esp`). | Profile state is different from real AppData. |
| 3 | Build the standalone and launch the game via the generated wrapper (`skse64_loader.exe`). | Game launches successfully. |
| 4 | While the game is running, inspect `%LOCALAPPDATA%\Skyrim Special Edition\plugins.txt`. | The file MUST contain `*MyMod.esp` (MO2 profile state). |

---

### STR-WRAP-02: AppData Post-Launch Restoration

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Close the game normally after executing STR-WRAP-01. | Wrapper finishes execution. |
| 2 | Inspect `%LOCALAPPDATA%\Skyrim Special Edition\plugins.txt`. | The file MUST revert back to its original state (`*Skyrim.esm`). |
| 3 | Inspect `%LOCALAPPDATA%\Skyrim Special Edition\`. | Ensure no `.bak_standalone` files are left behind. |

---

### STR-WRAP-03: AppData Crash Recovery (Deferred Restoration)

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Launch the game via the wrapper. | MO2 `plugins.txt` is injected into real AppData. |
| 2 | Force kill the wrapper process (`skse64_loader.exe`) via Task Manager, simulating a hard crash. | Wrapper does not reach its `finally` restoration block. |
| 3 | Verify `%LOCALAPPDATA%\Skyrim Special Edition\plugins.txt` still contains the MO2 injected state. | Expected; the process was killed before cleanup. |
| 4 | Relaunch the wrapper. | Wrapper detects crash via `_wrapper_state.json`. |
| 5 | Wrapper performs recovery. | The original `plugins.txt` is restored immediately BEFORE the next injection cycle begins. |

---

## 3. UAT Sync (Golden Pass Requirements)

- **Technical Verdict**: **GOLDEN PASS**. Automated execution via `test_wrapper.py` confirmed physical AppData injection, complete restoration on exit, and robust crash recovery via `_wrapper_state.json`.
- **Director Override**: Confirmed.

*Golden Pass has been issued. No false positives or orphaned backup files were detected during the crash recovery simulation.*
