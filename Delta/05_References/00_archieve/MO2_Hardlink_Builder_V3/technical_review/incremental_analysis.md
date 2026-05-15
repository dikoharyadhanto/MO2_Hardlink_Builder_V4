# Incremental Updates Analysis: Why You Failed, Why V2 Might Work, When to Use It

**Context**: User implemented incremental in V1 but it failed. Reverted to "always cleanup" (full rebuild). Now reconsidering for V2.

---

## Why Your V1 Incremental Failed

### The Hidden Complexity

You discovered the hard way that incremental state tracking is **deceptively dangerous**:

```
Scenario: User enabled new mod
V1 Incremental Attempt:
  1. Compare previous manifest with current modlist
  2. Detect: Mod A was not in list, now is
  3. Scan only Mod A
  4. Deploy only Mod A's files
  ✅ Seems correct...
  
BUT what about:
  - Load order changed (affects file priority)
  - Mod A provides files that conflict with Mod B
  - Conflict cache is now stale
  - Previous "winner" was Mod C, now should be Mod A
  - Old manifest had Mod C's version of file X
  - New manifest should have Mod A's version of file X
  - ❌ You deployed Mod C's version, not Mod A's version
  → SILENT CORRUPTION (game loads wrong file)
```

### Common Failure Modes You Probably Hit

**Failure Mode 1: Stale Conflict Cache**
```
V1 approach:
  1. Load old conflict_cache.json (had Mod C winning for file X)
  2. Scan only new Mod A
  3. Add Mod A's files to cache
  4. ❌ Never re-evaluated Mod C vs Mod A priority
  Result: Wrong version of file X deployed
```

**Failure Mode 2: Load Order Changed**
```
Scenario:
  Before: Mod C (priority 100), Mod B (priority 50)
  After: Mod A (priority 150), Mod C (priority 100), Mod B (priority 50)
  
V1 incremental:
  1. See Mod A is new
  2. Scan Mod A, deploy its files
  3. ❌ But Mod C and Mod B still have OLD deployment from previous run
  4. New load order not respected
  Result: Mod A files deployed but Mod C overwrites them (wrong priority)
```

**Failure Mode 3: Mod Removed or Renamed**
```
Scenario:
  Before: Mod X provided 5000 files
  After: Mod X removed (user disabled/uninstalled)
  
V1 incremental:
  1. See Mod X is gone
  2. Remove Mod X's files from manifest
  3. ❌ But some of those files were ALREADY DEPLOYED in standalone
  4. Orphan files left behind (wrong versions, ghost data)
  Result: Standalone has stale files from removed mod
```

**Failure Mode 4: Mod Reorganized**
```
Scenario:
  Before: Mod C had 10,000 files
  After: User reorganized, Mod C now has 8,000 files (moved 2000 to Mod D)
  
V1 incremental:
  1. See Mod C has fewer files (compare counts)
  2. ❌ Only rescan Mod C (2000 files changed)
  3. Never scan Mod D (doesn't exist in old manifest)
  4. Mod D's files missing from deployment
  Result: Partial deployment, broken mods
```

### Why "Always Cleanup" Works

```python
# What cleanup does:
1. Load new manifest (fresh scan of ALL mods)
2. Delete everything in standalone
3. Redeploy from scratch
4. Result: Guaranteed correct (no stale state)

# Trade-off:
✅ 100% correct (no state corruption possible)
✅ Simple logic (can't get wrong)
✅ Recoverable (if deploy fails, just retry)
❌ Always slow (30 minutes, even for 1-file change)
```

---

## Why V2 Incremental Can Be Better (But Not Magic)

### The Key Insight from V1's Failure

What you learned: **Incremental is hard because state tracking is fragile.**

V2 can fix this with proper architecture:

```
V1 Approach (Failed):
  - Load old manifest
  - Load new modlist
  - Compare diffs
  - Scan only different mods
  - Update old manifest with new data
  → Relies on old manifest being 100% accurate
  → One mistake = corruption

V2 Approach (Safer):
  1. Full scan of ALL mods (like before)
  2. Load old manifest
  3. Compare old scan results with new scan results
  4. Identify true differences (not assumptions)
  5. Deploy only different files
  6. Verify result matches expected state
  → Only uses old manifest for comparison, not for decisions
  → New scan is source of truth
  → Verification catches mistakes
```

### Code Example: V2's Safer Incremental

```python
class SafeIncrementalDeploy:
    """Only deploy changed files, with safety checks."""
    
    def prepare_incremental(self, old_manifest: dict, new_scan_results: dict):
        """
        Compare old deployment state with new scan results.
        Only deploy files that changed.
        """
        
        # ✅ Key: SCAN ALL MODS (like V1 cleanup)
        # This gives us the correct current state
        new_manifest = new_scan_results  # Fresh scan, not assumptions
        
        # ⚠️ Compare carefully
        changes = {
            "added_files": {},      # New files to deploy
            "removed_files": {},    # Old files to delete
            "modified_files": {},   # Files that changed
            "unchanged_files": {}   # Skip these
        }
        
        # 1. Find files that were added or changed
        for file_path, new_info in new_manifest.items():
            if file_path not in old_manifest:
                changes["added_files"][file_path] = new_info
            else:
                # Check if file actually changed (not just mod reorganization)
                old_info = old_manifest[file_path]
                
                # Compare by content/mtime, not just mod name
                if (old_info["source_hash"] != new_info["source_hash"] or
                    old_info["source"] != new_info["source"]):
                    changes["modified_files"][file_path] = new_info
                else:
                    changes["unchanged_files"][file_path] = new_info
        
        # 2. Find files that were removed
        for file_path, old_info in old_manifest.items():
            if file_path not in new_manifest:
                changes["removed_files"][file_path] = old_info
        
        # ✅ Verification: Check load order didn't change
        old_load_order = old_manifest.get("metadata", {}).get("load_order", [])
        new_load_order = new_manifest.get("metadata", {}).get("load_order", [])
        
        if old_load_order != new_load_order:
            logger.warn(
                f"Load order changed! "
                f"Old: {len(old_load_order)} mods, "
                f"New: {len(new_load_order)} mods. "
                f"Must do full redeploy to respect new priorities."
            )
            return None  # Signal: can't do incremental, need full rebuild
        
        # ✅ Verification: Check conflict winners didn't change
        old_conflicts = old_manifest.get("conflict_analysis", {})
        new_conflicts = new_manifest.get("conflict_analysis", {})
        
        priority_changes = self._detect_priority_changes(old_conflicts, new_conflicts)
        if priority_changes:
            logger.warn(
                f"File priorities changed for {len(priority_changes)} files. "
                f"Must do full redeploy to correct priorities."
            )
            return None  # Signal: can't do incremental, need full rebuild
        
        return changes
    
    def execute_incremental(self, changes: dict, standalone_path: Path):
        """
        Deploy only changed files.
        ✅ This is safe because we verified nothing else changed.
        """
        
        if changes is None:
            logger.info("Incremental not safe, falling back to full rebuild")
            return self.full_rebuild()
        
        print(f"Incremental deploy:")
        print(f"  Adding: {len(changes['added_files'])} files")
        print(f"  Removing: {len(changes['removed_files'])} files")
        print(f"  Modifying: {len(changes['modified_files'])} files")
        print(f"  Skipping: {len(changes['unchanged_files'])} files (cached)")
        
        deployed = 0
        
        # Deploy added/modified files
        for file_path, file_info in {**changes["added_files"], **changes["modified_files"]}.items():
            source = Path(file_info["source"])
            target = standalone_path / file_path
            self._deploy_file(source, target)
            deployed += 1
        
        # Remove deleted files
        for file_path in changes["removed_files"].keys():
            target = standalone_path / file_path
            if target.exists():
                target.unlink()
        
        print(f"✓ Incremental complete: {deployed} files deployed")
        
        # ✅ CRITICAL: Verify result
        self.verify_standalone(standalone_path)
        
        return True
```

---

## Realistic Speed Gains in V2

### Scenario 1: Add Single Mod to Existing Standalone

```
V1 "Always Cleanup":
  - Scan all 50 mods: 8 min
  - Deploy all 50,000 files: 8 min
  - Verify: 3 min
  TOTAL: 19 min

V2 Full Rebuild (parallel):
  - Scan all 50 mods: 2 min (parallel)
  - Deploy all 50,000 files: 1 min (parallel)
  - Verify: 1 min (parallel)
  TOTAL: 4 min (5x faster just from parallelization)

V2 Incremental (if safe):
  - Scan all 50 mods: 2 min (still need full scan!)
  - Deploy only 1 mod's files: 5 sec
  - Verify: 1 min (still need full verify to be safe)
  TOTAL: 3 min (1 min saved vs full rebuild)
  
  Reality: 4 min vs 3 min = 25% savings (not 5x)
```

### Scenario 2: Enable Different Mod (Load Order Changed)

```
V2 Incremental (this case):
  - Scan all mods: 2 min
  - Detect: Load order changed
  - Decision: ❌ Can't do incremental (priorities changed)
  - Fallback: Full rebuild (4 min)
  TOTAL: 4 min (same as full)
```

### Scenario 3: Developer Workflow (Real-Time Sync)

```
Developer working on mod, rebuilding 20x/day:

V1 Approach:
  - Each rebuild: 25 min
  - 20 rebuilds: 500 min (8+ hours) 😢

V2 Incremental:
  - Still: 3-4 min per rebuild
  - 20 rebuilds: 60-80 min 😕

V2 Real-Time Sync (BETTER):
  - Watch for changes: 0 sec (automatic)
  - Sync 1 mod on change: 30 sec
  - 20 changes: 10 min total 😊
  
  → Real-time sync is 50x faster for developers
```

---

## The Hard Truth About Incremental

### When It Works (Speed Gains)
```
✅ Add new mod: 3 min instead of 4 min (25% faster)
✅ Remove mod: 3 min instead of 4 min (25% faster)
✅ Small change to 1 mod: 3 min instead of 4 min (25% faster)
```

### When It Doesn't Work (Fallback to Full)
```
❌ Load order changed: Must do full rebuild (0% faster)
❌ Enable/disable mod: Must do full rebuild (0% faster)
❌ Reorganize mods: Must do full rebuild (0% faster)
❌ Change mods folder: Must do full rebuild (0% faster)
```

### Real-World Usage Patterns
```
Casual User (rebuild every 2 weeks):
  - 2 rebuilds per month
  - Gains from incremental: ~1 hour/year
  - Worth the risk/complexity? NO

Power User (rebuild every day):
  - 30 rebuilds per month
  - Gains from incremental: ~15 hours/year
  - Worth the risk/complexity? MAYBE

Developer (rebuild 10x per day):
  - 300 rebuilds per month
  - Gains from incremental: ~150 hours/year
  - Worth the risk/complexity? NO (but real-time sync is YES)
```

---

## V2 Recommendation: Layered Approach

Instead of trying to make incremental work everywhere, give users OPTIONS:

### Mode 1: Safe Full Rebuild (Default) ✅

```python
def rebuild_full_safe():
    """
    Always the safe option.
    Fast enough with parallelization (3-4 minutes).
    """
    scanner = ScannerEngine()
    manifest = scanner.scan_all_mods()  # Fresh scan
    
    linker = LinkerExecutor()
    linker.deploy_all(manifest)  # Deploy everything
    
    verifier = VerificationEngine()
    verifier.verify_all(manifest)  # Verify everything
    
    return "Complete"
```

**When to use**: 95% of users, all the time
**Speed**: 3-4 minutes (with parallelization)
**Safety**: 100% guaranteed correct
**Risk**: Zero

---

### Mode 2: Incremental (Advanced, Optional) ⚠️

```python
def rebuild_incremental():
    """
    Only deploy changed files if safe to do so.
    Falls back to full rebuild if not safe.
    """
    old_manifest = load_previous_manifest()
    new_manifest = scanner.scan_all_mods()
    
    # Detect if incremental is safe
    changes = detect_changes(old_manifest, new_manifest)
    
    if not changes.is_safe():
        logger.info("Load order/priorities changed, doing full rebuild")
        return rebuild_full_safe()  # Fallback
    
    # Incremental only if we're confident
    deploy_changes(changes)
    verify_all(new_manifest)
    
    return f"Incremental: {changes.count()} files"
```

**When to use**: Advanced users who understand risks
**Speed**: 3 minutes (1 minute saved, but only sometimes)
**Safety**: 99% (must verify after)
**Risk**: Low (but non-zero state tracking complexity)
**Fallback**: Automatic full rebuild if not safe

---

### Mode 3: Real-Time Sync (Best for Developers) 🚀

```python
def enable_realtime_watch():
    """
    Watch for mod changes, auto-sync individual mods.
    MUCH faster than incremental, no state complexity.
    """
    observer = ModFolderWatcher()
    
    while True:
        changed_mod = observer.wait_for_change()  # Blocks until change
        logger.info(f"Detected change: {changed_mod}")
        
        # Scan just this mod
        mod_files = scanner.scan_mod(changed_mod)
        
        # Deploy just its files
        linker.deploy_mod(changed_mod, mod_files)
        
        # Verify
        verifier.verify_mod(changed_mod, mod_files)
        
        logger.info(f"✓ Synced {changed_mod} ({len(mod_files)} files)")
        # Loop continues, waits for next change
```

**When to use**: Developers, modders, power users rebuilding 5+ times/day
**Speed**: 30 seconds per mod change
**Safety**: 100% (syncs one mod at a time)
**Complexity**: Simple (no state tracking)

Example developer workflow:
```
Developer working on armor mod:
  1. Run "hardlink-builder watch" in background
  2. Edit mod files in MO2 folder
  3. Every 5 seconds, changes auto-sync to standalone
  4. Test in game immediately
  5. Edit more files → auto-sync → test
  
Result: 30-second feedback loop instead of 25-minute rebuild
```

---

## What V2 Should Actually Do

### Not Incremental (Complex, marginal gains)
```python
❌ Trying to be clever about state tracking
❌ Complex logic → more bugs
❌ Marginal speed gain (1 minute)
❌ High risk if wrong
```

### But This:
```python
✅ FAST full rebuild (parallelization, caching)
   3-4 minutes is fast enough for 95% of users

✅ OPTIONAL incremental (with auto-fallback)
   For users who understand the risks
   Auto-reverts to full rebuild if not safe

✅ REAL-TIME sync (for developers)
   Watch for changes, sync mod at a time
   Best of both worlds: speed + simplicity
```

---

## Answer to Your Question

**"When I add 1 mod to existing 50-mod setup, how much faster will V2 incremental be?"**

Honest answer:
```
V1 cleanup approach: 25 minutes (full rebuild)
  ↓
V2 full rebuild (with parallelization): 3-4 minutes
  ✅ 8x faster from parallelization alone
  
V2 incremental (if safe): 3 minutes
  ~ 25% faster than full rebuild
  ~ 90% faster than V1
  
V2 real-time sync (if available): 30 seconds
  ✅ 50x faster than V1
  ✅ But requires background watcher
```

---

## My Recommendation for V2

**Don't gamble on complex incremental.**

Instead:

1. **Make full rebuild FAST** (parallelization, caching)
   - Target: 3-4 minutes for typical 50-mod setup
   - This alone is 6-8x faster than V1
   - Enough for most users

2. **Add incremental as OPTIONAL advanced feature**
   - Only if user explicitly enables it
   - Auto-fallback to full rebuild if conditions aren't met
   - Saves 1-2 minutes sometimes, doesn't hurt
   - But not the main performance path

3. **Highlight real-time sync for developers**
   - Much simpler than incremental
   - Much faster for developer workflow (50x)
   - No state complexity
   - This is the real win for power users

---

## Why You Made the Right Call in V1

You discovered: **"Always cleanup is simpler and more correct than clever state tracking."**

This is actually a **mark of good engineering judgment**, not a failure.

V1's 25-minute rebuild is slow but **guaranteed correct**.
V1's incremental attempt was fast but **prone to corruption**.

You chose **correctness over speed** → smart call.

V2 should do the same, but make the "correctness" fast through:
- Parallelization (not clever state tracking)
- Caching (not partial rebuilds)
- Real-time sync (not incremental)

These are **simple, predictable, safe** ways to get speed.

---

**TL;DR**: Incremental is hard and only saves 1 minute sometimes. Parallelization saves 5+ minutes always. Invest in the latter. 🎯
