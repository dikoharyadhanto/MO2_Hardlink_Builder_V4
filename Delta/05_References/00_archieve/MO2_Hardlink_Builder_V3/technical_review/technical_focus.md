# Technical Focus — MO2 Hardlink Builder V2
## Feature Roadmap, Fixes, Optimizations & Expected Outcomes

**Document Version**: v1.0  
**Target Release**: Q3 2026  
**Scope**: Complete rewrite with backward compatibility  

---

## Vision for V2

**From**: A functional but fragile Skyrim-only tool (V1)  
**To**: An enterprise-grade, multi-game platform with safety guarantees (V2)

**Core Promise**: "Deploy mods safely, verify completely, recover gracefully."

---

## Part 1: CRITICAL FIXES (Must Complete Before Release)

### FIX-001: Reliable Load Order Detection 🔴

**Current Problem** (V1):
```python
# Heuristic guessing based on keyword positions
# Silent failures if keywords don't match
# Result: Mods deployed in wrong order → game crashes
```

**V2 Solution**:
```
1. PRIMARY: Query MO2 via mobase.IOrganizer API
   - Load actual priority order from MO2
   - No parsing, no guessing
   - Eliminates heuristic failures entirely

2. FALLBACK: User-selected load order format
   - UI dropdown: "Top-Down" or "Bottom-Up"
   - Saved to config, reused for future builds

3. VALIDATION: Verify after read
   - Check that all active mods exist in mods folder
   - Validate plugin order (if .esm/.esp files)
   - Report missing/invalid entries before deployment
```

**V2 Code Structure**:
```python
class LoadOrderResolver:
    """Get actual mod order from MO2 or user config."""
    
    def __init__(self, organizer: mobase.IOrganizer):
        self.organizer = organizer
    
    def get_active_mods_ordered(self) -> List[str]:
        """
        Returns mods in priority order (highest to lowest).
        Uses mobase API, falls back to modlist.txt parsing.
        """
        try:
            # Use MO2 API - authoritative source
            return self._get_from_mobase_api()
        except Exception as e:
            logger.warning(f"MO2 API failed: {e}, falling back to modlist.txt")
            return self._get_from_modlist_txt()
    
    def validate_load_order(self, mods: List[str]) -> List[str]:
        """
        Validate mods exist and order is sane.
        Returns list of errors (empty = valid).
        """
        errors = []
        for mod in mods:
            if not (self.mods_dir / mod).exists():
                errors.append(f"Mod folder not found: {mod}")
        
        # Check for circular dependencies (future enhancement)
        
        return errors
```

**Expected Outcome**:
- ✅ Zero silent load order failures
- ✅ 100% accurate mod priority detection
- ✅ Clear error messages if anything is wrong
- ✅ User can override if needed (advanced option)

**Testing Strategy**:
- [ ] Test with MO2 instances with 500+ mods
- [ ] Test with non-English MO2 installations
- [ ] Test fallback parsing on all MO2 versions
- [ ] Verify with actual game launch

**Effort**: 1-2 weeks | **Risk**: Low

---

### FIX-002: Hardlink Verification & Validation 🔴

**Current Problem** (V1):
```
- No check that hardlink actually created
- No validation that link survives reboot
- User thinks they saved 50GB, but files are copies
- No way to detect difference until game fails to load
```

**V2 Solution**:

**Step 1: Create with Verification**
```python
class HardlinkManager:
    """Create and verify hardlinks safely."""
    
    def create_and_verify(self, source: Path, target: Path) -> str:
        """
        Create hardlink and VERIFY it worked.
        Returns: "hardlink" | "copy" (fallback)
        Raises: Exception if both fail
        """
        # 1. Clear target
        if target.exists():
            os.remove(target)
        
        # 2. Try hardlink
        try:
            os.link(source, target)
            
            # 3. CRITICAL: Verify hardlink worked
            if self._verify_hardlink(source, target):
                return "hardlink"
            else:
                # Hardlink failed silently - cleanup and fallback
                logger.warn(f"Hardlink verification failed: {target}")
                os.remove(target)
                raise OSError("Hardlink verification failed")
        
        except OSError as e:
            # 4. Fallback to copy
            logger.info(f"Hardlink failed ({e}), using copy: {target}")
            shutil.copy2(source, target)
            return "copy"
    
    def _verify_hardlink(self, source: Path, target: Path) -> bool:
        """
        Verify that hardlink was actually created.
        """
        source_stat = source.stat()
        target_stat = target.stat()
        
        # Check 1: Same inode (proof they're hardlinked)
        if source_stat.st_ino != target_stat.st_ino:
            logger.error(f"Inode mismatch: {source.st_ino} vs {target.st_ino}")
            return False
        
        # Check 2: Same size
        if source_stat.st_size != target_stat.st_size:
            logger.error(f"Size mismatch: {source_stat.st_size} vs {target_stat.st_size}")
            return False
        
        # Check 3: Same modification time (usually preserved)
        # Allow 1 second difference due to filesystem precision
        if abs(source_stat.st_mtime - target_stat.st_mtime) > 1:
            logger.warn(f"mtime differs: {source_stat.st_mtime} vs {target_stat.st_mtime}")
            # This is warning not error (filesystem may adjust times)
        
        return True
    
    def validate_hardlinks_post_deployment(self, manifest: dict) -> dict:
        """
        Post-deployment: Verify all hardlinks are still valid.
        Useful before user deletes original mods.
        """
        issues = {
            "broken_hardlinks": [],
            "orphaned_copies": [],
            "size_mismatches": []
        }
        
        for target_rel_path, file_info in manifest.items():
            if file_info.get("method") != "hardlink":
                continue
            
            target = self.standalone_path / target_rel_path
            source = Path(file_info["source"])
            
            if not self._verify_hardlink(source, target):
                issues["broken_hardlinks"].append({
                    "file": target_rel_path,
                    "source": str(source)
                })
        
        return issues
```

**Step 2: Report Hardlink Status**
```
Deployment Report:
  Total Files: 50,000
  Hardlinks: 48,500 (97%)
  Copies: 1,500 (3%)
  
  Why copies instead of hardlinks:
  - 1,000 cross-volume files (different drive)
  - 500 filesystem limitations (exFAT, network)
  
  Space Savings:
  - Original total: 150 GB
  - Hardlinks save: 145 GB (97%)
  - Copies cost: 5 GB (3%)
  - Final standalone: ~5 GB (vs 150 GB if all copies)
```

**Expected Outcome**:
- ✅ Users know EXACTLY which files are hardlinked vs copied
- ✅ Space savings are guaranteed and verified
- ✅ Hardlink failures detected early, not after user deletes mods
- ✅ Post-deployment verification catches broken links
- ✅ Detailed report explains what worked and why

**Testing Strategy**:
- [ ] Test on NTFS, FAT32, exFAT, network drives
- [ ] Verify hardlinks survive reboot
- [ ] Test concurrent access to hardlinked files
- [ ] Benchmark: 50,000 file verification takes <5 minutes

**Effort**: 2-3 weeks | **Risk**: Low

---

### FIX-003: Safe Orphan Cleanup with User Control 🔴

**Current Problem** (V1):
```
- Silently deletes files not in manifest
- No user confirmation
- No logging of what was deleted
- No recovery option
```

**V2 Solution**:

**Step 1: Dry-Run Preview**
```python
def preview_orphan_cleanup(self) -> dict:
    """Show user what WOULD be deleted before asking."""
    orphans = self._find_orphaned_files()
    
    return {
        "total_orphans": len(orphans),
        "total_size_gb": sum(f["size"] for f in orphans) / 1024**3,
        "files_by_type": {
            "user_saves": len([f for f in orphans if "saves" in f["path"]]),
            "user_configs": len([f for f in orphans if "ini" in f["path"] or "txt" in f["path"]]),
            "misc_data": len([f for f in orphans if not ("saves" in f["path"] or "ini" in f["path"])])
        },
        "sample_files": orphans[:20]  # Show first 20
    }
```

**Step 2: User Confirmation**
```
UI Dialog:
┌─ Cleanup Preview ─────────────────┐
│ Found 1,547 orphaned files (3.2GB) │
│                                    │
│ User Saves (250 files, 500MB)      │
│  - save_001.ess                    │
│  - save_002.ess                    │
│  ... 248 more                      │
│                                    │
│ User Configs (50 files, 1.2MB)     │
│  - Skyrim.ini (backup)             │
│  ... 49 more                       │
│                                    │
│ Misc Data (1,247 files, 2.7GB)     │
│  [Show Details ▼]                  │
│                                    │
│ [Cancel] [Archive Files] [Delete]  │
└─────────────────────────────────────┘
```

**Step 3: Options (Not Just Delete)**
```python
class CleanupAction(Enum):
    CANCEL = "cancel"           # Don't delete anything
    ARCHIVE = "archive"         # Zip to backup location
    DELETE = "delete"           # Delete with logging
    DELETE_EXCEPT_SAVES = "del"  # Delete but keep saves
```

**Step 4: Logging & Recovery**
```python
def cleanup_orphans(self, orphans: List[Path], action: CleanupAction):
    """Delete/archive orphans with full logging."""
    
    cleanup_log = {
        "timestamp": datetime.now().isoformat(),
        "action": action.value,
        "total_files": len(orphans),
        "deleted": [],
        "archived": [],
        "failed": []
    }
    
    if action == CleanupAction.ARCHIVE:
        # Create timestamped archive
        archive_name = f"orphans_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        archive_path = self.backup_root / archive_name
        
        with zipfile.ZipFile(archive_path, 'w') as zf:
            for orphan in orphans:
                try:
                    zf.write(orphan, arcname=orphan.relative_to(self.standalone_path))
                    cleanup_log["archived"].append(str(orphan))
                except Exception as e:
                    cleanup_log["failed"].append({"file": str(orphan), "error": str(e)})
    
    elif action == CleanupAction.DELETE:
        for orphan in orphans:
            try:
                orphan.unlink()
                cleanup_log["deleted"].append(str(orphan))
            except Exception as e:
                cleanup_log["failed"].append({"file": str(orphan), "error": str(e)})
    
    # Save cleanup log for recovery
    log_path = self.metadata_dir / f"cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_path, 'w') as f:
        json.dump(cleanup_log, f, indent=2)
    
    return cleanup_log
```

**Expected Outcome**:
- ✅ Users see exactly what will be deleted before it happens
- ✅ Can choose to archive instead of delete (safe recovery)
- ✅ Complete log of what was deleted
- ✅ Recovery: Unzip archived files if needed
- ✅ No surprise data loss

**Testing Strategy**:
- [ ] Test with 50,000 orphaned files (performance)
- [ ] Verify archive file integrity
- [ ] Test recovery from archive
- [ ] Confirm logging is complete

**Effort**: 1-2 weeks | **Risk**: Low

---

### FIX-004: Strict Configuration Verification 🔴

**Current Problem** (V1):
```
- Skips verification in stealth mode
- Doesn't validate plugins.txt/loadorder.txt match
- Config mismatches are silent (game crashes later)
```

**V2 Solution**:

**Step 1: Mandatory Verification**
```python
class ConfigVerification:
    """Verify all configs are properly synchronized."""
    
    def verify_critical_configs(self, strict=True) -> VerificationResult:
        """
        Verify that MO2 profile and standalone have matching critical configs.
        
        strict=True: Any mismatch is an error
        strict=False: Log warnings but don't fail
        """
        results = {
            "plugins_match": False,
            "loadorder_match": False,
            "ini_match": False,
            "errors": [],
            "warnings": []
        }
        
        # 1. CRITICAL: Check plugins.txt
        src_plugins = self._read_plugin_list(self.source_appdata / "plugins.txt")
        dst_plugins = self._read_plugin_list(self.target_appdata / "plugins.txt")
        
        if src_plugins != dst_plugins:
            diff = {
                "in_source_not_target": list(set(src_plugins) - set(dst_plugins)),
                "in_target_not_source": list(set(dst_plugins) - set(src_plugins))
            }
            if strict:
                results["errors"].append({
                    "type": "PLUGIN_MISMATCH",
                    "detail": diff
                })
            else:
                results["warnings"].append({"type": "PLUGIN_MISMATCH", "detail": diff})
        else:
            results["plugins_match"] = True
        
        # 2. CRITICAL: Check loadorder.txt
        src_order = self._read_loadorder(self.source_appdata / "loadorder.txt")
        dst_order = self._read_loadorder(self.target_appdata / "loadorder.txt")
        
        if src_order != dst_order:
            if strict:
                results["errors"].append({
                    "type": "LOADORDER_MISMATCH",
                    "source_count": len(src_order),
                    "target_count": len(dst_order)
                })
            else:
                results["warnings"].append({"type": "LOADORDER_MISMATCH"})
        else:
            results["loadorder_match"] = True
        
        # 3. Check INI files (functional comparison, not byte-exact)
        ini_issues = self._compare_ini_settings(
            src_docs=self.source_docs,
            dst_docs=self.target_docs,
            ignore_pattern=["sLocalSavePath"]  # Expected to differ
        )
        if ini_issues:
            if strict:
                results["errors"].extend(ini_issues)
            else:
                results["warnings"].extend(ini_issues)
        else:
            results["ini_match"] = True
        
        # 4. Fail if strict mode and errors exist
        if strict and results["errors"]:
            raise ConfigVerificationError(f"Configuration mismatch detected: {results['errors']}")
        
        return results
    
    def _compare_ini_settings(self, src_docs, dst_docs, ignore_pattern=None) -> List[dict]:
        """
        Compare INI settings functionally (not byte-exact).
        Handle whitespace, case, order differences.
        """
        issues = []
        ini_files = ["Skyrim.ini", "SkyrimPrefs.ini", "SkyrimCustom.ini"]
        
        for ini_file in ini_files:
            src_ini = src_docs / ini_file
            dst_ini = dst_docs / ini_file
            
            if not src_ini.exists() or not dst_ini.exists():
                continue
            
            src_config = self._parse_ini(src_ini)
            dst_config = self._parse_ini(dst_ini)
            
            # Compare functionally (normalize whitespace, case)
            src_normalized = self._normalize_config(src_config, ignore_pattern)
            dst_normalized = self._normalize_config(dst_config, ignore_pattern)
            
            # Find differences
            for section, keys in src_normalized.items():
                if section not in dst_normalized:
                    issues.append({
                        "type": "SECTION_MISSING",
                        "file": ini_file,
                        "section": section
                    })
                    continue
                
                for key, value in keys.items():
                    dst_value = dst_normalized[section].get(key)
                    if dst_value != value:
                        issues.append({
                            "type": "VALUE_MISMATCH",
                            "file": ini_file,
                            "key": f"{section}/{key}",
                            "source_value": value,
                            "target_value": dst_value
                        })
        
        return issues
```

**Step 2: Pre-Game Launch Validation**
```python
def validate_before_launch(standalone_path) -> bool:
    """
    Final check before user launches game.
    Catch misconfigurations before game crash.
    """
    checks = [
        check_plugins_loaded(),
        check_loadorder_applied(),
        check_ini_settings_active(),
        check_save_games_accessible(),
        check_critical_mods_present()
    ]
    
    if all(checks):
        print("✓ All validations passed. Safe to launch game.")
        return True
    else:
        print("✗ Validation failed. Fix issues before launching.")
        return False
```

**Expected Outcome**:
- ✅ Config mismatches detected BEFORE game launch
- ✅ User sees exact differences (not vague errors)
- ✅ Clear resolution steps provided
- ✅ No more silent game failures

**Testing Strategy**:
- [ ] Test with mismatched plugins.txt
- [ ] Test with different INI settings
- [ ] Test with missing sections
- [ ] Verify error messages are clear

**Effort**: 2 weeks | **Risk**: Low

---

### FIX-005: Transaction System with Rollback 🔴

**Current Problem** (V1):
```
- Deployment can fail halfway through
- Partial state is unrecoverable
- No rollback option
```

**V2 Solution**:

```python
class DeploymentTransaction:
    """Atomic deployment with full rollback capability."""
    
    def __init__(self, manifest_path: Path, target_path: Path, checkpoint_dir: Path):
        self.manifest = self._load_manifest(manifest_path)
        self.target = target_path
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_file = checkpoint_dir / ".deployment_in_progress.json"
        self.deployed: List[dict] = []
        self.failed: List[dict] = []
    
    def begin_transaction(self):
        """Start deployment, create checkpoint file."""
        self.checkpoint = {
            "status": "IN_PROGRESS",
            "start_time": datetime.now().isoformat(),
            "manifest_hash": self._hash_manifest(self.manifest),
            "target_path": str(self.target),
            "deployed_files": [],
            "failed_files": []
        }
        self._save_checkpoint()
        logger.info(f"Transaction started: {self.checkpoint_file}")
    
    def deploy_file(self, source: Path, target_rel_path: str) -> bool:
        """
        Deploy single file atomically.
        Update checkpoint after each successful file.
        """
        target_full_path = self.target / target_rel_path
        
        try:
            # Create parent directories
            target_full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Remove existing file (if any)
            if target_full_path.exists():
                os.remove(target_full_path)
            
            # Deploy with method tracking
            method = self._deploy_with_fallback(source, target_full_path)
            
            # Record success
            deployment_record = {
                "target": target_rel_path,
                "method": method,
                "timestamp": time.time(),
                "source_size": source.stat().st_size
            }
            
            self.deployed.append(deployment_record)
            
            # Update checkpoint (persist every file for recovery)
            self.checkpoint["deployed_files"].append(deployment_record)
            self._save_checkpoint()
            
            return True
        
        except Exception as e:
            # Record failure
            failure_record = {
                "target": target_rel_path,
                "error": str(e),
                "timestamp": time.time()
            }
            
            self.failed.append(failure_record)
            self.checkpoint["failed_files"].append(failure_record)
            self._save_checkpoint()
            
            logger.error(f"Deployment failed: {target_rel_path} - {e}")
            return False
    
    def commit(self) -> bool:
        """Finalize successful deployment."""
        if self.failed:
            logger.error(f"Cannot commit: {len(self.failed)} files failed")
            return False
        
        self.checkpoint["status"] = "COMPLETE"
        self._save_checkpoint()
        
        # Remove checkpoint file on success
        try:
            self.checkpoint_file.unlink()
        except:
            pass
        
        logger.info(f"Transaction committed: {len(self.deployed)} files deployed")
        return True
    
    def rollback(self) -> bool:
        """Revert deployment to pre-transaction state."""
        logger.warn(f"Rolling back {len(self.deployed)} files...")
        
        rollback_log = {
            "timestamp": datetime.now().isoformat(),
            "files_removed": [],
            "removal_failed": []
        }
        
        # Remove files in reverse order
        for deployment in reversed(self.deployed):
            target_path = self.target / deployment["target"]
            try:
                if target_path.exists():
                    target_path.unlink()
                rollback_log["files_removed"].append(deployment["target"])
            except Exception as e:
                logger.error(f"Rollback failed for: {target_path} - {e}")
                rollback_log["removal_failed"].append({
                    "file": deployment["target"],
                    "error": str(e)
                })
        
        # Mark transaction as rolled back
        self.checkpoint["status"] = "ROLLED_BACK"
        self._save_checkpoint()
        
        # Save rollback log
        rollback_log_path = self.checkpoint_dir / f"rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(rollback_log_path, 'w') as f:
            json.dump(rollback_log, f, indent=2)
        
        logger.info(f"Rollback complete. Log: {rollback_log_path}")
        return True
    
    def resume_from_checkpoint(self) -> dict:
        """
        Resume interrupted deployment from checkpoint.
        Returns: {'remaining_files': N, 'deployed_files': N, 'failed_files': N}
        """
        if not self.checkpoint_file.exists():
            raise FileNotFoundError("No checkpoint found, cannot resume")
        
        checkpoint = self._load_checkpoint()
        deployed = checkpoint["deployed_files"]
        failed = checkpoint["failed_files"]
        remaining = len(self.manifest) - len(deployed)
        
        logger.info(f"Resuming from checkpoint: {remaining} files remaining, {len(failed)} failed")
        
        return {
            "remaining_files": remaining,
            "deployed_files": len(deployed),
            "failed_files": len(failed),
            "checkpoint": checkpoint
        }
    
    def _save_checkpoint(self):
        """Persist checkpoint to disk."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_file, 'w') as f:
            json.dump(self.checkpoint, f, indent=2)
    
    def _load_checkpoint(self) -> dict:
        """Load checkpoint from disk."""
        with open(self.checkpoint_file, 'r') as f:
            return json.load(f)
    
    def _deploy_with_fallback(self, source: Path, target: Path) -> str:
        """Deploy with hardlink fallback, return method."""
        try:
            os.link(source, target)
            return "hardlink"
        except OSError:
            shutil.copy2(source, target)
            return "copy"
    
    def _hash_manifest(self, manifest: dict) -> str:
        """Hash manifest for integrity check."""
        manifest_json = json.dumps(manifest, sort_keys=True)
        return hashlib.sha256(manifest_json.encode()).hexdigest()[:16]
```

**Usage Example**:
```python
# Normal deployment
transaction = DeploymentTransaction(manifest, target, checkpoint_dir)
transaction.begin_transaction()

for target_rel_path, file_info in manifest.items():
    source = Path(file_info["source"])
    if not transaction.deploy_file(source, target_rel_path):
        # Log failure, continue (non-blocking)
        pass

if transaction.failed:
    logger.error(f"Deployment completed with {len(transaction.failed)} failures")
    # User can review failures and retry
    transaction.commit()  # Commit what succeeded
else:
    transaction.commit()  # Success


# Interrupted deployment (next run)
transaction = DeploymentTransaction(manifest, target, checkpoint_dir)
if transaction.checkpoint_file.exists():
    status = transaction.resume_from_checkpoint()
    print(f"Resuming: {status['remaining_files']} files left")
    # Continue deployment from where it stopped
```

**Expected Outcome**:
- ✅ Deployment always finishes (resume on interrupt)
- ✅ Partial failures don't corrupt installation
- ✅ User can see exactly what succeeded/failed
- ✅ Can rollback if needed (before committing)
- ✅ Checkpoint saved after every file (safe recovery)

**Testing Strategy**:
- [ ] Test interruption at various points (1%, 50%, 99%)
- [ ] Verify resume continues from correct point
- [ ] Test rollback with 50,000 files
- [ ] Verify checkpoint persistence

**Effort**: 2-3 weeks | **Risk**: Medium (complex logic)

---

## Part 2: FEATURE IMPROVEMENTS (Enhance Existing Functionality)

### IMPROVE-001: Multi-Game Support Framework

**Current Limitation** (V1):
```
- Hardcoded for Skyrim Special Edition
- Works with Skyrim but not Fallout/Starfield/Oblivion
- Extends compatibility to ~2% of potential users
```

**V2 Solution**:

**Step 1: Game Profile System**
```json
// game_profiles.json
{
  "skyrim_se": {
    "name": "Skyrim Special Edition",
    "mobase_plugin_path": "plugins",
    "docs_name": "Skyrim Special Edition",
    "appdata_name": "Skyrim Special Edition",
    "ini_prefix": "Skyrim",
    "ini_files": ["Skyrim.ini", "SkyrimPrefs.ini", "SkyrimCustom.ini"],
    "critical_extensions": [".esp", ".esm", ".esl", ".bsa", ".ba2"],
    "blacklist_extensions": [".pdf", ".docx"],
    "blacklist_files": ["meta.ini", "mo2_separator.txt", "thumbs.db"],
    "critical_folders": ["data", "root"],
    "save_file_extension": ".ess"
  },
  "fallout_4": {
    "name": "Fallout 4",
    "docs_name": "Fallout 4",
    "appdata_name": "Fallout 4",
    "ini_prefix": "Fallout4",
    "ini_files": ["Fallout4.ini", "Fallout4Prefs.ini", "Fallout4Custom.ini"],
    "critical_extensions": [".esp", ".esm", ".ba2"],
    "save_file_extension": ".fos"
  },
  "starfield": {
    "name": "Starfield",
    "docs_name": "Starfield",
    "appdata_name": "Starfield",
    "ini_prefix": "Starfield",
    "ini_files": ["Starfield.ini", "StarfieldPrefs.ini"],
    "critical_extensions": [".esp", ".esm", ".ba2"],
    "save_file_extension": ".sfs"
  }
}
```

**Step 2: Game-Agnostic Engines**
```python
class ScannerEngine:
    """Works with any game via GameProfile."""
    
    def __init__(self, mods_dir, game_profile: GameProfile):
        self.mods_dir = Path(mods_dir)
        self.game_profile = game_profile
        
        # Use profile for blacklist/critical lists
        self.blacklist_files = game_profile.blacklist_files
        self.critical_extensions = game_profile.critical_extensions
        self.critical_folders = game_profile.critical_folders
    
    def _scan_folder(self, folder_path, mod_name):
        """Works for any game, using game_profile settings."""
        for root, dirs, files in os.walk(folder_path):
            # Use game profile to filter folders
            dirs[:] = [d for d in dirs if d.lower() not in self.game_profile.blacklist_dirs]
            
            for file_name in files:
                # Use game profile to filter extensions
                ext = Path(file_name).suffix.lower()
                if ext in self.game_profile.blacklist_extensions:
                    continue
```

**Step 3: UI Game Selector**
```
UI Dialog:
┌─ Select Game ────────────────────┐
│ [v] Skyrim Special Edition       │
│ [ ] Fallout 4                    │
│ [ ] Starfield                    │
│ [ ] Oblivion                     │
│ [ ] Custom...                    │
│                                  │
│ Selected: Skyrim SE              │
│ Profile Location: <auto-detect>  │
│ [Next]                           │
└──────────────────────────────────┘
```

**Expected Outcome**:
- ✅ Single codebase supports all Bethesda games
- ✅ Easy to add new games (just add to game_profiles.json)
- ✅ 10x larger potential user base
- ✅ Configuration is data-driven, not code-driven

**Testing Strategy**:
- [ ] Test with Skyrim SE, Fallout 4, Starfield
- [ ] Verify each game's INI files are correct
- [ ] Test save game sync for each game
- [ ] Verify plugin extensions are correct

**Effort**: 2-3 weeks | **Risk**: Low

**Expected Gain**: 10x more users (multi-game support)

---

### IMPROVE-002: Incremental Scanning & Deployment

**Current Limitation** (V1):
```
- Always scans ALL mods (even if unchanged)
- Always redeploys ALL files (even if unchanged)
- 50,000 mods on 100GB installation = 30+ minutes every rebuild
- Users rebuild infrequently (only when adding/removing mods)
```

**V2 Solution**:

```python
class IncrementalDeploymentEngine:
    """Only deploy/scan changed mods."""
    
    def __init__(self, profile_dir, previous_manifest_path=None):
        self.profile_dir = profile_dir
        self.current_mods = self._get_current_mods()
        
        # Load previous state
        self.previous_manifest = self._load_manifest(previous_manifest_path) or {}
        self.previous_mods = set(self.previous_manifest.get("mods", []))
    
    def detect_changes(self) -> dict:
        """Detect which mods changed since last build."""
        current_mods = set(self.current_mods)
        
        return {
            "added_mods": current_mods - self.previous_mods,  # New mods to scan
            "removed_mods": self.previous_mods - current_mods,  # Mods to remove
            "unchanged_mods": current_mods & self.previous_mods,  # Keep from cache
            "modified_mods": self._detect_modified(current_mods & self.previous_mods)
        }
    
    def _detect_modified(self, mods: set) -> set:
        """Check which unchanged mods actually changed (by mtime)."""
        modified = set()
        
        for mod in mods:
            mod_dir = self.profile_dir / mod
            if not mod_dir.exists():
                modified.add(mod)
                continue
            
            # Get current mtime
            current_mtime = self._get_mtime(mod_dir)
            
            # Get previous mtime from manifest
            previous_mtime = self.previous_manifest.get(f"mods.{mod}.mtime", 0)
            
            if current_mtime != previous_mtime:
                modified.add(mod)
        
        return modified
    
    def build_manifest_incremental(self) -> dict:
        """Build new manifest by merging old + new changes."""
        changes = self.detect_changes()
        
        logger.info(f"Incremental build:")
        logger.info(f"  Added: {len(changes['added_mods'])}")
        logger.info(f"  Removed: {len(changes['removed_mods'])}")
        logger.info(f"  Modified: {len(changes['modified_mods'])}")
        logger.info(f"  Unchanged: {len(changes['unchanged_mods'])}")
        
        # Start with previous manifest (reuse unchanged)
        new_manifest = self.previous_manifest.copy()
        
        # Remove files from removed mods
        for removed_mod in changes["removed_mods"]:
            new_manifest["mapping"] = {
                k: v for k, v in new_manifest["mapping"].items()
                if v.get("mod_origin") != removed_mod
            }
        
        # Scan new/modified mods
        scanner = ScannerEngine(self.mods_dir, self.game_profile)
        for mod in changes["added_mods"] | changes["modified_mods"]:
            logger.info(f"Scanning: {mod}")
            scanner.scan_mod(mod)
        
        # Merge scanned files into manifest
        new_manifest["mapping"].update(scanner.get_manifest())
        
        # Update metadata
        new_manifest["timestamp"] = datetime.now().isoformat()
        new_manifest["incremental"] = {
            "added_mods": list(changes["added_mods"]),
            "removed_mods": list(changes["removed_mods"]),
            "modified_mods": list(changes["modified_mods"])
        }
        
        return new_manifest
    
    def deploy_incremental(self, manifest: dict, standalone_path: Path) -> dict:
        """Deploy only changed files."""
        changes = manifest.get("incremental", {})
        
        added_mods = set(changes.get("added_mods", []))
        removed_mods = set(changes.get("removed_mods", []))
        modified_mods = set(changes.get("modified_mods", []))
        
        # Files to deploy: from added/modified mods
        files_to_deploy = {
            k: v for k, v in manifest["mapping"].items()
            if v.get("mod_origin") in (added_mods | modified_mods)
        }
        
        # Files to remove: from removed mods (unless also in new mods)
        files_to_remove = {
            k: v for k, v in self.previous_manifest.get("mapping", {}).items()
            if v.get("mod_origin") in removed_mods
        }
        
        logger.info(f"Incremental deploy:")
        logger.info(f"  Deploy: {len(files_to_deploy)} files")
        logger.info(f"  Remove: {len(files_to_remove)} files")
        logger.info(f"  Skip: {len(manifest['mapping']) - len(files_to_deploy)} files")
        
        # Deploy new/modified files
        for target_rel_path, file_info in files_to_deploy.items():
            source = Path(file_info["source"])
            target = standalone_path / target_rel_path
            self._deploy_file(source, target)
        
        # Remove files from removed mods
        for target_rel_path in files_to_remove.keys():
            target = standalone_path / target_rel_path
            if target.exists():
                target.unlink()
        
        return {
            "deployed": len(files_to_deploy),
            "removed": len(files_to_remove),
            "skipped": len(manifest["mapping"]) - len(files_to_deploy)
        }
```

**Expected Outcome**:
- ✅ Adding 1 mod = scan 1 mod (not all 50)
- ✅ Removing 1 mod = delete that mod's files (not rescan all)
- ✅ 30-minute scan → 30-second incremental update
- ✅ 70% faster rebuilds for typical workflow
- ✅ Backward compatible (works if previous manifest missing)

**Performance Impact**:
```
V1: 50 mods @ 10 files/sec = 500 sec (8 min) scan
V2 (add 1 mod): 1 mod @ 10 files/sec = 10 sec scan (50x faster)

V1: 50,000 files @ 100 files/sec = 500 sec (8 min) deploy
V2 (add 100 files): 100 files @ 100 files/sec = 1 sec deploy (500x faster)
```

**Testing Strategy**:
- [ ] Baseline: 50 mods, 50,000 files
- [ ] Add 1 mod, rebuild (should scan only 1 mod)
- [ ] Add 10 mods, rebuild (should scan only 10)
- [ ] Remove mod, rebuild (should remove its files)
- [ ] Modify mod (change 1 file), rebuild (should rescan only that mod)
- [ ] Verify manifest completeness

**Effort**: 2-3 weeks | **Risk**: Medium (complex state tracking)

**Expected Gain**: 10-50x faster rebuilds (users rebuild more often)

---

### IMPROVE-003: Real-Time Sync Mode

**Current Limitation** (V1):
```
- All-or-nothing: Deploy entire standalone, or nothing
- Can't incrementally add mods to existing standalone
- Users want: "Add new mod to existing standalone without full rebuild"
```

**V2 Solution**:

```python
class RealtimeSyncEngine:
    """Sync changes to running/existing standalone without full rebuild."""
    
    def sync_to_existing_standalone(self, mod_name: str, standalone_path: Path):
        """
        Add or update single mod in existing standalone.
        Useful for testing mods without full rebuild.
        """
        logger.info(f"Syncing {mod_name} to {standalone_path}...")
        
        # Scan just this mod
        scanner = ScannerEngine(self.mods_dir, self.game_profile)
        scanner.scan_mod(mod_name)
        mod_files = scanner.get_manifest()
        
        # Deploy mod files
        for target_rel_path, file_info in mod_files.items():
            source = Path(file_info["source"])
            target = standalone_path / target_rel_path
            
            # Deploy with collision detection
            if target.exists():
                logger.warn(f"File exists (overwriting): {target_rel_path}")
            
            target.parent.mkdir(parents=True, exist_ok=True)
            self._deploy_file(source, target)
        
        logger.info(f"Synced {len(mod_files)} files from {mod_name}")
        
        # Update config files (plugins, loadorder, INI)
        self._update_standalone_configs()
        
        return len(mod_files)
    
    def watch_for_changes(self, standalone_path: Path, callback=None):
        """
        Monitor MO2 profile for changes, auto-sync to standalone.
        Useful for live testing while working on mods.
        """
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        
        class MO2ChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                
                # Check if it's a mod file
                rel_path = Path(event.src_path).relative_to(self.profile_dir)
                mod_name = rel_path.parts[0]
                
                logger.info(f"Change detected: {mod_name}/{rel_path}")
                
                # Sync this mod
                self.sync_to_existing_standalone(mod_name, standalone_path)
                
                if callback:
                    callback({"mod": mod_name, "file": str(rel_path)})
        
        observer = Observer()
        observer.schedule(MO2ChangeHandler(), self.mods_dir, recursive=True)
        observer.start()
        
        logger.info(f"Watching for changes in {self.mods_dir}...")
        return observer
```

**Use Case**: Developer testing
```
Developer workflow:
1. Create standalone once (full 100GB build)
2. Work on new mod (add files, edit configs)
3. Real-time sync syncs changes every 5 seconds
4. Test changes in game without 30-minute rebuild
5. When satisfied, full rebuild to verify everything
```

**Expected Outcome**:
- ✅ Instant feedback for mod development
- ✅ No need for full rebuilds during iteration
- ✅ Enables "live reloading" workflow
- ✅ 10x faster mod testing cycle

**Effort**: 1-2 weeks (optional feature)

**Expected Gain**: Developer experience (niche but enthusiastic users)

---

### IMPROVE-004: Advanced Reporting & Analytics

**Current State** (V1):
```
- Single HTML report per build
- Shows success/fail stats
- No historical data
- No comparison capability
```

**V2 Solution**:

```python
class AdvancedReportGenerator:
    """Generate detailed, historical reports with analytics."""
    
    def generate_full_report(self, deployment_data: dict, verification_data: dict):
        """Generate comprehensive multi-page report."""
        
        report = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "game": self.game_profile.name,
                "mod_count": deployment_data["mod_count"],
                "file_count": deployment_data["file_count"],
                "total_size_gb": deployment_data["total_size_gb"]
            },
            
            # Page 1: Executive Summary
            "summary": self._generate_summary(deployment_data),
            
            # Page 2: Deployment Details
            "deployment": {
                "total_files": len(deployment_data["files"]),
                "hardlinks_count": sum(1 for f in deployment_data["files"] if f["method"] == "hardlink"),
                "copies_count": sum(1 for f in deployment_data["files"] if f["method"] == "copy"),
                "space_saved_gb": self._calculate_space_saved(deployment_data),
                "failures": deployment_data["failed_files"],
                "timeline": deployment_data["timeline"]  # Duration breakdown
            },
            
            # Page 3: Verification Results
            "verification": verification_data,
            
            # Page 4: Mod Analysis
            "mods": self._analyze_mods(deployment_data),
            
            # Page 5: Recommendations
            "recommendations": self._generate_recommendations(deployment_data, verification_data),
            
            # Page 6: Historical Comparison
            "history": self._compare_with_previous_builds()
        }
        
        # Generate both JSON (for parsing) and HTML (for viewing)
        self._save_json_report(report)
        self._save_html_report(report)
        
        return report
    
    def _analyze_mods(self, deployment_data) -> dict:
        """Analyze per-mod statistics."""
        mods_stats = {}
        
        for file_info in deployment_data["files"]:
            mod = file_info["mod_origin"]
            if mod not in mods_stats:
                mods_stats[mod] = {
                    "file_count": 0,
                    "total_size_bytes": 0,
                    "hardlinks": 0,
                    "copies": 0
                }
            
            mods_stats[mod]["file_count"] += 1
            mods_stats[mod]["total_size_bytes"] += file_info.get("size_bytes", 0)
            if file_info["method"] == "hardlink":
                mods_stats[mod]["hardlinks"] += 1
            else:
                mods_stats[mod]["copies"] += 1
        
        return mods_stats
    
    def _compare_with_previous_builds(self) -> dict:
        """Compare current build with previous builds."""
        previous_reports = self._load_historical_reports(limit=10)
        
        return {
            "current_build": self._current_metrics(),
            "previous_builds": [self._extract_metrics(r) for r in previous_reports],
            "trends": {
                "file_count_trend": self._calculate_trend([r["file_count"] for r in previous_reports]),
                "size_trend": self._calculate_trend([r["total_size_gb"] for r in previous_reports]),
                "failure_rate_trend": self._calculate_trend([r["failure_rate"] for r in previous_reports])
            }
        }
    
    def _generate_recommendations(self, deployment_data, verification_data) -> List[str]:
        """Provide actionable recommendations based on results."""
        recommendations = []
        
        # Check hardlink efficiency
        hardlink_ratio = sum(1 for f in deployment_data["files"] if f["method"] == "hardlink") / len(deployment_data["files"])
        if hardlink_ratio < 0.9:
            recommendations.append(
                f"⚠️ Only {hardlink_ratio*100:.1f}% of files are hardlinked. "
                f"This may indicate cross-volume mods or filesystem limitations. "
                f"Consider organizing mods on same drive."
            )
        
        # Check for missing saves
        missing_saves = verification_data.get("save_issues", [])
        if missing_saves:
            recommendations.append(
                f"⚠️ {len(missing_saves)} save game issues detected. "
                f"Sync saves manually from Documents before playing."
            )
        
        # Check for config mismatches
        config_issues = verification_data.get("config_mismatch", [])
        if config_issues:
            recommendations.append(
                f"⚠️ {len(config_issues)} configuration mismatches. "
                f"Review INI settings before launching game."
            )
        
        # Performance recommendations
        if deployment_data["duration_seconds"] > 600:  # >10 minutes
            recommendations.append(
                f"💡 Deployment took {deployment_data['duration_seconds']/60:.1f} minutes. "
                f"Consider using incremental sync for future updates."
            )
        
        return recommendations
```

**Dashboard Example**:
```
Dashboard View (Web Interface):
┌─ Deployment History ────────────────────────┐
│ Build #5 (Today 3:45 PM)                    │
│   50,000 files | 150 GB | 48,500 hardlinks  │
│   ✓ All verified | 12 min duration          │
│                                              │
│ Build #4 (Yesterday 10:20 AM)                │
│   50,000 files | 150 GB | 48,200 hardlinks  │
│   ⚠️ 3 files failed | 14 min duration       │
│                                              │
│ Build #3 (2 days ago)                       │
│   49,500 files | 148 GB | 47,800 hardlinks  │
│   ✓ All verified | 13 min duration          │
│                                              │
│ Trend: File count ↑ 1% | Size ↑ 2%          │
│        Speed ↓ 8% (more files)               │
└──────────────────────────────────────────────┘
```

**Expected Outcome**:
- ✅ Users understand what's in their installation
- ✅ Historical comparison shows changes over time
- ✅ Actionable recommendations prevent issues
- ✅ Analytics for optimization decisions

**Effort**: 1-2 weeks (optional feature)

**Expected Gain**: User insights, troubleshooting aid

---

## Part 3: RESTRUCTURING & ARCHITECTURAL IMPROVEMENTS

### RESTRUCTURE-001: Model-View-Controller Pattern

**Current State** (V1):
```
plugin_ui.py (2,500 LOC)
  - UI layout
  - Event handlers
  - Business logic
  - Threading
  → Untestable, unmaintainable
```

**V2 Structure**:
```
Model Layer (No Qt dependency):
  config.py
    ├─ DeploymentConfig (user settings)
    ├─ GameProfile (game-specific data)
    └─ DeploymentMetrics (runtime statistics)
  
  state.py
    ├─ DeploymentState (current operation status)
    ├─ ManifestData (file mappings)
    └─ VerificationResults (post-deployment checks)
  
  orchestrator.py
    └─ DeploymentOrchestrator (coordinates engines)

View Layer (Qt only):
  ui/
    ├─ main_window.py
    │   └─ HardlinkBuilderMainWindow (top-level window)
    ├─ panels/
    │   ├─ setup_panel.py (game/path selection)
    │   ├─ config_panel.py (deployment options)
    │   ├─ progress_panel.py (real-time progress)
    │   └─ report_panel.py (results visualization)
    └─ widgets/
        ├─ path_selector.py
        ├─ progress_bar.py
        └─ log_viewer.py

Controller Layer (bridges Model ↔ View):
  controller.py
    ├─ DeploymentController (handles user actions)
    ├─ ConfigController (manages config)
    └─ ReportController (displays results)

Plugin Interface:
  __init__.py
    └─ HardlinkBuilderPlugin (mobase.IPluginTool interface)
```

**Benefits**:
- ✅ Test model logic without UI
- ✅ Reuse engines in CLI, API, web
- ✅ Each layer can be developed independently
- ✅ 2,500-line file becomes 300-line files
- ✅ Easy to add new UI (web, CLI)

**Effort**: 2-3 weeks | **Risk**: Medium

---

### RESTRUCTURE-002: Dependency Injection & Plugin System

**Current State** (V1):
```python
# Tight coupling
class ScannerEngine:
    def __init__(self, mods_dir):
        self.conflict_manager = ConflictManager()  # Hard-coded
```

**V2 Solution**:
```python
# Loose coupling via DI
class ScannerEngine:
    def __init__(self, mods_dir, conflict_manager=None):
        self.conflict_manager = conflict_manager or ConflictManager()

# Usage
injector = DIContainer()
injector.register(ConflictManager, singleton=True)
injector.register(ScannerEngine, dependencies=["ConflictManager"])

scanner = injector.get(ScannerEngine)  # Auto-wired
```

**Benefits**:
- ✅ Easy to mock for testing
- ✅ Can swap implementations (SQLite vs JSON)
- ✅ Plugin system for custom engines
- ✅ Future-proof architecture

**Effort**: 1 week

---

## Part 4: FEATURES TO KEEP (Proven Valuable)

### ✅ KEEP-001: Safety Validation Framework

**Why It Works** (V1):
- Pre-deployment checks prevent 90% of user errors
- Clear error messages guide users
- Protects against accidental data loss

**V2 Improvement**:
```python
class ValidationChain:
    """Extensible validation framework."""
    
    def add_validator(self, validator: Validator):
        """Add custom validator (plugins can extend)."""
        self.validators.append(validator)
    
    def validate_all(self) -> List[ValidationError]:
        """Run all validators, return comprehensive error list."""
        errors = []
        for validator in self.validators:
            try:
                result = validator.validate()
                if not result.success:
                    errors.extend(result.errors)
            except Exception as e:
                errors.append(ValidationError(f"Validator {validator.name} failed: {e}"))
        return errors
```

---

### ✅ KEEP-002: Metadata Persistence

**Why It Works** (V1):
- Manifest allows verification & comparison
- Conflict cache enables smart redeploys
- Snapshot enables rollback

**V2 Improvement**:
- Add schema versioning
- Migrate old formats automatically
- Compress for storage efficiency

---

### ✅ KEEP-003: Quarantine System for Conflicts

**Why It Works** (V1):
- Timestamped folders preserve conflicting saves
- User can choose overwrite or quarantine
- No data loss

**V2 Improvement**:
- GUI quarantine browser (show conflicts)
- One-click restore from quarantine
- Auto-cleanup old quarantines (>30 days)

---

### ✅ KEEP-004: Portable vs Shared Modes

**Why It Works** (V1):
- Portable = no system modifications (USB-friendly)
- Shared = uses real Documents/AppData (default behavior)
- Gives users choice

**V2 Improvement**:
- Add "Stealth" mode (live MO2 testing)
- Clear UI explanation of trade-offs
- Auto-detect optimal mode

---

## Part 5: RE-OPTIMIZATION TARGETS

### OPT-001: Parallel Deployment

**Current** (V1):
```python
# Sequential: 1 file at a time
for target_path, file_info in manifest.items():
    self._deploy_file(file_info["source"], target_path)
    # Takes 500 seconds for 50,000 files
```

**V2 Target**:
```python
# Parallel: 8 threads (configurable)
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = []
    for target_path, file_info in manifest.items():
        future = executor.submit(self._deploy_file, file_info["source"], target_path)
        futures.append(future)
    
    # Wait for all
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        # Takes 60 seconds for 50,000 files (8x faster)
```

**Expected Speedup**: 4-8x (8 parallel threads)
**Effort**: 1 week

---

### OPT-002: Caching & Memoization

**Current** (V1):
```python
# Recalculates same stats multiple times
for file in manifest:
    if file.extension in blacklist:
        # Checks same extension 1000x
```

**V2 Target**:
```python
# Cache common lookups
@functools.lru_cache(maxsize=128)
def is_blacklisted_extension(ext: str) -> bool:
    return ext in self.game_profile.blacklist_extensions

# Reduces repetitive checks by 99%
```

**Expected Speedup**: 10-20% (less relevant for I/O bound)
**Effort**: 3 days

---

### OPT-003: Memory-Efficient Manifest Loading

**Current** (V1):
```python
# Loads entire manifest into memory
manifest = json.load(f)  # 50MB for large projects
```

**V2 Target**:
```python
# Streaming JSON parser for large files
def load_manifest_streaming(path):
    """Load manifest in chunks, don't hold entire file."""
    with open(path) as f:
        for item in json.stream(f, "$.mapping.*"):
            yield item
```

**Expected Benefit**: 10x less memory (50MB → 5MB)
**Effort**: 1 week
**Impact**: Enables deployment on low-end machines

---

## Part 6: NEW FEATURES FOR V2

### NEW-001: CLI Mode (Headless)

**Why Needed**:
- Automation (scheduled builds)
- Scripting (batch processing)
- Server deployment (no GUI)

**Example Usage**:
```bash
$ hardlink-builder deploy \
  --game skyrim_se \
  --profile "My Profile" \
  --standalone "/path/to/standalone" \
  --config config.json

Output:
  Scanning mods...     [████████░░░░░░░░░░] 50%
  Deploying files...   [███████░░░░░░░░░░░░] 35%
  Verifying...         [██████░░░░░░░░░░░░░] 30%
  
  ✓ Complete: 50,000 files deployed in 5 minutes
```

**Effort**: 2 weeks

---

### NEW-002: REST API Mode

**Why Needed**:
- Web dashboard
- Remote deployment (managed service)
- Mobile app control

**Example API**:
```python
@app.post("/api/deployments")
def start_deployment(config: DeploymentConfig):
    """Start new deployment."""
    job_id = deployment_service.start(config)
    return {"job_id": job_id}

@app.get("/api/deployments/{job_id}")
def get_deployment_status(job_id: str):
    """Get deployment progress."""
    return deployment_service.status(job_id)

@app.get("/api/deployments/{job_id}/report")
def get_deployment_report(job_id: str):
    """Get final report."""
    return deployment_service.report(job_id)
```

**Effort**: 3-4 weeks (optional)

---

### NEW-003: Web Dashboard

**Why Needed**:
- View history across devices
- Monitor deployments in real-time
- Compare builds side-by-side

**Features**:
- Real-time progress (WebSocket)
- Build history with graphs
- Mod dependency visualization
- Config comparison view

**Effort**: 3-4 weeks (optional)

---

### NEW-004: Mod Conflict Analyzer

**Why Needed**:
- Help users understand file conflicts
- Suggest load order fixes
- Detect missing master files

**Output Example**:
```
Conflict Analysis:
  File: Data/meshes/armor.nif
  Provided by:
    1. Armor Overhaul (priority 100)
    2. Beautiful Armor (priority 90)
    3. Original Game (priority 0)
  
  Winner: Armor Overhaul (highest priority)
  
  ⚠️ Warning: Beautiful Armor is deprioritized
  Recommendation: Increase Beautiful Armor priority if you prefer its version
```

**Effort**: 2-3 weeks (optional)

---

## Part 7: EXPECTED OUTCOMES & METRICS

### Performance Improvements

| Metric | V1 | V2 | Improvement |
|--------|----|----|-------------|
| Full scan (50 mods) | 8 min | 30 sec | **16x** |
| Full deploy (50K files) | 8 min | 1 min | **8x** |
| Incremental update (1 mod) | 8 min | 30 sec | **16x** |
| Verify (50K files) | 3 min | 1 min | **3x** |
| **Total rebuild time** | **25 min** | **3 min** | **8x** |

---

### Reliability Improvements

| Issue | V1 | V2 |
|-------|----|----|
| Load order failures | ❌ Possible | ✅ Zero |
| Hardlink verification | ❌ Missing | ✅ Verified |
| Orphan cleanup safety | ❌ No confirmation | ✅ Preview + archive |
| Config mismatch detection | ❌ Skipped in stealth | ✅ Always verified |
| Recovery on crash | ❌ Impossible | ✅ Resumable |
| Data corruption risk | ⚠️ Medium | ✅ Very Low |

---

### Feature Completeness

| Feature | V1 | V2 |
|---------|----|----|
| Skyrim support | ✅ | ✅ |
| Fallout support | ❌ | ✅ |
| Starfield support | ❌ | ✅ |
| Incremental sync | ❌ | ✅ |
| Real-time watch | ❌ | ✅ |
| CLI mode | ❌ | ✅ |
| Web dashboard | ❌ | ✅ (opt) |
| Mod conflict analysis | ❌ | ✅ (opt) |
| Config backup/restore | ❌ | ✅ |
| Dry-run mode | ❌ | ✅ |

---

### User Impact

**Before V2**:
```
User Experience:
- Wait 25 minutes for rebuild
- Silent failures = game crashes
- Unclear what failed
- No recovery option
- Only Skyrim users
- Developer workflow: hours per iteration
```

**After V2**:
```
User Experience:
- Wait 3 minutes for rebuild (8x faster)
- Clear validation before launch
- Detailed reports explain issues
- Can rollback or resume
- Support all Bethesda games
- Developer workflow: seconds per iteration
```

---

### Success Metrics (Definition of "Done")

**Phase 1 (Critical Fixes)**:
- [ ] Zero load order detection failures (100 test builds)
- [ ] Hardlink verification passes 1000x across drives
- [ ] Orphan cleanup has zero unexpected deletions
- [ ] Config verification catches all mismatches
- [ ] Transaction system resumes from interruption

**Phase 2 (Refactoring)**:
- [ ] UI separates from logic (MVC pattern complete)
- [ ] 100% of engines work with game_profiles.json
- [ ] All logs routed through logging module
- [ ] Input validation catches 100% of invalid inputs

**Phase 3 (Features)**:
- [ ] Incremental builds 10x faster than full
- [ ] Multi-game support (3+ games tested)
- [ ] CLI mode works end-to-end
- [ ] Dry-run mode matches actual deployment

**Phase 4 (Production)**:
- [ ] 90%+ unit test coverage
- [ ] Zero critical bugs in 1000 user test builds
- [ ] All documented features working
- [ ] Performance benchmarks met

---

## Implementation Timeline

### Week 1-2: Critical Fixes (FIX-001 to FIX-005)
**Goal**: Stabilize core platform
- Load order detection → use MO2 API
- Hardlink verification → verify every link
- Orphan cleanup → user confirmation + archive
- Config verification → no more silent failures
- Transaction system → resumable deployments

**Deliverable**: Stable V2.0-beta with no data corruption risk

---

### Week 3-4: Refactoring (RESTRUCTURE-001, IMPROVE-001)
**Goal**: Prepare for expansion
- MVC architecture → separate UI from logic
- Game profiles → multi-game support
- Logging framework → structured logs
- Input validation → all user inputs checked

**Deliverable**: V2.0-beta with Skyrim + Fallout

---

### Week 5-6: Features (IMPROVE-002, IMPROVE-004, NEW-001)
**Goal**: User value
- Incremental scanning → 10x faster rebuilds
- Advanced reporting → dashboards & analytics
- CLI mode → automation ready

**Deliverable**: V2.0-rc with CLI + web reports

---

### Week 7+: Polish (Testing, Docs, Release)
**Goal**: Production-ready
- Comprehensive testing → 90%+ coverage
- Documentation → guides for each game
- Performance tuning → optimization pass
- Release → v2.0 stable

**Deliverable**: V2.0 stable with docs

---

## Budget & Resources

**Development**: 8-10 weeks (1 FTE)
**Testing**: 2-3 weeks (1 QA)
**Documentation**: 1-2 weeks (tech writer or owner)

**Total**: ~12 weeks → Q2-Q3 2026 delivery

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Parallel deployment race conditions | Medium | High | Extensive mutex testing |
| MO2 API changes | Low | Medium | Version compatibility layer |
| Large file performance | Low | Medium | Stream processing for large manifests |
| User adoption of new features | Low | Low | Documentation & tutorials |

---

## Conclusion

**V2 is a complete rewrite, not an upgrade.**

It transforms V1 from "functional but fragile" (6.5/10) into "enterprise-grade platform" (9/10).

### Key Wins:
1. **8x Performance** — Deploy in 3 minutes instead of 25
2. **Zero Silent Failures** — Verify everything before game launch
3. **Multi-Game** — Works with Skyrim, Fallout, Starfield, Oblivion
4. **Recovery** — Resume from crashes, rollback bad builds
5. **Automation** — CLI mode, REST API, web dashboard

### Primary Constraint:
Time to implement (~10 weeks) but V1 remains usable during development.

---

**End of Technical Focus Document**
