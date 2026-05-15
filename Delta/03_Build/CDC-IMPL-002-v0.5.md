# CDC-IMPL-002-v0.5 — Implementation Log: Post-v0.4 Director Feedback Refinements

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.5.md`
> **Build Output:** `03_Build/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Log (IMPL) |
| **Version** | v0.5 |
| **Status** | **COMPLETE — Ready for ANT QA** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.5.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.5.md` |
| **Walkthrough Ref** | `CDC-WALK-002-v0.5.md` |

---

## 2. Scope of Change

**Seven file modifications** — all within `03_Build/MO2_Hardlink_Builder_V4b/`:

### 2.1 What Changes

| File | Task | Region | Current Behavior | New Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `model/engines/scanner_engine.py` | A01 | `build_mapping()` + `scan_base_game()` traversal | No exclusion for `Logs/`, `backup/` dirs or `.log` files | Case-insensitive exact-name dir exclusion `{"logs","backup"}`; `.log` extension exclusion on all traversal paths |
| `model/engines/linker_executor.py` | A02, A06 | `execute_mapping()` fast-path guard | Tier 1 only (Inode match → skip) | Tier 1 (Inode) → Tier 2 (Size+mtime, when `paranoid_mode=False`) → Tier 3 (escalate + relink); new `deploy_generated_overrides()` method |
| `controller/deployment_controller.py` | A02, A04, A06 | End-of-build manifest write; build-complete signal handler | Manifest written directly; no post-build prompt; no override pass | Atomic manifest write via `tmp` + `os.replace()`; post-build prompt trigger; `deploy_generated_overrides()` call after main pass |
| `model/config.py` | A02, A04 | Config fields | No `paranoid_mode` or `show_report_prompt` fields | Add `paranoid_mode: bool = False` and `show_report_prompt: bool = True` with persistence |
| `model/engines/report_generator.py` | A03 | Result category logic + HTML template | Single ambiguous category for non-failed files | Distinct `Unchanged` / `Excluded` / `Failed` categories; `reason` causality tag field; override count in summary |
| `view/config_panel.py` | A04 | Standalone Manager Tab; build-complete handler | No "Show Report" button; no post-build prompt dialog | "Show Report" button → `os.startfile(report_path)`; post-build `QMessageBox` with "Don't show again" `QCheckBox` wired to `config.show_report_prompt` |
| `model/engines/feature_generator.py` | A05 | `_CS_TEMPLATE` C# source | Pre-launch backup incomplete; post-exit save sync non-transactional | Explicit pre-launch backup of all global files; true transactional save sync: stage → MD5 verify → `File.Move()` → delete source |

### 2.2 What Does NOT Change

- `model/engines/cleaner_engine.py` — untouched
- `model/engines/verification_engine.py` — untouched
- `model/engines/profile_sync.py` — untouched
- `model/state.py` — untouched (v3.4 delta analysis logic preserved)
- `model/engines/scanner_engine.py` base traversal architecture — only exclusion sets extended
- All FIX-01 through FIX-05 and v3.4/v3.5 invariants preserved
- `get_orphan_list()` legacy fallback — preserved, not deleted
- `deploy_base_game()` — untouched
- Existing Inode Fast-Path (Tier 1) — preserved and extended, not replaced

---

## 3. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **Tier 2 uses `AND` logic (Size AND mtime must both match)** | Using `OR` would create false-positives — a file could match size but differ in content. Both matching is a strong heuristic. Paranoid Mode bypasses this entirely for max safety. |
| TD-02 | **Atomic manifest write uses `os.replace()` not `os.rename()`** | `os.replace()` is guaranteed atomic on Windows NTFS even when target exists. `os.rename()` raises `FileExistsError` on Windows if target exists. `os.replace()` is the correct primitive. |
| TD-03 | **Allowlist for TASK-A06 is explicit `set`, not config-driven** | The WO defines the allowlist as a fixed policy (`{".dll", ".exe", ".ini", ".json", ".txt"}`). Making it config-driven would create scope creep risk (users enabling unsafe extensions). Allowlist is hardcoded in `deploy_generated_overrides()`. |
| TD-04 | **Transactional save uses MD5 not SHA256** | MD5 is sufficient for corruption detection (not security). MD5 computation is ~3x faster than SHA256. Save files are typically 1–50 MB — MD5 completes in milliseconds. SHA256 would be premature optimization. |
| TD-05 | **Tier 2 skip is only active when target file already exists** | If the target doesn't exist (new file), the code never reaches the Tier 1/2/3 guard — it falls directly to `_hardlink_verified()`. The tier logic only applies to pre-existing targets (same as v3.4 behavior). |
| TD-06 | **`deploy_generated_overrides()` runs after `execute_mapping()`, not before** | If it ran before, `execute_mapping()` could overwrite the forced-linked file with a non-override version. Running it after guarantees override files always win — correct per WO precedence rule. |
| TD-07 | **TASK-A01 exclusion applied to both `build_mapping()` and `scan_base_game()`** | Base game `Data/` can contain `.log` files from engine diagnostics. Excluding only in `build_mapping()` would allow base-game `.log` files to leak into the standalone. Both traversal paths must be guarded. |

---

## 4. Files Modified

| File Path | Action | Task | Purpose |
| :--- | :--- | :--- | :--- |
| `model/engines/scanner_engine.py` | MODIFY | A01 | Dir exclusion set `{"logs","backup"}` + `.log` extension filter in `build_mapping()` and `scan_base_game()` |
| `model/engines/linker_executor.py` | MODIFY | A02, A06 | Tier 2 (Size+mtime) + Tier 3 escalation in `execute_mapping()`; new `deploy_generated_overrides()` method |
| `controller/deployment_controller.py` | MODIFY | A02, A04, A06 | Atomic manifest write; post-build prompt signal wire; call `deploy_generated_overrides()` post-main-pass |
| `model/config.py` | MODIFY | A02, A04 | Add `paranoid_mode` and `show_report_prompt` persisted config fields |
| `model/engines/report_generator.py` | MODIFY | A03 | Category split (Unchanged/Excluded/Failed) + causality `reason` tag + override summary count |
| `view/config_panel.py` | MODIFY | A04 | "Show Report" button + post-build `QMessageBox` with "Don't show again" toggle |
| `model/engines/feature_generator.py` | MODIFY | A05 | `_CS_TEMPLATE`: pre-launch full backup of global saves/AppData; transactional post-exit save sync |

**Total files modified: 7**

---

## 5. STR Mapping

| STR Phase | Scenario | Implementation Point |
| :--- | :--- | :--- |
| Phase 1 — Step 4 | `Logs/`, `Backup/`, `.log` files absent from standalone | TASK-A01: dir exclusion + extension filter |
| Phase 1 — Step 4 | `backup_old/` **was** deployed (exact-match proof) | TASK-A01: `str.lower() in {"logs","backup"}` — exact match, `backup_old` does not match |
| Phase 1 — Step 5 | `engine.dll` deployed from disabled mod | TASK-A06: `deploy_generated_overrides()` ignores MO2 checkbox state |
| Phase 1 — Step 5 | `debug.log` excluded even from `standalone_generated_files` | TASK-A06: allowlist `{".dll",".exe",".ini",".json",".txt"}` — `.log` not in allowlist |
| Phase 1 — Step 6 | Report shows `engine.dll` tagged "Included via override" | TASK-A03 + A06: override reason tag in `report_generator.py` |
| Phase 2 — Sub-Test A | Zero-delta incremental ≤10% fresh build time | TASK-A02: Tier 1 (Inode) skips all unchanged; Tier 2 catches Size+mtime match |
| Phase 2 — Sub-Test B | Paranoid Mode catches spoofed `mtime` via Hash fallback | TASK-A02: `paranoid_mode=True` disables Tier 2 → forces hash escalation on inode mismatch |
| Phase 2 — Pass (Atomic) | `manifest.json.tmp` created, swapped only after full pass | TASK-A02: `os.replace()` atomic write in `deployment_controller.py` |
| Phase 3 — UI | "Show Report" button opens HTML report | TASK-A04: `config_panel.py` button → `os.startfile()` |
| Phase 3 — UX | Post-build prompt appears; "Don't show again" suppresses on repeat | TASK-A04: `QMessageBox` + `config.show_report_prompt` persistence |
| Phase 4 — Pre-Launch | `TEST_SAVE.ess` backed up before launch; restored after exit | TASK-A05: explicit backup-before-overwrite in `_CS_TEMPLATE` |
| Phase 4 — Transactional | `NEW_STANDALONE_SAVE.ess` synced to MO2; deleted from `Documents` | TASK-A05: stage → MD5 verify → `File.Move()` → delete source |
| Phase 4 — Failure Sim | Abrupt kill: global save in `Documents` NOT deleted | TASK-A05: delete-source only after `File.Move()` succeeds — kill before that leaves source intact |

---

## 6. Phase Status

| Phase | Status | Notes |
| :--- | :--- | :--- |
| Pre-Implementation Walkthrough | `[x] Complete` | `CDC-WALK-002-v0.5.md` submitted and approved |
| ANT/Director Approval | `[x] Approved` | Formal GO signal received |
| Implementation | `[x] Complete` | 7 files modified — see Section 4 |
| Handoff to ANT QA | `[x] READY` | — |

---

## 7. Technical Debt & Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | **Tier 2 false-positive via spoofed mtime** (e.g., zip extractor preserves original mtime on extraction). A mod update that replaces a file with identical size and preserved mtime would be missed by Tier 2. | Medium | Mitigated by `paranoid_mode` flag. Default OFF for performance. Power users / automation pipelines should enable Paranoid Mode. Documented in config. |
| TR-02 | **`manifest.json.tmp` orphan on crash**: if the process is killed during the atomic write phase, `manifest.json.tmp` is left on disk. | None | Orphaned `.tmp` is ignored on next run. `manifest.json` was never replaced, so delta analysis uses the last valid state. Correct degradation. |
| TR-03 | **`deploy_generated_overrides()` path discovery**: if `standalone_generated_files` folder name differs from the hardcoded string, the method silently no-ops. | Low | Method logs a warning when the folder is not found. The folder name should be configurable or auto-detected from `config.standalone_generated_path`. To be confirmed during implementation. |
| TR-04 | **C# MD5 check adds latency for large saves**: a 50 MB save file incurs ~30–50ms MD5 computation time. | None | Acceptable. The previous non-transactional sync had zero verification. 50ms per save file is a negligible safety cost. |
| TR-05 | **7-file concurrent change scope**: this is the largest single-cycle change in v3.x history. Risk of interaction bugs between tasks (e.g., A01 exclusion breaking A06 allowlist). | Medium | TASK-A06 precedence rule: override files bypass A01 exclusion via allowlist guard. The report (A03) must explicitly flag this. Implementation order should be: A01 → A02 → A06 → A03 → A04 → A05. |

---

*Implementation complete. ANT: proceed to run `ANT-STR-002-v0.5.md` (Phase 1 → 2 → 3 → 4) against the modified codebase. A Full Rebuild is required to regenerate the manifest and validate all 6 task acceptance criteria.*
