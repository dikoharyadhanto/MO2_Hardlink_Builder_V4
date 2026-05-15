# CDC-IMPL-002-v0.7 — Publish-Blocker Correction for Event-Driven Incremental Build

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.7.md`, `ANT-STR-002-v0.7.md`
> **Build Output:** `src/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Pre-Implementation Plan (IMPL) |
| **Version** | v0.7 |
| **Status** | **PENDING — Awaiting ANT/Director approval** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.7.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.7.md` |
| **STRAT Reference** | `GMN-STRAT-002-v1.0.md` |
| **Walkthrough Ref** | `CDC-WALK-002-v0.7.md` *(to be generated post-QA)* |

---

## 1b. Environment & Stack

| Field | Value |
| :--- | :--- |
| **OS / Platform** | Windows 10/11 (NTFS-only per CON-001) |
| **Runtime / Language** | Python 3.10+ |
| **Key Libraries** | `pathlib`, `os`, `hashlib`, `concurrent.futures`, `unittest` |
| **Key Tools** | `python -m unittest discover`, `python -m compileall` |
| **Execution Environment** | Local (no admin privileges per CON-002) |

---

## 2. Task Interpretation & Approach

**What must be built**: Five corrective changes addressing the publish blockers found during ANT pre-publish review of the v0.6 event-driven incremental build:

- **TASK-A01**: Fix incremental Layer B to register new virtual paths introduced by dirty mods.
- **TASK-A02**: Remove the mandatory `build_mapping()` full-scan precondition from the incremental controller path.
- **TASK-A03**: Replace the first-N alphabetical Gate 2 sample with a full-metadata fingerprint that catches changes at any file position.
- **TASK-A04**: Resolve the action queue verification policy conflict — choosing Path 2 (Safety Exception) and documenting it.
- **TASK-A05**: Modernize migrated test harnesses to eliminate legacy absolute path dependencies.

**Proposed approach**:
1. Fix the incremental Layer B update in `scanner_engine.py` — after rebuilding existing dirty-owned paths, scan dirty mods' NEW files and insert them.
2. Refactor `deployment_controller.py` Stage 3 — detect INCREMENTAL + valid `layered_manifest.json` and skip `build_mapping()`, routing directly to Stage 3b.
3. Replace `_count_deployable_files` + `_gate2_sample_dirty` with a combined `_gate2_compute_fingerprint` that accumulates `(file_count, sorted_hash_of_all_mtime_size_pairs)` during a single walk — stored in Layer A, compared on every Gate 2 check.
4. Retain `_hardlink_verified()` in the Action Queue executor (Path 2), update docstring/policy note, add tests.
5. Fix both test files to resolve source root dynamically; add four new `Delta/08_Test/test_v07_*.py` regression tests covering POS-01 through POS-04.

**Rationale**: All corrections trace directly to published WO blockers. No architectural changes beyond scope. Gate 2 fingerprint approach reuses the existing file-walk already done by `_count_deployable_files`, adding zero extra I/O passes.

**Expected outputs**: 4 modified source files, 2 fixed test files, 4 new test files under `Delta/08_Test/`.

---

## 2b. Sequential Reasoning & Branching Analysis

| Branch | Approach | Trade-Offs | Decision |
| :--- | :--- | :--- | :--- |
| A01-A | After incremental Layer B rebuild, scan each dirty mod's new files and insert into path_owners | One extra iteration over dirty mod files (O(dirty × new_files)). No new I/O — reads from `new_manifest.mod_index`. | **Chosen**: zero-I/O, bounded cost, correct semantics. |
| A01-B | Rebuild all of Layer B from scratch (full_recompute_layer_b) on every incremental run | Correct but removes all incremental performance gain. | Rejected: defeats ADR-003 constraint. |
| A02-A | Skip `build_mapping()` in Stage 3 for INCREMENTAL + valid layered manifest. Derive flat manifest from layered manifest if needed downstream. | Controller routing complexity increases slightly. Legacy flat manifest produced post-facto. | **Chosen**: fulfills WO requirement exactly. |
| A02-B | Keep `build_mapping()` but run it after Stage 3b for reporting only | Violates the WO directive — "must not require `build_mapping()` before `build_layered_manifest()`". | Rejected. |
| A03-A | Full metadata fingerprint: hash of all `(path_key, mtime, size)` pairs from stored Layer A, compared against recomputed from current disk during a single `os.walk` | **O(N) stat calls per dirty-check mod** — this is a full metadata traversal, not a free operation. It is the same cost as `_count_deployable_files` (which was already doing a full walk) combined into one pass, but the cost is still proportional to file count per mod. Accepted as a correctness-over-speed safety tradeoff. | **Chosen**: correctness requires covering all file positions; bounded cost is acceptable; no stronger OS-level change signal is available on NTFS without content hashing. |
| A03-B | Evenly distributed sample (first/middle/last + N positions) | Reduces metadata traversal cost but introduces residual false-negative risk for files between sample points. | Rejected: WO requires a mechanism ANT can validate against false negatives. Full fingerprint is the only metadata-based approach that eliminates position-based gaps. |
| A04-Path1 | Strict zero-stat: remove `_hardlink_verified()` from AQ path, use raw `os.link()` with OSError fallback | Eliminates inode-verification I/O but breaks CON-007 pseudo-hardlink detection and violates FIX-02 NEVER-SILENT guarantee. | Rejected: CON-007 is Level 1. |
| A04-Path2 | Safety Exception: retain `_hardlink_verified()`, document as intentional deviation, test the policy | Adds 2 stat calls per LINK op (src + dst inode). Maintains CON-007 compliance and FIX-02 guarantees. | **Chosen**: CON-007 > zero-stat preference. |
| A05-A | Dynamic root via `Path(__file__).resolve().parent.parent` from test files | Correct portable discovery. Works from any working directory. | **Chosen**. |

**Revision / Backtracking Notes:**
- A03 initially considered evenly-distributed sampling but rejected because `_count_deployable_files` already does a full walk — adding mtime+size accumulation adds zero I/O passes while eliminating the residual risk entirely.
- A04 Path 1 was seriously considered. Rejected because CON-007 (Level 1) mandates "every hardlink-to-copy fallback must be logged and reported". Without `_hardlink_verified()`, pseudo-hardlink fallbacks go undetected and unlogged.

---

## 2c. Agent Skill Routing Evaluation

| Skill ID | Routed | STRAT-Allowed | WO-Bound | Status | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| SKILL-PythonBestPractices | Yes | Yes | Yes | AUTHORIZED | Refactoring engine/controller scan logic within blocker scope. |
| SKILL-TestAutomation | Yes | Yes | Yes | AUTHORIZED | Regression tests for manifest, tri-gate, action queue, harness migration. |
| SKILL-WindowsNativeDevelopment | Yes | Yes | Yes | AUTHORIZED | Hardlink/AQ policy and NTFS path behavior validation. |

---

## 3. Constraints & Freedom Of Method

| Level | Source | Constraint | CDC Compliance Plan |
| :--- | :--- | :--- | :--- |
| Level 1 | STRAT/CON-001 | Windows 10/11 NTFS-only. No cross-platform redesign. | No cross-platform changes. All path handling uses `pathlib` + `ensure_long_path`. |
| Level 1 | STRAT/CON-002 | No admin privileges required. | No elevated operations. `os.link()`, `os.stat()`, `os.walk()` all user-space. |
| Level 1 | STRAT/CON-003 | Must not modify MO2 internal files, profile data, or mod directories. | Engine code reads mod directories; never writes to them. |
| Level 1 | STRAT/CON-007 | Every hardlink-to-copy fallback must be logged and reported. | `_hardlink_verified()` retained in AQ path. All fallbacks logged via `audit_logger`. |
| Level 1 | STRAT/ADR-002 | Dual-layer RAM manifest is the source of ownership truth. | Layer A + B remain authoritative. No flat-manifest ownership lookups in incremental path. |
| Level 1 | STRAT/ADR-003 | Tri-gate must avoid scanning unchanged physical mod directories during incremental. | TASK-A02 fix ensures clean mods are not traversed by `build_mapping()` or Gate 3. |
| Level 2 | STRAT/ADR-004 | Transactional checkpoint behavior must remain intact. | `DeploymentTransactionManager` untouched. AQ path calls `tx_manager.begin/tick/complete`. |

---

## 4. Technical Decision Log

| Decision ID | Decision | Alternatives | Rationale | Linked Constraint / SI |
| :--- | :--- | :--- | :--- | :--- |
| DEC-001 | Added-path insertion in incremental Layer B via a second pass over dirty mod files | Full `full_recompute_layer_b()` on every incremental run | Bounded O(dirty×new_files) in RAM, zero I/O, preserves incremental performance | ADR-003, SI-001 |
| DEC-002 | Skip `build_mapping()` in Stage 3 when INCREMENTAL + valid layered manifest | Always run `build_mapping()` | Eliminates the full-scan precondition that was the root cause of V07-FIND-002 | ADR-003, SI-002 |
| DEC-003 | Gate 2 uses stored `file_fingerprint` = SHA-256 of sorted `(path_key, mtime, size)` pairs, computed during a full metadata traversal (ANT Safety Exception — correctness-over-speed tradeoff) | Evenly-distributed sample of files | Zero false negatives from any file position; full O(N) metadata traversal per mod is the same cost class as the prior `_count_deployable_files` walk — no additional filesystem pass added, but total Gate 2 cost is O(mods × files). Benchmark evidence required in WALK. | ADR-003, SI-003 |
| DEC-004 | Action Queue executor keeps `_hardlink_verified()` (Path 2 Safety Exception); removes false "zero stat" docstring claim | Remove `_hardlink_verified()` (Path 1 strict) | CON-007 Level 1 compliance requires logging pseudo-hardlink fallbacks; raw `os.link()` cannot detect them | CON-007, SI-004 |
| DEC-005 | `execute_action_queue()` Phase 2 retains `target_full.exists()` guard before unlink | Remove the `exists()` stat call | `unlink(missing_ok=True)` on a non-existent path is a no-op, so the guard is redundant; remove it to reduce stat calls while keeping `missing_ok=True` idempotency | SI-004 |
| DEC-006 | `_flat_manifest_from_layered()` helper in controller derives `mapping_manifest.json` from `LayeredManifest._active_map` for INCREMENTAL runs | Run `build_mapping()` after Stage 3b for legacy compat | Layered manifest is the authoritative source; flat manifest for reports can be derived in O(N) without filesystem scan | ADR-002, WO TASK-A02 |
| DEC-007 | Gate 2 fingerprint stored as `"file_fingerprint"` key in Layer A entry | Embed in `file_count` as a compound field | Separate key is backwards-compatible and easy to validate in tests | ADR-002 |

---

## 5. Files To Create / Modify

| File Path | Action | Purpose | Linked WO Item |
| :--- | :--- | :--- | :--- |
| `src/MO2_Hardlink_Builder_V4b/model/engines/scanner_engine.py` | MODIFY | Fix incremental Layer B added-path handling; replace sample fingerprint with full metadata fingerprint | TASK-A01, TASK-A03 |
| `src/MO2_Hardlink_Builder_V4b/controller/deployment_controller.py` | MODIFY | Skip `build_mapping()` for INCREMENTAL + valid layered manifest; add `_flat_manifest_from_layered()` helper; add log messages distinguishing scan paths | TASK-A02 |
| `src/MO2_Hardlink_Builder_V4b/model/engines/linker_executor.py` | MODIFY | Remove redundant `exists()` guard from Phase 2; update docstring to accurately state inode verification is retained (Path 2 Safety Exception) | TASK-A04 |
| `tests/test_wrapper.py` | MODIFY | Replace hardcoded absolute path with dynamic repo-root resolution | TASK-A05 |
| `tests/simulate_incremental.py` | MODIFY | Replace hardcoded absolute path with dynamic repo-root resolution | TASK-A05 |
| `Delta/08_Test/test_v07_added_path.py` | CREATE | POS-01 regression: previous manifest has `file1`, dirty mod adds `file2`, action queue contains `LINK data/file2.txt` | TASK-A01, SI-001 |
| `Delta/08_Test/test_v07_no_full_prescan.py` | CREATE | POS-02 regression: incremental build with valid layered manifest does not call `build_mapping()` (mock call counter) | TASK-A02, SI-002 |
| `Delta/08_Test/test_v07_gate2_deep_file.py` | CREATE | POS-03 regression: 4 nested files, only 4th changes (same size, same root mtime), Gate 2 returns dirty | TASK-A03, SI-003 |
| `Delta/08_Test/test_v07_action_queue.py` | CREATE | POS-04 regression: phased DELETE→LINK execution, locked-file error handling, `execution_report.json` written | TASK-A04, SI-004 |

**Total: 3 modified source files + 2 fixed test files + 4 new test files**

---

## 6. Key Abstractions & Logic

### TASK-A01: Incremental Layer B Added-Path Insertion

**Current bug** (`scanner_engine.py`, `build_layered_manifest()` lines 604–644):
The incremental Layer B update collects `paths_to_rebuild` by scanning `prev_manifest.path_owners` for entries where any owner is in `dirty_mod_names`. However, if a dirty mod adds a **new** virtual path that was never in `prev_manifest.path_owners`, that path is never added to `new_manifest.path_owners`.

**Fix**: After the existing `paths_to_rebuild` loop, add a second pass:
```python
# Second pass: new paths introduced by dirty mods that were absent from prev Layer B
priority = {mod: idx for idx, mod in enumerate(load_order)}
for mod_name, _ in dirty_mods:
    new_entry = new_manifest.mod_index.get(mod_name, {})
    for path_key in new_entry.get("files", {}):
        if path_key not in new_manifest.path_owners:
            # New path — collect all providers and sort by priority
            providers = [
                m for m, e in new_manifest.mod_index.items()
                if m != "__meta__" and path_key in e.get("files", {})
            ]
            sorted_owners = sorted(providers, key=lambda m: priority.get(m, -1), reverse=True)
            if sorted_owners:
                new_manifest.path_owners[path_key] = sorted_owners
```
Then call `new_manifest._rebuild_active_map()` at the end.

---

### TASK-A02: Controller Incremental Path Without Full-Scan Precondition

**Current bug**: Stage 3 always calls `scanner.build_mapping()`. Stage 3b then calls `scanner.build_layered_manifest()` after this full scan.

**Fix**: Detect `INCREMENTAL + layered_manifest.json exists and loads without error`. If both conditions hold, skip `scanner.build_mapping()` and produce the flat manifest by deriving it from the layered manifest:

```python
# New helper in deployment_controller.py
def _flat_manifest_from_layered(layered_manifest, metadata_dir):
    """Derives mapping_manifest.json from LayeredManifest._active_map."""
    mapping = {}
    for path_key, entry in layered_manifest._active_map.items():
        mapping[path_key] = {
            "source": entry["source"],
            "mod_origin": entry["mod_origin"],
            "is_root": entry.get("is_root", False),
            "size_bytes": entry.get("size_bytes", 0),
            "mtime": entry.get("mtime", 0),
            "preferred_path": entry.get("preferred_path", path_key),
        }
    output = {
        "version": MANIFEST_VERSION,
        "mapping": mapping,
        "scan_failures": {},
        "folder_states": {},
    }
    manifest_path = metadata_dir / "mapping_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)
    return manifest_path
```

Stage 3 log messages will clearly state one of three states:
- `"[*] S3: INCREMENTAL (tri-gate) — skipping legacy full scan."`
- `"[*] S3: FULL/FRESH — legacy full scan running."`
- `"[*] S3: INCREMENTAL FALLBACK — layered manifest invalid, running full scan."`

**Invariant violation handling**: If `LayeredManifest.load()` raises `ValueError("invariant violation")` during Stage 3 routing, the build **aborts** (no silent fallback to full scan). This is consistent with the existing Stage 3b abort logic.

---

### TASK-A03: Gate 2 Full Metadata Fingerprint — Correctness-Over-Speed Safety Tradeoff

**Current bug**: `_gate2_sample_dirty()` samples only the first 3 alphabetical deep files. Files at other positions are invisible to Gate 2. POS-03 requires detecting a change to the 4th file when root mtime is unchanged.

**Fix**: Replace the separate `_count_deployable_files()` + `_gate2_sample_dirty()` with a unified `_gate2_compute_fingerprint()` that performs one walk and returns `(file_count, fingerprint_hex)`:

```python
def _gate2_compute_fingerprint(self, folder: Path) -> tuple[int, str]:
    """
    Single-pass walk: counts deployable files AND computes a metadata fingerprint.
    Fingerprint = SHA-256 of sorted (path_key, mtime_repr, size_repr) tuples.

    PERFORMANCE NOTE: This is a full metadata traversal — O(N) stat calls where
    N is the number of deployable files in the mod folder. This is a
    correctness-over-speed safety tradeoff (ANT Safety Exception, CDC-IMPL-002-v0.7
    DEC-003). The prior _count_deployable_files() already performed the same O(N)
    walk; this method replaces it without adding an additional filesystem pass,
    but the total metadata traversal cost (O(N) per checked mod) is unchanged
    and is the same cost class as Gate 3 for a single mod.

    Called during Gate 3 to store in Layer A, and during Gate 2 dirty-check to
    compare against the stored fingerprint.
    """
    import hashlib
    entries = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs
                   if d.lower() not in self.blacklist_dirs
                   and d.lower() not in self._EXCLUDED_DIRS]
        for fn in files:
            ext = Path(fn).suffix.lower()
            if (fn.lower() in self.blacklist_files
                    or ext in self.blacklist_extensions
                    or ext in self._EXCLUDED_EXTENSIONS):
                continue
            full = Path(root) / fn
            try:
                st = full.stat()
                rel = str(full.relative_to(folder)).replace("\\", "/")
                entries.append(f"{rel}|{st.st_mtime:.3f}|{st.st_size}")
            except OSError:
                entries.append(f"{str(full)}|ERR|ERR")
    entries.sort()
    h = hashlib.sha256("\n".join(entries).encode()).hexdigest()
    return len(entries), h
```

**Performance characterisation — Honest Statement (ANT Safety Exception)**:

Gate 2 now performs a full metadata traversal for every active mod on every incremental run. This is an explicit correctness-over-speed tradeoff:

- The prior `_count_deployable_files()` already did an O(N) `os.walk` per checked mod. This method replaces it without an additional pass — the number of filesystem traversals is unchanged.
- However, Gate 2 checks **all active mods** (not just dirty ones). The total cost is O(mods × files_per_mod) stat calls across the entire modlist.
- For a 1,000-mod list with an average of 500 files per mod, this is approximately 500,000 stat calls. On a local NTFS SSD, stat calls typically complete at ~100,000–500,000/sec. Estimated Gate 2 range: 1–5 seconds total.
- No stronger OS-level change signal (inotify/ReadDirectoryChangesW) is available in the current architecture without a persistent daemon — out of scope for this WO.

**Benchmark evidence requirement**: CDC will record Gate 2 timing in `CDC-WALK-002-v0.7.md` using a synthetic mod set (minimum: 100 mods × 500 files = 50,000 entries). If Gate 2 traversal exceeds 5 seconds for a 1,000-mod list, CDC will flag this as a performance concern requiring an ANT pivot decision before the STR passes.

**Correctness guarantee**: Any change to any file's mtime or size — regardless of alphabetical position — triggers a dirty result. No false negatives from file position. This is the only metadata-based mechanism that satisfies POS-03 without content hashing.

**Layer A schema addition**: `_gate3_scan_mod()` stores `"file_fingerprint": str` alongside `file_count`. Gate 2 `_gate2_mod_dirty()` replaces the `_count_deployable_files` + `_gate2_sample_dirty` calls with a single `_gate2_compute_fingerprint()` call and compares both `file_count` and `file_fingerprint`.

**Residual risk (TASK-A03-RR)**: A file whose **content** changes while **both mtime and size remain identical** (e.g., deliberate mtime preservation, or re-extraction from an archive with an identical binary) will not be detected by Gate 2 or Gate 3. This is an acknowledged and unchanged limitation of metadata-based dirty detection. `paranoid_mode` does not help; Gate 3 does not hash content. This risk existed in v3.6 and is not a regression. Users who require content-level verification must run a full rebuild. CDC declares this residual risk explicitly per WO TASK-A03 requirement.

---

### TASK-A04: Action Queue Verification Policy — Path 2 Safety Exception

**Policy choice**: Path 2 — Safety Exception. `_hardlink_verified()` is retained in `execute_action_queue()` Phase 2.

**Rationale**:
- CON-007 (Level 1): "Every hardlink-to-copy fallback must be logged and reported." Without inode verification, pseudo-hardlinks (FAT32, AV interference, cross-volume edge cases on NTFS) are silently promoted to apparent success. The FIX-02 guarantee of "NEVER silent" is only achievable by reading the inode after link creation.
- The 2 stat calls per LINK operation (`src.stat()` + `dst.stat()`) are bounded, fast, and unavoidable for CON-007 compliance.
- The `target_full.exists()` guard before unlink in Phase 2 is **removed** (DEC-005). `unlink(missing_ok=True)` already handles the non-existent case. This eliminates one redundant stat call per LINK operation.

**Updated docstring** in `execute_action_queue()`:
> "Note — Bounded inode verification: `_hardlink_verified()` performs 2 stat calls per LINK to detect pseudo-hardlinks and log fallbacks (CON-007 Level 1 compliance). This is a documented Safety Exception per CDC-IMPL-002-v0.7.md DEC-004. The 'zero stat' claim in the v0.6 docstring was incorrect and is removed."

---

### TASK-A05: Test Harness Modernization

Both `tests/test_wrapper.py` and `tests/simulate_incremental.py` use:
```python
workspace = Path(os.path.abspath(r"i:\Works\005_MO2_Hardlink_Builder_V4b"))
sys.path.insert(0, str(workspace / "03_Build" / "MO2_Hardlink_Builder_V4b"))
```

**Fix**: Replace with dynamic root resolution:
```python
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))
```

The four new `Delta/08_Test/test_v07_*.py` files will each:
- Resolve `_SRC_ROOT` the same way from `Delta/08_Test/` (`parent.parent.parent / "src" / ...`)
- Stub the `mobase` import to allow test discovery without MO2 runtime
- Use only in-process mocks/tempdir (no real MO2 paths)
- Be discoverable by `python -m unittest discover -s Delta\08_Test -p "test_v07*.py"`

---

## 7. Dependency Changes

No new dependencies. All changes use Python stdlib: `pathlib`, `os`, `hashlib`, `json`, `unittest`, `unittest.mock`.

---

## 8. Testing Plan

| Test Area | Method / Command | Linked ANT-STR Scenario | Expected Result |
| :--- | :--- | :--- | :--- |
| POS-01: Added-path incremental | `python -m unittest Delta\08_Test\test_v07_added_path.py` | POS-01 / SI-001 | Action queue contains `LINK data/file2.txt`; `path_owners` includes `data/file2.txt` |
| POS-02: No full-pre-scan | `python -m unittest Delta\08_Test\test_v07_no_full_prescan.py` | POS-02 / SI-002 | `build_mapping` mock call count = 0 for INCREMENTAL path |
| POS-03: Gate 2 deep file | `python -m unittest Delta\08_Test\test_v07_gate2_deep_file.py` | POS-03 / SI-003 | `_gate2_mod_dirty()` returns `True` when 4th nested file mtime changes |
| POS-04: Action queue phased execution | `python -m unittest Delta\08_Test\test_v07_action_queue.py` | POS-04 / SI-004 | All DELETEs before LINKs; locked-file error logged and counted; `execution_report.json` written |
| Source syntax gate | `python -m compileall -q src\MO2_Hardlink_Builder_V4b` | SI-006 | Exit 0 |
| Src test discovery | `python -m unittest discover -s src\MO2_Hardlink_Builder_V4b -p "test*.py"` | SI-005 | No import errors |
| External test discovery | `python -m unittest discover -s tests -p "test*.py"` | SI-005 | No import errors |
| v0.7 regression gate | `python -m unittest discover -s Delta\08_Test -p "test_v07*.py"` | POS-01 through POS-04 | All tests pass |

---

## 9. Technical Debt & Residual Risks

| Risk ID | Risk | Impact | Mitigation / Follow-Up |
| :--- | :--- | :--- | :--- |
| RISK-A03-RR | Gate 2 fingerprint cannot detect content changes when mtime+size are both identical (e.g., preserved-mtime re-extraction) | Medium — missed dirty mod goes unredeployed | Inherited risk from v3.6; not a regression. Users must run a full rebuild for content-level audit. Declared per WO TASK-A03. |
| RISK-A03-PERF | Gate 2 now performs O(mods × files) metadata traversal — full modlist scan on every incremental run | Medium — Gate 2 cost scales with total active mod file count | Prior `_count_deployable_files` walk had the same O(N) per-mod class; no additional filesystem pass added. Benchmark required in WALK. ANT pivot required if Gate 2 exceeds 5s for 1,000-mod list. |
| RISK-A04-SE | Path 2 Safety Exception adds ~2 stat calls per LINK op in the Action Queue path | Low — bounded, fast syscalls | Accepted. CON-007 Level 1 compliance requires this cost. No removal without Director approval and constraint revision. |
| RISK-A02-FLAT | `_flat_manifest_from_layered()` derives the flat manifest from `_active_map`, which only contains winning-mod entries. Multi-provider conflicts are not recorded in the flat manifest. | Low — flat manifest used for reporting only, not for deployment logic | Acceptable: flat manifest is a reporting artifact. The layered manifest (authoritative) captures all providers in Layer B. A note will be added to the ReportGenerator call. |
| RISK-A05-MOBASE | `tests/simulate_incremental.py` and `test_wrapper.py` import `model.engines.*` which transitively may import `mobase`. A stub is required for import to succeed in test discovery. | Medium — import error blocks CI discovery | Each fixed test file adds a `sys.modules['mobase'] = MagicMock()` stub before importing source modules. |

---

## 10. NLM Knowledge Research Request

None. All changes are within existing Python stdlib and established project patterns.

---

## 11. IMPL Completeness Checklist

- [x] Task interpretation reflects locked ANT-WO.
- [x] Approach respects DI/STRAT/WO hierarchy.
- [x] Sequential reasoning and fallback path are documented.
- [x] Skill routing outcome is recorded.
- [x] Level 1/2 constraints have explicit compliance plans.
- [x] Files and dependency changes are identified.
- [x] Testing plan maps to ANT-STR scenarios.
- [x] Risks and open questions are documented.
- [x] No unresolved requirement invention remains.
- [x] TASK-A03 residual risk explicitly stated (per WO requirement).
- [x] TASK-A04 policy choice (Path 2) explicitly documented with rationale.

---

## 12. Runtime Lifecycle

```bash
delta impl complete --file CDC-IMPL-002-v0.7.md
```

IMPL is auto-locked when same-version ANT-STR is locked, if IMPL is COMPLETE.

---

*CDC-IMPL-002-v0.7 drafted. Status: **PENDING ANT/Director approval**. No code will be modified until the GO signal is received.*
