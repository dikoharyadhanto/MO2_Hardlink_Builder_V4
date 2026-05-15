# CDC-IMPL-005-v3.5 — Implementation Log: Vanilla Asset Starvation Fix

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-005-v3.5.md`
> **Build Output:** `03_Build/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Implementation Log (IMPL) |
| **Version** | v3.5 |
| **Status** | **COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-005-v3.5.md` |
| **Test Plan Ref** | `ANT-STR-005-v3.5.md` |
| **Walkthrough Ref** | `CDC-WALK-005-v3.5.md` |

---

## 2. Scope of Change

**Single file modification**: `model/engines/scanner_engine.py`

### 2.1 What Changes

| Region | Current Behavior | New Behavior |
| :--- | :--- | :--- |
| `scan_base_game()` — `excluded_dirs` (line 201) | `{"data", "mods", "_commonredist"}` — skips vanilla Data/ entirely | `{"mods", "_commonredist"}` — correctly traverses and registers all vanilla Data/ assets |
| `scan_base_game()` — docstring | States "Skips Data/ and mods/ subdirectories" | Updated to "Skips mods/ and _commonredist/ subdirectories" |

### 2.2 What Does NOT Change

- `LinkerExecutor.deploy_base_game()` — unchanged, already handles full base_mapping deployment
- `LinkerExecutor.execute_mapping()` — unchanged, correctly overwrites base game files with mod files via `os.remove()` + `_hardlink_verified()` (TASK-A02 verified)
- `ScannerEngine.build_mapping()` — unchanged, mod manifest is independent of base game scan
- All FIX-01 through FIX-05 and FEAT-15/v3.4 invariants preserved

### 2.3 TASK-A02 Verification

| Check | Result |
| :--- | :--- |
| Does `execute_mapping()` delete target before relinking? | ✅ Yes — line 296: `os.remove(target_full_path)` |
| Does Inode Fast-Path detect vanilla-vs-mod mismatch? | ✅ Yes — different source files have different inodes → falls through to destructive relink |
| Does `deploy_base_game()` run before `execute_mapping()`? | ✅ Yes — controller lines 454–457 (base game) before lines 482–492 (mod deploy) |

**TASK-A02: No code change required.**

---

## 3. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **Remove `"data"` from set rather than adding a separate Data/ scan path** | The existing `rglob("*")` recursion at line 226 already handles arbitrary subdirectories. Removing the exclusion is the minimal, zero-risk fix that restores exact V3 behavior. |
| TD-02 | **Updated docstring to match new behavior** | Prevents future developers from re-adding the exclusion based on the old documentation. |

---

## 4. Files Modified

| File Path | Action | Purpose |
| :--- | :--- | :--- |
| `model/engines/scanner_engine.py` | MODIFY | TASK-A01: Remove `"data"` from `excluded_dirs` in `scan_base_game()`. Update docstring. |

**Total files modified: 1**

---

## 5. STR Mapping

| STR Phase | Scenario | Implementation Point |
| :--- | :--- | :--- |
| Phase 1 | Pre-implementation baseline: confirm missing BSAs (472 count, no `Skyrim.esm`) | N/A — baseline verification only |
| Phase 2 | Post-implementation: BSA count must reach 565, `Skyrim.esm` present | `excluded_dirs` fix → `scan_base_game()` traverses Data/ → `deploy_base_game()` hardlinks all vanilla assets |
| Phase 3 | Runtime stability: game reaches Main Menu without 0x00 crash | All vanilla BSAs and ESMs present → engine loads successfully |

---

## 6. Phase Status

| Phase | Status | Notes |
| :--- | :--- | :--- |
| Pre-Implementation Walkthrough | `[x] Complete` | `CDC-WALK-005-v3.5.md` submitted |
| ANT/Director Approval | `[x] Fast-tracked` | Director authorized immediate implementation (critical hotfix) |
| Implementation | `[x] Complete` | `scanner_engine.py` — 1 line changed + docstring updated |
| Handoff to ANT QA | `[x] READY` | — |

---

## 7. Technical Debt & Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | The original FEAT-05 blueprint (`V3_UPDATE_GUIDANCE.md`) contains the incorrect `"data"` exclusion directive. If anyone references that document for future development, they may re-introduce the bug. | Low | The blueprint is a historical document in the archive. The current `scanner_engine.py` code and this IMPL log serve as the authoritative reference. |

---

*Implementation complete. ANT: proceed to run `ANT-STR-005-v3.5.md` (Phase 1 → 2 → 3) — Full Rebuild required to regenerate base_mapping with vanilla Data/ included.*
