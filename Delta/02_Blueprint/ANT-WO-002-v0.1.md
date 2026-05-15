# Work Order

> [!IMPORTANT]
> **Runtime Gate**: Create this document with `delta wo new`. WO creation requires locked `GMN-STRAT`; WO lock requires `delta wo complete` plus the required audit verdicts recorded through `delta audit record`. Do not create or lock a WO by editing `Delta/progress.json`.

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Work Order (WO) |
| **Runtime State** | PENDING |
| **Created by** | ANT (Technical Foreman) |
| **Issued to** | CDC (Lead Developer) |
| **DI Reference** | `DIR-DI-002-v1.0.md` |
| **STRAT Reference** | `GMN-STRAT-002-v1.0.md` |
| **Source WO (archieve)** | `ANT-WO-005-v3.1.md` — V3-Based Rebuild Foundation |

---

## 2. Work Order Summary

> **Task Title:** V3-Based Rebuild Foundation — MVC Refactoring, Critical Bug Fixes & Safety Layer
> **Summary:** Clone V3 as new project base and apply targeted improvements: MVC separation, mobase API integration, transactional deployment, crash logging, preflight sensing, tiered verification, and restore V3 features. **V3's core scan/conflict/deploy pipeline is NOT rewritten — improvements are additions or wrappers only.** A previous V4 attempt failed by rebuilding from scratch; this WO corrects that course by preserving V3's proven engine and applying surgical patches.

### 2b. Alignment With DI / STRAT

- **DIR-DI Intent**: Primary trade-off — Correctness & Traceability over Raw Speed (§5); Defensive by Default — assume hostile OS (§4); User Data is Sacred — save files never silently overwritten (§4)
- **STRAT Goal / Success Indicator**: SI-2 (Verification Velocity <3min for 50K+ files), SI-3 (100% Fallback Awareness), SI-4 (Deployment Speed <30s incremental), SI-5 (100% State Parity)
- **Functional Requirement**: REQ-001 (MO2 Integration), REQ-002 (NTFS Hardlink Deployment), REQ-005 (Wrapper Generation), REQ-006 (Preflight Sensing), REQ-008 (Game Profile Abstraction)
- **Risk / Constraint Link**: CON-001 (Windows/NTFS only), CON-002 (No admin), CON-003 (Don't modify MO2), CON-006 (Quarantine saves), CON-007 (Log every fallback), CON-008 (Transactional checkpoints). Mitigates RR-001 through RR-006.
- **Architecture Decision Link**: ADR-001 (Python + C#), ADR-002 (Dual-Layer Manifest), ADR-004 (Checkpointing), ADR-005 (mobase API), ADR-006 (Strict MVC)

---

## 3. Success Indicators

These indicators must be measurable and testable by ANT-STR.

| ID | Indicator | Measurement Method | Required Result |
| :--- | :--- | :--- | :--- |
| SI-001 | Scan + deploy speed ≥ V3 original | Baseline benchmark on known modlist (record scan time + deploy time) | Same or faster than V3 |
| SI-002 | All V3 core features work identically after MVC refactoring | Run original V3 test profile; compare output hash with new build | Output identical |
| SI-003 | mobase API resolves load order correctly | Test against MO2 profile with known load order | 100% match with MO2 priority |
| SI-004 | Hardlink inode validation catches pseudo-hardlinks | Force copy + verify inode check logs fallback | Every fallback logged explicitly |
| SI-005 | Transactional checkpoint resumes correctly | Kill process mid-deployment; restart and verify resume | Resume from last 500-file checkpoint |
| SI-006 | Crash logger never throws its own exception | Inject exception into worker thread; verify crash_log written | crash_log_<timestamp>.txt generated, tool shows dialog |
| SI-007 | Save quarantine works on conflict | Create save conflict scenario; run sync | Conflicting save moved to quarantine_<timestamp>/ |
| SI-008 | Preflight sensing detects AV/OneDrive/PID locks | Run with OneDrive syncing target; run with game process holding files | Attribution report shown, options: Retry/Abort |
| SI-009 | C# wrapper compiles and functions | Build with csc.exe available; launch game through wrapper | Wrapper injects plugins.txt, syncs saves, detects crash |
| SI-010 | Batch launcher fallback works | Build without csc.exe available | .bat launcher generated with explicit warning |

---

## 4. Implementation Constraints

| Constraint ID | Source | Constraint | CDC Freedom |
| :--- | :--- | :--- | :--- |
| WO-CON-001 | STRAT §0g + Director | V3's core scan/conflict/deploy pipeline is NOT rewritten. Improvements are additions or wrappers. | Level 1 |
| WO-CON-002 | STRAT CON-001 | Windows 10/11, NTFS only. No cross-platform abstractions. | Level 1 |
| WO-CON-003 | STRAT CON-002 | Must NOT require administrator privileges — no UAC elevation. | Level 1 |
| WO-CON-004 | STRAT CON-003 | Must NOT modify MO2's internal files, profile data, or mod directories. | Level 1 |
| WO-CON-005 | STRAT CON-005 | C# wrapper must fall back to .bat launcher if csc.exe unavailable — never block build. | Level 1 |
| WO-CON-006 | STRAT CON-006 | Save files must NEVER be silently overwritten — quarantine on conflict, skip sync on crash. | Level 1 |
| WO-CON-007 | STRAT CON-008 | Deployment checkpoints every 500 files; resume prompt on interrupted build. | Level 1 |
| WO-CON-008 | STRAT ADR-001 | Python 3.10+ for engine/UI; C# for wrapper. PySide6 preferred for GUI. | Level 2 |
| WO-CON-009 | STRAT ADR-006 | Strict MVC separation. No Qt imports in model layer. View never touches model directly. | Level 2 |

### Authority Levels For CDC

- **Level 1 (Non-Negotiable)**: CDC must not violate this. Escalate to ANT/GMN if impossible.
- **Level 2 (Guided Methods)**: CDC may choose the method, but must satisfy the constraint and justify trade-offs.
- **Level 3 (Soft Preferences)**: CDC may deviate with rationale in CDC-IMPL/WALK.
- **Level 4 (Freedom of Method)**: CDC owns implementation details.

---

## 5. Scope Boundaries

### In Scope

- Clone V3 from `04_Reference/00_archieve/MO2_Hardlink_Builder_V3/` as new project base into `src/MO2_Hardlink_Builder_V4b/`
- MVC separation: extract `plugin_ui.py` into `model/`, `view/`, `controller/` layers
- PySide6 upgrade with `qt_compat.py` shim (PySide6 → PyQt6 → PyQt5 fallback)
- Replace heuristic load order detection with `mobase.IOrganizer.modList()` API
- Inode validation on every hardlink; log fallback to copy explicitly
- Transactional deployment: `.deployment_state` checkpoints every 500 files with resume
- `ConflictManager` cache validation — reject corrupt cache, rebuild from scratch
- Orphan cleanup: preview count → user confirmation → logged deletion
- Externalize game config to `game_profiles.json` (minimum: skyrim_se, fallout_4 stub, starfield stub)
- Add version field to `mapping_manifest.json`; reject on version mismatch
- Replace all `print()` with `logging` module (DEBUG/INFO/WARN/ERROR, file rotation, audit trail)
- Base game hardlinking (executables, DLLs, root assets) before mod deployment
- Clean Standalone button with confirmation dialog and `CleanWorker` thread
- Progress bar granularity: update every 50 files via `QTimer.singleShot()`
- Crash logger: wrap worker `run()` in universal try/except; NEVER throw own exception
- Save Export Guard: detect saves before clean; prompt user; block clean if declined
- Save Sync Before Clean: sync saves to MO2 before deleting standalone
- Save Quarantine: on conflict, move to `quarantine_<timestamp>/` instead of overwriting
- Preflight Environment Sensing: check OneDrive, Defender, PID locks; attribution report
- Long path `\\?\ ` verification across all `os.link()`, `shutil.copy2()`, `os.walk()`
- Tiered Verification: Quick (size+mtime), Sampled (random 5% SHA256), Full (manual only)
- Delta Analysis: compare new manifest vs previous; if >70% delta → trigger full rebuild
- HOW TO LAUNCH.txt and steam_appid.txt written after every successful build
- C# wrapper compilation at build time using csc.exe; enhanced over V3
- .bat launcher fallback if csc.exe unavailable
- Update notification banner on startup (GitHub version check, 5s timeout)
- Cross-drive warning label in UI
- Clickable paths in metadata display (`setOpenExternalLinks(True)`)
- Qt framework name in footer

### Out of Scope

- OS-level tweaks (CPU priority, IO priority, RAM trim, MMCS, CPU affinity, thermal failsafe)
- Tab 2: Tweaks & Optimization (entire tab removed — all content was OS tweaks)
- Rewriting V3's `ScannerEngine.build_mapping()`, `ConflictManager`, `LinkerExecutor.execute_mapping()`
- Cross-platform support (Linux, macOS) — CON-001

### Non-Goals

- CDC must NOT port or restore any of the "Authorized Amputations" (OS tweaks)
- CDC must NOT rewrite V3's core scan/conflict/deploy pipeline
- CDC must NOT implement features beyond those listed in the 8 phases
- CDC must NOT spend time on automated testing infrastructure — ANT owns test design

---

## 5b. Skill Routing Authorization

> Bind only skills that are already listed in `GMN-STRAT` Section 2d. CDC may load a routed skill only if it passes all three gates: routed by `~/.delta/skills/SKILLS_ROUTING.json`, allowed by STRAT, and bound here.

| Skill ID | Authorized Use For This WO | Forbidden In This WO |
| :--- | :--- | :--- |
| SKILL-PythonBestPractices | Type hints, pathlib, concurrent.futures, dataclasses, logging module | No architectural deviations |
| SKILL-WindowsNativeDevelopment | C# wrapper, NTFS hardlink ops, Shell API path resolution, csc.exe discovery | No cross-platform abstractions |
| SKILL-GUIDevelopment | PySide6 GUI, qt_compat.py shim, QTimer thread-safe signals, QLabel links | No Qt imports in model layer |
| SKILL-TestAutomation | (Not for CDC — ANT uses this skill for ANT-STR) | CDC does not design test plans |

---

## 6. Action Items For CDC

### PHASE 1 — Foundation (P1)
1. [ ] **P1-T01**: Clone V3 from `04_Reference/00_archieve/MO2_Hardlink_Builder_V3/` → `src/MO2_Hardlink_Builder_V4b/`. Source archive is read-only. Do not modify any V3 file during clone.
2. [ ] **P1-T02**: Apply MVC Separation — extract `plugin_ui.py` (~2500 LOC) into `model/`, `view/`, `controller/` layers. V3 engines move to `model/engines/` unchanged. Move code, do not rewrite logic. No Qt imports in model layer.
3. [ ] **P1-T03**: Apply PySide6 upgrade — update UI imports. Add `qt_compat.py` shim (PySide6 → PyQt6 → PyQt5 fallback). UI layer only. Zero changes to engine code.
4. [ ] **P1-T04**: Verify build runs and produces identical output to original V3. Baseline benchmark: record scan time + deploy time for a known modlist.

### PHASE 2 — Critical Bug Fixes (P2)
5. [ ] **P2-T01 (FIX-01)**: Replace heuristic load order detection with `mobase.IOrganizer.modList()` API call. If API unavailable → halt with explicit "API Link Failure" error. No silent fallback.
6. [ ] **P2-T02 (FIX-02)**: After `os.link()`, compare `source.stat().st_ino == target.stat().st_ino`. On mismatch → delete target, log as pseudo-hardlink, fall back to copy. Log every fallback.
7. [ ] **P2-T03 (FIX-03)**: Transactional deployment — write `.deployment_state` with manifest hash before loop. Checkpoint every 500 files. On crash recovery → offer Resume or Full Rebuild. Remove state file on clean completion.
8. [ ] **P2-T04 (FIX-04)**: `ConflictManager.load()` — validate cache format and version field on load. If corrupt or version mismatch → rebuild from scratch. Remove bare `except: pass`.
9. [ ] **P2-T05 (FIX-05)**: Orphan cleanup — collect orphan list first, show preview count, require user confirmation before deletion. Log every deletion with path.

### PHASE 3 — Architecture Support (P3)
10. [ ] **P3-T01 (ARCH-02)**: Extract game-specific strings to `game_profiles.json`. Minimum profiles: skyrim_se (full), fallout_4 (stub), starfield (stub). Add loader class.
11. [ ] **P3-T02 (ARCH-03)**: Add `"version": 3` field to `mapping_manifest.json`. On load: if version mismatch → reject with clear error and force fresh scan.
12. [ ] **P3-T03 (ARCH-04)**: Replace all `print()` with `logging` module. Levels: DEBUG/INFO/WARN/ERROR. File rotation. Separate audit trail for deployment operations.

### PHASE 4 — Director Feedback Features (P4)
13. [ ] **P4-T01 (FEAT-05)**: Base game hardlinking — new `scan_base_game()` method in `ScannerEngine`. Hardlink base game directory (executables, DLLs, root assets) before mod deployment. Skip `Data/` and `mods/`.
14. [ ] **P4-T02 (FEAT-06)**: Clean Standalone button — dedicated UI button (red) that deletes standalone folder without full rebuild. Requires confirmation dialog. New `CleanWorker` thread.
15. [ ] **P4-T03 (FEAT-07)**: Progress bar granularity — update every 50 files during hardlink loop (not per-mod). Emit progress signal every 50 iterations via `QTimer.singleShot()`.

### PHASE 5 — Safety Layer (P5)
16. [ ] **P5-T01 (FEAT-03)**: Crash logger — wrap all worker thread `run()` in universal try/except. On unhandled exception → write `crash_log_<timestamp>.txt`, show crash dialog. Crash logger must NEVER throw its own exception.
17. [ ] **P5-T02 (FEAT-11)**: Save Export Guard — at start of clean phase, detect `.ess`/`.skse` save files. If found → prompt user to export to MO2. Block clean if user declines.
18. [ ] **P5-T03 (FEAT-12)**: Save Sync Before Clean — in `CleanWorker`, before deleting standalone folder, call `ProfileSync.sync_saves_to_mo2()`. Log sync count.
19. [ ] **P5-T04 (FEAT-13)**: Save Quarantine — on save file conflict during sync, move conflicting file to `quarantine_<timestamp>/` instead of overwriting. Default to quarantine.
20. [ ] **P5-T05 (FEAT-01)**: Preflight Environment Sensing — new `EnvironmentSensor` class. Check OneDrive sync conflict, Windows Defender CFA, PID locks on game files. On conflict → pause, show attribution report, offer Retry/Abort.

### PHASE 6 — New Capabilities (P6)
21. [ ] **P6-T01 (FEAT-04)**: Long path verification — confirm `ensure_long_path()` wraps all `os.link()`, `shutil.copy2()`, and `os.walk()` calls. Fill any gaps.
22. [ ] **P6-T02 (FEAT-02)**: Tiered Verification — new `VerificationEngine` class. Quick (size+mtime), Sampled (random 5% SHA256), Full (100% hash, manual only). Run Quick + Sampled automatically after build.
23. [ ] **P6-T03 (FEAT-15)**: Delta Analysis — new `ManifestDeltaAnalyzer` class. Compare new scan manifest vs previous state. If delta > 70% (configurable per profile) → trigger full rebuild.

### PHASE 7 — V3 Feature Restoration (P7)
24. [ ] **P7-T01 (FEAT-08)**: HOW TO LAUNCH.txt — after every successful build, write to standalone root. Content: which EXE, SKSE note, build date, profile name.
25. [ ] **P7-T02 (FEAT-09)**: steam_appid.txt — after build, write with game's Steam AppID from `game_profiles.json` to standalone root.
26. [ ] **P7-T03 (FEAT-10)**: C# wrapper compilation — scan standalone root for known loaders, rename original to `_<name>_original.exe`, compile C# wrapper using csc.exe, place in original EXE position. Fallback: if csc.exe unavailable → deploy `.bat` launcher + log fallback.
27. [ ] **P7-T04 (FEAT-14)**: Update Notification Banner — background thread checks remote version file (GitHub raw). If newer → clickable banner with version info and Nexus URL. 5s timeout. Silent fail on network error.

### PHASE 8 — UX Polish (P8)
28. [ ] **P8-T01 (UX-01)**: Cross-drive warning label — visible warning if MO2 mods source and destination on different drives.
29. [ ] **P8-T02 (UX-02)**: Clickable paths in metadata display — `setOpenExternalLinks(True)`. Paths as `<a href="file:///...">` links.
30. [ ] **P8-T03 (UX-03)**: Qt framework name in footer — display active Qt framework (PySide6/PyQt6/PyQt5) in UI footer.

---

## 7. Execution Prerequisites Checklist

- [ ] `DIR-DI-002-v1.0.md` reference reviewed.
- [ ] `GMN-STRAT-002-v1.0.md` is locked in runtime state.
- [ ] STRAT audit policy has been satisfied for lock.
- [ ] WO scope traces to STRAT goals (SI-2 through SI-5), requirements (REQ-001, 002, 005, 006, 008), constraints (CON-001–008), and risks (RR-001–006).
- [ ] No unresolved conflict exists between DI, STRAT, and this WO.
- [ ] Skill Routing Authorization is explicit — 4 skills authorized, each with boundaries.
- [ ] No active cascade block affects the target document/version.

---

## 8. WO Completeness Checklist

Before completing and locking this WO, ANT must verify:

- [ ] Task title and summary are specific — "V3-Based Rebuild Foundation: MVC Refactoring, Critical Bug Fixes & Safety Layer"
- [ ] Alignment section references DI/STRAT source material — DI §4, §5; STRAT §2b, §3a, §0c, §5d
- [ ] Success indicators are measurable and suitable for ANT-STR — 10 SI entries, all quantifiable
- [ ] Implementation constraints are realistic and classified by authority level — 9 constraints, Levels 1–2
- [ ] Scope boundaries and non-goals are explicit — In Scope (30 tasks), Out of Scope (4 exclusions), Non-Goals (4 items)
- [ ] Action items are atomic and ordered — 30 items in 8 sequential phases
- [ ] Skill authorization is documented — 4 skills with authorized use and forbidden boundaries
- [ ] All placeholders are replaced — no `[Brief title]`, `[e.g.]`, or empty fields remain
- [ ] CDC can produce CDC-IMPL without inventing requirements — all tasks have target components and constraints

---

## 9. Runtime Lifecycle & Sign-Off

### CLI Lifecycle

```bash
delta wo new --file ANT-WO-002-v0.1.md
delta wo advance
delta wo complete
delta audit record --wo ANT-WO-002-v0.1.md --actor Director --approve --note "WO approved"
delta wo lock --file ANT-WO-002-v0.1.md
```

### Lock Requirements

WO is CDC-ready only when runtime state is `LOCKED`.

- **ANT**: Owns WO content, success indicators, and technical acceptance boundaries.
- **Director**: Provides required audit verdict for WO lock.
- **CDC**: Begins IMPL/WALK only after WO is locked and ANT-STR exists at the same version.

### Next Phase

After WO is `LOCKED`, ANT creates ANT-STR with `delta str new`. CDC creates IMPL and WALK only when the same-version ANT-STR exists.

---

# Quick Reference: Document Metadata & Rules

## Naming Convention

**Format:** `{AGENT_CODE}-{DOCUMENT_CODE}-002-{VERSION}.md`

**Example:** `ANT-WO-002-v0.1.md`

## Version Management Rules

- WO is a versioned planning artifact.
- Create separate versioned files for revisions; do not overwrite historical WOs.
- Use `delta wo supersede --new-file ...` when replacing an active WO.
- This v0.1 WO corresponds to `ANT-WO-005-v3.1.md` in the archieve. Subsequent versions (v0.2 → v0.7) will map to archieve versions v3.2 → v3.7.

## Document Specifics

- **Purpose**: Technical work specification and acceptance boundary.
- **Created by**: ANT.
- **Input**: Locked `GMN-STRAT-002-v1.0.md`, `DIR-DI-002-v1.0.md`, audit status.
- **Output**: CDC-ready implementation scope after runtime lock.
- **Source WO**: `archieve/02_Blueprint/ANT-WO-005-v3.1.md` — adapted to Delta 2.0 format with DI/STRAT references.
- **Authority**: Subordinate to `DELTA_CONSTITUTION.md`, `DELTA_PROTOCOL.md`, runtime state, and active STRAT.
