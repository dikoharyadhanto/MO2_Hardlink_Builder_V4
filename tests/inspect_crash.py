import os
import subprocess
import time
from pathlib import Path

def main():
    loader_path = r"F:\Skyrim_Standalone\skse64_loader.exe"
    cwd = r"F:\Skyrim_Standalone"
    
    print(f"Launching {loader_path} in {cwd}...")
    proc = subprocess.Popen([loader_path], cwd=cwd)
    
    print("Waiting 5 seconds for game to launch...")
    time.sleep(5)
    
    appdata_dir = Path(os.environ["LOCALAPPDATA"]) / "Skyrim Special Edition"
    docs_dir = Path(os.environ["USERPROFILE"]) / "Documents" / "My Games" / "Skyrim Special Edition"
    
    print("\n--- APPDATA CONTENTS ---")
    if appdata_dir.exists():
        for p in appdata_dir.iterdir():
            print(f"{p.name} - {p.stat().st_size} bytes")
    else:
        print("Directory does not exist!")
        
    print("\n--- DOCUMENTS CONTENTS ---")
    if docs_dir.exists():
        for p in docs_dir.iterdir():
            print(f"{p.name} - {p.stat().st_size} bytes")
    else:
        print("Directory does not exist!")
        
    print("\nKilling process to clean up...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        
    print("Inspection complete.")

if __name__ == "__main__":
    main()
