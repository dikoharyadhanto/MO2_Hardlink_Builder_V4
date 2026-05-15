# CDC-IMPL-005-v3.3 — Implementation Log: Wrapper AppData Physical Sync

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-005-v3.3.md`
> **Build Output:** `03_Build/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Implementation Log (IMPL) |
| **Version** | v3.3 |
| **Status** | **COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-005-v3.3.md` |
| **Test Plan Ref** | `ANT-STR-005-v3.3.md` |
| **Walkthrough Ref** | `CDC-WALK-005-v3.3.md` |

---

## 2. Scope of Change

**Single file modification**: `model/engines/feature_generator.py`

### 2.1 What Changes

| Region | Current Behavior | New Behavior |
| :--- | :--- | :--- |
| `_CS_TEMPLATE` — Pre-launch block | Injects `psi.EnvironmentVariables["LOCALAPPDATA"]` pointing to MO2 standalone profile | Physically copies `plugins.txt` + `loadorder.txt` from MO2 profile to real `%LOCALAPPDATA%\<AppDataName>\`, with `.bak_standalone` backup of originals |
| `_CS_TEMPLATE` — `WriteState()` | Stores `ini_pairs` only | Stores `ini_pairs` + `appdata_pairs` |
| `_CS_TEMPLATE` — `RecoverIfNeeded()` | Restores INI files only | Restores INI files + AppData files (`plugins.txt`, `loadorder.txt`) |
| `_CS_TEMPLATE` — `finally` block | Restores INI files, syncs saves, deletes state | Additionally restores AppData files from `.bak_standalone` |
| `_CS_TEMPLATE` — `ProcessStartInfo` | Sets `psi.EnvironmentVariables["LOCALAPPDATA"]` | Block removed entirely — `UseShellExecute = false` remains for working directory control |
| `_generate_cs_source()` | 4 replacements: `IS_STEALTH`, `MO2_PROFILE_PATH`, `DOCS_NAME`, `GAME_NAME` | 5 replacements: adds `APPDATA_NAME` |

### 2.2 What Does NOT Change

- `wrap_loaders()` signature — already has `appdata_name` parameter
- `deployment_controller.py` — already passes `appdata_name` from `game_profile.appdata_name`
- `game_profiles.json` — already contains `appdata_name` for all 3 profiles
- `_find_csc()`, `_compile_launcher()`, `_deploy_bat_fallback()` — untouched
- `write_launch_instructions()`, `write_steam_appid()` — untouched
- All D1–D8 invariants preserved

---

## 3. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **Physical copy over symlink/junction** | Symlinks require elevated privileges on most Windows configurations. Physical copy of 2 small text files (~1 KB each) is negligible overhead and requires zero special permissions. Matches the proven INI injection pattern. |
| TD-02 | **Separate `appdata_pairs` in state file** | Keeps INI recovery and AppData recovery logically independent. A pre-v3.3 state file with no `appdata_pairs` key is handled gracefully via `ContainsKey()` checks — zero backward-compat risk. |
| TD-03 | **Profile lookup order: `mo2Profile/` root → fallback `mo2Profile/standalone_profile/AppData/Local/<appDataName>`** | MO2 stores `plugins.txt` and `loadorder.txt` directly in the profile root (e.g., `profiles/Default/plugins.txt`), not in a game-named subfolder. The fallback path covers the `standalone_profile` AppData directory created by `ProfileSync.deploy_mo2_profile()`. Primary path is checked with `File.Exists()` per file; fallback is directory-level. |
| TD-04 | **Delete injected file if no backup exists** | If the real `%LOCALAPPDATA%\<game>\plugins.txt` didn't exist before injection (no `.bak_standalone`), the wrapper must delete the injected copy in `finally` to leave the system in the same state as before. This prevents accumulation of orphaned files. |
| TD-05 | **`UseShellExecute = false` retained** | Even though env-var injection is removed, `UseShellExecute = false` is still needed for `WorkingDirectory` to take effect per MSDN docs. No behavioral change. |

---

## 4. Files Modified

| File Path | Action | Purpose |
| :--- | :--- | :--- |
| `model/engines/feature_generator.py` | MODIFY | Task 1: Update `_CS_TEMPLATE` (remove env var injection, add AppData physical sync + crash recovery). Update `_generate_cs_source()` to inject `{APPDATA_NAME}`. |

**Total files modified: 1**

---

## 5. STR Mapping

| STR ID | Scenario | Implementation Point |
| :--- | :--- | :--- |
| STR-WRAP-01 | AppData Physical Injection (Success Path) | Pre-launch block: `File.Copy(src, dest, true)` for `plugins.txt` and `loadorder.txt` to real `%LOCALAPPDATA%\<appdata_name>\` |
| STR-WRAP-02 | AppData Post-Launch Restoration | `finally` block: iterate `appDataBackupPairs`, `File.Copy(backup, dest, true)` + `File.Delete(backup)` |
| STR-WRAP-03 | AppData Crash Recovery (Deferred Restoration) | `RecoverIfNeeded()`: parse `appdata_pairs` from `_wrapper_state.json`, restore originals before next injection cycle |

---

## 6. Phase Status

| Phase | Status | Notes |
| :--- | :--- | :--- |
| Pre-Implementation Walkthrough | `[x] Complete` | `CDC-WALK-005-v3.3.md` submitted |
| ANT/Director Approval | `[x] Approved with revision` | Path mismatch corrected per ANT feedback |
| Implementation | `[x] Complete` | `feature_generator.py` updated — D9 AppData physical sync |
| Handoff to ANT QA | `[x] READY` | — |

---

## 7. Technical Debt & Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | Games using non-standard AppData subfolder names (not matching `appdata_name` in `game_profiles.json`) will not have their `plugins.txt` injected. | Low | `appdata_name` is already configurable per game profile. Adding a new game requires only a JSON entry. |
| TR-02 | If a user manually places `plugins.txt` in real AppData between builds (outside MO2), the backup/restore cycle will overwrite their manual changes during the wrapper's lifecycle, but restore them after. | None | This is the intended behavior — the wrapper owns AppData during game execution only. |

---

*Implementation complete. ANT: proceed to run `ANT-STR-005-v3.3.md` (STR-WRAP-01, STR-WRAP-02, STR-WRAP-03) against the compiled wrapper.*
