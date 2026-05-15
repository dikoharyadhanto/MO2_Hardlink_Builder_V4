# CDC-WALK-002-v0.5 — Pre-Implementation Walkthrough: Post-v0.4 Director Feedback Refinements

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.5.md` + `ANT-STR-002-v0.5.md`
> **Status**: Pre-Implementation Walkthrough — PENDING ANT/Director approval before coding begins.

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Implementation Walkthrough (WALK) |
| **Version** | v0.5 |
| **Status** | **PENDING APPROVAL** |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-002-v0.5.md` |
| **Test Plan Ref** | `ANT-STR-002-v0.5.md` |

---

## 2. Task Interpretation

### What I understand must be implemented (6 tasks):

| Task | Title | Target Component |
| :--- | :--- | :--- |
| **TASK-A01** | Hardlink Exclusion Expansion | `ScannerEngine` / Exclusion Logic |
| **TASK-A02** | Incremental Build Optimization (Dual-Logic Verification) | `builder_core` / `linker_executor.py` / `manifest.json` |
| **TASK-A03** | Reporting Enhancements | `report_generator.py` |
| **TASK-A04** | UI & UX Improvements | GUI / Main Window |
| **TASK-A05** | C# Wrapper Logic Refinement | `feature_generator.py` (`_CS_TEMPLATE`) |
| **TASK-A06** | Forcing Standalone Generated Files | Deployment Engine |

This work order represents the broadest scope of any single v3.x cycle. Each task touches a different subsystem. Analysis below is per-task.

---

## 3. Proposed Approach (Per Task)

### 3.1 TASK-A01 — Hardlink Exclusion Expansion (`scanner_engine.py`)

**Current State**: `ScannerEngine` has no explicit exclusion for `.log` files or directories named `Logs` / `backup`. These pass through the scan and get hardlinked into the standalone build.

**Proposed Change**:

The exclusion logic must be applied at two points in `scanner_engine.py`:
1. **Directory-level**: During `os.walk()` / `rglob()` traversal, check each directory name against an exclusion set `{"logs", "backup"}` using a **case-insensitive exact name match** (compare `dir.name.lower()` against the set). Matching directories are pruned from the walk — they are not traversed at all.
2. **File-level**: After directory pruning, check each file's extension. If `file.suffix.lower() == ".log"`, skip the file.

**Critical Rule**: Exact name match only — `"backup_old"` does NOT match `"backup"`. The `lower()` comparison provides case-insensitivity.

**Affected function**: `build_mapping()` (mod scan) and `scan_base_game()` (base game scan) — both traversal paths must receive the same exclusion rules to prevent `.log` files sneaking in through the base game path.

---

### 3.2 TASK-A02 — Incremental Build Optimization (`linker_executor.py`, `deployment_controller.py`)

**Current State**: The v3.4 incremental build uses Inode Fast-Path (Tier 1: `st_ino` match → skip). However, the Work Order states that a "Full Verification" (hashing) is being triggered, making incremental builds as slow as fresh builds. This suggests the Inode Fast-Path is not being reached, or the manifest delta is always returning `full_rebuild_required = True`.

**Proposed Dual-Logic Extension**:

The v3.4 Inode Fast-Path is the correct foundation. The v3.6 extension adds two new tiers **as fallbacks** when Tier 1 fails (inode mismatch), plus atomic manifest write:

| Tier | Condition | Action |
| :--- | :--- | :--- |
| **Tier 1** (existing) | `target.st_ino == source.st_ino` | → `SKIPPED_UNCHANGED` (instant) |
| **Tier 2** (new) | Inode mismatch + Size AND mtime match | → `SKIPPED_UNCHANGED` (fast) — only when Paranoid Mode is OFF |
| **Tier 3** (new) | Size or mtime differ | → Escalate: `os.remove()` + `_hardlink_verified()` relink |
| **Paranoid Mode** | Config flag `paranoid_mode = True` | Disables Tier 2 — forces Hash check on any inode mismatch |

**Implementation location**: `linker_executor.py` — `execute_mapping()` method, after the existing Tier 1 guard.

**Atomic Manifest Write**:
- After a complete successful pass, write updated state to `manifest.json.tmp`
- Perform OS-level rename (`os.replace()` on Windows is atomic): `manifest.json.tmp` → `manifest.json`
- If the process crashes mid-pass, `manifest.json` retains its pre-build state (safe stale manifest, triggers full rebuild on next run)
- Applies to `deployment_controller.py` — wherever the manifest is written at end of build

**Config integration**: `paranoid_mode` flag to be added to `config.py` and surfaced in the GUI config panel.

---

### 3.3 TASK-A03 — Reporting Enhancements (`report_generator.py`)

**Current State**: The HTML report likely conflates "Excluded" and "Unchanged" files under a single category, and does not attach causality tags to entries.

**Proposed Change**:

Introduce three explicit result categories to replace any ambiguous grouping:

| Category | Description |
| :--- | :--- |
| `Unchanged` | File existed, Inode/Tier 2 match — skipped with no action |
| `Excluded` | File matched an exclusion rule — not deployed |
| `Failed` | Deployment attempted but encountered an error |

Each `Excluded` entry must carry a **causality tag**, e.g.:
- `Excluded (rule: .log extension)`
- `Excluded (rule: exact dir match — Logs)`
- `Excluded (rule: exact dir match — backup)`

Each `Failed` entry must carry a **stage tag**, e.g.:
- `Failed (stage: hardlink — permission denied)`
- `Failed (stage: verification — hash mismatch)`

**Implementation**: `report_generator.py` — extend the result object/dict to accept an optional `reason` string, and update the HTML template to render the causality tag inline with the file entry.

---

### 3.4 TASK-A04 — UI & UX Improvements (`deployment_controller.py` / `config_panel.py` / `view/`)

**Two sub-tasks**:

#### 3.4.1 "Show Report" Button
- **Location**: Standalone Manager Tab (in the GUI)
- **Behavior**: Opens `report.html` using `webbrowser.open()` or `os.startfile()`
- **File**: `view/config_panel.py` — add button widget connected to a slot that calls `os.startfile(report_path)`

#### 3.4.2 Post-Build Prompt
- **Trigger**: Immediately after `BuildWorker` emits a build-complete signal
- **Dialog**: Modal message box — "Build complete. Do you want to view the build report?" with Yes/No buttons
- **"Don't show again" toggle**: A `QCheckBox` in the dialog, or a persistent config key `show_report_prompt = True/False` in `config.py`
- **Suppression**: If `show_report_prompt = False`, skip the dialog entirely and proceed silently
- **File**: `view/config_panel.py` or wherever the build-complete signal is connected in the main window

---

### 3.5 TASK-A05 — C# Wrapper Logic Refinement (`feature_generator.py`)

**Two sub-tasks**:

#### 3.5.1 Pre-Launch Backup Clarification/Fix
**Current State**: The wrapper copies `plugins.txt`/`loadorder.txt` and save files to the game's `AppData`/`Documents` locations before launch. However, it is unclear whether it backs up the **existing global state** before overwriting. If not, the user's global `plugins.txt` is silently destroyed.

**Fix**: Before the copy loop, add an explicit backup step for **all target files**:
- For each `plugins.txt`, `loadorder.txt` → back up to `<file>.bak_standalone` in `%LOCALAPPDATA%\<AppDataName>\`
- For each save in `Documents\My Games\<Game>\Saves\` → back up to `<file>.bak_standalone` in the same folder

The backup check must happen **before** any write. If a `.bak_standalone` already exists (crash recovery scenario), restore it first, then re-backup the fresh current state.

#### 3.5.2 Post-Exit Save Cleanup — True Transactional Model
**Current State**: The wrapper syncs saves from `Documents` back to MO2. If this copy is interrupted (crash, kill), the source file in `Documents` may have been partially deleted, causing save corruption.

**Fix — True Transactional Sync**:
1. Copy `NEW_STANDALONE_SAVE.ess` from `Documents\...\Saves\` → staging temp folder inside MO2 (e.g., `<mo2_profile>\standalone_saves_staging\`)
2. Verify integrity: compute CRC32 or SHA256 of staged file vs source
3. If checksum matches: `MoveFileEx(staged_file, final_mo2_path, MOVEFILE_REPLACE_EXISTING)` — atomic swap
4. If checksum matches and atomic move succeeded: **only then** delete source from `Documents`
5. If any step fails: abort — leave source in `Documents` untouched (fail-safe)

**Implementation**: `feature_generator.py` — `_CS_TEMPLATE` C# source. Uses `File.Move()` (which maps to `MoveFileEx` on Windows NTFS for same-drive moves — atomic). CRC check via `FileStream` + `Crc32` or MD5.

---

### 3.6 TASK-A06 — Forcing Standalone Generated Files (`deployment_controller.py` / `linker_executor.py`)

**Current State**: Files in `standalone_generated_files` are only deployed if the mod is enabled in MO2. If the folder is disabled, its contents are skipped entirely.

**Proposed Change**:

After the main `execute_mapping()` pass completes, run a second dedicated pass for `standalone_generated_files`:

1. **Detect**: Locate the `standalone_generated_files` directory in the MO2 mods folder
2. **Allowlist filter**: Only process files with extensions in `{".dll", ".exe", ".ini", ".json", ".txt"}` — reject all others (e.g., `.log` is excluded by this allowlist AND by TASK-A01)
3. **Hardlink**: Force-link each allowed file into the standalone build output — regardless of MO2 checkbox state
4. **Report flag**: Count these files separately and add a summary line to the HTML report: `"X files included via standalone_generated_files override"`
5. **Per-file report tag**: Each such file appears in the report with tag `Included via override`

**Precedence rule**: Override files win over general exclusion rules (e.g., an `.ini` in `standalone_generated_files` is deployed even if an `ini` rule would otherwise exclude it — but `.log` still cannot appear because it is not in the allowlist).

**Implementation**:
- New method in `linker_executor.py`: `deploy_generated_overrides(generated_files_path, allowlist_extensions, output_root)`
- Called from `deployment_controller.py` **after** `execute_mapping()` completes
- Results fed back into the report data structure with `reason = "Included via override"`

---

## 4. Files to Create/Modify

| File | Action | Task | Purpose |
| :--- | :--- | :--- | :--- |
| `model/engines/scanner_engine.py` | MODIFY | A01 | Add `{"logs", "backup"}` dir exclusion + `.log` extension exclusion to all traversal paths |
| `model/engines/linker_executor.py` | MODIFY | A02, A06 | Add Tier 2 (Size+mtime) and Tier 3 escalation to `execute_mapping()`; add `deploy_generated_overrides()` method |
| `controller/deployment_controller.py` | MODIFY | A02, A04, A06 | Atomic manifest write (`manifest.json.tmp` → rename); wire post-build prompt; call `deploy_generated_overrides()` after main pass |
| `model/config.py` | MODIFY | A02, A04 | Add `paranoid_mode: bool` and `show_report_prompt: bool` config fields |
| `model/engines/report_generator.py` | MODIFY | A03 | Add `Unchanged` / `Excluded` / `Failed` category split; add `reason` causality tag to all entries |
| `view/config_panel.py` | MODIFY | A04 | Add "Show Report" button; add post-build prompt dialog with "Don't show again" toggle |
| `model/engines/feature_generator.py` | MODIFY | A05 | Update `_CS_TEMPLATE`: pre-launch global backup (saves + AppData); transactional post-exit save sync (stage → verify → atomic move → delete source) |

**Total files to modify: 7** — no new files required.

---

## 5. Dependencies

| Dependency | Required By | Status |
| :--- | :--- | :--- |
| `os.replace()` (Python stdlib) | TASK-A02 atomic manifest | ✅ Standard — no new package |
| `webbrowser` or `os.startfile()` (Python stdlib) | TASK-A04 Show Report | ✅ Standard — no new package |
| `PyQt5.QtWidgets.QMessageBox`, `QCheckBox` | TASK-A04 post-build dialog | ✅ Already a project dependency |
| `System.IO.File.Move()` (C# BCL) | TASK-A05 transactional save | ✅ Already in `_CS_TEMPLATE` dependencies |
| CRC/MD5 check in C# | TASK-A05 checksum verify | ✅ `System.Security.Cryptography.MD5` — BCL, no external NuGet |

**No new external packages or NuGet dependencies required.**

---

## 6. Flags / Risks

| # | Risk | Severity | Mitigation |
| :--- | :--- | :--- | :--- |
| F-01 | **TASK-A02: Tier 2 false-positive** — spoofed `mtime` (e.g., zip extractor sets mtime to original timestamp) causes stale file to be treated as unchanged. | Medium | This is the exact case Paranoid Mode addresses. Default config: `paranoid_mode = False`. Users with automated pipelines can enable it. ANT-STR Phase 2 Sub-Test B explicitly tests this scenario. |
| F-02 | **TASK-A02: Atomic manifest on crash mid-write** — `manifest.json.tmp` is left orphaned. | Low | On next run, `manifest.json.tmp` is stale metadata and is silently ignored. The real `manifest.json` was never swapped, so the builder falls back to the previous valid manifest. |
| F-03 | **TASK-A05: CRC mismatch during transactional save** — network drive or antivirus interference causes byte-level corruption of the staged file. | Low | Checksum failure → abort → leave source in `Documents` untouched. User's save is never lost. Logged explicitly. |
| F-04 | **TASK-A06: `standalone_generated_files` dir not found** — mod doesn't exist or path misconfigured. | None | Method returns early with zero overrides and logs a warning. Build succeeds without override pass. |
| F-05 | **TASK-A01: Exclusion regression** — `backup_old` must NOT be excluded (exact-match only). | Low | `dir.name.lower() in {"logs", "backup"}` — string equality, not `startswith` or `in`. ANT-STR Phase 1 step 4 explicitly verifies `backup_old` was deployed. |
| F-06 | **TASK-A04: "Don't show again" persisted across sessions** — config must be written to disk, not just in-memory. | Low | `paranoid_mode` and `show_report_prompt` are added to `config.py` with `save()` — same pattern as all existing config flags. |

---

## 7. Success Indicator Mapping

| WO Acceptance Criterion | Implementation Point |
| :--- | :--- |
| **AC-1**: No `.log` files, `Logs/`, or `backup/` in final standalone | TASK-A01: `scanner_engine.py` dir + extension exclusion |
| **AC-2**: Incremental builds of unchanged 1,000-file dataset ≤10% fresh build time | TASK-A02: Tier 1 (existing) + Tier 2 (size+mtime) fast paths in `execute_mapping()` |
| **AC-3**: HTML report cleanly separates Unchanged / Excluded / Failed with causality tags | TASK-A03: `report_generator.py` category + reason fields |
| **AC-4**: GUI has working "Show Report" button + post-build prompt with "Don't show again" | TASK-A04: `config_panel.py` button + dialog |
| **AC-5**: Wrapper backs up global files before deploy, transactional save sync after exit | TASK-A05: `_CS_TEMPLATE` — pre-launch backup + stage→verify→atomic move pipeline |
| **AC-6**: `standalone_generated_files` hardlinked regardless of MO2 checkbox, flagged in report | TASK-A06: `deploy_generated_overrides()` in `linker_executor.py` |

---

*Awaiting ANT/Director approval to proceed to implementation.*
