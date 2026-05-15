# Changelog - MO2 Hardlink Builder V4
## User Impact Evolution

V4 is completely rebuilt to eliminate the performance bottlenecks and reliability risks of V3. We focused on speed, defensive safety, and workflow integrity.

### ⚡ Speed Gain: The End of "Stat Storms"
**Before:** Incremental updates were painfully slow. V3 had to scan every single file on your hard drive just to see if you updated one mod.
**Now:** Updates happen in seconds.
* **How:** The engine now tracks your mods in RAM and uses "Tri-Gate Change Detection". If a mod didn't change, the tool completely ignores it. No more disk thrashing.

### 🛡️ Risk Reduction: Active Defensive Guards
**Before:** A crash during a build or a save sync conflict could corrupt your setup or overwrite your progress without warning.
**Now:** The system assumes things will go wrong and protects you.
* **Mid-Build Resumes:** If your PC crashes or you close the tool mid-build, the "Transactional Deployment" system lets you resume exactly where you left off.
* **Save File Quarantine:** If the wrapper detects a conflict while syncing your save games back to MO2, it moves the conflicting file to a `quarantine` folder instead of silently overwriting your hard-earned progress.
* **Crash Detection:** If your game crashes, the wrapper knows. It will intentionally halt the save sync to protect your MO2 saves from corruption.

### 🛠️ Workflow Improvement: Smarter, Not Harder
**Before:** You had to guess if your files were actually hardlinked or copied, and compiling the wrapper sometimes failed silently.
**Now:** The tool actively guides and protects your workflow.
* **Cross-Drive Warnings:** The UI actively warns you if you accidentally select a target folder on the wrong drive, preventing massive accidental disk space usage.
* **Preflight Checks:** Before the build even starts, the system checks for active file locks, Windows Defender blocks, and OneDrive sync conflicts.
* **Atomic AppData Injection:** The wrapper now injects `plugins.txt` and `loadorder.txt` instantly and atomically. If the game crashes exactly as it launches, your load order won't be corrupted.
* **Cleaner Reporting:** The HTML report now explicitly separates skipped/unchanged files from actual failures, so you know exactly what happened.
