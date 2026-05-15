# Automated Simulation Test Report

> [!IMPORTANT]
> **Runtime Gate**: Create this document with `delta str new` only after the governing WO is `LOCKED`. ANT-STR is the automated test design and execution record. IMPL and WALK require a same-version ANT-STR to exist; locking ANT-STR auto-locks same-version IMPL/WALK when they are COMPLETE or IMPLEMENTED.

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Automated Simulation Test Report (ANT-STR) |
| **Runtime State** | PENDING |
| **Created by** | ANT (Technical Foreman) |
| **WO Reference** | `ANT-WO-002-v0.1.md` |
| **IMPL Reference** | `CDC-IMPL-002-v0.1.md` |
| **WALK Reference** | `CDC-WALK-002-v0.1.md` |
| **Source STR (archieve)** | `ANT-STR-005-v3.1.md` — V3-Based Rebuild Test Suite |

---

## 2. Test Plan Overview

> **Purpose**: Verify that CDC implementation satisfies the locked WO v0.1 success indicators and constraints across all 8 phases — Foundation, Critical Bug Fixes, Architecture Support, Director Features, Safety Layer, New Capabilities, V3 Feature Restoration, and UX Polish.

### 2b. Alignment With WO

- **WO Reference**: `ANT-WO-002-v0.1.md`
- **Success Indicators Tested**: SI-001 through SI-010 — all 10 WO indicators
- **Constraints Tested**: WO-CON-001 through WO-CON-009
- **Test Entry Criteria**: WO is locked; ANT-STR exists at same version; CDC-WALK is ready when execution begins.
- **Test Exit Criteria**: All 31 test scenarios executed (22 success + 9 failure), results recorded, and Golden Pass verdict assigned.
- **Testing Principles**: All tests performed by ANT against CDC output. CDC does not self-certify. Every test reproducible with documented procedure. "PASS" requires ALL criteria met. Silent failures always = FAIL.

---

## 3. Success Scenarios

| Scenario ID | Condition | Expected Result | Links to WO SI | Status |
| :--- | :--- | :--- | :--- | :--- |
| POS-01 | Clone V3 and apply MVC separation; diff core files against V3 archive | Zero diff on `scanner_engine`, `state_manager`, `linker_executor`, `path_utils`, `profile_sync`, `verification_engine`, `cleaner_engine` (import path updates allowed) | SI-001, SI-002 | PENDING |
| POS-02 | Grep `model/` for Qt imports | Zero Qt imports in `model/` layer. `view/` has only Qt widget code, no business logic. `controller/` bridges model ↔ view | SI-002 | PENDING |
| POS-03 | `qt_compat.py` tested with PySide6, PyQt6, PyQt5 individually | Application starts under all three Qt binding scenarios; no crash on import | SI-002 | PENDING |
| POS-04 | Baseline benchmark: run build on known modlist; compare scan+deploy time vs V3 original | Scan + deploy speed ≥ V3 original (same or faster) | SI-001 | PENDING |
| POS-05 | Replace heuristic load order with `mobase.IOrganizer.modList()` API | Load order matches MO2 priority exactly. If API unavailable → `RuntimeError("API Link Failure")` raised, no silent fallback | SI-003 | PENDING |
| POS-06 | Post-link inode comparison: `source.stat().st_ino == target.stat().st_ino` | True hardlinks match. On mismatch → delete target, log "PSEUDO-HARDLINK DETECTED", fallback to copy | SI-004 | PENDING |
| POS-07 | Transactional deployment: kill process mid-deployment at file ~1,200; restart | `.deployment_state` detected → Resume prompt shown → resumes from file 1,000 (last 500-file checkpoint) | SI-005 | PENDING |
| POS-08 | `ConflictManager.load()` with corrupted cache (bad JSON / version mismatch) | Cache rejected → `self.mapping = {}` → rebuild from scratch with warning log. No crash. | SI-003 | PENDING |
| POS-09 | Orphan cleanup: 15 orphan files detected; decline confirmation | Cleanup skipped, count logged. On accept → only those 15 deleted, paths logged | SI-003 | PENDING |
| POS-10 | `game_profiles.json` with skyrim_se, fallout_4, starfield; select each | Correct profile loaded with AppID, loaders, blacklist, threshold per game | SI-002 | PENDING |
| POS-11 | Manifest with `version: 3` written and loaded; inject version mismatch | Version 2 manifest rejected with clear error → force fresh scan | SI-002 | PENDING |
| POS-12 | Replace all `print()` with `logging`; grep engine files for `print(` | Zero `print()` calls in any model or engine file. `RotatingFileHandler` active. Separate `hardlink_audit` logger. | SI-004 | PENDING |
| POS-13 | Base game hardlinking: scan Skyrim SE root directory | Executables, DLLs, root assets hardlinked. `Data/`, `mods/`, `_commonredist/` skipped | SI-002 | PENDING |
| POS-14 | Click "Clean Standalone" button; confirm dialog; clean proceeds | Confirmation dialog required. On confirm → `CleanWorker` runs → standalone folder cleaned | SI-007 | PENDING |
| POS-15 | Build with 10,000 files; monitor progress bar updates | Progress signals emitted every 50 files (not per-mod). 4 bars mapped to 4 stages. UI responsive. | SI-002 | PENDING |
| POS-16 | Inject deliberate exception into `BuildWorker.run()` | `crash_log_<timestamp>.txt` written with exception type, full traceback, Python version, MO2 profile name, build config. Crash dialog shown. Crash logger itself never throws. | SI-006 | PENDING |
| POS-17 | Place `.ess`/`.skse` saves in standalone; trigger clean; decline export | Prompt appears. On decline → clean blocked. On accept → clean proceeds. | SI-007 | PENDING |
| POS-18 | `CleanWorker` invoked; check sync order in log | `ProfileSync.sync_saves_to_mo2()` logged before any deletion log entry | SI-007 | PENDING |
| POS-19 | Create save file conflict (same name in MO2 and standalone); trigger sync | Conflicting file moved to `quarantine_<timestamp>/`. MO2 original untouched. NEVER silently overwritten. | SI-007, SI-008 | PENDING |
| POS-20 | Simulate OneDrive syncing target, Defender CFA blocking, PID lock on game EXE | All three detected. Attribution report shown. Deployment paused. Retry/Abort offered. | SI-008 | PENDING |
| POS-21 | Quick + Sampled verification run automatically after build | Quick (size+mtime) and Sampled (random 5% SHA256) logged. Full (100% hash) does NOT run automatically. | SI-002 | PENDING |
| POS-22 | Delta analysis: >70% files changed → full rebuild; <70% → incremental; threshold set to 50% in config | Full rebuild triggered at 55%. Threshold configurable per `game_profiles.json` entry. | SI-004 | PENDING |
| POS-23 | After build: check standalone root for `HOW TO LAUNCH.txt` | File present with EXE path, SKSE note, build date, profile name. Updated on rebuild. | SI-002 | PENDING |
| POS-24 | After build: check standalone root for `steam_appid.txt` | File present with correct AppID from `game_profiles.json` | SI-002 | PENDING |
| POS-25 | `skse64_loader.exe` present in standalone after build | Original renamed to `_skse64_loader_original.exe`. C# wrapper in place. `.bat` fallback if csc.exe absent. Non-existent EXEs skipped silently. | SI-009, SI-010 | PENDING |
| POS-26 | Mock remote version higher than local; start tool | Update banner shown with version info and Nexus URL. Same version → no banner. Network timeout → silent, tool starts normally. | SI-002 | PENDING |
| POS-27 | Source C:, destination D: → open tool | Cross-drive warning label visible. Same drive → hidden. | SI-002 | PENDING |
| POS-28 | Click path in metadata display | Windows Explorer opens to that path. `setOpenExternalLinks(True)` active. | SI-002 | PENDING |
| POS-29 | Qt framework label in Tab 1 footer | Footer shows correct binding name (PySide6 / PyQt6 / PyQt5) resolved at runtime. | SI-002 | PENDING |

---

## 4. Failure Scenarios

| Scenario ID | Failure Condition | Expected Handling | Links to Constraint | Status |
| :--- | :--- | :--- | :--- | :--- |
| NEG-01 | `organizer` is `None` (mobase API not injected) | `RuntimeError("API Link Failure — mobase organizer not injected")` → caught by `@crash_safe` → crash log written → build aborted with clear error. No silent fallback to keyword heuristics. | WO-CON-004 | PENDING |
| NEG-02 | Hardlink succeeds at OS level but produces copy (cross-volume junction) | Post-link `st_ino` mismatch detected → target deleted → `shutil.copy2()` fallback → "PSEUDO-HARDLINK DETECTED" audit log entry. Never proceeds with false hardlink. | WO-CON-001 | PENDING |
| NEG-03 | `.deployment_state` file corrupted (invalid JSON / missing fields) | Detected on load → state treated as absent → full rebuild from scratch. No crash on malformed state file. | WO-CON-007 | PENDING |
| NEG-04 | `ConflictManager` cache corrupted or version mismatch | `self.mapping = {}` → full rebuild with warning log. No crash. | WO-CON-001 | PENDING |
| NEG-05 | `clean_orphaned_files()` called without `confirm_callback` | Returns immediately, logs warning. Prevents silent mass deletion in automated pipeline. | WO-CON-001 | PENDING |
| NEG-06 | Save file conflict during sync | Unconditional move to `quarantine_<timestamp>/`. Overwrite prompt removed — no destructive choice possible. | WO-CON-006 | PENDING |
| NEG-07 | Game detected as crashed (non-zero exit code) | Wrapper skips exit sync. Saves not written back to MO2. `wrapper.log` records crash detection event. | WO-CON-006 | PENDING |
| NEG-08 | csc.exe not found (no .NET SDK installed) | `.bat` launcher deployed as fallback. Explicit warning shown. Build does not abort. | WO-CON-005 | PENDING |
| NEG-09 | Crash logger itself throws an exception | Entire `write_crash_log()` body wrapped in `try/except Exception: pass`. Never raises, never blocks execution. | WO-CON-001 | PENDING |

---

## 5. Verification Commands

All generated test scripts, mock data, logs, and simulation outputs belong in `Delta/08_Test/`.

```bash
# Core file integrity
diff -rq 04_Reference/00_archieve/MO2_Hardlink_Builder_V3/Scripts/ src/MO2_Hardlink_Builder_V4b/model/engines/ | grep -v __pycache__

# MVC separation audit
grep -r "from PySide6\|from PyQt6\|from PyQt5" src/MO2_Hardlink_Builder_V4b/model/

# Logging migration audit
grep -r "print(" src/MO2_Hardlink_Builder_V4b/model/engines/

# Manifest version validation
python -c "import json; m=json.load(open('standalone_metadata/mapping_manifest.json')); assert m['version']==3"

# Inode parity check
python -c "import os; s=os.stat('source'); t=os.stat('target'); print('OK' if s.st_ino==t.st_ino else 'PSEUDO')"

# Crash logger self-test
python -c "from model.engines.crash_logger import write_crash_log; write_crash_log(Exception('test'), '.', '.', 'test', {})"

# Save quarantine test
# 1. Create conflict: copy save to both MO2 and standalone saves/
# 2. Run sync
# 3. Check quarantine_<timestamp>/ folder exists with conflicting file
# 4. Verify MO2 original unchanged

# Delta analysis threshold
python -c "from model.state import ManifestDeltaAnalyzer; ..."
```

---

## 6. Golden Pass — Final Acceptance

The project reaches v0.1 when ALL of the following are confirmed:

| # | Criterion | Source Scenario | Result |
| :--- | :--- | :--- | :--- |
| 1 | Speed ≥ V3 original | POS-04 | PENDING |
| 2 | V3 core files preserved unchanged | POS-01 | PENDING |
| 3 | Crash logger active and exception-safe | POS-16, NEG-09 | PENDING |
| 4 | Base game hardlinking works | POS-13 | PENDING |
| 5 | Progress bar updates every 50 files | POS-15 | PENDING |
| 6 | Clean button present and functional | POS-14 | PENDING |
| 7 | Inode validation logged for every hardlink | POS-06, NEG-02 | PENDING |
| 8 | No silent failures (FIX-01 through FIX-05) | POS-05, POS-06, POS-07, POS-08, POS-09, NEG-01 through NEG-05 | PENDING |
| 9 | Director Manual Test Report reviewed | DIR-STR (future) | PENDING |

**All 9 criteria must be PASS. Any FAIL blocks v0.1 release.**

---

## 7. UAT Sync Section

*(To be populated by ANT after Director submits manual test observations.)*

| Director Observation | Technical Interpretation | Verdict |
| :--- | :--- | :--- |
| — | — | Pending |

---

## 8. Runtime Lifecycle & Sign-Off

### CLI Lifecycle

```bash
delta str new --file ANT-STR-002-v0.1.md
delta str advance       # PENDING → IN_PROGRESS (ANT running tests)
delta str complete      # IN_PROGRESS → COMPLETE (tests executed)
delta str lock          # COMPLETE → LOCKED (auto-locks IMPL+WALK)
```

### Next Phase

After STR is LOCKED, CDC can complete IMPL and WALK. STR lock auto-locks same-version IMPL/WALK when they are COMPLETE/IMPLEMENTED.

---

# Quick Reference: Document Metadata & Rules

## Naming Convention

**Format:** `{AGENT_CODE}-{DOCUMENT_CODE}-002-{VERSION}.md`

**Example:** `ANT-STR-002-v0.1.md`

## Document Specifics

- **Purpose**: Automated test design and execution record.
- **Created by**: ANT.
- **Input**: Locked `ANT-WO-002-v0.1.md`, CDC-IMPL, CDC-WALK.
- **Output**: Test verdict (PASS/FAIL) per scenario; Golden Pass gate for release.
- **Source STR**: `archieve/02_Blueprint/ANT-STR-005-v3.1.md` — adapted to Delta 2.0 format.
- **Authority**: Subordinate to `DELTA_CONSTITUTION.md`, `DELTA_PROTOCOL.md`, runtime state, and active STRAT.
