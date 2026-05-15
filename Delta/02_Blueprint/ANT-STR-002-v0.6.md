# ANT STRATEGY (STR) — 002-v0.6
**Project:** MO2 Hardlink Builder V4b
**Phase:** Event-Driven Incremental Build Validation Strategy
**Status:** ACTIVE

## 1. Objective
To define the testing, validation, and execution boundaries for the v0.6 Event-Driven Incremental Build Architecture. This strategy ensures the transition from an I/O-bound verification model to a RAM-bound state machine is executed without introducing silent ownership corruption or false-negative update skips.

## 2. Validation Directives

### 2.1. Invariant Integrity Testing (Multi-Layered State)
*   **Hypothesis:** The `Virtual Path-to-Owners Stack` perfectly mirrors the MO2 load order.
*   **Test Vector (T1 - Pop Fallback):** Disable a high-priority mod that overrides a base mod. 
*   **Expected Outcome:** The system must resolve the fallback owner in $O(1)$ time strictly by popping the top of the stack. The physical hardlink must be updated to the base mod without scanning the base mod's directory.
*   **Failure Condition:** The system fails the invariant check (`top_of_stack != active_owner`) or requires a full traversal to find the fallback owner.

### 2.2. Tri-Gate Resilience Testing
*   **Hypothesis:** The tri-gate detection system blocks unnecessary `os.stat` calls while catching deep file modifications.
*   **Test Vector (T2 - Deep Mod Edit):** Modify a texture file nested 4 directories deep inside a mod using an external editor without modifying the root folder `mtime`.
*   **Expected Outcome:** Gate 2 (Mod Dirty Flag) must detect the change either via `meta.ini` timestamp or `file_count` mismatch, triggering Gate 3 (Selective Stat) for that specific mod only.
*   **Failure Condition:** The system skips the mod (False Negative) resulting in an outdated hardlink.

### 2.3. Explicit Load Order Shift Testing
*   **Hypothesis:** Changes in `modlist.txt` trigger a pure RAM-based global recompute.
*   **Test Vector (T3 - Reorder):** Swap the priority of two major mods in MO2.
*   **Expected Outcome:** The system detects the Gate 1 hash mismatch and initiates a full ownership recalculation in memory. No physical files are scanned unless they also fail Gate 2/Gate 3. The `Virtual Path-to-Owners Stack` is fully rebuilt and correct action queues are generated.
*   **Failure Condition:** The system attempts a "semi-incremental" physical scan, causing an I/O stat storm.

### 2.4. Idempotency & Action Queue Execution
*   **Hypothesis:** The action queue is blindly executed but mathematically safe.
*   **Test Vector (T4 - Double Execution):** Run the linker executor twice without changing the manifest or the source files.
*   **Expected Outcome:** The second run produces zero items in the Action Queue. If the queue is manually re-fed into the executor, it overwrites the existing hardlinks without errors, side-effects, or duplications.
*   **Failure Condition:** Running the same queue twice corrupts the target directory or throws unhandled OS exceptions.

## 3. Rollback Protocol
If any of the invariant checks fail during testing, the CDC is instructed to immediately halt execution and abort the build. Under no circumstances should the builder default to a "best-guess" physical relink. The system must hard-fail to protect the user's game directory from corrupted states.

## 4. Minor Bugs Detection

### 1. Incremental False-Positive Bypass (Redeploy All Bug)
- **Status**: FIXED
- **Symptom**: Saat melakukan *Incremental Build* untuk pertama kali setelah *Fresh Build*, mesin tidak melewatkan file yang ada, melainkan menghapus dan menautkan ulang seluruh isi modlist (500,000+ file) secara paksa. Selain itu, UI menampilkan log `SKIPPED_UNCHANGED` milik `execute_mapping` v3.6 yang usang, memberikan kesan "berhasil dilewati" padahal terjadi I/O masif di belakang layar.
- **Root Cause**: 
  1. Di *Stage 3b* (`deployment_controller.py`), pembuatan `layered_manifest.json` dilewati secara sengaja jika status `build_strategy` adalah `FULL_REBUILD`. Akibatnya, pada operasi *Incremental* berikutnya, mesin tidak menemukan manifest lama (`prev_manifest = None`).
  2. Saat `prev_manifest = None`, logika `compute_action_queue` menganggap tidak ada file di disk, sehingga memproduksi instruksi `LINK` secara massal untuk seluruh file aktif.
  3. `execute_action_queue` di `linker_executor.py` belum diinstruksikan untuk menulis file `execution_report.json`, sehingga UI membaca file laporan sisa dari sesi `execute_mapping` sebelumnya.
- **Resolution**:
  - *Stage 3b Guard Removed*: `deployment_controller.py` dimodifikasi agar **selalu** mengeksekusi `build_layered_manifest` meskipun statusnya *Full Rebuild*. Ini memastikan siklus data ke *Incremental* tidak terputus.
  - *Executor Reporting Injection*: Fungsi `execute_action_queue` disuntikkan perintah `json.dump` untuk mem-bypass *blind logging* dan memastikan *Action Queue* menulis metrik keberhasilannya secara eksplisit ke dalam `execution_report.json`.

---

## 5. ANT QA Execution Record

**Execution date:** 2026-05-14  
**Executor:** ANT  
**Scope:** v0.6 event-driven incremental architecture, reconstructed WALK cross-check, and Director manual observation `DIR-STR-002-v0.6` / `OBS-001`.

| Check | Command / Method | Result | Notes |
| :--- | :--- | :--- | :--- |
| Runtime compile | `python -m compileall -q src\MO2_Hardlink_Builder_V4b` | PASS | Source tree compiles. |
| v3.7 architecture unit simulation | `python src\MO2_Hardlink_Builder_V4b\test_v37_sim.py` | PASS | 4 tests passed: owner-stack fallback, load-order recompute, action queue idempotency, unknown-priority guard. |
| `unittest` source discovery | `python -m unittest discover -s src\MO2_Hardlink_Builder_V4b -p "test*.py"` | PASS | 4 tests passed. |
| Legacy external incremental harness | `python tests\simulate_incremental.py` | FAIL - HARNESS | Fails before execution: hardcoded legacy path prevents `model` import after migration. Not treated as product-code failure. |
| External wrapper test discovery | `python -m unittest discover -s tests -p "test*.py"` | FAIL - HARNESS | Fails before execution for the same `model` import path assumption. |
| Generated-file preservation probe | Ad hoc scratch test using `CleanerEngine.harvest_generated_files()` then `total_cleanup()` | PASS | A generated `Data/CommunityShaders/Cache/shader_cache.bin` file was copied into `mods/standalone_generated_files/CommunityShaders/Cache/` and survived standalone cleanup. |
| Delta integrity refresh | `delta refresh` | PARTIAL | v0.6 files present, but registry reports missing `DIR-STR-002-v0.5.md` as an unrelated effective `BROKEN` hygiene issue. |

### 5.1 STR Vector Coverage

| STR Vector | QA Status | Evidence |
| :--- | :--- | :--- |
| T1 - Pop Fallback | PASS | Covered by `test_t1_pop_fallback` in `test_v37_sim.py`. |
| T2 - Deep Mod Edit | PARTIAL | Tri-gate implementation is present in `scanner_engine.py`; no dedicated migrated executable harness currently runs this vector end-to-end because `tests\simulate_incremental.py` is path-broken and legacy-oriented. |
| T3 - Reorder | PASS | Covered by `test_t3_explicit_load_order_shift` and verified against `full_recompute_layer_b()`. |
| T4 - Double Execution | PASS | Covered by `test_t4_action_queue_idempotency`; executor compile and report write path also verified by static inspection. |
| DIR-STR OBS-001 - Generated cache retention | PASS - PROBE | `harvest_generated_files()` and post-cleanup retention passed in scratch QA. Director should retest in real MO2/SKSE flow before manual verdict. |

### 5.2 QA Findings

| ID | Severity | Finding | Recommendation |
| :--- | :--- | :--- | :--- |
| QA-001 | Medium | External test harnesses still contain migrated legacy path/import assumptions. | Modernize `tests\simulate_incremental.py` and `tests\test_wrapper.py` to resolve the current source root dynamically before using them as gates. |
| QA-002 | Low | `deployment_controller.py` Stage 3b comments still say FRESH/FULL_REBUILD does not build a layered manifest, but the code now always builds and saves it. | Clean up the stale comment during the next CDC maintenance pass to avoid future QA confusion. |
| QA-003 | Medium | Delta registry reports missing optional `DIR-STR-002-v0.5.md`. | Restore/recreate/supersede the v0.5 DIR-STR artifact through governed workflow or accept it as migration debt before relying on clean `delta refresh` output. |

### 5.3 ANT QA Verdict

**Technical QA verdict:** CONDITIONAL_PASS

The v0.6 implementation is coherent enough to proceed to Director real-world retest. The blocking product behavior raised in `OBS-001` has a code path and scratch-level proof of preservation, but the migrated external harnesses are not yet reliable gates and the DIR-STR v0.5 registry issue keeps project integrity from being fully clean.
