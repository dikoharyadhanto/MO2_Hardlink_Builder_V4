# ANT-WO-005-v3.1 — Work Order: MO2 Hardlink Builder (V3-Based Rebuild)

> [!IMPORTANT]
> **This Work Order supersedes all previous WO documents (v3.2, v3.3). Those documents are deleted.**
> **Primary Source:** `V3_UPDATE_GUIDANCE.md`
> **Strategy Source:** `GMN-PROJ-005-v4.0.md`, `GMN-PRD-005-v3.3.md`, `GMN-FLOW-005-v3.3.md`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Work Order (WO) |
| **Version** | v3.1 |
| **Issued By** | ANT — Technical Foreman |
| **Issued To** | CDC — Lead Developer (Claude Code, VS Code Extension) |
| **Status** | **Active — WALK Waived by Director. CDC proceed directly to PHASE 1.** |
| **Date** | 2026-04-20 |
| **Updated** | 2026-04-26 |

---

## 2. Context & Mandate

### Why This WO Exists

The previous V4 attempt failed. CDC and ANT incorrectly decided to rebuild the core engine from scratch. The result was a codebase slower, less accurate, and less stable than V3.

**The correct approach, defined in `V3_UPDATE_GUIDANCE.md`:**
- Clone V3 from `03_Build/archieve/MO2_Hardlink_Builder_V3/` as the new project base
- Apply improvements as targeted patches on top of V3
- Never replace V3's proven core pipeline

### The Non-Negotiable Rule

> **V3's core scan/conflict/deploy pipeline is NOT rewritten. Improvements are additions or wrappers only.**

---

## 3. V3 Core — PRESERVE AS-IS

CDC must not rename, restructure, or rewrite these files/classes unless fixing a documented bug listed in this WO.

| V3 File | Class / Function | Reason |
| :--- | :--- | :--- |
| `Scripts/scanner_engine.py` | `ScannerEngine.build_mapping()` | Proven scan loop with conflict registration |
| `Scripts/state_manager.py` | `ConflictManager` | Correct load order conflict resolution |
| `Scripts/linker_executor.py` | `LinkerExecutor.execute_mapping()` | Battle-tested deploy loop |
| `Scripts/state_manager.py` | `ModlistSnapshot` | Accurate modlist reading |
| `Scripts/path_utils.py` | `ensure_long_path()`, `clean_path_for_display()` | Long path support |
| `Scripts/profile_sync.py` | `ProfileSync` | Save/INI sync logic |
| `Scripts/verification_engine.py` | Core verification logic | Tested against real deployments |
| `Scripts/cleaner_engine.py` | `CleanerEngine` | Cleanup pipeline |

---

## 4. Implementation Phases & Tasks

CDC has freedom of method within each task. Do not micromanage coding style or algorithm choice unless explicitly required.

---

### PHASE 1 — Foundation

**Goal:** Establish new project structure. V3 must still run identically after this phase.

| Task ID | Task | Constraint |
| :--- | :--- | :--- |
| PHASE1-T01 | Clone V3 from `04_Reference/00_archieve/MO2_Hardlink_Builder_V3/` as the new project base. Output goes into `03_Build/MO2_Hardlink_Builder_V4b/` | Do not modify any V3 file during clone. Source archive is read-only. |
| PHASE1-T02 | Apply ARCH-01: MVC Separation — extract `plugin_ui.py` (~2500 LOC) into `model/`, `view/`, `controller/` layers | V3 engines move to `model/engines/` unchanged. Move code, do not rewrite logic. No Qt imports in model layer. |
| PHASE1-T03 | Apply ARCH-05: PySide6 upgrade — update UI imports. Add `qt_compat.py` shim (PySide6 → PyQt6 → PyQt5 fallback order) | UI layer only. Zero changes to engine code. |
| PHASE1-T04 | Verify build runs and produces identical output to original V3 | Baseline benchmark: record scan time + deploy time for a known modlist |

---

### PHASE 2 — Critical Bug Fixes

**Goal:** Eliminate all silent failure and data integrity risks from V3.

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE2-T01 (FIX-01) | Replace heuristic load order detection with `mobase.IOrganizer.modList()` API call. If API unavailable → halt with explicit "API Link Failure" error. No silent fallback to guessing. | `ScannerEngine._get_active_mods()` only |
| PHASE2-T02 (FIX-02) | After `os.link()`, compare `source.stat().st_ino == target.stat().st_ino`. On mismatch → delete target, log as pseudo-hardlink, fall back to copy. Log every fallback explicitly. | `LinkerExecutor` only — wrap the hardlink call |
| PHASE2-T03 (FIX-03) | Transactional deployment: write `.deployment_state` file with manifest hash before loop starts. Checkpoint every 500 files. On crash recovery → offer Resume or Full Rebuild. Remove state file on clean completion. | Wrapper around existing `execute_mapping()` loop. Do not change the loop itself. |
| PHASE2-T04 (FIX-04) | `ConflictManager.load()`: validate cache format and version field on load. If corrupt or version mismatch → rebuild from scratch. Remove bare `except: pass`. | 10-line fix in `ConflictManager.load()` only |
| PHASE2-T05 (FIX-05) | Orphan cleanup: collect orphan list first, show preview count, require user confirmation before deletion. Log every deletion with path. Never silently skip errors. | Modify cleanup method to preview-then-confirm pattern |

---

### PHASE 3 — Architecture Support

**Goal:** Externalize config and logging. Zero engine behavior changes.

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE3-T01 (ARCH-02) | Extract game-specific strings to `game_profiles.json`. Minimum profiles: `skyrim_se` (full), `fallout_4` (stub), `starfield` (stub). Add loader class. Update references. | Do not change engine behavior |
| PHASE3-T02 (ARCH-03) | Add `"version": 3` field to `mapping_manifest.json`. On load: if version mismatch → reject with clear error and force fresh scan. | Manifest write + manifest load only |
| PHASE3-T03 (ARCH-04) | Replace all `print()` with `logging` module. Levels: DEBUG / INFO / WARN / ERROR. File rotation. Separate audit trail for deployment operations. | Find-and-replace throughout engine files. Do not change logic. |

---

### PHASE 4 — Director Feedback Features

**Goal:** Three highest-priority user-visible gaps identified in `DIR-STR-005-v3.3.1`.

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE4-T01 (FEAT-05) | Base game hardlinking: new `scan_base_game()` method in `ScannerEngine`. Hardlink base game directory (executables, DLLs, root assets) to standalone before mod deployment loop. Skip `Data/` and `mods/` subdirectories. | New method in ScannerEngine only |
| PHASE4-T02 (FEAT-06) | Clean Standalone button: dedicated UI button (red, Tab 1) that deletes standalone folder contents without triggering full rebuild. Requires confirmation dialog. New `CleanWorker` thread. | New CleanWorker + UI button |
| PHASE4-T03 (FEAT-07) | Progress bar granularity: update every 50 files during hardlink loop (not per-mod). Emit progress signal every 50 iterations via `QTimer.singleShot()` for thread-safe UI update. | Counter in `LinkerExecutor` deploy loop |

---

### PHASE 5 — Safety Layer

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE5-T01 (FEAT-03) | Crash logger: wrap all worker thread `run()` methods in universal try/except. On unhandled exception → write `crash_log_<timestamp>.txt` (exception type, full stack trace, Python version, MO2 profile name, build config), show crash dialog with log path. Crash logger must NEVER throw its own exception. | Decorator or base class wrapper on BuildWorker and CleanWorker |
| PHASE5-T02 (FEAT-11) | Save Export Guard: at start of any clean phase, detect `.ess`/`.skse` save files. If found → prompt user to export to MO2. Block clean if user declines. | Check at start of clean phase in BuildWorker |
| PHASE5-T03 (FEAT-12) | Save Sync Before Clean: in `CleanWorker`, before deleting standalone folder, call `ProfileSync.sync_saves_to_mo2()`. Log sync count. | Pre-clean step in CleanWorker |
| PHASE5-T04 (FEAT-13) | Save Quarantine: on save file conflict during sync, move conflicting file to `quarantine_<timestamp>/` instead of overwriting. Default to quarantine — never silent overwrite. | `ProfileSync._process_sync()` |
| PHASE5-T05 (FEAT-01) | Preflight Environment Sensing: new `EnvironmentSensor` class. Before deployment starts, check for OneDrive sync conflict, Windows Defender CFA blocking target, PID locks on game files. On conflict → pause, show attribution report, offer Retry/Abort. | New class, plug into deployment flow before scan begins |

---

### PHASE 6 — New Capabilities

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE6-T01 (FEAT-04) | Long path `\\?\` verification: confirm `ensure_long_path()` wraps all `os.link()`, `shutil.copy2()`, and `os.walk()` calls. Fill any gaps. Not a rewrite — verification + gap fill. | Review `path_utils.py` application across engine files |
| PHASE6-T02 (FEAT-02) | Tiered Verification: new `VerificationEngine` class. Quick (size + mtime, ~0.06ms/file), Sampled (random 5% SHA256), Full (100% hash, manual only). Run Quick + Sampled automatically after every build. | New class wrapping existing `verification_engine.py` |
| PHASE6-T03 (FEAT-15) | Delta Analysis: new `ManifestDeltaAnalyzer` class. Compare new scan manifest vs previous `.deployment_state`. If delta > 70% (configurable per profile in `game_profiles.json`) → trigger full rebuild. | New class wrapping existing manifest comparison |

---

### PHASE 7 — V3 Feature Restoration

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE7-T01 (FEAT-08) | HOW TO LAUNCH.txt: after every successful build, write `HOW TO LAUNCH.txt` to standalone root. Content: which EXE to run, SKSE note, build date, profile name. | Called at end of BuildWorker. Pure file write. |
| PHASE7-T02 (FEAT-09) | `steam_appid.txt`: after build, write `steam_appid.txt` with game's Steam AppID to standalone root. AppID from `game_profiles.json`. | Single file write after build complete. |
| PHASE7-T03 (FEAT-10) | SKSE/Loader EXE wrapping: after build, scan standalone root for known loaders (`skse64_loader.exe`, game launcher EXE). Rename original to `_<name>_original.exe`. Compile a C# wrapper EXE using `csc.exe` and place it in the original EXE position. The wrapper must be better, smarter, and more robust than V3's original. See Section 7 for wrapper responsibilities and enhancement requirements. Fallback: if `csc.exe` is unavailable or compilation fails → deploy `.bat` launcher instead + log the fallback explicitly. Conditional — only wrap EXEs that physically exist. | Post-build compile + deploy loop. `csc.exe` is the primary mechanism — `.bat` is emergency fallback only. |
| PHASE7-T04 (FEAT-14) | Update Notification Banner: on startup, background thread checks remote version file (GitHub raw). If newer version exists → show clickable banner with version info and Nexus URL. 5-second timeout. Silent fail on network error. | Background thread on startup. Minimal GET + QLabel show/hide. |

---

### PHASE 8 — UX Polish

| Task ID | Task | Scope |
| :--- | :--- | :--- |
| PHASE8-T01 (UX-01) | Cross-drive warning label: show visible warning if MO2 mods source and destination are on different drives. Hardlinks cannot work cross-drive — files will be copied instead. | UI label only |
| PHASE8-T02 (UX-02) | Clickable paths in metadata display: `setOpenExternalLinks(True)` on standalone manager metadata display. Paths wrapped as `<a href="file:///...">` links. | UI layer only |
| PHASE8-T03 (UX-03) | Qt framework name in footer: display active Qt framework (PySide6 / PyQt6 / PyQt5) in Tab 1 footer. | UI label only |

---

## 5. Salvageable V4 Code

> [!IMPORTANT]
> **No V4 source code exists in this repository.** The failed V4 attempt is not archived here. CDC must implement all items below from scratch using the patterns described. The table is a reference for what each feature should do — not a porting guide.


| V4 File | What's Useful |
| :--- | :--- |
| `model/engines/hardlink_manager.py` | Inode validation pattern (FIX-02) |
| `model/engines/diagnostics.py` | `EnvironmentSensor` class (FEAT-01) |
| `model/engines/verification.py` | Tiered verification (FEAT-02) |
| `model/engines/crash_logger.py` | Crash log writer (FEAT-03) |
| `model/engines/cleanup.py` | Orphan preview + confirm pattern (FIX-05) |
| `model/state.py` | Checkpoint/transaction logic (FIX-03) |
| `model/config.py` | `GameProfile` + `DeploymentConfig` dataclasses (ARCH-02) |
| `utils/path_utils.py` | `ensure_long_path()` (FEAT-04) |
| `model/engines/feature_generator.py` | HOW TO LAUNCH, steam_appid, EXE wrapping (FEAT-08/09/10) |
| `model/engines/profile_sync.py` | Save quarantine logic (FEAT-13) |

**DO NOT port:** `model/engines/scanner.py`, `model/manifest.py` — these replaced V3's working scanner with a slower rewrite.

---

## 6. Authorized Amputations — DO NOT Restore

These features were intentionally removed. Do not bring them back under any circumstance.

| Feature | Reason |
| :--- | :--- |
| CPU Priority / IO Priority settings | OS Tweak — not this tool's responsibility |
| RAM Trim (EmptyWorkingSet) | OS Tweak — not this tool's responsibility |
| MMCSS registration | OS Tweak — not this tool's responsibility |
| CPU Affinity grid | OS Tweak — not this tool's responsibility |
| Thermal failsafe (CPU temp monitoring) | OS Tweak — not this tool's responsibility |
| Tab 2: Tweaks & Optimization | All content was OS Tweaks — entire tab removed |

---

## 7. C# Wrapper — Enhanced csc.exe Compilation

> [!IMPORTANT]
> **Director Decision (2026-04-26):** Pre-compiled `StandaloneLauncher.exe` approach is reverted. The C# wrapper is compiled at build time using `csc.exe`, as in V3. The wrapper system must be enhanced to be better, smarter, and more robust than V3's original.

### Core Responsibilities (unchanged from V3)
- AppData backup before game launch
- AppData injection (plugins.txt, INIs) into game's AppData
- AppData restore after game exit
- Save sync: MO2 saves → native Saves folder before launch
- Save sync: native Saves → MO2 after game close
- Crash detection → skip save sync if game crashed

### Enhancement Requirements (new — must improve on V3)

| Enhancement | Requirement |
| :--- | :--- |
| **Robust csc.exe discovery** | Search `%WINDIR%\Microsoft.NET\Framework64\` for the latest installed version. Try multiple known paths. Do not hardcode a single framework version. |
| **Compilation error surfacing** | If `csc.exe` is found but compilation fails, capture stderr and write it to a `wrapper_compile_error_<timestamp>.txt` in the standalone root. Never silently fail compilation. |
| **Long path support** | All file operations in the C# source must use `\\?\` prefix on paths. `File.Move`, `File.Copy`, `Directory.CreateDirectory` all must handle paths > 260 chars. |
| **Atomic AppData swap** | AppData injection must use atomic rename/move operations — not copy-then-delete. Prevents partial state if the game crashes mid-injection. |
| **Crash detection improvement** | V3 used exit code 0 to detect clean exit. Enhanced: also check for `GameCrashed.txt` sentinel file or Windows crash artifacts. If crash detected, log it explicitly in the wrapper log. |
| **Wrapper log** | The compiled wrapper must write a `wrapper_log_<timestamp>.txt` recording: game start time, save sync count, AppData swap status, game exit code, crash detection result. |
| **Fallback to `.bat`** | If `csc.exe` is unavailable or compilation returns non-zero exit code → deploy `.bat` launcher as fallback. Log the fallback explicitly at WARNING level. |

### csc.exe Discovery Order
```
1. %WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
2. %WINDIR%\Microsoft.NET\Framework64\  (latest subdir by sort order)
3. %WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe  (32-bit fallback)
4. where csc  (PATH search)
5. If none found → .bat fallback
```

### C# Template Location
CDC must embed the C# source template as a string inside `feature_generator.py`. The template is parameterized with: `TARGET_EXE_PATH`, `MO2_PROFILE_PATH`, `GAME_SAVES_PATH`, `MO2_SAVES_PATH`, `INI_PREFIX`.

### Scope Boundary
CDC owns: `model/engines/feature_generator.py` (csc.exe discovery, template, compilation, fallback logic). The C# source code template is part of the Python deliverable.

---

## 8. CDC Pre-Implementation Requirements

Before writing any code, CDC must submit a **WALK document** (`CDC-WALK-005-v3.1.md`) covering:
1. Proposed new project folder structure
2. Confirmation that V3 core files are preserved as-is
3. List of V4 files to be ported (with rationale)
4. Proposed approach for PHASE 1 (MVC separation + PySide6)
5. Any risks or conflicts detected in this WO

ANT will review WALK before approving implementation start.

---

## 9. Success Definition

The project is complete when ALL of the following are true:

| # | Criterion |
| :--- | :--- |
| 1 | Scan + deploy speed ≥ V3 original (same speed or faster) |
| 2 | All V3 core features work identically |
| 3 | Crash logging active and never throws its own exception (FEAT-03) |
| 4 | Base game hardlinking works (FEAT-05) |
| 5 | Progress bar updates smoothly every 50 files during deploy (FEAT-07) |
| 6 | Clean Standalone button present and functional (FEAT-06) |
| 7 | Inode validation logged for every hardlink operation (FIX-02) |
| 8 | No silent failures anywhere — FIX-01 through FIX-05 all active |

---

*Source Documents: `V3_UPDATE_GUIDANCE.md`, `GMN-PROJ-005-v4.0.md`, `GMN-PRD-005-v3.3.md`, `GMN-FLOW-005-v3.3.md`*
