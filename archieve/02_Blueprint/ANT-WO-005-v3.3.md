# ANT-WO-005-v3.3 — Work Order: Wrapper Redirection Fix & V3 Feature Restoration

> [!IMPORTANT]
> **Logic Dependencies**: `GMN-PRD-005-v3.3`, `GMN-FLOW-005-v3.3`
> **Context**: The C# Wrapper currently attempts to sandbox AppData by modifying `psi.EnvironmentVariables["LOCALAPPDATA"]`. However, most games (like Skyrim/Fallout) use `SHGetFolderPath` which bypasses environment variables, causing `plugins.txt` and `loadorder.txt` to not be read.

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Work Order (WO) |
| **Version** | v3.3 |
| **Issued By** | ANT — Technical Foreman |
| **Issued To** | CDC — Lead Developer (Claude Code) |
| **Status** | **COMPLETED / IMPLEMENTED** |

---

## 2. Root Cause & Solution

### Problem
The wrapper system fails to redirect the game's AppData reads because it relies solely on injecting the `LOCALAPPDATA` environment variable. Games using `SHGetFolderPath` read the real `C:\Users\...\AppData\Local` directly, completely ignoring the injected variable. Thus, `plugins.txt` deployed to the standalone profile's `AppData` folder are never seen by the game.

### Solution
Instead of relying on environment variable injection, the C# wrapper must physically copy the required AppData files (`plugins.txt`, `loadorder.txt`) from the MO2 profile to the real `LOCALAPPDATA` folder before launching the game, just like it already does for the INI files in the Documents folder. After the game exits, it should clean them up and restore any backups.

---

## 3. Implementation Task

### Task 1: Update C# Wrapper Template (FEAT-10 Fix)
**File:** `model/engines/feature_generator.py` (`_CS_TEMPLATE`)

1. **Remove Environment Variable Injection:**
   Remove the `psi.EnvironmentVariables["LOCALAPPDATA"]` logic from the C# wrapper.

2. **Add AppData Physical Sync Logic:**
   Update the C# template to backup the existing real `LOCALAPPDATA` game folder and copy `plugins.txt` and `loadorder.txt` from the `mo2Profile` directly into the real `LOCALAPPDATA` folder before launch.

3. **Template Variables Needed:**
   Add `{APPDATA_NAME}` to the `_generate_cs_source` replacement logic to resolve the target folder name inside `AppData\Local`.

   ```csharp
   // Inside Main() pre-launch:
   string appDataName = "{APPDATA_NAME}";
   string realAppDataPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), appDataName);
   
   // Backup existing plugins.txt/loadorder.txt and copy from mo2Profile
   ```

4. **Restore Logic:**
   Update the `finally` block and `RecoverIfNeeded` to properly restore the real `LOCALAPPDATA` files after the game exits or crashes.

---

## 4. Success Indicators

| # | Indicator | Test |
| :--- | :--- | :--- |
| SI-01 | `plugins.txt` and `loadorder.txt` are physically present in the real `AppData\Local\<GameName>` folder while the wrapper is running. | STR-WRAP-01 |
| SI-02 | The original `AppData\Local` files are successfully restored after the wrapper exits. | STR-WRAP-02 |
| SI-03 | Crash recovery successfully restores the `AppData\Local` files on the next run. | STR-WRAP-03 |

---

*End of WO*
