# CDC-WALK-002-v0.4 — Pre-Implementation Walkthrough: Vanilla Asset Starvation Fix

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.4.md` + `ANT-STR-002-v0.4.md`
> **Status**: Implementation complete — fast-tracked by Director (critical hotfix).

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Walkthrough (WALK) |
| **Version** | v0.4 |
| **Status** | **IMPL COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.4.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.4.md` |

---

## 2. Task Interpretation

### What I understand must be implemented:

The V4 `ScannerEngine.scan_base_game()` method incorrectly excludes the `Data/` directory from the base game scan due to a flawed FEAT-05 blueprint directive. This causes all vanilla master files (`Skyrim.esm`, `Update.esm`, etc.) and critical BSA archives (`Skyrim - Interface.bsa`, `Skyrim - Meshes0.bsa`, Creation Club content) to be missing from the standalone environment.

**Impact**: `EXCEPTION_ACCESS_VIOLATION` (0x00) crash at Main Menu when shaders or UI frameworks attempt to load assets from missing BSAs.

**Root cause**: Line 201 of `scanner_engine.py`:
```python
excluded_dirs = {"data", "mods", "_commonredist"}  # ← "data" must be removed
```

### The fix (per ANT-WO-002-v0.4):

**TASK-A01**: Remove `"data"` from `excluded_dirs`. The set becomes `{"mods", "_commonredist"}`.

**TASK-A02**: Verify that `LinkerExecutor.execute_mapping()` correctly handles mod-over-vanilla conflicts. **Verified** — the existing `os.remove()` + `_hardlink_verified()` loop (and the v3.4 Inode Fast-Path) correctly detect inode mismatches and relink when a mod file needs to overwrite a base game hardlink. No code change needed.

---

## 3. Proposed Approach

### 3.1 scanner_engine.py — Remove "data" from excluded_dirs

One-line change at line 201. The `scan_base_game()` method already has full recursive traversal logic for subdirectories (line 224–237 via `rglob("*")`). Removing `"data"` from the exclusion set is sufficient to restore V3 behavior.

### 3.2 Conflict Resolution (TASK-A02 — Verification Only)

The deployment flow is: base game → mod overlay. `LinkerExecutor.deploy_base_game()` runs first, then `execute_mapping()` runs the mod manifest. When a mod overwrites a vanilla file:

1. The v3.4 Inode Fast-Path checks `target.stat().st_ino == source.stat().st_ino`.
2. The base game file's inode ≠ the mod file's inode → mismatch.
3. Falls through to `os.remove()` + `_hardlink_verified()` → vanilla file deleted, mod file linked.

**Result**: Correct conflict resolution. No change needed.

---

## 4. Files to Create/Modify

| File | Action | Purpose |
| :--- | :--- | :--- |
| `model/engines/scanner_engine.py` | MODIFY | Remove `"data"` from `excluded_dirs` in `scan_base_game()`, update docstring |

**All changes within `03_Build/`.** Single file, single line of logic changed.

---

## 5. Dependencies

**None.**

---

## 6. Flags / Risks

| # | Risk | Severity | Mitigation |
| :--- | :--- | :--- | :--- |
| F-01 | **Increased scan time**: Traversing the full vanilla `Data/` adds ~500+ files to `base_mapping`. | None | The V3 builder did this exact traversal. The scan is I/O-bound and the additional files are a trivial overhead compared to the mod scan. |
| F-02 | **Duplicate deployment**: If a mod file and a vanilla file share the same relative path, the mod's version should win. | None | Base game files are deployed first via `deploy_base_game()`, then `execute_mapping()` overwrites with mod versions. The `os.remove()` before `_hardlink_verified()` ensures correct replacement. |

---

## 7. Success Indicator Mapping

| WO Indicator | Implementation Point |
| :--- | :--- |
| **AC-1**: Standalone Data/ contains same vanilla BSA/ESM count as real game | `scan_base_game()` now traverses Data/ → `deploy_base_game()` hardlinks all vanilla assets |
| **AC-2**: Game reaches Main Menu without 0x00 crash | All required BSAs and ESMs present → engine loads successfully |

---

*Implementation complete. See `CDC-IMPL-002-v0.4.md` for the full implementation log.*
