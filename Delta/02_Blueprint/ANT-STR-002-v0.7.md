# ANT STRATEGY (STR) — 002-v0.7
**Project:** MO2 Hardlink Builder V4b  
**Phase:** Publish-Blocker Regression Validation  
**Runtime State:** COMPLETE  
**Created by:** ANT (Technical Foreman)  
**WO Reference:** `ANT-WO-002-v0.7.md`  
**IMPL Reference:** `CDC-IMPL-002-v0.7.md`  
**WALK Reference:** `CDC-WALK-002-v0.7.md`

---

## 1. Objective

Validate that CDC's v0.7 corrective implementation removes the publish blockers found during ANT pre-publish review of the v0.6 event-driven incremental build. This STR focuses only on release-blocking correctness, performance-path integrity, and executable regression gates.

The implementation must prove that the layered manifest is the active incremental source of truth and that the test harness can catch the defects identified in v0.6.

---

## 2. Alignment With WO

- **WO Reference:** `ANT-WO-002-v0.7.md`
- **Success Indicators Tested:** SI-001 through SI-006
- **Constraints Tested:** CON-001, CON-002, CON-003, CON-007, ADR-002, ADR-003, ADR-004
- **Test Entry Criteria:** WO v0.7 is LOCKED; ANT-STR v0.7 exists; CDC-IMPL v0.7 and CDC-WALK v0.7 are ready for ANT review.
- **Test Exit Criteria:** All required scenarios are executed, evidence is stored under `Delta/08_Test/`, and ANT assigns PASS / FIX_AND_RETRY / FAIL.

---

## 3. Required Success Scenarios

| Scenario ID | Condition | Expected Result | Links to WO SI | Status |
| :--- | :--- | :--- | :--- | :--- |
| POS-01 | Previous layered manifest contains `data/file1.txt`; same mod becomes dirty and adds `data/file2.txt` with unchanged load order. | New manifest includes `data/file2.txt` in `path_owners` and `_active_map`; action queue contains `LINK data/file2.txt`; executor deploys the file. | SI-001 | PASS |
| POS-02 | Incremental build starts with valid `layered_manifest.json` and unchanged load order. | Controller does not call legacy full `build_mapping()` before tri-gate; clean mods are not physically traversed. | SI-002 | PASS |
| POS-03 | A mod has at least four nested deployable files; only the fourth/deeper file changes with same size and unchanged root folder mtime. | Gate 2 returns dirty and triggers Gate 3 for that mod. | SI-003 | PASS |
| POS-04 | Action queue contains DELETE and LINK operations for changed ownership. | Executor runs all DELETEs before LINKs, logs locked-file OS errors without aborting unrelated actions, and writes accurate `execution_report.json`. | SI-004 | PASS |
| POS-05 | Migrated test harness is run from current repository root. | `tests` discovery imports successfully without legacy absolute path assumptions. | SI-005 | PASS |
| POS-06 | Source tree is compiled. | Python source compiles without syntax errors. | SI-006 | PASS |

---

## 4. Required Failure Scenarios

| Scenario ID | Failure Condition | Expected Handling | Links to Constraint | Status |
| :--- | :--- | :--- | :--- | :--- |
| NEG-01 | Stored `layered_manifest.json` has invariant corruption. | Build aborts; no fallback to legacy full scan; user-facing log instructs full rebuild. | ADR-002 | PASS |
| NEG-02 | Gate 2 cannot guarantee zero false negatives under chosen fingerprint design. | CDC documents residual risk in IMPL and requests ANT/Director decision before claiming PASS. | ADR-003 | PASS |
| NEG-03 | Action queue strict zero-stat policy conflicts with fallback-awareness logging. | CDC selects strict compliance or explicit safety exception; undocumented mixed behavior is rejected. | CON-007 / SI-004 | PASS |
| NEG-04 | Wrapper/integration tests require real AppData or executable mutation. | Tests are marked or isolated as integration tests; unit discovery still passes without modifying user state. | CON-003 | PASS |

---

## 5. Verification Commands

All generated scripts, mock datasets, logs, and simulation outputs must be stored in `Delta/08_Test/`.

```powershell
# Source syntax gate
python -m compileall -q src\MO2_Hardlink_Builder_V4b

# Source unit discovery gate
python -m unittest discover -s src\MO2_Hardlink_Builder_V4b -p "test*.py"

# Migrated external test discovery gate
python -m unittest discover -s tests -p "test*.py"

# v0.7 targeted regression gate
# CDC may implement this as unittest/pytest, but it must cover POS-01 through POS-04.
python -m unittest discover -s Delta\08_Test -p "test_v07*.py"
```

If CDC uses `pytest`, CDC must document the equivalent command and dependency expectation in `CDC-IMPL-002-v0.7.md`.

---

## 6. Required Evidence

| Evidence ID | Required Artifact | Location |
| :--- | :--- | :--- |
| EV-001 | Added-path incremental regression log/output | `Delta/08_Test/` |
| EV-002 | Controller no-full-pre-scan proof, preferably mock call counter or instrumentation log | `Delta/08_Test/` |
| EV-003 | Gate 2 false-negative regression output | `Delta/08_Test/` |
| EV-004 | Action queue execution report and policy test | `Delta/08_Test/` and standalone metadata scratch output |
| EV-005 | Test discovery output for `src` and `tests` | `Delta/08_Test/` |
| EV-006 | `compileall` output or transcript | `Delta/08_Test/` |

---

## 7. QA Findings To Retest

| Finding ID | Severity | Original Evidence | Required Retest |
| :--- | :--- | :--- | :--- |
| V07-FIND-001 | Critical | Added file in dirty mod was absent from `path_owners` and `_active_map`. | POS-01 |
| V07-FIND-002 | Critical | Controller called legacy `build_mapping()` before layered tri-gate. | POS-02 |
| V07-FIND-003 | Critical | Gate 2 returned clean when fourth nested file changed with same size. | POS-03 |
| V07-FIND-004 | High | Action queue docstring claimed zero stat, but executor used `exists()` and inode verification through `_hardlink_verified()`. | POS-04 / NEG-03 |
| V07-FIND-005 | Medium | `tests` discovery failed due to hardcoded legacy absolute paths. | POS-05 / NEG-04 |

---

## 8. Director Manual Testing Sync

Director manual testing is not required before CDC starts v0.7. If the Director performs a real MO2 retest after CDC implementation, ANT will sync observations here before final STR verdict.

| DIR-STR Observation | Technical Implication | ANT Decision |
| :--- | :--- | :--- |
| Director reports large load order trial completed without overall issue. CDC-WALK §8 records 100 mods x 500 files = 3.895s, 200 mods x 500 files = 7.745s, throughput about 12,900 entries/s, and 1,000-mod extrapolation about 38.8s. | Gate 2 fingerprint traversal is a real O(mods x files) cost and exceeds the 5s pivot threshold at 200 x 500. Correctness risk is resolved; performance risk remains size-dependent. | ACCEPT for v0.7 as documented residual performance risk. Do not block publish on A03-PERF; track async/cached fingerprint optimization as future WO if Director targets very large load orders. |

---

## 9. STR Completeness Checklist

- [x] Test scenarios map to locked WO success indicators.
- [x] Negative scenarios cover expected failure paths.
- [x] Commands and evidence locations are recorded.
- [x] Test artifacts are required under `Delta/08_Test/`.
- [x] Constraint compliance is verified.
- [x] RCA targets are recorded for every v0.6 blocker.
- [x] Verdict will be assigned after CDC implementation.
- [x] All placeholders are replaced.

---

## 10. Runtime Lifecycle & Sign-Off

This STR was advanced to `IN_PROGRESS` when ANT QA execution began and is complete after the commands below passed in the current workspace.

## 11. ANT Execution Results

| Gate | Command | Result |
| :--- | :--- | :--- |
| Source syntax | `python -m compileall -q src\MO2_Hardlink_Builder_V4b` | PASS, exit 0 |
| Source unit discovery | `python -m unittest discover -s src\MO2_Hardlink_Builder_V4b -p "test*.py"` | PASS, 4/4 |
| External test discovery | `python -m unittest discover -s tests -p "test*.py"` | PASS, 10 tests, 1 expected skip |
| v0.7 targeted regression | `python -m unittest discover -s Delta\08_Test -p "test_v07*.py"` | PASS, 15/15 |

### ANT Verdict

**PASS.** CDC implementation satisfies ANT-WO-002-v0.7 success indicators SI-001 through SI-006. RISK-A03-PERF is accepted for v0.7 as a documented residual performance risk, not a publish blocker.

Expected CLI sequence after implementation:

```powershell
delta str advance
delta str complete
delta audit record --str ANT-STR-002-v0.7.md --actor Director --approve --note "STR v0.7 passed publish-blocker regression"
delta str lock --file ANT-STR-002-v0.7.md
```

### Verdict Rules

- **PASS:** POS-01 through POS-06 pass, NEG-01 through NEG-04 are handled, and no undocumented policy conflict remains.
- **FIX_AND_RETRY:** A blocker is fixable within v0.7 scope.
- **FAIL:** Silent ownership corruption, false-negative dirty detection, or uncontrolled full-scan fallback remains.
