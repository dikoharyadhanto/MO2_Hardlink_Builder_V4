import os
import json
from pathlib import Path

class ModlistSnapshot:
    """Handles Reading, Saving, and Diffing modlist.txt"""
    def __init__(self, profile_path=None, custom_file_path=None):
        if custom_file_path:
             self.modlist_path = Path(custom_file_path)
             self.profile_path = self.modlist_path.parent
        elif profile_path:
            self.profile_path = Path(profile_path)
            self.modlist_path = self.profile_path / "modlist.txt"
        else:
            raise ValueError("Must provide either profile_path or custom_file_path")

    def get_active_mods(self):
        """Reads the current modlist and returns a list of ACTIVE mod names in Load Order."""
        if not self.modlist_path.exists():
            return []
        
        active_mods = []
        try:
            with open(self.modlist_path, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
            
            processed_lines = [line.strip() for line in lines if line.strip()]
            
            # MO2 modlist logic: Top is High Priority? Or Bottom is High Priority?
            # Standard MO2 UI: Priority 0 is at Top.
            # modlist.txt file: High Priority is usually at TOP (weirdly).
            # Wait, let's stick to the same logic as Updater:
            # "reversed(processed_lines)" implies we assume bottom-up if not reversed?
            # Actually, let's just use the exact same logic.
            
            for line in reversed(processed_lines):
                if line.startswith('+'):
                    active_mods.append(line[1:])
            
        except Exception as e:
            print(f"[Snapshot] Error reading modlist: {e}")
        
        return active_mods

    def save_snapshot(self, output_path):
        """Saves a raw copy of modlist.txt"""
        if self.modlist_path.exists():
            try:
                import shutil
                shutil.copy2(self.modlist_path, output_path)
            except Exception as e:
                print(f"[Snapshot] Failed to save snapshot: {e}")

    @staticmethod
    def diff(old_list, new_list):
        old_set = set(old_list)
        new_set = set(new_list)
        
        added = new_set - old_set
        removed = old_set - new_set
        unchanged = old_set & new_set
        
        old_common = [m for m in old_list if m in unchanged]
        new_common = [m for m in new_list if m in unchanged]
        
        reordered = (old_common != new_common)
        
        return {
            "added": list(added),
            "removed": list(removed),
            "reordered": reordered,
            "unchanged": list(unchanged),
            "new_order": new_list
        }


class ConflictManager:
    """
    Manages the `conflict_cache.json`.
    Maps: FilePath -> List of ModNames (that provide this file)
    """
    def __init__(self, metadata_path):
        self.cache_file = Path(metadata_path) / "conflict_cache.json"
        self.mapping = {}

    def load(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.mapping = json.load(f)
            except:
                self.mapping = {}
    
    def save(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.mapping, f, indent=2)
        except: pass

    def register_file(self, rel_path, mod_name):
        """Registers that `mod_name` provides `rel_path`."""
        key = rel_path.lower().replace("\\", "/")
        
        if key not in self.mapping:
            self.mapping[key] = []
        
        # Check if entry exists
        if mod_name not in self.mapping[key]:
            self.mapping[key].append(mod_name)

    def remove_mod(self, mod_name):
        empty_keys = []
        for key, mods in self.mapping.items():
            if mod_name in mods:
                mods.remove(mod_name)
                if not mods:
                    empty_keys.append(key)
        
        for k in empty_keys:
            del self.mapping[k]

    def get_winner_fast(self, rel_path, mod_indices):
        key = rel_path.lower().replace("\\", "/")
        providers = self.mapping.get(key, [])
        
        if not providers: return None
        
        best_mod = None
        best_prio = -1
        
        for mod in providers:
            prio = mod_indices.get(mod, -1)
            if prio > best_prio:
                best_prio = prio
                best_mod = mod
        
        return best_mod
