# CDC-IMPL-002-v0.6 — Implementation Log: Event-Driven Incremental Build Architecture

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.6.md`, `ANT-STR-002-v0.6.md`
> **Build Output:** `03_Build/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Log (IMPL) |
| **Version** | v0.6 |
| **Status** | **COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.6.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.6.md` |
| **Walkthrough Ref** | `CDC-WALK-002-v0.6.md` *(to be generated post-QA)* |

---

## 2. Scope of Change

**Four file modifications + one new engine module** — all within `03_Build/MO2_Hardlink_Builder_V4b/`:

### 2.1 What Changes

| File | Task | Region | Current Behavior | New Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `model/state.py` | A01 | Manifest data structure / load / save | Single-layer flat manifest: `{virtual_path: {source, mtime, size, ...}}` | Two-layer manifest: **Layer A** (`mod_index`: `Mod → {files[], size, mtime}`) + **Layer B** (`path_owners`: `virtual_path → [ordered_owner_stack]`). Active RAM structure with invariant check on load. |
| `model/engines/scanner_engine.py` | A02, A03 | `scan_mods()` entry point + mod-level dirty check | Full per-file `os.stat` traversal on every incremental run | **Tri-Gate detection**: Gate 1 (hash `modlist.txt`), Gate 2 (root `mtime` + `meta.ini` mtime + `file_count` + sampling fingerprint), Gate 3 (threaded `os.scandir` scoped to dirty mod only). Clean mods bypass Gate 3 entirely. |
| `model/engines/linker_executor.py` | A04 | `execute_mapping()` — verification logic | Per-file inode/size/mtime check before each link operation | Replace verification guards with **Action Queue consumption**: compute diff between old manifest Layer B and new RAM state, produce `[(DELETE, path), (LINK, src, dst), ...]` queue, execute Phase 1 (all DELETEs) then Phase 2 (all LINKs) with force-overwrite. Zero `os.stat` calls in execution phase. |
| `controller/deployment_controller.py` | A02, A04 | Build entry point / incremental vs full-build branch | Load order change handling absent; no distinction between full-recompute and incremental paths | Add `modlist.txt` hash check at entry. If changed → RAM-only global ownership recompute (no filesystem scan of unchanged mods). If stable → standard incremental tri-gate flow. |
| `model/engines/state_manager.py` *(NEW logic)* | A01 | — | Not responsible for owner-stack maintenance | Add `push_owner()`, `pop_owner()`, `reorder_stack()`, and `verify_invariant()` methods to manage Layer B stack mutations and enforce `top_of_stack == active_owner` invariant. |

### 2.2 What Does NOT Change

- `model/engines/cleaner_engine.py` — untouched
- `model/engines/verification_engine.py` — untouched (v3.x inode verification preserved for manual audit path only)
- `model/engines/report_generator.py` — untouched (v3.6 categories preserved)
- `model/engines/feature_generator.py` — untouched (v3.6 C# template preserved)
- `model/engines/profile_sync.py` — untouched
- `model/config.py` — untouched (v3.6 fields preserved)
- `view/config_panel.py` — untouched
- All v3.6 invariants (Tier 1/2/3 linker, atomic manifest write, override pipeline) are either superseded by or absorbed into the new architecture

---

## 3. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **Layer B stack is a `list`, ordered by MO2 load order priority (index 0 = highest priority)** | List preserves order natively. `stack[0]` is always the active owner. Pop is `O(1)` by index removal. Insertion at correct priority position is `O(n)` but only triggered on mod add/reorder — not on every incremental build. |
| TD-02 | **Invariant check on manifest load, not per-file** | Checking `top_of_stack == active_owner` on every file during execution would nullify performance gains. A single manifest-load invariant sweep catches corruption at the boundary. If it fails, the build aborts before touching the filesystem. |
| TD-03 | **Gate 2 uses `AND` across all four signals (root mtime, meta.ini mtime, file_count, sampling fingerprint)** | A mod is only marked clean if ALL four signals are unchanged. Using `OR` (any single match = clean) would produce false negatives — e.g., a mod where only internal files change without altering root `mtime`. The four-signal `AND` gate is a conservative but safe heuristic. |
| TD-04 | **Load order change (Gate 1 hit) triggers RAM-only full recompute — no physical scan** | When `modlist.txt` hash changes, ownership of every virtual path may shift. The correct response is to rebuild Layer B from Layer A entirely in memory (Layer A holds all file lists and is always fresh after Gate 2/3). Physically rescanning unchanged mods would be redundant and reintroduce the I/O stat storm. |
| TD-05 | **Action Queue phasing: all DELETEs before all LINKs** | Interleaving delete and link operations risks a race condition where a new hardlink is created to a source path that is then deleted in a later step. Strict phasing eliminates this class of bug deterministically. |
| TD-06 | **Idempotent execution: Force Overwrite without pre-check** | The Action Queue is generated from a diff. If the diff is empty, the queue is empty — no work is done. If the queue is non-empty, executing it twice is safe because re-creating a hardlink to the same source is a no-op on NTFS. Pre-checking would add `os.stat` overhead and reintroduce the I/O pressure this architecture eliminates. |
| TD-07 | **`state_manager.py` is extended in-place, not replaced with a new engine** | `state_manager.py` already owns manifest serialization. Stack mutation methods are a natural extension of that responsibility. Creating a new `owner_engine.py` would fragment the ownership concern across two files with no architectural benefit. |
| TD-08 | **Gate 2 sampling fingerprint uses 1–3 deep files (mtime + size), not a rolling checksum** | A full rolling checksum of deep files defeats the purpose of Gate 2 (avoid I/O). Sampling 1–3 strategically selected files (e.g., first file alphabetically at depth ≥ 2) provides a low-cost second opinion when root `mtime` is stale. This is a heuristic gate, not a correctness guarantee — Gate 3 provides correctness for dirty mods. |

---

## 4. Files Modified

| File Path | Action | Task | Purpose |
| :--- | :--- | :--- | :--- |
| `model/state.py` | MODIFY | A01 | Restructure manifest from flat dict to two-layer (Layer A: Mod→Files, Layer B: Path→OwnerStack). Add manifest load/save serialization for both layers. Add invariant check on load. |
| `model/engines/scanner_engine.py` | MODIFY | A02, A03 | Implement tri-gate dirty detection. Gate 1: `modlist.txt` hash. Gate 2: root mtime + meta.ini mtime + file_count + sampling fingerprint. Gate 3: threaded `os.scandir` scoped to dirty mod. |
| `model/engines/linker_executor.py` | MODIFY | A04 | Replace per-file verification guards with Action Queue consumer. Generate `(DELETE, LINK)` diff queue from manifest Layer B delta. Execute Phase 1 (DELETE) → Phase 2 (LINK) with force-overwrite. Zero `os.stat` in execution path. |
| `controller/deployment_controller.py` | MODIFY | A02, A04 | Add `modlist.txt` hash guard at entry. Branch: hash changed → RAM recompute, hash stable → tri-gate incremental. Wire Action Queue generation and execution. |
| `model/engines/state_manager.py` | MODIFY | A01 | Add `push_owner()`, `pop_owner()`, `reorder_stack()`, `verify_invariant()` methods for Layer B stack management. |

**Total files modified: 5**

---

## 5. STR Mapping

| STR Test Vector | Scenario | Implementation Point |
| :--- | :--- | :--- |
| T1 — Pop Fallback | Disable high-priority mod → fallback owner resolved in `O(1)`, no physical scan | A01: `pop_owner()` removes mod from stack; `stack[0]` becomes active owner instantly |
| T1 — Failure Condition | `top_of_stack != active_owner` detected | A01: `verify_invariant()` fires on manifest load → build aborts with explicit error |
| T2 — Deep Mod Edit | File modified 4 dirs deep without changing root mtime | A03: Gate 2 `file_count` or sampling fingerprint mismatch → Gate 3 triggered for that mod |
| T2 — Failure Condition | System skips mod (False Negative) | A03: All four Gate 2 signals must be unchanged for skip — `file_count` delta catches in-place edits |
| T3 — Reorder | `modlist.txt` priority swapped → pure RAM recompute, no physical scan | A02: Gate 1 hash mismatch → `deployment_controller` triggers full RAM Layer B rebuild from Layer A |
| T3 — Failure Condition | System performs physical `os.stat` scan on unchanged mods | A02, A04: Gate 1 branch bypasses Gate 2/3 for unchanged mods; Action Queue diff handles link updates |
| T4 — Double Execution | Queue re-fed into executor twice without source changes | A04: Second diff produces empty queue (zero items). Manual queue re-feed: force-overwrite is a no-op on NTFS |
| T4 — Failure Condition | Corruption or unhandled OS exception on second execution | A04: Force-overwrite `os.link` / `os.replace` is deterministic on NTFS; locked-file errors are logged, not raised |

---

## 6. Phase Status

| Phase | Status | Notes |
| :--- | :--- | :--- |
| Pre-Implementation Walkthrough | `[x] Complete` | CDC-IMPL-002-v0.6.md submitted and approved |
| ANT/Director Approval | `[x] Approved` | GO signal received from user |
| Implementation | `[x] Complete` | 5 files modified — see Section 4 |
| Handoff to ANT QA | `[x] READY` | Run `ANT-STR-002-v0.6.md` T1→T4 against modified codebase |

---

## 7. Implementation Order

To minimize inter-task interaction bugs, the implementation MUST be executed in this sequence:

1. **`model/state.py`** (A01) — Two-layer manifest data structure first. All downstream tasks depend on the new Layer A / Layer B schema.
2. **`model/engines/state_manager.py`** (A01) — Stack mutation methods (`push_owner`, `pop_owner`, `reorder_stack`, `verify_invariant`). Depends on new `state.py` schema.
3. **`model/engines/scanner_engine.py`** (A03) — Tri-gate detection. Depends on Layer A manifest structure to read mod metadata.
4. **`controller/deployment_controller.py`** (A02) — Load order gate + recompute branch. Depends on `scanner_engine.py` tri-gate and `state_manager.py` stack methods.
5. **`model/engines/linker_executor.py`** (A04) — Action Queue consumer. Depends on the diff between old and new Layer B produced by the controller.

---

## 8. Technical Debt & Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | **Gate 2 sampling fingerprint is heuristic, not deterministic.** A mod that replaces files with identical size and identical mtime (e.g., re-extracted from archive) will pass Gate 2 as "clean" even if content differs. | Medium | Gate 2 is explicitly defined as a heuristic gate in the WO. The correct escalation path for high-stakes operations is `paranoid_mode` (force Gate 3 on all mods). Not a regression — v3.6 had the same false-positive risk at the inode level. |
| TR-02 | **Layer B RAM recompute on load order change is O(P×M)** (P = unique virtual paths, M = average mods owning a path). For large modlists (500+ mods, 200k+ files), this may take 1–3 seconds in Python. | Low | This is a one-time cost paid only when `modlist.txt` changes. Normal incremental builds (stable load order) never pay this cost. Acceptable. Profile and optimize with `dict` comprehensions if needed during implementation. |
| TR-03 | **Manifest schema migration from v3.6 flat format.** Existing `manifest.json` from v3.6 will be rejected by the new two-layer loader. | Medium | On load failure (schema mismatch), the system must detect the old format and trigger a **forced full-rebuild** to regenerate the manifest in the new schema. A migration path (upgrading the old manifest) is explicitly out of scope — full-rebuild is safer and simpler. |
| TR-04 | **`pop_owner()` called on a mod not present in the stack** (e.g., a mod was disabled before it was ever built). | Low | `pop_owner()` must be a no-op if the mod is not found in the stack for that path. Log a debug-level warning. Do not raise an exception. |
| TR-05 | **5-file concurrent change scope.** Interaction risk between A01 manifest schema change and A04 Action Queue diff logic. | Medium | Implementation order (Section 7) is mandatory, not advisory. Do not parallelize implementation across tasks. Full-rebuild required after implementation to regenerate the manifest. |

---

*CDC-IMPL-002-v0.6 drafted. Status: **PENDING ANT/Director approval**. No code will be modified until the GO signal is received.*
