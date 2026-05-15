import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

# Resolve source root dynamically from this file's location (TASK-A05)
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src" / "MO2_Hardlink_Builder_V4b"))
workspace = _REPO_ROOT

from model.engines.feature_generator import wrap_loaders

def run_tests():
    test_dir = Path(os.environ.get("TEMP", workspace)) / "mo2_wrapper_test"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True)

    mo2_profile = test_dir / "mo2_profile"
    mo2_profile.mkdir()
    sa_path = test_dir / "standalone"
    sa_path.mkdir()

    # Create dummy plugins.txt in mo2 profile
    with open(mo2_profile / "plugins.txt", "w") as f:
        f.write("*MyMod.esp\n")

    # Create dummy MO2 ini
    with open(mo2_profile / "Skyrim.ini", "w") as f:
        f.write("[General]\nTest=1\n")

    appdata_name = "Antigravity_Test_Game"
    docs_name = "Antigravity_Test_Docs"
    game_exe = "test_game.exe"

    # Create dummy game exe
    cmd_path = Path(r"C:\Windows\System32\cmd.exe")
    target_exe = sa_path / game_exe
    shutil.copy(cmd_path, target_exe)

    print("--- COMPILING WRAPPER ---")
    result = wrap_loaders(
        str(sa_path),
        [game_exe],
        game_exe=game_exe,
        is_stealth=True,
        mo2_profile_path=str(mo2_profile),
        docs_name=docs_name,
        appdata_name=appdata_name,
        ini_prefix="Skyrim"
    )
    print("Wrap Result:", result)

    wrapper_exe = sa_path / game_exe
    if not wrapper_exe.exists():
        print("Wrapper exe was not created!")
        return

    real_appdata = Path(os.environ["LOCALAPPDATA"]) / appdata_name
    real_appdata.mkdir(exist_ok=True)
    real_plugins = real_appdata / "plugins.txt"

    # Set baseline (real appdata)
    with open(real_plugins, "w") as f:
        f.write("*Skyrim.esm\n")

    print("\n--- STR-WRAP-01: AppData Physical Injection ---")
    proc = subprocess.Popen([str(wrapper_exe), "/c", "timeout", "3"])
    time.sleep(1.5) # Wait for wrapper to backup and copy
    
    injected_content = ""
    if real_plugins.exists():
        with open(real_plugins, "r") as f:
            injected_content = f.read().strip()
    print("While running plugins.txt:", injected_content)
    if injected_content == "*MyMod.esp":
        print("PASS STR-WRAP-01")
    else:
        print("FAIL STR-WRAP-01")

    print("\n--- STR-WRAP-02: AppData Post-Launch Restoration ---")
    proc.wait() # Wait for game to exit and wrapper to restore
    
    restored_content = ""
    if real_plugins.exists():
        with open(real_plugins, "r") as f:
            restored_content = f.read().strip()
    print("After exit plugins.txt:", restored_content)
    if restored_content == "*Skyrim.esm":
        print("PASS STR-WRAP-02")
    else:
        print("FAIL STR-WRAP-02")
        
    print("\n--- STR-WRAP-03: Crash Recovery ---")
    # Set baseline again
    with open(real_plugins, "w") as f:
        f.write("*Skyrim.esm\n")
        
    # Start wrapper, it will inject, then we force kill the wrapper
    proc = subprocess.Popen([str(wrapper_exe), "/c", "timeout", "10"])
    time.sleep(1.5)
    
    # Kill the wrapper process (skipping its finally block)
    proc.kill()
    proc.wait()
    
    killed_content = ""
    if real_plugins.exists():
        with open(real_plugins, "r") as f:
            killed_content = f.read().strip()
    print("After force-kill plugins.txt:", killed_content)
    if killed_content == "*MyMod.esp":
        print("Kill successful. Injected state persists.")
    else:
        print("Failed to simulate kill or injection failed.")
        
    # Run wrapper again to trigger RecoverIfNeeded
    # The new instance will first recover, then inject again.
    # To observe the recovery, we just run it with a very short timeout
    proc2 = subprocess.Popen([str(wrapper_exe), "/c", "timeout", "2"])
    # Wait for the recovery and the new injection
    time.sleep(1.5)
    
    re_injected_content = ""
    if real_plugins.exists():
        with open(real_plugins, "r") as f:
            re_injected_content = f.read().strip()
            
    proc2.wait()
    
    # After proc2 finishes, it should restore the ORIGINAL baseline (*Skyrim.esm)
    final_content = ""
    if real_plugins.exists():
        with open(real_plugins, "r") as f:
            final_content = f.read().strip()
            
    print("After recovery and second run finishes plugins.txt:", final_content)
    if final_content == "*Skyrim.esm":
        print("PASS STR-WRAP-03")
    else:
        print("FAIL STR-WRAP-03")
        
    print("\nCleaning up real appdata...")
    shutil.rmtree(real_appdata)
    
if __name__ == "__main__":
    run_tests()
