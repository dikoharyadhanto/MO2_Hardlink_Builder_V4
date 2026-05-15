import sys
import os
from pathlib import Path
import time
import shutil
import json

# Resolve source root dynamically from this file's location (TASK-A05)
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))

from model.engines.scanner_engine import ScannerEngine
from model.engines.linker_executor import LinkerExecutor
from model.state import ManifestDeltaAnalyzer

class MockModList:
    def __init__(self, mods):
        self.mods = mods
    def allModsByProfilePriority(self, profile):
        return self.mods
    def state(self, name):
        return 0x02

class MockOrganizer:
    def __init__(self, mods):
        self.mod_list = MockModList(mods)
    def modList(self):
        return self.mod_list
    def profile(self):
        return "DummyProfile"

def setup_env():
    base = Path(os.environ.get("TEMP", _REPO_ROOT)) / "mo2_sim_incremental_env"
    if base.exists():
        shutil.rmtree(base)
    
    sa_path = base / "Standalone"
    game_path = base / "Game"
    mo2_path = base / "MO2"
    mods_path = mo2_path / "mods"
    profile_path = mo2_path / "profiles" / "DummyProfile"
    overwrite_path = mo2_path / "overwrite"
    metadata_dir = sa_path / "standalone_metadata"
    
    for p in [sa_path, game_path, mods_path, profile_path, overwrite_path, metadata_dir]:
        p.mkdir(parents=True, exist_ok=True)
        
    # Create Game files
    (game_path / "SkyrimSE.exe").write_text("dummy exe")
    
    # Create ModA
    (mods_path / "ModA" / "Data").mkdir(parents=True, exist_ok=True)
    (mods_path / "ModA" / "Data" / "file1.txt").write_text("ModA file1")
    (mods_path / "ModA" / "Data" / "file2.txt").write_text("ModA file2")
    
    # Create ModB
    (mods_path / "ModB" / "Data").mkdir(parents=True, exist_ok=True)
    (mods_path / "ModB" / "Data" / "file1.txt").write_text("ModB file1 wins") # Conflict
    (mods_path / "ModB" / "Data" / "file4.txt").write_text("ModB file4")
    
    # Dummy modlist
    (profile_path / "modlist.txt").write_text("+ModB\n+ModA\n")
    
    return {
        "base": base,
        "sa_path": sa_path,
        "game_path": game_path,
        "mods_path": mods_path,
        "profile_path": profile_path,
        "overwrite_path": overwrite_path,
        "metadata_dir": metadata_dir
    }

def print_step(msg):
    print(f"\n{'='*50}\n[*] {msg}\n{'='*50}")

def rotate_manifest(metadata_dir):
    curr = metadata_dir / "mapping_manifest.json"
    prev = metadata_dir / "mapping_manifest_prev.json"
    if curr.exists():
        shutil.move(str(curr), str(prev))

def main():
    env = setup_env()
    organizer = MockOrganizer(["ModA", "ModB"]) # ModB wins file1.txt
    
    # ==========================================
    # STR-INC-01: Baseline Full Build (Control)
    # ==========================================
    print_step("STR-INC-01: Baseline Full Build (Control)")
    
    scanner = ScannerEngine(env["mods_path"], env["overwrite_path"], env["profile_path"], output_dir=env["metadata_dir"])
    scanner.build_mapping(organizer=organizer)
    
    delta_analyzer = ManifestDeltaAnalyzer(
        str(env["metadata_dir"] / "mapping_manifest.json"),
        None,
        delta_threshold=0.7
    )
    delta = delta_analyzer.analyze()
    print(f"Delta: {delta}")
    
    linker = LinkerExecutor(env["sa_path"], env["game_path"], output_dir=env["metadata_dir"])
    
    t0 = time.time()
    linker.execute_mapping(clean=True)
    t1 = time.time()
    
    print(f"Full Build Time: {t1 - t0:.4f}s")
    assert (env["sa_path"] / "Data" / "file1.txt").read_text() == "ModB file1 wins"
    print("STR-INC-01 PASS")
    
    # ==========================================
    # STR-INC-02: Zero-Delta Incremental Build
    # ==========================================
    print_step("STR-INC-02: Zero-Delta Incremental Build")
    rotate_manifest(env["metadata_dir"])
    
    scanner.build_mapping(organizer=organizer)
    
    delta_analyzer = ManifestDeltaAnalyzer(
        str(env["metadata_dir"] / "mapping_manifest.json"),
        str(env["metadata_dir"] / "mapping_manifest_prev.json"),
        delta_threshold=0.7
    )
    delta = delta_analyzer.analyze()
    print(f"Delta: {delta}")
    assert delta["full_rebuild_required"] == False
    
    t0 = time.time()
    linker.execute_mapping(clean=False)
    t1 = time.time()
    
    print(f"Incremental Build Time: {t1 - t0:.4f}s")
    print("STR-INC-02 PASS")
    
    # ==========================================
    # STR-INC-03: Condition 1 & 2 — Add and Remove Files
    # ==========================================
    print_step("STR-INC-03: Condition 1 & 2 — Add and Remove Files")
    # Remove file2
    (env["mods_path"] / "ModA" / "Data" / "file2.txt").unlink()
    # Add file3
    (env["mods_path"] / "ModA" / "Data" / "file3.txt").write_text("ModA file3 added")
    
    rotate_manifest(env["metadata_dir"])
    scanner.build_mapping(organizer=organizer)
    
    delta_analyzer = ManifestDeltaAnalyzer(
        str(env["metadata_dir"] / "mapping_manifest.json"),
        str(env["metadata_dir"] / "mapping_manifest_prev.json"),
        delta_threshold=0.7
    )
    delta = delta_analyzer.analyze()
    print(f"Delta: {delta}")
    assert delta["added"] == 1
    assert delta["removed"] == 1
    
    linker.clean_orphaned_files(removed_keys=delta["removed_keys"])
    linker.execute_mapping(clean=False)
    
    assert not (env["sa_path"] / "Data" / "file2.txt").exists()
    assert (env["sa_path"] / "Data" / "file3.txt").exists()
    print("STR-INC-03 PASS")
    
    # ==========================================
    # STR-INC-04: Condition 3 — Modify / Priority Change
    # ==========================================
    print_step("STR-INC-04: Condition 3 — Modify / Priority Change")
    
    # ModA now wins over ModB
    organizer = MockOrganizer(["ModB", "ModA"])
    
    # User manually modifies file4 (change inode)
    file4 = env["mods_path"] / "ModB" / "Data" / "file4.txt"
    file4.unlink()
    file4.write_text("ModB file4 MODIFIED CONTENT")
    
    rotate_manifest(env["metadata_dir"])
    scanner.build_mapping(organizer=organizer)
    
    delta_analyzer = ManifestDeltaAnalyzer(
        str(env["metadata_dir"] / "mapping_manifest.json"),
        str(env["metadata_dir"] / "mapping_manifest_prev.json"),
        delta_threshold=0.7
    )
    delta = delta_analyzer.analyze()
    print(f"Delta: {delta}")
    
    linker.execute_mapping(clean=False)
    
    # Verify file1.txt now comes from ModA
    assert (env["sa_path"] / "Data" / "file1.txt").read_text() == "ModA file1"
    # Verify file4.txt content updated
    assert (env["sa_path"] / "Data" / "file4.txt").read_text() == "ModB file4 MODIFIED CONTENT"
    
    print("STR-INC-04 PASS")
    
if __name__ == "__main__":
    main()
