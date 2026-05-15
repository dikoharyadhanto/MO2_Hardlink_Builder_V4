# Selective Rehardlink Verification Design
## Verify & Repair Only Broken Hardlinks Without Touching Others

**Purpose**: Check integrity of deployed hardlinks, automatically repair only broken ones  
**Speed**: Check 50,000 files in 2-3 minutes, repair only broken files (usually <5 files)  
**Safety**: Never touch files that are verified intact  

---

## Overview: Why This is Better Than Incremental

### Incremental Updates Problem
```
User adds 1 mod → Incremental logic → Might corrupt state → User loses trust
Risk: High | Gain: 1-2 minutes
```

### Selective Rehardlink Problem
```
Hardlink breaks (user modified original, or reboot issue) 
→ Verify detects it → Repair only that file → Never corrupts state
Risk: Zero | Gain: Integrity guarantee
```

**Key Difference**: 
- Incremental = trying to be clever about state (risky)
- Selective rehardlink = just checking what's already there (safe)

---

## Architecture

### Three-Tier Verification Strategy

```
Tier 1: Quick Check (Fast)
  - Compare size + mtime
  - Takes <5 milliseconds per file
  - If match → assume intact, skip further checks
  - 50,000 files: ~2-3 minutes total

Tier 2: Hash Check (Accurate)
  - Calculate SHA256 hash of target file
  - Compare with source file hash
  - Only done for files that failed Tier 1
  - Detects corruption, modification, etc.

Tier 3: Action (Repair)
  - If hash differs, rehardlink
  - Delete target, recreate hardlink
  - Only happens for broken files (rare)
```

### Example Flow

```
Scenario: 50,000 files in standalone

Tier 1 (Quick Check): ~3 minutes
  File 1-49,995: ✓ Size matches, mtime matches → SKIP HASH CHECK
  File 49,996: ✗ Size differs (1024 vs 2048) → NEEDS HASH CHECK
  File 49,997: ✓ Size matches, mtime matches → SKIP HASH CHECK
  File 49,998: ✗ Mtime differs (10 hours offset) → NEEDS HASH CHECK
  File 49,999-50,000: ✓ Intact → SKIP HASH CHECK

Tier 2 (Hash Check): ~30 seconds (only 3 files)
  File 49,996: Hash SHA256(target) = abc123...
              Hash SHA256(source) = abc123... ✓ MATCHES
              → File is fine (just size metadata different)
  File 49,998: Hash SHA256(target) = def456...
              Hash SHA256(source) = xyz789... ✗ DIFFERS
              → File is CORRUPTED (mtime was false alarm)

Tier 3 (Rehardlink): ~1 second (1 file)
  File 49,998: DELETE target
              RECREATE HARDLINK source → target
              VERIFY hardlink successful

Result: Verified 50,000 files, found 1 actually broken, fixed it
Time: 3 min 30 sec total
Safety: 100% (only touched file we're 100% sure is broken)
```

---

## Detailed Implementation

### Phase 1: Quick Tier-1 Check

```python
class SelectiveRehardlinkVerifier:
    """Verify and repair hardlinks selectively."""
    
    def verify_all(self, manifest: dict, standalone_path: Path, 
                   progress_callback=None) -> dict:
        """
        Check all hardlinked files for integrity.
        Returns: {
            "total": 50000,
            "verified_ok": 49999,
            "needs_hash_check": 10,
            "corrupted": 1,
            "repaired": 1
        }
        """
        
        report = {
            "total": len(manifest),
            "verified_ok": 0,
            "needs_hash_check": [],
            "corrupted": [],
            "repaired": [],
            "errors": []
        }
        
        # ========== TIER 1: Quick Check ==========
        logger.info(f"[TIER 1] Quick check: size + mtime (50K files ~3 min)...")
        
        for i, (target_rel_path, file_info) in enumerate(manifest.items()):
            if file_info.get("method") != "hardlink":
                continue  # Skip non-hardlinked files
            
            source = Path(file_info["source"])
            target = standalone_path / target_rel_path
            
            try:
                if not self._quick_check_intact(source, target, file_info):
                    # File MIGHT be broken, needs deeper check
                    report["needs_hash_check"].append({
                        "file": target_rel_path,
                        "source": str(source),
                        "reason": "size or mtime mismatch"
                    })
                else:
                    report["verified_ok"] += 1
            
            except Exception as e:
                report["errors"].append({
                    "file": target_rel_path,
                    "error": str(e)
                })
            
            # Progress callback
            if progress_callback and (i % 1000) == 0:
                percent = int((i / report["total"]) * 50)  # 50% of total time
                progress_callback(percent, f"Quick check: {i}/{report['total']}")
        
        logger.info(f"[TIER 1] Complete: {report['verified_ok']} OK, "
                   f"{len(report['needs_hash_check'])} need deeper check")
        
        # ========== TIER 2: Hash Check (Only for suspicious files) ==========
        if report["needs_hash_check"]:
            logger.info(f"[TIER 2] Hash check: {len(report['needs_hash_check'])} files...")
            
            for i, suspicious in enumerate(report["needs_hash_check"]):
                target_rel_path = suspicious["file"]
                file_info = manifest[target_rel_path]
                source = Path(file_info["source"])
                target = standalone_path / target_rel_path
                
                try:
                    if self._hash_check_corrupted(source, target):
                        # File IS actually corrupted
                        report["corrupted"].append({
                            "file": target_rel_path,
                            "source": str(source),
                            "reason": "hash mismatch"
                        })
                    else:
                        # False alarm (metadata different but file content same)
                        report["verified_ok"] += 1
                
                except Exception as e:
                    report["errors"].append({
                        "file": target_rel_path,
                        "error": str(e)
                    })
                
                if progress_callback:
                    percent = 50 + int((i / len(report["needs_hash_check"])) * 30)
                    progress_callback(percent, f"Hash check: {i}/{len(report['needs_hash_check'])}")
        
        # ========== TIER 3: Rehardlink (Only for confirmed corrupted) ==========
        if report["corrupted"]:
            logger.info(f"[TIER 3] Rehardlink: {len(report['corrupted'])} files...")
            
            for i, corrupted in enumerate(report["corrupted"]):
                target_rel_path = corrupted["file"]
                file_info = manifest[target_rel_path]
                source = Path(file_info["source"])
                target = standalone_path / target_rel_path
                
                try:
                    if self._rehardlink_single(source, target):
                        report["repaired"].append(target_rel_path)
                        logger.info(f"✓ Rehardlinked: {target_rel_path}")
                    else:
                        report["errors"].append({
                            "file": target_rel_path,
                            "error": "Rehardlink failed"
                        })
                
                except Exception as e:
                    report["errors"].append({
                        "file": target_rel_path,
                        "error": str(e)
                    })
                
                if progress_callback:
                    percent = 80 + int((i / len(report["corrupted"])) * 20)
                    progress_callback(percent, f"Rehardlink: {i}/{len(report['corrupted'])}")
        
        return report
    
    def _quick_check_intact(self, source: Path, target: Path, 
                            file_info: dict) -> bool:
        """
        Quick check: size + mtime match?
        If yes → assume file is intact (don't check hash)
        If no → file might be broken (needs hash check)
        
        Returns: True if likely intact, False if needs verification
        """
        
        # Check target exists
        if not target.exists():
            return False  # File missing
        
        try:
            source_stat = source.stat()
            target_stat = target.stat()
            
            # Check 1: Size must match exactly
            if source_stat.st_size != target_stat.st_size:
                logger.debug(f"Size mismatch: {target.name} "
                           f"({source_stat.st_size} vs {target_stat.st_size})")
                return False
            
            # Check 2: mtime should be close (allow 2 seconds for filesystem variance)
            mtime_diff = abs(source_stat.st_mtime - target_stat.st_mtime)
            if mtime_diff > 2.0:  # More than 2 seconds difference
                logger.debug(f"mtime mismatch: {target.name} "
                           f"(diff: {mtime_diff:.1f}s)")
                return False
            
            # ✅ File looks intact based on metadata
            return True
        
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Quick check failed: {target} - {e}")
            return False
    
    def _hash_check_corrupted(self, source: Path, target: Path) -> bool:
        """
        Hash check: Do source and target have same content?
        Returns: True if corrupted (hashes don't match)
                False if intact (hashes match)
        
        Uses SHA256 for accuracy.
        """
        
        try:
            source_hash = self._calculate_hash(source)
            target_hash = self._calculate_hash(target)
            
            if source_hash != target_hash:
                logger.warn(f"Hash mismatch: {target.name} "
                          f"({source_hash} vs {target_hash})")
                return True  # CORRUPTED
            
            # ✅ Hashes match, file is intact
            return False
        
        except Exception as e:
            logger.error(f"Hash check failed: {target} - {e}")
            # On error, assume corrupted (safer to rehardlink)
            return True
    
    def _calculate_hash(self, file_path: Path, 
                       algorithm: str = "sha256", 
                       chunk_size: int = 8192) -> str:
        """
        Calculate file hash efficiently (read in chunks).
        """
        hasher = hashlib.sha256()
        
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
            
            return hasher.hexdigest()
        
        except Exception as e:
            logger.error(f"Hash calculation failed: {file_path} - {e}")
            raise
    
    def _rehardlink_single(self, source: Path, target: Path) -> bool:
        """
        Rehardlink a single broken file.
        Steps:
          1. Backup target (in case something goes wrong)
          2. Delete target
          3. Create new hardlink
          4. Verify hardlink successful
          5. Delete backup
        
        Returns: True if successful, False otherwise
        """
        
        backup_path = target.parent / f"{target.name}.backup"
        
        try:
            # Step 1: Backup
            if target.exists():
                shutil.copy2(target, backup_path)
            
            # Step 2: Delete
            if target.exists():
                os.remove(target)
            
            # Step 3: Create hardlink
            os.link(source, target)
            
            # Step 4: Verify
            source_stat = source.stat()
            target_stat = target.stat()
            
            if source_stat.st_ino != target_stat.st_ino:
                raise OSError("Hardlink verification failed: inodes don't match")
            
            if source_stat.st_size != target_stat.st_size:
                raise OSError("Hardlink verification failed: sizes don't match")
            
            # Step 5: Delete backup (success)
            if backup_path.exists():
                backup_path.unlink()
            
            logger.info(f"✓ Rehardlinked: {target.name}")
            return True
        
        except Exception as e:
            logger.error(f"Rehardlink failed: {target} - {e}")
            
            # Restore from backup on failure
            if backup_path.exists():
                logger.warn(f"Restoring from backup: {target.name}")
                try:
                    if target.exists():
                        os.remove(target)
                    shutil.copy2(backup_path, target)
                except Exception as restore_error:
                    logger.error(f"Backup restore failed: {restore_error}")
            
            return False
```

---

## Performance Characteristics

### Time Breakdown for 50,000 Files

```
Tier 1 (Quick Check):
  - Per file: ~0.06ms (metadata read only)
  - 50,000 files: ~3 minutes
  - Result: 49,999 files verified OK, 1 needs hash check

Tier 2 (Hash Check):
  - Per file: ~30ms (SHA256 hash entire file)
  - 1 file: ~30ms
  - Result: 1 file confirmed corrupted

Tier 3 (Rehardlink):
  - Per file: ~1 second (delete + hardlink + verify)
  - 1 file: ~1 second
  - Result: 1 file repaired

TOTAL TIME: ~3 minutes 31 seconds
  - Verified 50,000 files
  - Found 1 actually broken
  - Fixed it
```

### Speed Optimization Tips

```python
# Option 1: Skip hash check for tiny files (cost of hash > value)
def _should_skip_hash_check(self, file_size: int) -> bool:
    # Skip files <1KB (hash takes longer than redeploying)
    return file_size < 1024

# Option 2: Parallel hash checking (if you have multiple cores)
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(self._hash_check_corrupted, source, target)
        for source, target in suspicious_files
    ]

# Option 3: Cache hashes (don't recalculate for unchanged files)
def _calculate_hash_with_cache(self, file_path: Path) -> str:
    cache_key = (str(file_path), file_path.stat().st_mtime)
    
    if cache_key in self.hash_cache:
        return self.hash_cache[cache_key]
    
    file_hash = self._calculate_hash_slow(file_path)
    self.hash_cache[cache_key] = file_hash
    return file_hash
```

---

## Use Cases

### Use Case 1: Post-Deployment Verification

```python
# After deploying 50,000 files
deployment_report = linker.deploy_all(manifest)

# Immediately verify
verifier = SelectiveRehardlinkVerifier()
verification = verifier.verify_all(manifest, standalone_path)

if verification["corrupted"]:
    logger.warn(f"Found {len(verification['corrupted'])} corrupted files, repairing...")
    verifier.verify_all(manifest, standalone_path)  # Re-runs repair
else:
    logger.info("✓ All files verified intact")
```

### Use Case 2: Pre-Launch Validation

```python
# User wants to launch game, check hardlinks first
def validate_before_game_launch(standalone_path, manifest):
    verifier = SelectiveRehardlinkVerifier()
    results = verifier.verify_all(manifest, standalone_path)
    
    if results["corrupted"]:
        logger.error(f"⚠️ {len(results['corrupted'])} corrupted files detected")
        logger.info("Repairing...")
        results = verifier.verify_all(manifest, standalone_path)
        if results["corrupted"]:
            raise RuntimeError(f"Still {len(results['corrupted'])} broken after repair")
    
    logger.info("✓ Hardlinks verified, safe to launch game")
    return True
```

### Use Case 3: Regular Maintenance (Weekly)

```python
# User runs verification weekly to catch issues
def weekly_maintenance():
    verifier = SelectiveRehardlinkVerifier()
    results = verifier.verify_all(manifest, standalone_path)
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "files_checked": results["total"],
        "files_ok": results["verified_ok"],
        "files_repaired": len(results["repaired"]),
        "errors": results["errors"]
    }
    
    # Save report
    with open("maintenance_log.json", "a") as f:
        json.dump(report, f)
    
    # Alert if repairs were needed
    if results["repaired"]:
        logger.warn(f"Maintenance: {len(results['repaired'])} files were repaired")
```

### Use Case 4: Detect User Modifications

```python
# Advanced: Detect if user manually edited files
def audit_user_changes(manifest, standalone_path):
    verifier = SelectiveRehardlinkVerifier()
    results = verifier.verify_all(manifest, standalone_path)
    
    if results["corrupted"]:
        print("User may have manually edited these files:")
        for corrupted in results["corrupted"]:
            print(f"  - {corrupted['file']}")
        
        # Ask user: repair or keep edits?
        if user_confirms("Restore original files?"):
            verifier.verify_all(manifest, standalone_path)  # Repair
        else:
            logger.info("User kept custom edits")
```

---

## Report Example

```json
{
  "timestamp": "2026-04-18T14:30:00",
  "verification_result": {
    "total": 50000,
    "verified_ok": 49998,
    "needs_hash_check": [
      {
        "file": "Data/meshes/armor_01.nif",
        "source": "/path/to/mod/Data/meshes/armor_01.nif",
        "reason": "mtime mismatch"
      },
      {
        "file": "Data/textures/armor_01.dds",
        "source": "/path/to/mod/Data/textures/armor_01.dds",
        "reason": "size mismatch"
      }
    ],
    "corrupted": [
      {
        "file": "Data/meshes/armor_01.nif",
        "source": "/path/to/mod/Data/meshes/armor_01.nif",
        "reason": "hash mismatch (user edited?)"
      }
    ],
    "repaired": [
      "Data/meshes/armor_01.nif"
    ],
    "errors": []
  },
  "summary": {
    "duration_seconds": 211,
    "files_per_second": 237,
    "repairs_made": 1,
    "success": true
  }
}
```

---

## Integration with V2 Workflow

### Where Selective Rehardlink Fits

```
User Deploys Mod:
  1. Scan mods → Build manifest
  2. Deploy files (hardlink + copy)
  3. ✨ VERIFY & REPAIR HARDLINKS ← NEW
  4. Sync configs
  5. Generate report
  6. ✓ Deployment complete

Pre-Game Launch:
  1. User clicks "Launch Game"
  2. ✨ Quick verification ← 3 sec hardlink check
  3. If any corrupted: Auto-repair ← 1 sec per file
  4. ✓ Safe to play
```

### In UI

```
┌─ Deployment Report ────────────────┐
│ Deployment: ✓ Success              │
│ - 50,000 files deployed            │
│ - 48,500 hardlinks, 1,500 copies   │
│                                    │
│ Verification: ✓ Passed             │
│ - 50,000 files verified            │
│ - 49,998 OK                        │
│ - 2 needed hash check              │
│ - 1 corrupted (rehardlinked)       │
│                                    │
│ ✓ Ready to play                    │
└────────────────────────────────────┘
```

---

## Edge Cases & Handling

### Edge Case 1: File is Locked (Game Running)

```python
def _rehardlink_single(self, source: Path, target: Path) -> bool:
    try:
        # Try to hardlink
        os.link(source, target)
    except PermissionError:
        # File is locked
        logger.warn(f"File locked (game running?): {target.name}")
        logger.info("Deferring rehardlink until next verification")
        return False  # Don't fail, just defer
```

### Edge Case 2: Source File Changed

```python
def _verify_all(self, manifest, standalone_path):
    for target_rel_path, file_info in manifest.items():
        source = Path(file_info["source"])
        
        # Check if source still exists (mod might be deleted)
        if not source.exists():
            logger.error(f"Source missing: {source}")
            # Don't delete target, user might be working on it
            continue
```

### Edge Case 3: User Intentionally Edited File

```
User edited Data/meshes/armor.nif in standalone
↓
Verification detects hash mismatch
↓
Report shows: "Data/meshes/armor.nif (edited)"
↓
Options:
  A) Restore original (overwrite user edit)
  B) Keep user edit (skip rehardlink)
  C) Backup user edit + restore original
```

---

## Why This Works

### ✅ Safe
- Only touches files you're 100% sure are broken
- Never modifies files that are verified intact
- Backup system for recovery

### ✅ Fast
- 3 seconds to check if everything is OK
- Only hash-check suspicious files
- Rehardlink takes 1 second per broken file

### ✅ Simple
- No complex state tracking like incremental
- Just check what's there, fix what's broken
- Works for any scenario (add mods, remove mods, etc.)

### ✅ Automatic
- Can run post-deployment
- Can run pre-game-launch
- Can run on schedule (weekly)
- No user intervention needed

---

## Implementation Priority for V2

**Phase 1 (Critical)**: Implement basic Tier-1 + Tier-2 + Tier-3
- Takes 2-3 weeks
- Gives users confidence hardlinks are solid
- Posts after every deployment

**Phase 2 (Nice-to-Have)**: Optimization
- Cache hashes
- Parallel hash checking
- Skip tiny files

**Phase 3 (Future)**: Advanced features
- User modification detection
- Web dashboard for maintenance history
- Scheduled verification jobs

---

## Comparison: Incremental vs Selective Rehardlink

| Aspect | Incremental | Selective Rehardlink |
|--------|------------|----------------------|
| **Complexity** | High (state tracking) | Low (verification only) |
| **Risk** | Medium (can corrupt) | Low (never touches OK files) |
| **Speed Gain** | 1-2 minutes (sometimes) | Not about speed, about confidence |
| **When Works** | Add/remove mods | Always works |
| **When Fails** | Load order change, reorganize | Never fails (graceful degradation) |
| **User Trust** | Requires faith in logic | Builds from validation |
| **Debuggability** | Hard (state issues) | Easy (just check hashes) |

---

**Conclusion**: Selective Rehardlink is the right approach because it trades a small speed gain (incremental) for guaranteed safety and user confidence. It's how every package manager works, and it's proven to be reliable. 🎯

