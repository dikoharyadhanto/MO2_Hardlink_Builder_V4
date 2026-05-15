# ANT WORK ORDER — 002-v0.7

**Project:** MO2 Hardlink Builder V4b  
**Task:** Publish-Blocker Correction for Event-Driven Incremental Build  
**Runtime State:** PENDING  
**Created by:** ANT (Technical Foreman)  
**Issued to:** CDC (Lead Developer)  
**DI Reference:** `DIR-DI-002-v1.0.md`  
**STRAT Reference:** `GMN-STRAT-002-v1.0.md`  
**Supersedes / Corrects:** v0.6 implementation findings from ANT pre-publish review

---

## 1. Work Order Summary

This WO directs CDC to correct the remaining publish blockers in the v0.6 event-driven incremental build architecture. The current code contains the intended `LayeredManifest`, tri-gate scanner, and action queue concepts, but ANT review found behavioral gaps that can cause missed incremental files, false-negative dirty detection, and continued full-scan I/O behavior before the tri-gate path runs.

CDC must make the event-driven path function as the actual deployment path for incremental builds, not as a parallel artifact generated after a legacy full scan.

---

## 2. Alignment With DI / STRAT

- **DIR-DI Intent:** Preserve exact MO2 profile parity while avoiding silent corruption and unsafe publish behavior.
- **STRAT Goal / Success Indicator:** Section 2b Success Indicator 4, incremental updates under 30 seconds for 1000+ modlists when fewer than 5 mods changed; Success Indicator 5, 100% load order parity.
- **Functional Requirement:** REQ-003 Incremental Updates via Tri-Gate Change Detection; REQ-004 Action Queue Execution.
- **Risk / Constraint Link:** STRAT Section 0f, Incremental Update Path; Section 0g Launch Blocker definition for silent load order corruption.
- **Architecture Decision Link:** ADR-002 Dual-Layer RAM Manifest; ADR-003 Tri-Gate Change Detection; ADR-004 Transactional Deployment with Checkpoint Resume.

---

## 3. Corrective Directives

### TASK-A01: Fix Incremental Layer B Added-Path Handling

**Target Components:** `model/engines/scanner_engine.py`, `model/state.py`

When a dirty mod is rescanned during stable-load-order incremental mode, all newly introduced virtual paths must be inserted into `LayeredManifest.path_owners` and `_active_map`.

Requirements:

- If a dirty mod adds a new file, the corresponding path must appear in `path_owners`.
- If the new file conflicts with clean mods, the owner stack must include all providers sorted by current load-order priority.
- If the new file is unique, the owner stack must contain the dirty mod as active owner.
- `compute_action_queue()` must emit a `LINK` operation for every new active path.
- Add a regression test covering: previous manifest has `file1`, dirty mod adds `file2`, resulting queue includes `LINK data/file2.txt`.

### TASK-A02: Remove Legacy Full-Scan Precondition From Incremental Path

**Target Component:** `controller/deployment_controller.py`

The incremental event-driven path must not require `scanner.build_mapping()` to scan all active mods before `build_layered_manifest()`.

Requirements:

- For incremental builds with a usable `layered_manifest.json`, call the tri-gate layered builder directly.
- Flat `mapping_manifest.json` may still be generated for compatibility/reporting, but it must be derived from the layered manifest or produced only where a full build requires it.
- Full rebuild and first-run migration may still perform full scan.
- Add log messages that clearly distinguish:
  - fresh/full legacy-compatible scan,
  - incremental tri-gate selective scan,
  - fallback to legacy linker.
- Do not silently fall back to legacy full scan if the layered manifest has an invariant violation; abort instead.

### TASK-A03: Eliminate Gate 2 False Negatives

**Target Component:** `model/engines/scanner_engine.py`

Gate 2 must not classify a changed mod as clean when a deep file changes outside the deterministic sample window.

Requirements:

- Replace fixed-first-three alphabetical sampling with a stronger dirty signal.
- Acceptable approaches:
  - store and compare a cheap rolling fingerprint over all deployable file metadata,
  - store and compare a deterministic sampled fingerprint that changes across runs and covers more than the first alphabetical files,
  - or use another bounded mechanism that ANT can validate against false negatives.
- The solution must catch same-size content replacement when mtime changes but root directory mtime does not.
- Add a regression test with at least four nested files where only the fourth file changes; Gate 2 must return dirty.
- If the chosen approach cannot guarantee zero false negatives, CDC must state the residual risk explicitly in `CDC-IMPL` and propose an ANT decision point.

### TASK-A04: Resolve Action Queue Verification Policy Conflict

**Target Components:** `model/engines/linker_executor.py`, `Delta/03_Build/CDC-IMPL-002-v0.7.md`

ANT review found a conflict between WO v0.6 "zero stat / blind execution" and existing fallback-awareness behavior that verifies hardlinks via inode stat.

CDC must choose one of these paths and document it:

- **Path 1: Strict WO Compliance.** Create a true action-queue execution path that avoids inode verification and target pre-check stat calls during queue execution.
- **Path 2: Safety Exception Request.** Keep inode verification for fallback-awareness, but explicitly mark this as a WO-level deviation requiring ANT/Director acceptance before lock.

Requirements for either path:

- Delete and link operations must remain phased.
- Locked-file OS errors must be logged and must not halt unrelated operations.
- Report output must accurately represent action queue results.
- Tests must assert the chosen policy.

### TASK-A05: Modernize Publish Test Harnesses

**Target Components:** `tests/test_wrapper.py`, `tests/simulate_incremental.py`, source test discovery

The migrated tests still reference legacy absolute paths and cannot serve as publish gates.

Requirements:

- Remove hardcoded `I:\Works\005_MO2_Hardlink_Builder_V4b` paths.
- Resolve source root dynamically from the current repository.
- Ensure `python -m unittest discover -s tests -p "test*.py"` imports successfully.
- Preserve wrapper tests as optional/integration tests if they require Windows executable behavior or real user AppData writes.
- Add at least one automated incremental test that exercises `build_layered_manifest()` and `execute_action_queue()` without requiring MO2 runtime.

---

## 4. Success Indicators

| ID     | Indicator                                            | Measurement Method                                                                                                                   | Required Result                                                                |
|:------ |:---------------------------------------------------- |:------------------------------------------------------------------------------------------------------------------------------------ |:------------------------------------------------------------------------------ |
| SI-001 | Added files in dirty mods are deployed incrementally | Automated test using previous layered manifest + added file                                                                          | Action queue contains correct `LINK`; target file exists after execution       |
| SI-002 | Incremental path does not pre-scan every mod         | Instrumented test or mock scanner call counter                                                                                       | Clean mods are not traversed by `build_mapping()` before tri-gate              |
| SI-003 | Gate 2 detects deep-file changes beyond first sample | Automated test with 4+ nested files and same-size modification                                                                       | Dirty result is `True`                                                         |
| SI-004 | Action queue policy is deterministic and documented  | Unit test + CDC-IMPL policy note                                                                                                     | Either strict zero-stat path passes or safety exception is explicitly approved |
| SI-005 | Publish tests are executable after migration         | `python -m unittest discover -s src\MO2_Hardlink_Builder_V4b -p "test*.py"` and `python -m unittest discover -s tests -p "test*.py"` | Both commands complete without import-path errors                              |
| SI-006 | Source syntax remains valid                          | `python -m compileall -q src\MO2_Hardlink_Builder_V4b`                                                                               | PASS                                                                           |

---

## 5. Implementation Constraints

| Constraint ID | Source           | Constraint                                                                                    | CDC Freedom |
|:------------- |:---------------- |:--------------------------------------------------------------------------------------------- |:----------- |
| CON-001       | STRAT Section 0c | Windows 10/11 and NTFS-only assumptions remain valid; no cross-platform redesign.             | Level 1     |
| CON-002       | STRAT Section 0c | Must not require administrator privileges.                                                    | Level 1     |
| CON-003       | STRAT Section 0c | Must not modify MO2 internal files, profile data, or mod directories.                         | Level 1     |
| CON-007       | STRAT Section 0c | Every hardlink-to-copy fallback must be logged and reported.                                  | Level 1     |
| ADR-002       | STRAT Section 5d | Dual-layer RAM manifest remains the source of ownership truth.                                | Level 1     |
| ADR-003       | STRAT Section 5d | Tri-gate must avoid scanning unchanged physical mod directories during incremental operation. | Level 1     |
| ADR-004       | STRAT Section 5d | Transactional checkpoint behavior must remain intact.                                         | Level 2     |

---

## 6. Scope Boundaries

### In Scope

- Correct incremental `LayeredManifest` state updates.
- Correct Gate 2 dirty detection.
- Controller routing between legacy full build and event-driven incremental build.
- Action queue execution policy resolution.
- Publish test harness migration and regression tests.

### Out of Scope

- New UI features.
- New supported games.
- Save-sync redesign.
- C# wrapper feature expansion beyond making existing tests importable/runnable.
- Delta legacy migration cleanup for missing `DIR-STR-002-v0.5.md`.

### Non-Goals

- Do not rewrite the full engine.
- Do not remove legacy full-build support if it is still needed for first build or migration.
- Do not claim benchmark success without a runnable benchmark or instrumented proof.

---

## 7. Skill Routing Authorization

| Skill ID                       | Authorized Use For This WO                                                                                   | Forbidden In This WO                                                   |
|:------------------------------ |:------------------------------------------------------------------------------------------------------------ |:---------------------------------------------------------------------- |
| SKILL-PythonBestPractices      | Refactor Python engine/controller code, improve tests, maintain type-safe and deterministic data structures. | Broad architectural rewrite unrelated to v0.7 blockers.                |
| SKILL-TestAutomation           | Build regression tests for manifest, tri-gate, action queue, and harness migration.                          | Creating tests that require real user MO2 state as the only pass gate. |
| SKILL-WindowsNativeDevelopment | Validate hardlink/action-queue policy and Windows path behavior.                                             | Expanding wrapper/native features outside the publish blockers.        |

---

## 8. Action Items For CDC

1. [ ] Implement added-path handling in stable-load-order incremental Layer B updates.
2. [ ] Refactor controller Stage 3 / Stage 3b so tri-gate is the active incremental path, not a post-full-scan side path.
3. [ ] Strengthen Gate 2 fingerprinting and add false-negative regression coverage.
4. [ ] Resolve and document action queue verification policy.
5. [ ] Modernize migrated test harness import paths.
6. [ ] Add publish-gate tests for incremental add, deep edit, load-order recompute, and action queue execution.
7. [ ] Run compile and unit discovery commands listed in Section 4.
8. [ ] Document implementation result and residual risks in CDC-WALK v0.7.

---

## 9. Execution Prerequisites Checklist

- [x] `DIR-DI` reference reviewed.
- [x] `GMN-STRAT` is locked in runtime state.
- [x] STRAT audit policy has been satisfied for lock.
- [x] WO scope traces to STRAT goals, requirements, success indicators, constraints, and risks.
- [x] No unresolved conflict exists between DI, STRAT, and this WO.
- [x] Skill Routing Authorization is explicit.
- [x] No active cascade block affects `ANT-WO-002-v0.7.md`.
- [x] Director audit verdict recorded before WO lock.

---

## 10. WO Completeness Checklist

- [x] Task title and summary are specific.
- [x] Alignment section references DI/STRAT source material.
- [x] Success indicators are measurable and suitable for ANT-STR.
- [x] Implementation constraints are realistic and classified by authority level.
- [x] Scope boundaries and non-goals are explicit.
- [x] Action items are atomic and ordered.
- [x] Skill authorization is documented.
- [x] All placeholders are replaced.
- [x] CDC can produce CDC-IMPL without inventing requirements.

---

## 11. Runtime Lifecycle & Sign-Off

WO is CDC-ready only when runtime state is `LOCKED`.

Expected CLI sequence:

```bash
delta wo advance
delta wo complete
delta audit record --wo ANT-WO-002-v0.7.md --actor Director --approve --note "WO v0.7 corrective publish blockers approved"
delta wo lock --file ANT-WO-002-v0.7.md
```

After WO v0.7 is `LOCKED`, ANT creates the matching ANT-STR v0.7 through:

```bash
delta str new --v 0.7
```

CDC must not begin v0.7 IMPL/WALK until same-version ANT-STR exists according to Delta runtime gates.
