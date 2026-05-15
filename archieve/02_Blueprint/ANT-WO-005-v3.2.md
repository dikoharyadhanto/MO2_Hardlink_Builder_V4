# ANT-WO-005-v3.2 — Work Order: Generated File Harvest

> [!IMPORTANT]
> **Addendum to:** `ANT-WO-005-v3.1.md` (main build WO — remains active)
> **Logic Source:** Director session 2026-04-27

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Work Order (WO) |
| **Version** | v3.2 |
| **Issued By** | ANT — Technical Foreman |
| **Issued To** | CDC — Lead Developer (Claude Code, VS Code Extension) |
| **Status** | Active |
| **Date** | 2026-04-27 |

---

## 2. Context & Mandate

### Problem

The current `total_cleanup()` (called before every rebuild) uses `shutil.rmtree()` — it blindly wipes everything in the standalone folder. Files generated at runtime by the game or mods (shader caches, INI modifications, plugin outputs) are silently destroyed alongside the hardlinks on every rebuild.

### Solution

Before clean, the tool must:
1. Identify which files in standalone are **confirmed hardlinks** (manifest + inode match) vs **generated** (everything else)
2. Copy all generated files into a dedicated mod folder in MO2 (`standalone_generated_files`)
3. Notify the user of the count
4. Then proceed with `total_cleanup()` as normal

Hardlinks are safe to remove — `os.unlink()` only removes the directory entry; the source data in MO2 mods is untouched. What remains after hardlinks are identified is definitively generated content.

### Non-Negotiable Rules

- Tool must **never decide** which generated files are important — all non-excluded files go to the mod folder
- Tool must **never create** the `standalone_generated_files` mod folder if there is nothing to harvest
- All tool-generated artifacts (files written by this tool, not the game) must be **excluded** from harvest

---

## 3. Implementation Task

### Single Task: FEAT-16 — Generated File Harvest

**File:** `model/engines/cleaner_engine.py`
**Method:** New `harvest_generated_files(manifest_path)` on `CleanerEngine`
**Integration:** `BuildWorker` calls `harvest_generated_files()` **before** `total_cleanup()` on every clean/rebuild

---

### 3.1 Detection Logic

```
1. Load manifest from manifest_path
   → Build: set of relative_path_lower strings (all tool-deployed files — hardlink OR copy)
   → No inode lookup. Deployment method is irrelevant.
   → If manifest absent: treat all non-excluded files as generated.

2. Walk entire standalone folder (os.walk)
   For each file:
     a. Check against TOOL_EXCLUSIONS → if matched: skip (do not harvest)
     b. Check relative_path against manifest path set
        → IN manifest: deployed by tool (hardlink or copy) → skip
        → NOT in manifest: not deployed by tool → GENERATED → add to harvest list

3. If harvest list is empty → return immediately, do NOT create mod folder

4. For each file in harvest list:
   → Determine destination path (see §3.2)
   → Copy to destination (overwrite silently if exists)
   → Count harvested files

5. Return {"harvested": int}
```

> **Why path-presence, not inode:** Copy-mode deployed files (cross-drive, pseudo-hardlink fallback)
> have different inodes from their MO2 source. Inode comparison incorrectly flags all copy-mode
> files as generated — false positive on potentially thousands of files. Path presence in the
> manifest is the correct gate: if the tool wrote it (hardlink or copy), skip it.

---

### 3.2 Destination Path Mapping

Mod folder root: `<mods_path>/standalone_generated_files/`

| File location in standalone | Destination in mod folder |
| :--- | :--- |
| `standalone/Data/<rel>` | `standalone_generated_files/<rel>` |
| `standalone/<rel>` (root or any non-Data subdir) | `standalone_generated_files/root/<rel>` |

**Examples:**

| Standalone path | Mod folder path |
| :--- | :--- |
| `standalone/Data/ShaderCache/foo.dds` | `standalone_generated_files/ShaderCache/foo.dds` |
| `standalone/Data/SKSE/Plugins/cc3.json` | `standalone_generated_files/SKSE/Plugins/cc3.json` |
| `standalone/SkyrimPrefs.ini` | `standalone_generated_files/root/SkyrimPrefs.ini` |
| `standalone/SKSE/Plugins/bar.log` | `standalone_generated_files/root/SKSE/Plugins/bar.log` |
| `standalone/enblocal.ini` | `standalone_generated_files/root/enblocal.ini` |

This matches MO2's own mod structure convention — files in `root/` are deployed to the game root; files in the mod root are deployed to `Data/`.

---

### 3.3 Tool Exclusion List

These files and folders are written by this tool — not the game. They must **never** be harvested.

**Exact name matches (case-insensitive, apply to files and top-level folders):**

```python
HARVEST_EXCLUSIONS_EXACT = {
    "standalone_metadata",
    "_wrapper_state.json",
    "how to launch.txt",
    "steam_appid.txt",
    ".deployment_state",
    "wrapper_log.txt",
    "standalone_bridge",
    "standalone_generated_files",
}
```

**Glob pattern matches (case-insensitive, match against filename only):**

```python
HARVEST_EXCLUSIONS_PATTERNS = [
    "crash_log_*.txt",
    "_*_original.exe",
    "*.bat",
    "*_source.cs",
    "*.pdb",
]
```

CDC has freedom to implement the pattern matching using `fnmatch` or equivalent. Implementation detail is CDC's choice — the exclusion coverage is the constraint.

---

### 3.4 Overwrite Behavior

If a file already exists in `standalone_generated_files` at the destination path: **overwrite silently**. Latest runtime version always wins. No quarantine, no timestamp subfolder.

---

### 3.5 Integration in BuildWorker

Call order in `BuildWorker.run()` before the clean stage:

```
1. harvest_generated_files(manifest_path)        ← NEW
2. total_cleanup()                                ← existing
```

Progress signal after harvest:
- If harvested > 0: `"[*] Generated files harvested: {n} file(s) → standalone_generated_files"`
- If harvested == 0: `"[*] No generated files detected."`

No detailed log file. Notification count only.

---

### 3.6 Edge Cases CDC Must Handle

| Case | Required Behavior |
| :--- | :--- |
| `mods_path` is None or does not exist | Log `WARNING` and skip harvest — do not abort build |
| Manifest file does not exist | Skip inode check entirely — treat all non-excluded files as generated |
| File copy fails (locked, permission) | Log `WARNING` per file — continue harvest, do not abort |
| `standalone_generated_files` folder already exists | Merge into it — do not wipe it first |
| Harvest list is empty | Return without creating `standalone_generated_files` folder |
| File in standalone root that is a directory (not file) | Skip directories — only harvest files |

---

## 4. Success Indicators

| # | Indicator | Test |
| :--- | :--- | :--- |
| SI-01 | Generated files appear in correct subfolder of `standalone_generated_files` | STR-HARVEST-01, 02, 03 |
| SI-02 | All tool artifact files are excluded from harvest | STR-HARVEST-04 |
| SI-03 | Confirmed hardlinked files are excluded from harvest | STR-HARVEST-05 |
| SI-04 | Existing `standalone_generated_files` files are overwritten, not duplicated | STR-HARVEST-06 |
| SI-05 | No mod folder created when nothing to harvest | STR-HARVEST-07 |
| SI-06 | Harvest always runs before `total_cleanup()` | STR-HARVEST-08 |
| SI-07 | `mods_path` absent → warning logged, build continues normally | STR-HARVEST-09 |

---

## 5. Test Scenarios (STR-HARVEST)

### STR-HARVEST-01: Data subfolder file → mod root

| Step | Procedure |
| :--- | :--- |
| 1 | Place a file at `standalone/Data/ShaderCache/compiled.dds` that is NOT in the manifest |
| 2 | Trigger build/clean |
| 3 | Confirm file appears at `mods/standalone_generated_files/ShaderCache/compiled.dds` |

**Pass:** File at correct destination path. Not under `root/`.

---

### STR-HARVEST-02: Standalone root file → `root/` subfolder

| Step | Procedure |
| :--- | :--- |
| 1 | Place `SkyrimPrefs.ini` at standalone root — not in manifest |
| 2 | Trigger build/clean |
| 3 | Confirm file at `mods/standalone_generated_files/root/SkyrimPrefs.ini` |

**Pass:** File under `root/`.

---

### STR-HARVEST-03: Non-Data subdirectory file → `root/<subdir>/`

| Step | Procedure |
| :--- | :--- |
| 1 | Place `standalone/SKSE/Plugins/bar.log` — not in manifest |
| 2 | Trigger build/clean |
| 3 | Confirm file at `mods/standalone_generated_files/root/SKSE/Plugins/bar.log` |

**Pass:** Relative path preserved under `root/`.

---

### STR-HARVEST-04: Tool artifacts excluded

| Step | Procedure |
| :--- | :--- |
| 1 | Confirm `HOW TO LAUNCH.txt`, `steam_appid.txt`, `crash_log_*.txt`, `_*_original.exe`, `*.bat`, `_wrapper_state.json` are present in standalone |
| 2 | Trigger build/clean |
| 3 | Confirm none of these appear in `standalone_generated_files` |

**Pass:** Zero tool artifacts harvested.

---

### STR-HARVEST-05: Confirmed hardlink excluded

| Step | Procedure |
| :--- | :--- |
| 1 | Verify a hardlinked file exists in standalone (inode matches source in MO2 mods) |
| 2 | Trigger build/clean |
| 3 | Confirm the hardlinked file does NOT appear in `standalone_generated_files` |

**Pass:** Hardlinked file not harvested.

---

### STR-HARVEST-06: Overwrite existing mod folder file

| Step | Procedure |
| :--- | :--- |
| 1 | Pre-populate `standalone_generated_files/root/SkyrimPrefs.ini` with old content |
| 2 | Place a newer `SkyrimPrefs.ini` in standalone root |
| 3 | Trigger build/clean |
| 4 | Confirm `standalone_generated_files/root/SkyrimPrefs.ini` contains new content |
| 5 | Confirm no duplicate files or timestamp subfolders created |

**Pass:** Silent overwrite. Single file, no duplicates.

---

### STR-HARVEST-07: Empty harvest — no mod folder created

| Step | Procedure |
| :--- | :--- |
| 1 | Ensure all files in standalone are confirmed hardlinks or tool exclusions |
| 2 | Delete `standalone_generated_files` mod folder if it exists |
| 3 | Trigger build/clean |
| 4 | Confirm `standalone_generated_files` folder was NOT created |

**Pass:** Folder absent when nothing to harvest.

---

### STR-HARVEST-08: Harvest runs before clean

| Step | Procedure |
| :--- | :--- |
| 1 | Place a generated file in standalone |
| 2 | Trigger build/clean. Inspect log |
| 3 | Confirm harvest log entry appears BEFORE any deletion log entry |

**Pass:** Harvest precedes `total_cleanup()` in log.

---

### STR-HARVEST-09: `mods_path` absent — build continues

| Step | Procedure |
| :--- | :--- |
| 1 | Set `mods_path` to None or a non-existent path |
| 2 | Trigger build/clean |
| 3 | Confirm WARNING is logged |
| 4 | Confirm build/clean proceeds normally without abort |

**Pass:** Warning logged, build not aborted.

---

## 6. Scope Boundary

| In scope | Out of scope |
| :--- | :--- |
| `CleanerEngine.harvest_generated_files()` | New UI elements |
| `BuildWorker` call order update | Filtering by file type or folder |
| `game_profiles.json` exclusion extension (if CDC deems needed) | User-configurable exclusion lists |
| Progress signal count emission | Detailed harvest log file |

---

*Paired Documents: `ANT-WO-005-v3.1.md`, `ANT-STR-005-v3.1.md`*
*Source: Director session 2026-04-27*
