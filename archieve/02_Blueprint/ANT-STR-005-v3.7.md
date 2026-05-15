# ANT STRATEGY (STR) — 005-v3.7
**Project:** MO2 Hardlink Builder V4b
**Phase:** Event-Driven Incremental Build Validation Strategy
**Status:** ACTIVE

## 1. Objective
To define the testing, validation, and execution boundaries for the v3.7 Event-Driven Incremental Build Architecture. This strategy ensures the transition from an I/O-bound verification model to a RAM-bound state machine is executed without introducing silent ownership corruption or false-negative update skips.

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
