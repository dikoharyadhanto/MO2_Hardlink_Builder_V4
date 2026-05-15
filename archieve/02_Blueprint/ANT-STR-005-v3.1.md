# ANT-STR-005-v3.1 — Test Plan: MO2 Hardlink Builder (V3-Based Rebuild)

> [!IMPORTANT]
> **Paired With:** `ANT-WO-005-v3.1.md`
> **This STR supersedes all previous STR documents (v3.1, v3.2, v3.3). Those documents are deleted.**

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Technical Test Suite (STR) |
| **Version** | v3.1 |
| **Issued By** | ANT — Technical Foreman |
| **Date** | 2026-04-20 |
| **Status** | Active — Awaiting CDC IMPL output |

---

## 2. Testing Principles

- All tests are performed by ANT against CDC's IMPL output
- CDC does not self-certify — ANT validates independently
- Every test must be reproducible with a documented test procedure
- A "PASS" requires all criteria met; a single unmet criterion = "FAIL"
- Silent failures (no log, no error, no feedback to user) always = FAIL regardless of other behavior

---

## 3. Phase 1 Tests — Foundation

### STR-P1-01: V3 Core Preserved

**What it verifies:** V3 core files are untouched after clone and restructure.

| Step | Procedure |
| :--- | :--- |
| 1 | Compare `Scripts/scanner_engine.py`, `state_manager.py`, `linker_executor.py`, `path_utils.py`, `profile_sync.py`, `verification_engine.py`, `cleaner_engine.py` against original V3 archive via `diff` |
| 2 | Confirm zero diff on all listed core files (excluding imports updated for new folder paths) |

**Pass Criteria:**
- No logic changes in any V3 core file
- Only allowed delta: import path updates if files moved to `model/engines/`

---

### STR-P1-02: MVC Layer Separation

**What it verifies:** `plugin_ui.py` is correctly split into model/view/controller.

| Step | Procedure |
| :--- | :--- |
| 1 | Grep `model/` directory for Qt imports (`from PySide6`, `from PyQt`) |
| 2 | Confirm `model/` layer has zero Qt imports |
| 3 | Confirm `view/` layer contains only Qt widget code, no business logic |
| 4 | Confirm `controller/` bridges model ↔ view |

**Pass Criteria:**
- `model/` has zero Qt imports
- No business logic in `view/` layer
- No UI code in `model/` layer

---

### STR-P1-03: PySide6 Compatibility Shim

**What it verifies:** `qt_compat.py` correctly falls back across Qt bindings.

| Step | Procedure |
| :--- | :--- |
| 1 | With PySide6 installed: verify application starts and loads normally |
| 2 | With PySide6 uninstalled / PyQt6 only: verify application still loads |
| 3 | With PyQt6 uninstalled / PyQt5 only: verify application still loads |

**Pass Criteria:**
- Application starts successfully under all three Qt binding scenarios
- No crash on import under any supported Qt version

---

### STR-P1-04: Baseline Performance Benchmark

**What it verifies:** New project structure does not regress speed vs. original V3.

| Step | Procedure |
| :--- | :--- |
| 1 | Run full scan + deploy cycle on a known modlist (1000+ mods) using original V3 |
| 2 | Record: scan time, deploy time, total time |
| 3 | Run same cycle on new V3-based build after PHASE 1 |
| 4 | Compare results |

**Pass Criteria:**
- Scan time: ≤ V3 original (within 5% tolerance)
- Deploy time: ≤ V3 original (within 5% tolerance)
- No functional regressions in output

---

## 4. Phase 2 Tests — Critical Bug Fixes

### STR-P2-01: mobase API Load Order (FIX-01)

**What it verifies:** Load order is read from `mobase` API, not heuristic keyword detection.

| Step | Procedure |
| :--- | :--- |
| 1 | Run scan while MO2 API is available. Confirm mods are loaded in correct MO2 priority order |
| 2 | Simulate API unavailability (mock or disconnect). Confirm tool halts with explicit "API Link Failure" message |
| 3 | Confirm no silent fallback to keyword guessing occurs |

**Pass Criteria:**
- API available: load order matches MO2 exactly
- API unavailable: explicit halt with "API Link Failure" — no silent fallback, no guessing

---

### STR-P2-02: Inode Validation After Hardlink (FIX-02)

**What it verifies:** Every hardlink is verified by inode comparison. Pseudo-hardlinks are detected and logged.

| Step | Procedure |
| :--- | :--- |
| 1 | Deploy to NTFS volume. Inspect log — confirm every `os.link()` call has a corresponding inode match log entry |
| 2 | Simulate pseudo-hardlink (FAT32 or cross-volume target). Confirm: target deleted, fallback to copy, log entry with "pseudo-hardlink" label |
| 3 | Confirm no hardlink fallback is silent |

**Pass Criteria:**
- 100% of hardlink calls produce an inode check log entry
- Any pseudo-hardlink triggers: delete target + copy fallback + explicit log entry
- Zero silent fallbacks

---

### STR-P2-03: Transactional Deployment (FIX-03)

**What it verifies:** Deployment is recoverable from mid-run crash.

| Step | Procedure |
| :--- | :--- |
| 1 | Start deployment. Confirm `.deployment_state` file is created before first file is linked |
| 2 | Interrupt deployment at file ~500 (kill process or simulate crash) |
| 3 | Restart tool. Confirm Resume prompt appears |
| 4 | Accept Resume. Confirm deployment continues from checkpoint, not from file 1 |
| 5 | Let deployment complete cleanly. Confirm `.deployment_state` file is removed |

**Pass Criteria:**
- `.deployment_state` written before first file link
- Checkpoint written every 500 files
- Resume prompt appears on restart after interrupted deployment
- Resume continues from last checkpoint
- State file deleted on clean completion

---

### STR-P2-04: Conflict Cache Validation (FIX-04)

**What it verifies:** Corrupt or stale cache is detected and rebuilt, not silently ignored.

| Step | Procedure |
| :--- | :--- |
| 1 | Corrupt the conflict cache file manually (delete version field, truncate JSON) |
| 2 | Start tool. Confirm corrupt cache is detected and logged |
| 3 | Confirm tool rebuilds cache from scratch instead of proceeding with stale data |
| 4 | Confirm no bare `except: pass` silently swallowing the error |

**Pass Criteria:**
- Corrupt cache: detected, logged, rebuilt
- Version mismatch: detected, logged, rebuilt
- No silent swallowing of cache errors

---

### STR-P2-05: Orphan Cleanup Safety (FIX-05)

**What it verifies:** No silent file deletion. User sees preview and confirms before any deletion.

| Step | Procedure |
| :--- | :--- |
| 1 | Trigger orphan cleanup. Confirm preview dialog shows orphan count before deletion |
| 2 | Confirm no files are deleted until user explicitly confirms |
| 3 | Confirm every deletion is logged with full file path |
| 4 | Confirm any deletion error is logged (not silently skipped) |

**Pass Criteria:**
- Preview shown before deletion
- User confirmation required
- Every deletion logged with path
- No silent errors during deletion

---

## 5. Phase 3 Tests — Architecture Support

### STR-P3-01: Game Profiles JSON (ARCH-02)

**What it verifies:** Game-specific strings are loaded from `game_profiles.json`, not hardcoded.

| Step | Procedure |
| :--- | :--- |
| 1 | Grep engine files for hardcoded Skyrim/Fallout/Starfield strings (docs_name, appdata_name, ini_prefix, blacklist_files) |
| 2 | Confirm zero hardcoded game strings remain in engine files |
| 3 | Confirm `game_profiles.json` contains valid `skyrim_se`, `fallout_4`, `starfield` entries |

**Pass Criteria:**
- Zero hardcoded game strings in engine files
- All three profiles present in JSON and loadable at runtime

---

### STR-P3-02: Manifest Version Field (ARCH-03)

**What it verifies:** Version mismatch on manifest load is caught and reported.

| Step | Procedure |
| :--- | :--- |
| 1 | Generate a manifest. Confirm `"version": 3` field present |
| 2 | Manually edit manifest to wrong version (e.g., `"version": 1`). Reload tool |
| 3 | Confirm tool rejects manifest with clear error and forces fresh scan |

**Pass Criteria:**
- Version field present in all generated manifests
- Wrong version: rejected with clear error + fresh scan forced

---

### STR-P3-03: Logging Framework (ARCH-04)

**What it verifies:** No `print()` remains in engine files. All output goes through `logging` module.

| Step | Procedure |
| :--- | :--- |
| 1 | Grep all engine files for `print(` calls |
| 2 | Confirm zero `print()` calls remain |
| 3 | Run a deployment cycle. Confirm log file is created with timestamps and levels (INFO, WARN, ERROR) |
| 4 | Confirm deployment operations are in separate audit trail log |

**Pass Criteria:**
- Zero `print()` in engine files
- Log file created with correct format (timestamp + level + message)
- Deployment audit trail separate and readable

---

## 6. Phase 4 Tests — Director Feedback Features

### STR-P4-01: Base Game Hardlinking (FEAT-05)

**What it verifies:** Base game executables and root assets are hardlinked to standalone before mod deployment.

| Step | Procedure |
| :--- | :--- |
| 1 | Run full build. Confirm standalone folder contains base game EXEs and DLLs |
| 2 | Confirm `Data/` and `mods/` subdirectories are NOT scanned during base game scan |
| 3 | Confirm base game files are hardlinks (inode match), not copies |

**Pass Criteria:**
- Standalone is independently executable (base game files present)
- `Data/` and `mods/` excluded from base game scan
- Base game files are true hardlinks (inode verified)

---

### STR-P4-02: Clean Standalone Button (FEAT-06)

**What it verifies:** Red button deletes standalone contents without triggering rebuild.

| Step | Procedure |
| :--- | :--- |
| 1 | Confirm red "Clean Standalone" button visible in Tab 1 |
| 2 | Click button. Confirm confirmation dialog appears |
| 3 | Confirm standalone folder contents are deleted after confirmation |
| 4 | Confirm no rebuild is triggered |
| 5 | Decline confirmation. Confirm no files are deleted |

**Pass Criteria:**
- Button present in Tab 1
- Confirmation dialog before deletion
- Only deletion occurs — no rebuild triggered
- Cancelling dialog leaves files intact

---

### STR-P4-03: Smooth Progress Bar (FEAT-07)

**What it verifies:** Progress bar updates every 50 files during hardlink loop.

| Step | Procedure |
| :--- | :--- |
| 1 | Run a deployment of 1000+ files. Observe progress bar |
| 2 | Confirm progress bar visibly increments multiple times during deploy (not just once per mod) |
| 3 | Confirm UI does not freeze during update |

**Pass Criteria:**
- Progress bar updates at least every 50 files
- No UI freeze during deployment

---

## 7. Phase 5 Tests — Safety Layer

### STR-P5-01: Crash Logger (FEAT-03)

**What it verifies:** Unhandled exceptions in worker threads produce crash logs, never propagate silently.

| Step | Procedure |
| :--- | :--- |
| 1 | Inject a deliberate exception into `BuildWorker.run()` |
| 2 | Confirm `crash_log_<timestamp>.txt` is written to standalone root |
| 3 | Confirm log contains: exception type, full stack trace, Python version, MO2 profile name, build config |
| 4 | Confirm crash dialog shown to user with log file path |
| 5 | Confirm crash logger itself does not throw an exception |

**Pass Criteria:**
- Crash log written on any unhandled exception
- Log contains all required fields
- Crash dialog shown with path
- Crash logger is exception-safe (never throws)

---

### STR-P5-02: Save Export Guard (FEAT-11)

**What it verifies:** Clean phase is blocked if saves exist and user declines export.

| Step | Procedure |
| :--- | :--- |
| 1 | Place `.ess` and `.skse` save files in standalone saves folder |
| 2 | Trigger clean/rebuild |
| 3 | Confirm prompt appears asking user to export saves to MO2 |
| 4 | Decline prompt. Confirm clean is blocked |
| 5 | Accept prompt. Confirm clean proceeds |

**Pass Criteria:**
- Prompt appears when saves present
- Clean blocked if user declines
- Clean proceeds if user accepts

---

### STR-P5-03: Save Sync Before Clean (FEAT-12)

**What it verifies:** `ProfileSync.sync_saves_to_mo2()` is called before standalone folder deletion.

| Step | Procedure |
| :--- | :--- |
| 1 | Run CleanWorker. Inspect log |
| 2 | Confirm sync log entry appears before any deletion log entry |
| 3 | Confirm sync count is logged |

**Pass Criteria:**
- Sync logged before deletion
- Sync count visible in log

---

### STR-P5-04: Save Quarantine (FEAT-13)

**What it verifies:** Save conflicts result in quarantine, never silent overwrite.

| Step | Procedure |
| :--- | :--- |
| 1 | Create a save file conflict (same filename in MO2 and standalone) |
| 2 | Trigger save sync |
| 3 | Confirm conflicting file is moved to `quarantine_<timestamp>/` folder |
| 4 | Confirm original in MO2 is not overwritten |

**Pass Criteria:**
- Conflicting file moved to quarantine folder with timestamp
- MO2 original preserved
- No silent overwrite under any condition

---

### STR-P5-05: Preflight Environment Sensing (FEAT-01)

**What it verifies:** OneDrive, Defender CFA, and PID locks are detected before deployment.

| Step | Procedure |
| :--- | :--- |
| 1 | Simulate OneDrive sync on target directory. Confirm attribution report shown, deployment paused |
| 2 | Simulate Windows Defender CFA blocking target. Confirm attribution report shown, deployment paused |
| 3 | Simulate PID lock on a game file. Confirm attribution report shown |
| 4 | Confirm Retry and Abort options are presented in all cases |

**Pass Criteria:**
- All three conflict types detected and reported
- Deployment paused (not failed silently) on any detection
- Retry/Abort offered to user

---

## 8. Phase 6 Tests — New Capabilities

### STR-P6-01: Long Path Coverage (FEAT-04)

**What it verifies:** `ensure_long_path()` is applied to all filesystem operations.

| Step | Procedure |
| :--- | :--- |
| 1 | Grep all engine files for `os.link(`, `shutil.copy2(`, `os.walk(` calls |
| 2 | For each occurrence, confirm `ensure_long_path()` is applied to the path argument |
| 3 | Test deployment with a mod file whose path exceeds 260 characters. Confirm no failure. |

**Pass Criteria:**
- Every `os.link`, `shutil.copy2`, `os.walk` call uses long-path-safe paths
- Files with path > 260 characters deploy successfully

---

### STR-P6-02: Tiered Verification (FEAT-02)

**What it verifies:** Quick + Sampled verification runs automatically after every build.

| Step | Procedure |
| :--- | :--- |
| 1 | Run full build. Confirm log shows Quick verification (size + mtime) ran automatically |
| 2 | Confirm log shows Sampled verification (5% SHA256) ran automatically |
| 3 | Confirm Full verification does NOT run automatically (manual only) |
| 4 | Trigger Full verification manually. Confirm 100% hash pass runs |

**Pass Criteria:**
- Quick + Sampled run automatically after every build
- Full only runs on manual trigger
- All verification results logged with method label (Quick / Sampled / Full)

---

### STR-P6-03: Delta Analysis Threshold (FEAT-15)

**What it verifies:** Delta > 70% triggers full rebuild. Configurable per profile.

| Step | Procedure |
| :--- | :--- |
| 1 | Run a scan where >70% of files have changed. Confirm full rebuild is triggered |
| 2 | Run a scan where <70% of files have changed. Confirm incremental deploy runs |
| 3 | Set threshold to 50% in `game_profiles.json`. Confirm 55% delta now triggers full rebuild |

**Pass Criteria:**
- Full rebuild triggered when delta exceeds threshold
- Incremental deploy when delta below threshold
- Threshold is configurable per game profile

---

## 9. Phase 7 Tests — V3 Feature Restoration

### STR-P7-01: HOW TO LAUNCH.txt (FEAT-08)

**What it verifies:** Launch instructions file written to standalone root after every successful build.

| Step | Procedure |
| :--- | :--- |
| 1 | Run full build. Confirm `HOW TO LAUNCH.txt` exists in standalone root |
| 2 | Confirm file contains: EXE to run, SKSE note, build date, profile name |
| 3 | Run rebuild. Confirm file is updated (new build date) |

**Pass Criteria:**
- File present in standalone root after every build
- All four required fields present
- File updated on rebuild

---

### STR-P7-02: steam_appid.txt (FEAT-09)

**What it verifies:** Steam AppID file written to standalone root after build.

| Step | Procedure |
| :--- | :--- |
| 1 | Run full build. Confirm `steam_appid.txt` exists in standalone root |
| 2 | Confirm content matches game's AppID from `game_profiles.json` |

**Pass Criteria:**
- `steam_appid.txt` present after build
- Content matches correct AppID for active game profile

---

### STR-P7-03: SKSE/Loader EXE Wrapping (FEAT-10)

**What it verifies:** Known loader EXEs are wrapped with `StandaloneLauncher.exe`.

| Step | Procedure |
| :--- | :--- |
| 1 | Confirm `skse64_loader.exe` present in standalone after build |
| 2 | Confirm original renamed to `_skse64_loader_original.exe` |
| 3 | Confirm `StandaloneLauncher.exe` placed in its position |
| 4 | Remove `StandaloneLauncher.exe`. Run build. Confirm `.bat` launcher deployed as fallback |
| 5 | Confirm wrapping only occurs for EXEs that physically exist — no error on missing EXE |

**Pass Criteria:**
- Original EXE renamed with `_original` suffix
- `StandaloneLauncher.exe` in place of original
- `.bat` fallback when `StandaloneLauncher.exe` absent
- Non-existent EXEs skipped without error

---

### STR-P7-04: Update Notification Banner (FEAT-14)

**What it verifies:** Version check runs on startup, banner shown if newer version exists.

| Step | Procedure |
| :--- | :--- |
| 1 | Mock remote version file to return a higher version number. Start tool. Confirm banner appears with version info and Nexus URL |
| 2 | Mock remote version file to return same version. Confirm no banner shown |
| 3 | Simulate network timeout (> 5 seconds). Confirm tool starts normally with no error dialog |

**Pass Criteria:**
- Banner shown when newer version available
- No banner when up to date
- Silent fail on network error — tool starts normally

---

## 10. Phase 8 Tests — UX Polish

### STR-P8-01: Cross-Drive Warning (UX-01)

**What it verifies:** Warning label appears when MO2 mods and destination are on different drives.

| Step | Procedure |
| :--- | :--- |
| 1 | Set source (MO2 mods) on drive C:, destination on drive D:. Open tool. Confirm warning label is visible. |
| 2 | Set source and destination on same drive. Confirm warning label is hidden. |

**Pass Criteria:**
- Warning visible on cross-drive config
- Warning hidden on same-drive config

---

### STR-P8-02: Clickable Paths (UX-02)

**What it verifies:** Paths in standalone manager metadata are clickable file links.

| Step | Procedure |
| :--- | :--- |
| 1 | Click a path in the metadata display. Confirm Windows Explorer opens to that path. |

**Pass Criteria:**
- Paths open in Explorer when clicked

---

### STR-P8-03: Qt Framework Label (UX-03)

**What it verifies:** Active Qt framework name shown in Tab 1 footer.

| Step | Procedure |
| :--- | :--- |
| 1 | Run with PySide6. Confirm footer shows "PySide6". |
| 2 | Run with PyQt6 only. Confirm footer shows "PyQt6". |

**Pass Criteria:**
- Footer shows correct Qt binding name at runtime

---

## 11. Final Acceptance — Golden Pass

The project reaches v1.0 only when ALL of the following are confirmed:

| # | Criterion | Source Test |
| :--- | :--- | :--- |
| 1 | Speed ≥ V3 original | STR-P1-04 |
| 2 | V3 core files preserved unchanged | STR-P1-01 |
| 3 | Crash logger active and exception-safe | STR-P5-01 |
| 4 | Base game hardlinking works | STR-P4-01 |
| 5 | Progress bar updates every 50 files | STR-P4-03 |
| 6 | Clean button present and functional | STR-P4-02 |
| 7 | Inode validation logged for every hardlink | STR-P2-02 |
| 8 | No silent failures (FIX-01 through FIX-05) | STR-P2-01 through STR-P2-05 |
| 9 | Director Manual Test Report reviewed and transcribed to UAT Sync | DIR-STR (new) |

**All 9 criteria must be PASS. Any FAIL blocks v1.0 release.**

---

## 12. UAT Sync Section

*(To be populated by ANT after Director submits `DIR-STR-005-v3.1.md` manual test observations.)*

| Director Observation | Technical Interpretation | Verdict |
| :--- | :--- | :--- |
| — | — | Pending |

---

*Paired Document: `ANT-WO-005-v3.1.md`*
*Source Documents: `V3_UPDATE_GUIDANCE.md`, `GMN-PRD-005-v3.3.md`, `GMN-FLOW-005-v3.3.md`, `GMN-PROJ-005-v4.0.md`*
