# MO2 Hardlink Builder — V3 Update Guidance

## Critical Reference: Apply V4 Improvements onto V3 Architecture

**Prepared:** 2026-04-20  
**Purpose:** Blueprint for the correct update path — clone V3, apply targeted improvements.  
**What Went Wrong:** V4 rebuilt the core engine from scratch instead of layering improvements on top of V3. V3's core (ScannerEngine, ConflictManager, LinkerExecutor) was proven, fast, and accurate. It should have been kept intact.

---

## The Correct Strategy

```
WRONG (what happened):
  Build new V4 engine from scratch → lost V3 speed + accuracy

CORRECT (what should happen):
  03_Build/archieve/MO2_Hardlink_Builder_V3/   ← CLONE THIS
             ↓
  Apply improvements as patches on top of V3
             ↓
  V3 core stays intact, only new layers added
```

**Rule #1:** Never touch V3's core scan/conflict/deploy pipeline unless fixing a documented bug.  
**Rule #2:** Improvements are additions or wrappers, not replacements.  
**Rule #3:** Every change must map to a specific issue from the audit or WO. No speculative refactors.

---

## V3 Core — PRESERVE AS-IS

These files/classes are the reason V3 is faster and more accurate than V4. Do not rewrite them.

| V3 File                          | Class/Function                                   | Why Preserve                                |
| -------------------------------- | ------------------------------------------------ | ------------------------------------------- |
| `Scripts/scanner_engine.py`      | `ScannerEngine.build_mapping()`                  | Proven scan loop with conflict registration |
| `Scripts/state_manager.py`       | `ConflictManager`                                | Correct load order conflict resolution      |
| `Scripts/linker_executor.py`     | `LinkerExecutor.execute_mapping()`               | Battle-tested deploy loop                   |
| `Scripts/state_manager.py`       | `ModlistSnapshot`                                | Accurate modlist reading                    |
| `Scripts/path_utils.py`          | `ensure_long_path()`, `clean_path_for_display()` | Long path support                           |
| `Scripts/profile_sync.py`        | `ProfileSync`                                    | Save/INI sync logic (keep base, fix bugs)   |
| `Scripts/verification_engine.py` | Core verification logic                          | Tested against real deployments             |
| `Scripts/cleaner_engine.py`      | `CleanerEngine`                                  | Cleanup pipeline                            |

**Do not rename, restructure, or "modernize" these unless fixing a specific issue listed below.**

---

## What V4 Correctly Solved — Apply These to V3

Organized by priority. Each item maps to the source document that authorized it.

---

### PRIORITY 1 — Critical Bug Fixes (Apply First)

These are data corruption / silent failure risks identified in `technical_critic_audit.md`.

#### FIX-01: Replace Heuristic Load Order with mobase API

**Source:** Technical Critic Audit §1 (🔴 CRITICAL), WO v3.2 TASK-A02  
**Problem:** `scanner_engine.py` lines 59-77 uses keyword-based heuristic to detect load order direction. Fails silently on edge cases and non-English MO2 installations.  
**Fix:** Replace with `mobase.IOrganizer.modList()` API call. If API unavailable, halt with explicit error — do NOT fall back to guessing.  
**Scope:** Modify `ScannerEngine._get_active_mods()` only. Leave rest of scan pipeline intact.  

```python
# REPLACE:
# heuristic keyword-detection in _get_active_mods()
# WITH:
def _get_active_mods_from_api(self, organizer):
    mod_list = organizer.modList()
    return [mod_list.moduleName(i) for i in range(mod_list.size())
            if mod_list.state(mod_list.moduleName(i)) & 0x02]  # active flag
```

#### FIX-02: Inode Validation After os.link()

**Source:** Technical Critic Audit §2 (🔴 CRITICAL), WO v3.2 TASK-B01  
**Problem:** `linker_executor.py` calls `os.link()` but never verifies the hardlink was created (inode match). Silent pseudo-hardlinks possible on FAT32/cross-volume/AV interference.  
**Fix:** After `os.link()`, compare `source.stat().st_ino == target.stat().st_ino`. If mismatch → delete target, log as pseudo-hardlink, fall back to copy. Log every fallback explicitly.  
**Scope:** Wrap the hardlink call in `LinkerExecutor` only.

#### FIX-03: Transactional Deployment with Checkpoint

**Source:** Technical Critic Audit §5 (🔴 CRITICAL), WO v3.2 TASK-B03  
**Problem:** If deployment crashes at file 25,000 of 50,000, state is inconsistent with no recovery.  
**Fix:** Before deployment loop begins, write `.deployment_state` file with manifest hash. Checkpoint every 500 files. On crash recovery, detect incomplete state and offer resume or full rebuild. On clean completion, remove state file.  
**Scope:** Add wrapper around existing `execute_mapping()` loop. Do not change the loop itself.

#### FIX-04: Conflict Cache Validation on Load

**Source:** Technical Critic Audit §6 (🟠 MAJOR), WO v3.2  
**Problem:** `state_manager.py ConflictManager.load()` silently discards invalid cache with bare `except: pass`. Stale mod references accumulate.  
**Fix:** Validate cache format on load. Check for version field. If corrupt or version mismatch, rebuild from scratch rather than silently proceeding with stale data.  
**Scope:** 10-line fix in `ConflictManager.load()`.

#### FIX-05: Orphan Cleanup Safety

**Source:** Technical Critic Audit §3 (🔴 CRITICAL), WO v3.2 TASK-B05  
**Problem:** `cleaner_engine.py` deletes files with `except: pass` — no logging, no user preview, no confirmation.  
**Fix:** Collect orphan list first, show preview count, require user confirmation before deletion. Log every deletion with path. Never silently skip errors.  
**Scope:** Modify cleanup method to preview-then-confirm pattern.

---

### PRIORITY 2 — Architecture Layer (Apply Second)

These are structural improvements. Apply them WITHOUT touching core engine logic.

#### ARCH-01: MVC Separation

**Source:** Technical Critic Audit §8 (🟠 MAJOR), WO v3.2 TASK-A01  
**Problem:** `plugin_ui.py` is ~2,500 LOC with UI, business logic, threads, and dialogs all mixed in one class.  
**Fix:** Extract into three layers:

- `model/` — DeploymentConfig, DeploymentState, GameProfile (no Qt imports)
- `view/` — Qt widgets only (ConfigPanel, ProgressPanel)
- `controller/` — DeploymentController bridging Model ↔ View
  **Critical constraint:** The V3 engines (Scanner, Linker, Cleaner) move to `model/engines/` unchanged.  
  **Scope:** This is a restructure, not a rewrite. Move code, do not rewrite logic.

#### ARCH-02: Game Profile Abstraction

**Source:** Technical Critic Audit §11 (🟡 MEDIUM), WO v3.2 TASK-A03  
**Problem:** Game-specific strings (docs_name, appdata_name, ini_prefix, blacklist_files) are hardcoded across multiple files.  
**Fix:** Extract to `game_profiles.json`. Load by key at runtime. Minimum profiles: `skyrim_se` (full), `fallout_4` (stub), `starfield` (stub).  
**Scope:** Create JSON file + loader class. Update references. Do not change engine behavior.

#### ARCH-03: Manifest Schema Versioning

**Source:** Technical Critic Audit §12 (🟡 MEDIUM), WO v3.2 TASK-A05  
**Problem:** `mapping_manifest.json` has no version field. Format changes break silently.  
**Fix:** Add `"version": 3` field to manifest. On load, check version. If mismatch, reject with clear error and force fresh scan.  
**Scope:** Add version field to manifest write. Add version check on manifest load. No other changes.

#### ARCH-04: Replace print() with logging Module

**Source:** Technical Critic Audit §13 (🟡 MEDIUM), WO v3.2 TASK-A04  
**Problem:** All diagnostics use `print()`. No timestamps, levels, rotation, or structured output.  
**Fix:** Replace all `print()` with `logging` module. Levels: DEBUG/INFO/WARN/ERROR. File rotation. Separate audit trail for deployment operations.  
**Scope:** Find-and-replace throughout engine files. Do not change logic.

#### ARCH-05: PySide6 Upgrade

**Source:** WO v3.2 TASK-RC04  
**Problem:** V3 used older Qt binding. PySide6 is the modern choice for MO2 plugin compatibility.  
**Fix:** Update UI imports to PySide6. Keep a compatibility shim (`qt_compat.py`) that tries PySide6 → PyQt6 → PyQt5 in order.  
**Scope:** UI layer only. Zero changes to engine code.

---

### PRIORITY 3 — New Feature Layer (Apply Third)

These are new capabilities that did not exist in V3. Layer them on top after PRIORITY 1 and 2 are stable.

#### FEAT-01: Preflight Environment Sensing

**Source:** WO v3.2 TASK-C01  
**What it does:** Before deployment starts, check for:

- OneDrive sync conflict on target directory
- Windows Defender Controlled Folder Access (CFA) blocking target
- PID locks on game files
  **On conflict detected:** Pause deployment, show attribution report, offer Retry/Abort.  
  **Implementation:** New `EnvironmentSensor` class. Plug into deployment flow before scan begins.

#### FEAT-02: Tiered Verification Policy

**Source:** WO v3.2 TASK-B02  
**What it does:** After deployment, run:

- **Quick:** Size + mtime check (~0.06ms/file) — default
- **Sampled:** Random 5% SHA256 check (95% confidence) — default
- **Full:** 100% hash pass — manual only
  **Implementation:** New `VerificationEngine` class wrapping the existing `verification_engine.py`. Run Quick + Sampled automatically after every build.

#### FEAT-03: Crash Logger

**Source:** WO v3.3 TASK-D01, TASK-D02, TASK-D03  
**What it does:** Wrap all worker thread `run()` methods in universal try/except. On any unhandled exception:

- Write `crash_log_<timestamp>.txt` to standalone root (or plugin dir if path unavailable)
- Include: Exception type, full stack trace, Python version, MO2 profile name, build config
- Show crash dialog to user with log file path
  **Critical:** Crash logger must NEVER throw its own exception.  
  **Implementation:** Decorator or base class wrapper on BuildWorker and CleanWorker.

#### FEAT-04: Long Path Support (\\?\ Prefix)

**Source:** WO v3.3 TASK-H01 through H04  
**What it does:** Enable deployment of files in paths > 260 characters using Windows `\\?\` prefix.  
**V3 already has `path_utils.py`** — verify it's applied in `os.link()`, `shutil.copy2()`, and `os.walk()` calls.  
**Implementation:** Review and confirm `ensure_long_path()` wraps all filesystem operations. Not a rewrite — just verification + gaps filled.

#### FEAT-05: Base Game Hardlinking

**Source:** DIR-STR-005-v3.3.1 Director Observation #3  
**What it does:** Before mod files are deployed, hardlink the base game directory (executables, DLLs, root assets) to the standalone folder so the standalone is independently executable.  
**Implementation:** New `scan_base_game()` method in ScannerEngine. Run before mod deployment loop. Skip Data/ and mods/ subdirectories when scanning base game.

#### FEAT-06: Clean Standalone Button

**Source:** DIR-STR-005-v3.3.1 Director Observation #1  
**What it does:** Dedicated UI button to delete standalone folder contents without triggering a full rebuild. Shows confirmation dialog.  
**Implementation:** New `CleanWorker` thread + red button in UI Tab 1.

#### FEAT-07: Smooth Progress Bar (Granular Updates)

**Source:** DIR-STR-005-v3.3.1 Director Observation #2  
**What it does:** Progress bar updates every 50 files during hardlink loop (not just per-mod).  
**Implementation:** Add counter in `LinkerExecutor` deploy loop. Emit progress signal every 50 iterations via `QTimer.singleShot()` for thread-safe UI update.

#### FEAT-08: HOW TO LAUNCH.txt Auto-Generation

**Source:** WO v3.3 TASK-F01, v3_v4_adaptation_features.md regression #1  
**What it does:** After every successful build, write `HOW TO LAUNCH.txt` to standalone root. Content: which EXE to run, SKSE note, build date, profile name.  
**Implementation:** Called at end of BuildWorker. Pure file write — no engine changes.

#### FEAT-09: steam_appid.txt Auto-Write

**Source:** WO v3.3 TASK-F02, v3_v4_adaptation_features.md regression #2  
**What it does:** After build, write `steam_appid.txt` with game's Steam AppID to standalone root.  
**Implementation:** AppID from `game_profiles.json`. Single file write after build complete.

#### FEAT-10: SKSE/Loader EXE Auto-Wrapping

**Source:** WO v3.3 TASK-F03, v3_v4_adaptation_features.md regression #6  
**What it does:** After build, scan standalone root for known loaders (`skse64_loader.exe`, game launcher EXE). Rename original to `_<name>_original.exe`, copy `StandaloneLauncher.exe` in its place.  
**Fallback:** If `StandaloneLauncher.exe` not available, deploy `.bat` launcher.  
**Implementation:** Post-build scan loop. Conditional — only wrap EXEs that physically exist.

#### FEAT-11: Data Safety — Save Export Guard

**Source:** WO v3.3 TASK-E01, v3_v4_adaptation_features.md regression #3  
**What it does:** Before any rebuild that would clean the standalone folder, detect `.ess`/`.skse` save files. If found, prompt user to export to MO2 before proceeding.  
**Implementation:** Check at start of clean phase in BuildWorker. Block clean if saves found and user declines.

#### FEAT-12: Data Safety — Save Sync Before Clean

**Source:** WO v3.3 TASK-E02, v3_v4_adaptation_features.md regression #4  
**What it does:** In CleanWorker, before deleting standalone folder, automatically sync saves to MO2 profile.  
**Implementation:** Call `ProfileSync.sync_saves_to_mo2()` before `total_cleanup()`. Log sync count.

#### FEAT-13: Data Safety — Save Quarantine System

**Source:** WO v3.3 TASK-E03, v3_v4_adaptation_features.md regression #7  
**What it does:** On save file conflict during sync, move conflicting file to `quarantine_<timestamp>/` instead of overwriting.  
**Implementation:** Add conflict-check in `ProfileSync._process_sync()`. Default to quarantine — never silent overwrite.

#### FEAT-14: Update Notification Banner

**Source:** WO v3.3 TASK-F04, v3_v4_adaptation_features.md regression #5  
**What it does:** On startup, check remote version file (GitHub raw). If newer version exists, show clickable banner with version info and Nexus URL. 5-second timeout, silent fail on network error.  
**Implementation:** Background thread on startup. Minimal — just a GET request and a QLabel show/hide.

#### FEAT-15: Delta Analysis with Configurable Threshold

**Source:** WO v3.2 TASK-B04  
**What it does:** Compare new scan manifest vs previous `.deployment_state`. If delta > threshold (default 70%, configurable per game profile in `game_profiles.json`) → trigger full rebuild instead of incremental.  
**Implementation:** New `ManifestDeltaAnalyzer` class. Wrap around existing manifest comparison logic.

---

### PRIORITY 4 — UX Polish (Apply Last)

#### UX-01: Cross-Drive Warning Label

**Source:** v3_v4_adaptation_features.md ⚠️ #124  
Show visible warning if source (MO2 mods) and destination are on different drives. Hardlinks will not work cross-drive — files will be copied instead.

#### UX-02: Clickable Paths in Metadata Display

**Source:** v3_v4_adaptation_features.md ⚠️ #92  
`setOpenExternalLinks(True)` on the standalone manager metadata display. Paths wrapped as `<a href="file:///...">` links.

#### UX-03: Qt Framework Name in Footer

**Source:** WO v3.3 TASK-G03  
Footer of Tab 1 shows active Qt framework name (PySide6 / PyQt6 / PyQt5).

---

## Authorized Amputations — DO NOT Restore

These features were intentionally removed per WO v3.3 §5.1. Do not bring them back.

| Feature                                | Reason                                                      |
| -------------------------------------- | ----------------------------------------------------------- |
| CPU Priority / IO Priority settings    | OS Tweak — not tool's responsibility                        |
| RAM Trim (EmptyWorkingSet)             | OS Tweak — not tool's responsibility                        |
| MMCSS registration                     | OS Tweak — not tool's responsibility                        |
| CPU Affinity grid                      | OS Tweak — not tool's responsibility                        |
| Thermal failsafe (CPU temp monitoring) | OS Tweak — not tool's responsibility                        |
| Tab 2: Tweaks & Optimization           | All content was OS Tweaks — entire tab removed              |
| `.bat` wrapper fallback                | Pre-compiled `StandaloneLauncher.exe` replaces this cleanly |

---

## C# Component — StandaloneLauncher.exe

V4 correctly moved from dynamic C# compilation at build time (`csc.exe`) to a **pre-compiled** `StandaloneLauncher.exe`. This is the right approach. Keep it.

The C# wrapper is responsible for:

- AppData backup before game launch
- AppData injection (plugins.txt, INIs) into game's AppData
- AppData restore after game exit
- Save sync: MO2 saves → native Saves folder before launch
- Save sync: native Saves → MO2 after game close
- Crash detection → skip save sync if game crashed

**Long path in C# wrapper:** .NET 8 handles long paths better than legacy framework, but verify `\\?\` prefix handling for any `MoveFileEx` native calls.

---

## Implementation Order (Recommended Sequence)

```
PHASE 1 — Foundation (Start Here)
  Clone V3 from archive
  Set up new project structure
  Apply ARCH-01 (MVC): move engines to model/, wrap UI
  Apply ARCH-05 (PySide6): update UI imports
  Verify it still builds and runs identical to V3

PHASE 2 — Bug Fixes
  Apply FIX-01 (mobase API load order)
  Apply FIX-02 (inode validation)
  Apply FIX-03 (transactional deployment)
  Apply FIX-04 (conflict cache validation)
  Apply FIX-05 (orphan cleanup safety)
  Run existing V3 test cases — must pass

PHASE 3 — Architecture Support
  Apply ARCH-02 (game_profiles.json)
  Apply ARCH-03 (manifest versioning)
  Apply ARCH-04 (logging framework)
  All engine behavior unchanged — just logging + config externalized

PHASE 4 — Director Feedback Features
  Apply FEAT-05 (base game hardlinking)    ← DIR-STR-005-v3.3.1 #3
  Apply FEAT-06 (clean button)             ← DIR-STR-005-v3.3.1 #1
  Apply FEAT-07 (progress bar granularity) ← DIR-STR-005-v3.3.1 #2
  These are the three most user-visible gaps

PHASE 5 — Safety Layer
  Apply FEAT-03 (crash logger)
  Apply FEAT-11 (save export guard)
  Apply FEAT-12 (save sync before clean)
  Apply FEAT-13 (save quarantine)
  Apply FEAT-01 (preflight environment sensing)

PHASE 6 — New Capabilities
  Apply FEAT-04 (long path \\?\ verification)
  Apply FEAT-02 (tiered verification)
  Apply FEAT-15 (delta analysis)

PHASE 7 — V3 Feature Restoration
  Apply FEAT-08 (HOW TO LAUNCH.txt)
  Apply FEAT-09 (steam_appid.txt)
  Apply FEAT-10 (SKSE/loader EXE wrapping)
  Apply FEAT-14 (update notification banner)

PHASE 8 — Polish
  Apply UX-01, UX-02, UX-03
  Performance benchmark vs original V3
  Target: same speed or faster
```

---

## What V4 Built That is Salvageable

If migrating useful code from the V4 attempt, these specific files/classes are worth porting:

| V4 File                              | What's Worth Keeping                                        |
| ------------------------------------ | ----------------------------------------------------------- |
| `model/engines/hardlink_manager.py`  | Clean `HardlinkManager` with inode validation (FIX-02)      |
| `model/engines/diagnostics.py`       | `EnvironmentSensor` for preflight checks (FEAT-01)          |
| `model/engines/verification.py`      | Tiered verification (Quick/Sampled/Full) (FEAT-02)          |
| `model/engines/crash_logger.py`      | Crash log writer (FEAT-03)                                  |
| `model/engines/cleanup.py`           | Orphan preview + confirm pattern (FIX-05)                   |
| `model/state.py`                     | `DeploymentTransactionManager` checkpoint logic (FIX-03)    |
| `model/config.py`                    | `GameProfile` + `DeploymentConfig` dataclasses (ARCH-02)    |
| `utils/path_utils.py`                | `ensure_long_path()` + `clean_path_for_display()` (FEAT-04) |
| `model/engines/feature_generator.py` | HOW TO LAUNCH, steam_appid, EXE wrapping (FEAT-08/09/10)    |
| `model/engines/profile_sync.py`      | Save quarantine logic (FEAT-13)                             |
| `model/engines/reporting.py`         | HTML report generator with CSS                              |

**Do NOT port:** `model/engines/scanner.py`, `model/manifest.py` — these replaced V3's working scanner with a slower rewrite. Go back to V3's `scanner_engine.py` and `state_manager.py`.

---

## Performance Note

V3 is faster because:

1. `ScannerEngine` was written specifically for this use case with accumulated optimizations
2. `ConflictManager` used a pre-built in-memory dict with a single pass
3. `LinkerExecutor` had no abstraction overhead — direct loop over manifest

The V4 scanner was slower because it introduced abstraction layers, a two-phase raw_candidates dict, and Python overhead that wasn't in V3's direct scan loop.

**When porting:** measure each phase against a V3 baseline. If any phase is slower after a change, investigate before moving on.

---

## Success Definition

The updated V3 is successful when:

1. Speed ≥ V3 original (same or faster)
2. All V3 core features work identically
3. Crash logging active (FEAT-03)
4. Base game hardlinking works (FEAT-05)
5. Progress bar updates smoothly during deploy (FEAT-07)
6. Clean button present and working (FEAT-06)
7. Inode validation logged (FIX-02)
8. No silent failures anywhere (FIX-01 through FIX-05)

---

*Source documents: GMN-PROJ-005-v4.0.md, GMN-PRD-005-v3.3.md, ANT-WO-005-v3.2.md, ANT-WO-005-v3.3.md, v3_v4_adaptation_features.md, technical_critic_audit.md, DIR-STR-005-v3.3.1.md*
