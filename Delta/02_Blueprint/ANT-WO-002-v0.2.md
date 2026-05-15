# Work Order

> [!IMPORTANT]
> **Runtime Gate**: Created with `delta wo new`.

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Work Order (WO) |
| **Runtime State** | PENDING |
| **DI Reference** | `DIR-DI-002-v1.0.md` |
| **STRAT Reference** | `GMN-STRAT-002-v1.0.md` |
| **Source** | `archieve/02_Blueprint/ANT-WO-005-v3.3.md` |

---

## 2. Work Order Summary

> **Task Title:** Wrapper AppData Physical Sync Fix & V3 Feature Restoration
> **Summary:** C# wrapper uses environment variable injection (`LOCALAPPDATA`) to redirect game AppData reads, but games using `SHGetFolderPath` bypass this entirely — `plugins.txt` and `loadorder.txt` are never seen. Fix: physically copy AppData files to real `LOCALAPPDATA` folder before launch (same pattern as INI sync). Remove env var injection. Add backup/restore for crash resilience.

## 3. Action Items

1. [ ] Remove `psi.EnvironmentVariables["LOCALAPPDATA"]` from C# wrapper template in `feature_generator.py`
2. [ ] Add `{APPDATA_NAME}` variable for physical AppData path resolution
3. [ ] Update wrapper to backup real AppData files, copy from MO2 profile, restore on exit/crash

---

*Source: `ANT-WO-005-v3.3.md` — Wrapper Redirection Fix*
