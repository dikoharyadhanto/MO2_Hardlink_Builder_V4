# CDC-WALK-002-v0.2 — Pre-Implementation Walkthrough: Wrapper AppData Physical Sync

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.2.md` + `ANT-STR-002-v0.2.md`
> **Status**: Pre-Implementation Walkthrough — PENDING ANT/Director approval before coding begins.

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Walkthrough (WALK) |
| **Version** | v0.2 |
| **Status** | **IMPL COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.2.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.2.md` |

---

## 2. Task Interpretation

### What I understand must be implemented:

The C# wrapper currently injects `psi.EnvironmentVariables["LOCALAPPDATA"]` to redirect the game's AppData reads to the MO2 profile's `standalone_profile/AppData/Local`. This **does not work** because Bethesda games (Skyrim, Fallout 4, Starfield) use the Win32 `SHGetFolderPath` API, which reads the real registry-backed folder path and completely ignores environment variables.

**Result**: `plugins.txt` and `loadorder.txt` deployed to the standalone profile's AppData are never read by the game.

### The fix (per ANT-WO-002-v0.2):

Replace environment variable injection with **physical file copy** — the same pattern the wrapper already uses for INI files in `Documents\My Games\`:

1. **Before launch**: Backup real `%LOCALAPPDATA%\<AppDataName>\plugins.txt` and `loadorder.txt`, then copy the MO2 profile versions into the real `%LOCALAPPDATA%`.
2. **After game exit**: Restore the originals from backup.
3. **Crash recovery**: If the wrapper is killed before cleanup, detect orphaned `.bak_standalone` files on next launch and restore them before the next injection cycle.

---

## 3. Proposed Approach

### 3.1 C# Template Changes (`_CS_TEMPLATE` in `feature_generator.py`)

**Pattern**: Mirror the existing INI injection logic but target `%LOCALAPPDATA%\<appdata_name>\` instead of `Documents\My Games\<docs_name>\`.

#### 3.1.1 New Variable: `{APPDATA_NAME}`
- Add a new placeholder `{APPDATA_NAME}` to the C# template (alongside existing `{DOCS_NAME}`, `{GAME_NAME}`, etc.).
- Resolve it in `_generate_cs_source()` via a new parameter `appdata_name`.

#### 3.1.2 Remove Environment Variable Injection
Remove lines 300-308 from the current template:
```csharp
// REMOVE THIS BLOCK:
if (isStealth)
{
    string localAppData = Path.Combine(mo2Profile, "standalone_profile", "AppData", "Local");
    if (Directory.Exists(localAppData))
    {
        psi.EnvironmentVariables["LOCALAPPDATA"] = localAppData;
        Log("Set LOCALAPPDATA to: " + localAppData);
    }
}
```

#### 3.1.3 Add Pre-Launch AppData Sync
After the existing INI injection block (line ~287), add a new block:
```csharp
// AppData Physical Sync: copy plugins.txt + loadorder.txt to real LOCALAPPDATA
string appDataName = "{APPDATA_NAME}";
string realAppDataPath = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), appDataName);
List<string[]> appDataBackupPairs = new List<string[]>();

if (isStealth && !string.IsNullOrEmpty(appDataName))
{
    // Primary source: MO2 profile root (MO2 stores plugins.txt/loadorder.txt here)
    string profileAppData = mo2Profile;
    // Fallback: standalone_profile synced directory if not found in profile root
    if (!File.Exists(Path.Combine(profileAppData, "plugins.txt")))
        profileAppData = Path.Combine(mo2Profile, "standalone_profile", "AppData", "Local", appDataName);

    string[] appDataFiles = new string[] { "plugins.txt", "loadorder.txt" };

    if (Directory.Exists(profileAppData))
    {
        Directory.CreateDirectory(realAppDataPath);
        foreach (string fileName in appDataFiles)
        {
            string src = Path.Combine(profileAppData, fileName);
            if (!File.Exists(src)) continue;

            string dest = Path.Combine(realAppDataPath, fileName);
            string backup = dest + ".bak_standalone";
            if (File.Exists(dest))
            {
                File.Copy(dest, backup, true);
                Log("Backed up AppData: " + fileName);
            }
            File.Copy(src, dest, true);
            Log("Injected AppData: " + fileName);
            appDataBackupPairs.Add(new string[] { dest, backup });
        }
    }
}
```

#### 3.1.4 Update `WriteState` / `RecoverIfNeeded`
- **State file**: Extend `_wrapper_state.json` to include `appdata_pairs` alongside `ini_pairs`, using the same `<<<`/`>>>` encoding.
- **WriteState**: Add `appDataPairs` parameter.
- **RecoverIfNeeded**: Parse `appdata_pairs` from state and restore the real `%LOCALAPPDATA%` files on recovery.

#### 3.1.5 Update `finally` Block
- After the existing INI restoration loop, add a parallel loop to restore AppData files from `.bak_standalone`.
- If no backup exists (i.e., the file didn't exist before injection), delete the injected file to leave the folder clean.
- Include `appDataBackupPairs` in the `SYNC_PENDING` state write.

### 3.2 Python-side Changes (`feature_generator.py`)

#### `_generate_cs_source()`
- Add `appdata_name: str` parameter.
- Add `src.replace("{APPDATA_NAME}", appdata_name)` to the replacement chain.

#### `wrap_loaders()`
- Already receives `appdata_name` parameter (line 571) — currently unused by the template. No signature change needed.
- Pass `appdata_name` to `_generate_cs_source()`.

---

## 4. Files to Create/Modify

| File | Action | Purpose |
| :--- | :--- | :--- |
| `model/engines/feature_generator.py` | MODIFY | Update `_CS_TEMPLATE` (remove env var injection, add physical AppData sync + recovery), update `_generate_cs_source()` to inject `{APPDATA_NAME}` |

**All changes are within `03_Build/`.** No other files require modification — `deployment_controller.py` already passes `appdata_name` to `wrap_loaders()`, and `game_profiles.json` already has `appdata_name` for all three game profiles.

---

## 5. Dependencies

**None.** No new packages or version changes required. The C# template uses only `System`, `System.IO`, `System.Diagnostics`, `System.Collections.Generic`, and `System.Reflection` — all .NET Framework standard libraries already referenced.

---

## 6. Flags / Risks

| # | Risk | Severity | Mitigation |
| :--- | :--- | :--- | :--- |
| F-01 | **Real AppData file lock**: If the game is already running (from a non-wrapper launch) and has `plugins.txt` locked, `File.Copy()` will throw. | Low | This is the same risk as the INI injection which already works. The `try/catch` wrapper logs the failure and continues. |
| F-02 | **No `plugins.txt` in MO2 profile**: If the profile doesn't contain `plugins.txt`, the block is a no-op (guarded by `File.Exists(src)`). No error, no injection. | None | By design — skip missing files silently. |
| F-03 | **State file backward compat**: Existing `_wrapper_state.json` files from pre-v3.3 wrappers won't have `appdata_pairs`. | Low | `RecoverIfNeeded` already handles missing keys via `fields.ContainsKey()` — a missing `appdata_pairs` key will produce an empty list and skip AppData recovery. Fully backward-compatible. |
| F-04 | **AppData folder doesn't exist yet**: First-time game launch where `%LOCALAPPDATA%\<GameName>\` hasn't been created. | Low | `Directory.CreateDirectory(realAppDataPath)` handles this. If the folder is created by the wrapper but was empty before, the `finally` block cleans up injected files. |

---

## 7. Success Indicator Mapping

| WO Indicator | Implementation Point |
| :--- | :--- |
| **SI-01**: `plugins.txt` and `loadorder.txt` present in real AppData during wrapper execution | Pre-launch block copies from MO2 profile → `Environment.GetFolderPath(LocalApplicationData)\<appdata_name>\` |
| **SI-02**: Original AppData files restored after wrapper exits | `finally` block iterates `appDataBackupPairs` and restores from `.bak_standalone` |
| **SI-03**: Crash recovery restores AppData files on next run | `RecoverIfNeeded()` parses `appdata_pairs` from `_wrapper_state.json` and restores before next injection cycle |

---

*Awaiting ANT/Director approval to proceed to implementation.*
