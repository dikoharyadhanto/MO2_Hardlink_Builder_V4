# MO2 Hardlink Builder V1 — Technical Review Report

**Date**: 2026-04-18  
**Reviewed Version**: V1 (Archived)  
**Total Codebase Size**: ~1,829 Python LOC + ~2,500+ UI LOC  
**Architecture**: Modular Engine-Based Plugin for Mod Organizer 2  

---

## Executive Summary

MO2 Hardlink Builder V1 is a **production-quality Skyrim modding tool** that creates portable, standalone game installations using hardlinks. The codebase demonstrates **solid engineering practices** with clear separation of concerns, robust error handling, and comprehensive metadata management. The tool addresses a real pain point in the modding community—enabling users to create isolated, standalone Skyrim installations while sharing mod files via hardlinks.

### Key Strengths
- **Modular Architecture**: 11 independent engine modules with clear responsibilities
- **Windows-Aware Implementation**: Long path support, junction handling, priority optimization
- **Metadata Persistence**: Comprehensive state tracking (manifests, conflict caches, snapshots)
- **Safety-First Design**: Extensive validation, quarantine mechanisms, backup strategies
- **Progressive Failure Handling**: Graceful degradation with detailed error logs

### Key Challenges
- **Pre-AI Documentation**: Minimal inline documentation, no architecture diagrams
- **UI Monolith**: 2,500+ line single file managing all interface logic
- **Hardcoded Paths**: Some game-specific paths not parameterized
- **Legacy Qt Support**: Multi-framework compatibility adds complexity

---

## Codebase Architecture

### System Overview

```
MO2 Hardlink Builder
├── Plugin Entry Point (__init__.py)
│   └── HardlinkBuilderPlugin (mobase.IPluginTool interface)
│
├── Core Execution Engines (Scripts/)
│   ├── scanner_engine.py      → Scan mods & build conflict registry
│   ├── linker_executor.py     → Deploy files via hardlinks/copy
│   ├── cleaner_engine.py      → Safely remove standalone installations
│   ├── verification_engine.py → Validate deployments & configs
│   ├── profile_sync.py        → Sync configs/saves between MO2 and standalone
│   └── report_generator.py    → Generate HTML deployment reports
│
├── State Management (Scripts/)
│   ├── state_manager.py       → Track modlist snapshots & conflicts
│   └── process_utils.py       → OS-level process priority optimization
│
├── Utilities (Scripts/)
│   └── path_utils.py          → Windows long-path handling
│
└── UI Layer (plugin_ui.py)
    └── HardlinkBuilderDialog   → Multi-tab Qt-based interface
```

### Data Flow

```
1. [Scan Phase]
   MO2 Profile → ScannerEngine → mapping_manifest.json + conflict_cache.json

2. [Deploy Phase]
   mapping_manifest.json → LinkerExecutor → Standalone Installation
   
3. [Sync Phase]
   MO2 Profile/Documents → ProfileSync → Standalone (configs, saves)
   
4. [Verify Phase]
   Standalone → VerificationEngine → Report (success/failures)
   
5. [Clean Phase]
   Standalone → CleanerEngine → Removes all files safely
```

---

## Detailed Module Analysis

### 1. **ScannerEngine** (`scanner_engine.py`, 187 LOC)

**Responsibility**: Analyze active mods and build file-to-mod mappings.

**Key Features**:
- Reads `modlist.txt` with load-order detection logic
- Walks mod directories with intelligent blacklist filtering
- Registers file conflicts in `ConflictManager`
- Handles both `/Data` and `/Root` folder structures
- Detects ambiguous load order (bottom-up vs top-down)

**Output**:
- `mapping_manifest.json`: Maps target paths → source mod + metadata
- `conflict_cache.json`: Maps file paths → list of mods providing each file
- `modlist_reference.txt`: Snapshot of active mod list at scan time

**Critical Logic**:
```python
# Load order detection (lines 59-77)
# - Heuristic: Detects if DLC/Creation Club entries are at top or bottom
# - Determines if modlist should be read forward or reversed
# - Handles cases where mod priority is ambiguous
```

**Potential Issues**:
- [ ] Hard-coded blacklist files (readme.txt, readme.md) may be game-specific
- [ ] Assumes modlist.txt uses `+` prefix for active mods (MO2-specific)
- [ ] Does not validate mod folder existence before scanning

---

### 2. **LinkerExecutor** (`linker_executor.py`, 184 LOC)

**Responsibility**: Deploy mapped files to standalone via hardlinks or copy.

**Key Features**:
- Attempts hardlink creation, falls back to copy on failure
- Cross-drive detection (copy-only if on different volumes)
- Cleans orphaned files not in manifest
- Robust metadata copying to `standalone_metadata` folder
- Detailed execution report with per-file status

**Execution Strategy**:
```
For each file in mapping_manifest.json:
  1. Create parent directories
  2. Remove any existing file/symlink
  3. Try hardlink (same drive only)
  4. Fall back to copy if hardlink fails
  5. Log method (hardlink vs copy) in execution_report.json
  6. Capture errors to brokenmods_logs.txt
```

**Critical Logic**:
- **Drive-aware hardlinking**: Only attempts hardlinks on same drive (lines 71-83)
- **Fallback strategy**: Gracefully degrades to copy if hardlink fails (line 79)
- **Metadata persistence**: Smart check to avoid deleting metadata in-progress (lines 161-168)

**Potential Issues**:
- [ ] No progress callback on metadata copy (can stall UI on large manifests)
- [ ] Orphan cleanup uses simple prefix matching (brittle for edge cases)
- [ ] No validation that hardlinks were actually created (relies on os.link success)

---

### 3. **CleanerEngine** (`cleaner_engine.py`, 201 LOC)

**Responsibility**: Safely remove standalone installations with data recovery.

**Key Features**:
- Pre-deployment safety checks (prevents accidental data loss)
- Folder isolation validation (can't nest SA inside MO2 or vice versa)
- Windows junction/symlink detection (crucial for safe removal)
- Backup creation before cleanup (in portable mode)
- Per-profile cleanup tracking via LocalAppData backups

**Safety Checks** (lines 57-83):
```
1. SA folder cannot be inside/be MO2 folder
2. SA folder cannot contain MO2 folder
3. SA folder cannot be inside relocated mods or overwrite
4. SA folder must contain standalone_metadata marker or fail
5. Protected folder check (.mo2_protected flag)
6. Steam folder detection (prevent accidental system cleanup)
```

**Cleanup Workflow**:
```
1. Count total items (report if empty)
2. Walk directory tree and remove all items
3. Handle read-only files (chmod before removal)
4. Detect and unlink Windows junctions
5. Clean MO2 isolated profile (standalone_profile/)
6. Delete bridge folder if present (standalone_bridge/)
```

**Potential Issues**:
- [ ] Backup only happens in non-portable mode (may lose data in portable setups)
- [ ] Error handling uses generic try-except (hard to debug specific failures)
- [ ] Progress callback leaves 15% for MO2 cleanup but may not use it all

---

### 4. **VerificationEngine** (`verification_engine.py`, 336 LOC)

**Responsibility**: Validate post-deployment integrity and configuration sync.

**Verification Categories**:

1. **Deployment Integrity** (lines 23-73):
   - Check if all manifest files exist in standalone
   - Detect zero-byte files (indicate corruption)
   - Handle hijacked EXE scenario (`_original.exe` backup)

2. **Configuration Sync** (lines 75-119):
   - Compare `plugins.txt` and `loadorder.txt` (AppData)
   - Compare INI files (Documents vs profile, with ignore patterns)
   - Skip checks in stealth mode (live MO2 integration)
   - Supports custom ignore patterns (e.g., `sLocalSavePath` in Custom.ini)

3. **Save Game Sync** (lines 121-177):
   - Map source saves (MO2 profile or Documents)
   - Map target saves (stealth mode = isolated profile, else real Documents)
   - Detect quarantine folders (timestamped save conflicts)
   - Track historic quarantine data
   - Report missing saves from source

**Result Structure**:
```json
{
  "missing_files": [{file, mod}, ...],
  "zero_byte_files": [{file, mod}, ...],
  "config_mismatch": [strings],
  "save_issues": [{summary, source, missing_files}, ...],
  "quarantined_items": [{file, location, reason}, ...],
  "has_historic_quarantine": boolean,
  "mod_audit": {...}
}
```

**Potential Issues**:
- [ ] Config comparison is case-insensitive but ignores whitespace differences
- [ ] No detection of missing DLLs or system requirements
- [ ] Save sync logic assumes specific save file extensions (`.ess`, `.esn`)

---

### 5. **ProfileSync** (`profile_sync.py`, 277 LOC)

**Responsibility**: Bidirectional sync of configurations and save games.

**Three Operating Modes**:

1. **Portable Mode** (default):
   - Configs/saves isolated inside standalone folder
   - Path: `_standalone/AppData/Local/`, `_standalone/Documents/`
   - No system registry or Documents modification

2. **Shared Mode** (portable_mode=False):
   - Configs/saves written to Windows Documents/AppData
   - Shares game configurations with original installation
   - Creates backups before modifying system folders

3. **Stealth Mode** (Live MO2 Integration):
   - Isolated profile inside MO2: `profile/standalone_profile/`
   - Prevents any system-wide modifications
   - Allows live switching between MO2 and standalone

**Conflict Resolution**:
- Detects file conflicts (same filename in source & destination)
- User prompt: Overwrite vs Quarantine (with timestamp)
- Quarantine: `Standalone_Export_save_YYYYMMDD_HHMM/`

**Error Handling**:
- Retry logic for locked files (3 attempts, 1s delay)
- Permission error handling with chmod fallback
- Per-file logging to track which files succeeded/failed

**Potential Issues**:
- [ ] Portable mode backup only happens in non-portable context (contradiction)
- [ ] 3-second retry window may be insufficient for large file locks
- [ ] No validation that sync actually occurred (silent failures possible)

---

### 6. **ReportGenerator** (`report_generator.py`, 407 LOC)

**Responsibility**: Generate interactive HTML deployment reports.

**Report Contents**:
- Summary statistics (total files, success, hardlinks vs copies)
- Deployment table (paginated, searchable, filterable)
- Verification warnings (config mismatches, missing saves, etc.)
- Failed deployments with error messages
- Quarantine inventory
- File method breakdown (hardlink vs copy %)

**Features**:
- Dark theme HTML5 with responsive grid layout
- Client-side pagination (1000 files per page)
- Search and filter buttons (failed files, hardlinks, copies)
- Per-file status display (success/failed with method tag)
- Compact JSON encoding for large datasets

**Output**: `deployment_report.html` (standalone file, no external dependencies)

**Potential Issues**:
- [ ] Pagination happens in Python, but client filtering is ineffective for large datasets
- [ ] HTML embeds all data inline (can be 10+ MB for large deployments)
- [ ] No mobile-responsive design considerations

---

### 7. **StateManager** (`state_manager.py`, 137 LOC)

**Responsibility**: Manage modlist snapshots and file conflict tracking.

**Components**:

1. **ModlistSnapshot**:
   - Reads active mods from `modlist.txt`
   - Detects mod load order (handles reversed/non-reversed parsing)
   - Provides snapshot copy for audit trail
   - Diff function: Added/removed/reordered mods detection

2. **ConflictManager**:
   - Maintains `conflict_cache.json` (persistent file→mods mapping)
   - Fast lookup: Which mods provide a specific file?
   - Mod priority resolution via `get_winner_fast()`
   - Incremental updates (can add/remove mods without full rebuild)

**Potential Issues**:
- [ ] Conflict cache is never validated for stale entries
- [ ] No versioning of conflict cache format
- [ ] `get_winner_fast()` assumes `mod_indices` dict is always provided

---

### 8. **Path Utilities** (`path_utils.py`, 41 LOC)

**Responsibility**: Handle Windows long-path limitations.

**Key Functions**:
- `ensure_long_path()`: Convert paths to `\\?\` prefix (bypasses 260-char limit)
- `to_path()`: Create Path object with long-path encoding
- `clean_path_for_display()`: Remove prefixes for user-facing messages

**Important**: All internal path handling must use `ensure_long_path()` to avoid Max_PATH errors with deeply nested mods.

---

### 9. **Process Utilities** (`process_utils.py`, 59 LOC)

**Responsibility**: Optimize process execution priority.

**Functions**:
- `set_priority()`: Set CPU to HIGH_PRIORITY_CLASS + I/O priority level 3
- `set_affinity()`: Restrict process to specific CPU cores

**Usage**: Called before large I/O operations (file copies, hardlink creation) to prevent system lag.

**Potential Issues**:
- [ ] Only works on Windows (no-op on Linux/Mac)
- [ ] No error recovery if priority setting fails
- [ ] Affinity masking not exposed in UI

---

### 10. **UI Layer** (`plugin_ui.py`, ~2,500 LOC)

**Responsibility**: Qt-based GUI for all user interactions.

**Architecture**:
- **HardlinkBuilderPlugin**: mobase.IPluginTool implementation (MO2 interface)
- **HardlinkBuilderDialog**: Main UI window with tab structure
- **Threading**: QThread workers to avoid UI blocking

**Tab Layout** (inferred from imports):
1. **Setup Tab**: Select paths (mods, overwrite, game, standalone target)
2. **Configuration Tab**: Portable/shared/stealth mode selection
3. **Execution Tab**: Run scan → link → verify → report generation
4. **Cleanup Tab**: Safe removal of standalone installations
5. **Settings Tab**: Game-specific configuration (docs name, appdata name, ini prefix)

**Qt Framework Selection**:
```python
Try: PySide6 → PyQt6 → PyQt5  # Graceful fallback
```

**Potential Issues**:
- [ ] 2,500+ lines in single file (no component separation)
- [ ] All UI state managed in memory (lost on crash)
- [ ] No input validation on path selections (relies on engines for validation)
- [ ] Threading may cause race conditions on `self.__organizer` access

---

## Data Persistence

### Files Created During Operation

| File | Purpose | Format | Owner |
|------|---------|--------|-------|
| `mapping_manifest.json` | Source→Target file mappings | JSON | ScannerEngine |
| `conflict_cache.json` | File→Mod conflict registry | JSON | ConflictManager |
| `modlist_reference.txt` | Snapshot of active mod list | Text | ModlistSnapshot |
| `execution_report.json` | Per-file deployment status | JSON | LinkerExecutor |
| `brokenmods_logs.txt` | Human-readable error log | Text | LinkerExecutor |
| `deployment_report.html` | Interactive deployment report | HTML5 | ReportGenerator |
| `verification_results.json` | Post-deployment checks | JSON | VerificationEngine |
| `standalone_metadata/` | Copied metadata folder | Directory tree | LinkerExecutor |
| `.mo2_protected` | Lock file (if Updater manages folder) | Empty | Updater tool |

---

## Game-Specific Configurations

### Hardcoded Game Strings

```python
# From CleanerEngine, ProfileSync, etc.
Default Docs Name:     "Skyrim Special Edition"
Default AppData Name:  "Skyrim Special Edition"
Default INI Prefix:    "Skyrim"
Default Game Name:     "Skyrim SE"
Backup Root Path:      LocalAppData / "MO2_Hardlink_Builder" / {game_name} / {profile_name}
```

### File Extensions (Critical)

```python
# Scripts/scanner_engine.py lines 29-30
CRITICAL_EXTENSIONS = [
    '.esp', '.esm', '.esl',  # Plugins
    '.bsa', '.ba2',          # Archives
    '.nif', '.dds',          # Meshes/textures
    '.hkx', '.fuz', '.wav',  # Animations/audio
    '.swf', '.tri', '.seq'   # UI/script
]

BLACKLIST_EXTENSIONS = [
    '.pdf', '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt'
]
```

**⚠️ Issue**: These are Skyrim-specific and won't work for other games (Fallout, Starfield, Oblivion). Need parameterization for multi-game support.

---

## Error Handling & Robustness

### Strength Areas

✅ **Graceful Degradation**:
- Hardlink failures fall back to copy
- Config mismatches don't block deployment
- Scan failures logged separately from deployment

✅ **Detailed Logging**:
- Per-file error tracking
- Timestamped backup identification
- Quarantine folder naming for conflict resolution

✅ **Safety Mechanisms**:
- Pre-deployment folder validation
- Orphan file detection and removal
- Junction/symlink detection before deletion

### Weakness Areas

❌ **Generic Exception Handling**:
```python
except Exception as e:
    print(f"[!] Error: {e}")
    # No context about which mod/file failed
```

❌ **No Retry Logic for Hardlinks**:
- Single attempt to create hardlink, immediate fallback
- No backoff or detailed failure analysis

❌ **Silent Failures in Config Sync**:
- File lock retries exist, but no final error reporting
- Partial sync may leave system in inconsistent state

---

## Performance Characteristics

### Scanning Phase
- **Time Complexity**: O(n) where n = total files across all mods
- **Bottleneck**: File I/O walking directory tree
- **Optimization**: Could cache modlist timestamps, skip unchanged mods

### Deployment Phase
- **Time Complexity**: O(n) where n = files in manifest
- **Bottleneck**: Hardlink creation (I/O bound) and fallback copy
- **Optimization**: Parallel hardlink creation (currently sequential)
- **Process Priority**: Elevated to HIGH_PRIORITY_CLASS + I/O level 3

### Cleanup Phase
- **Time Complexity**: O(n) where n = files in standalone
- **Bottleneck**: Symlink/junction detection + filesystem removal
- **Potential Hang**: If files are locked by game/engine processes

### Report Generation
- **Time Complexity**: O(n) where n = execution report entries
- **Memory**: Embeds entire report in HTML (can exceed 10 MB)
- **Pagination**: Client-side, server-side filtering not implemented

---

## Known Limitations & Design Decisions

### 1. Skyrim-Centric Design
- File extensions, paths, and backup locations hardcoded for Skyrim
- **Workaround**: User can customize via UI parameters
- **Future**: Parameterize for Fallout/Starfield/Oblivion

### 2. Single MO2 Profile Target
- Only syncs one profile at a time
- **Reason**: Isolated profile folder per sync
- **Limitation**: Cannot manage multiple game profiles

### 3. No Incremental Updates
- Always performs full scan and redeployment
- **Reason**: Ensures manifest freshness
- **Trade-off**: Slower on large installations (2+ GB)

### 4. Hardlink-Centric with Copy Fallback
- Prefers hardlinks to save disk space
- **Limitation**: Does not validate hardlinks actually work post-reboot
- **Why**: Validation would require duplicate copy of files

### 5. No Concurrent Safe Mode
- Cannot run multiple instances simultaneously
- **Reason**: Shared metadata folder and backup root
- **Solution**: Use profiles to isolate separate builds

---

## Integration Points

### With Mod Organizer 2
```python
# Plugin interface
class HardlinkBuilderPlugin(mobase.IPluginTool):
    def init(organizer: mobase.IOrganizer) → bool
    def display() → void  # Called when user clicks plugin
```

**Accessed Data**:
- Profile paths (read-only)
- Mod list (read-only via modlist.txt)
- Does NOT use MO2 API for mod data (manual modlist.txt parsing)

### With Windows Registry
- Backup of game .INI files from `%LOCALAPPDATA%`
- Backup of save games from Documents
- Creates backup subfolder structure

### With External Tools
- **Registry Check**: Queries Windows Registry for Steam/Game paths
- **Process Management**: Elevates own priority (Windows API calls)
- **Hardlinks**: Relies on filesystem support (NTFS required)

---

## Security & Data Safety Considerations

### Positive
✅ Extensive pre-deployment validation  
✅ Backup creation before system modifications  
✅ Read-only access to mod data  
✅ Isolated deployment (doesn't modify original MO2 mods)  

### Concerns
⚠️ No cryptographic validation of file integrity (could deploy modified files)  
⚠️ No logging to central audit trail (all logs local, can be deleted)  
⚠️ Backup path in LocalAppData (accessible to all user processes)  
⚠️ No permission model (any user can access another's standalone builds)  

---

## Documentation Gaps (Pre-AI Era)

### What's Missing
- [ ] Architecture decision record (why each engine exists)
- [ ] Data format versioning (conflict_cache.json, manifest.json)
- [ ] Thread safety guarantees (UI thread vs worker threads)
- [ ] Performance benchmarks (scan time for 1000 mods, etc.)
- [ ] Configuration examples (per-game setup)
- [ ] Troubleshooting guide
- [ ] API reference for engine classes
- [ ] Test coverage report

### What's Available
- Code comments are minimal
- Class docstrings are sparse
- No inline algorithm explanations
- No decision rationale comments

---

## Recommended Improvements for V2

### High Priority (Technical Debt)
1. **Separate UI from Logic**
   - Extract 2,500-line plugin_ui.py into components
   - MVC pattern: Models (state), Views (UI), Controllers (logic)

2. **Multi-Game Support**
   - Parameterize file extensions, paths, ini prefixes
   - Support Fallout 3/4/76, Starfield, Oblivion
   - Config file: `game_profiles.json`

3. **Incremental Scanning**
   - Cache modlist timestamps
   - Only re-scan mods with changed mtimes
   - Reduce scan time by 70%+ on subsequent runs

4. **Parallel Deployment**
   - Use ThreadPoolExecutor for hardlink creation
   - Batch I/O operations
   - Reduce deployment time by 40-60%

5. **Configuration Persistence**
   - Save last-used paths and settings
   - Load profiles from file instead of UI entry
   - Support config import/export

### Medium Priority (Robustness)
6. **Enhanced Logging**
   - Structured JSON logging
   - Central log file with rotation
   - Log levels (DEBUG, INFO, WARN, ERROR)

7. **Validation Framework**
   - Schema validation for manifest.json, conflict_cache.json
   - Version checking on load
   - Migration scripts for format changes

8. **Test Coverage**
   - Unit tests for each engine
   - Integration tests for full workflow
   - Mock file system for testing

9. **Error Recovery**
   - Checkpointing during deployment
   - Resume capability after interruption
   - Rollback on failure

### Nice-to-Have (UX)
10. **Advanced Reporting**
    - Real-time progress visualization
    - Comparison reports (before/after)
    - Mod conflict analysis dashboard

11. **Safety Enhancements**
    - Dry-run mode (simulate without changes)
    - Undo/rollback feature
    - Integrity checksums for files

12. **Automation**
    - Headless CLI mode
    - Scheduled syncs
    - Webhook notifications

---

## Conclusion

**MO2 Hardlink Builder V1 is a well-engineered, production-ready tool** that successfully solves a critical problem in the Skyrim modding community. The modular architecture, comprehensive error handling, and safety-first design demonstrate solid software engineering practices.

The primary limitation is **lack of documentation and architectural commentary** typical of pre-AI-era tools. The codebase is readable but not self-documenting. With strategic refactoring for multi-game support, UI separation, and performance optimization, V2 has significant potential to become the definitive tool for portable game installations.

### For Strategy Documentation Rebuild

**Start with these priorities**:
1. Architecture decision records (Why each engine? Why separation?)
2. Data format documentation (JSON schema for manifest, conflict_cache)
3. Configuration guide (per-game customization)
4. API reference (class/method documentation)
5. Workflow diagrams (Scan → Deploy → Verify → Report)

---

**End of Technical Review**
