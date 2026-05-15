# MO2 Hardlink Builder V4
## The Ultimate MO2 Escape Hatch

**Run heavily modded games completely outside MO2 while preserving your load order exactly as MO2 defines it, saving disk space, and keeping your save files safe.**

*(Not for casual users. Built specifically for heavy modders, automation users, and stability freaks).*

---

## 1. Why This Exists (The Problem)
Mod Organizer 2’s Virtual File System (VFS) is a masterpiece of mod management, but it has physical limits. 

When your load order starts choking under the weight of a massive 2000+ modlist, when external tools (like DynDOLOD, xLODGen, or heavy ENBs) refuse to cooperate with VFS injection, or when you simply need raw stability more than convenience—you need a physical, standalone game folder.

However, copying a 200GB mod directory destroys your SSD space, and manually copying save files back and forth is a recipe for disaster.

**The Escape Hatch:** Turn unstable VFS environments into stable standalone builds, while resolving file conflicts exactly as defined by your MO2 priority.

---

## 2. What It Does (The Solution)
MO2 Hardlink Builder reads your active MO2 profile and generates a real, physical game folder using zero-space NTFS hardlinks.

- **No VFS Conflicts with External Tools:** Run the game or heavy external tools directly from the standalone folder without injection issues, VFS overhead, or virtual directory crashes.
- **No More 10-20 Minute Rebuilds:** Instead of re-scanning and copying thousands of files every time you tweak a mod, our incremental updates identify what actually changed and deploy in seconds.
- **Concrete Integrity Shields:** Rather than raw, unmonitored scripts, the engine uses automated preflight environment checks, crash-aware save syncing, and transactional deployment checkpoints to shield your progress from corruption.

---

## 3. How It Works & Defensive Safety (The Reality)
We know modding trauma is real: corrupted profiles, broken load orders, and losing a 200-hour playthrough. This tool is built defensively. We don't promise magic; we build specific safety mechanisms.

### What Happens When Things Go Wrong
- **Crash mid-build?** *No broken half-states.* If your PC loses power or crashes halfway through deployment, our transactional checkpoint system allows you to resume exactly where you left off, rather than forcing a frustrating full rebuild from scratch.
- **Save file conflict?** *No overwritten progress.* If the game wrapper detects a mismatched save file during sync back to MO2, it places the conflict in a secure quarantine folder instead of silently vaporizing your active playthrough.
- **Game crashed mid-session?** *No corrupt profile saves.* The wrapper detects a game crash instantly and aborts the sync process, preventing potentially corrupted memory states from being written back into your pristine MO2 profile.

---

## 4. Boundary of Responsibility
Before deploying, it is vital to understand what this tool does and does not do. 

- **What it DOES do:** It mirrors your MO2 setup exactly into a physical directory. This includes loose files, BSA/BA2 priority, script extender DLLs, and override behavior exactly as resolved by MO2 at runtime.
- **What it DOES NOT do:** It does NOT fix broken mods, resolve existing plugin conflicts, or validate load order correctness. If your game was already crashing inside MO2 due to a broken mod or a missing master file, it will still crash in the standalone folder.

---

## 5. The Real-World Workflow

### Step 1: Prepare
Ensure your chosen target folder is on the **SAME DRIVE** as your MO2 `mods` folder. Hardlinks are an NTFS feature and physically cannot cross partitions. 

### Step 2: Build
Launch the builder, select your profile, set the target folder, and click Build. 
*(Note: First builds and massive changes will take longer, especially on mechanical HDDs; incremental updates are where the speed gain is most noticeable, taking only a few seconds).*

### Step 3: Verify (How You Know It Worked)
Before launching the game, you can confirm deployment success:
- **The Lazy Confirmation:** If the game launches normally and your mods behave exactly as they did in MO2 after a brief gameplay check (e.g., loading a save and verifying a key mod or patch), the build is valid.
- **The Interactive Report:** Open the generated `report.html` in your standalone folder to see exactly what was linked, skipped, or quarantined.
- **Launch Files:** Ensure `HOW TO LAUNCH.txt` and `steam_appid.txt` are successfully written to your standalone root.

### Step 3.5: Verify Runtime (Wrapper Integrity)
Building the standalone folder is only half the battle. The generated game wrapper is responsible for ensuring the game actively respects your load order and safely syncs your data during gameplay. 

> [!TIP]
> **The Quick Rule:** If the wrapper launches the game, your load order is correct. If it refuses to launch, something is wrong—and that block is completely intentional.

#### What the Wrapper Does (At Runtime)
When you launch the game through the wrapper:
1. **Failsafe Load Order Guard:** It copies your `plugins.txt` and `loadorder.txt` *before* the game starts. **Crucially, if this injection fails (e.g., files are locked, corrupted, or missing), the wrapper will block the game from launching and pop up an explicit error window.** When this occurs, an explicit error window is shown, and a detailed `wrapper.log` file is written to your standalone folder for inspection. This prevents the game from silently running in a broken vanilla state.
2. **Save Syncing:** It pulls your latest MO2 profile saves into the game's native directory before launching, and syncs any new saves *back* to your MO2 profile directory after you exit normally.
3. **Crash Defenses:** If the game crashes mid-session, the wrapper detects the crash and intentionally skips the exit sync to prevent writing a corrupted memory state back into your pristine MO2 profile.

#### How to Confirm It’s Working (Self-Audit)
You don’t need to guess if the wrapper is active. Use these quick tests:
- **Load Order Verification:** Launch the game through the wrapper. Open your load order or mod configuration menu inside the game—your mod priorities and patches should exactly mirror your MO2 configuration.
- **Save Sync Confirmation:** Open the game $\rightarrow$ load your profile $\rightarrow$ make a quick save $\rightarrow$ exit the game normally. Open MO2—if the new save file is visible in your MO2 saves tab, the sync cycle is perfectly healthy.
- **AppData File Audit (Advanced):** After launching the game once, navigate to your `%LOCALAPPDATA%\<GameName>` directory. Check the timestamps on `plugins.txt` and `loadorder.txt`—they should match the exact minute you launched the game.

#### Failure Signals (Red Flags)
If you observe any of these symptoms, stop and investigate:
- New save files created during standalone play do not appear back in your MO2 profile.
- Mods behave differently or load order appears randomized/reverted to vanilla.
- No `wrapper.log` file is written to your standalone directory.
- **Fallback Active (Degraded Safety Mode):** If the C# wrapper compiler was blocked by your antivirus during the build, the tool gracefully falls back to a basic `.bat` launcher. Under fallback mode, **automatic save syncing is completely disabled**, and you must manage your saves manually. Do not rely on fallback mode for long-term play.

> [!IMPORTANT]
> **First-Time Habit:** For your first-time use, always perform a quick "save-and-exit" test (create a save, exit normally, verify in MO2) before committing to a long, uninterrupted play session.

---

### Step 4: Play
Launch the game using the generated wrapper executable in the standalone folder. The wrapper seamlessly manages your `plugins.txt`, INIs, and save files.

### Step 5: Update
Tweak your mods or adjust load order in MO2? Run the builder again. It will safely update the standalone directory in seconds.

---

## 6. What Could Go Wrong & When NOT to Use

### Real-World Failure Cases
- **Choosing the wrong drive:** The build will complete, but the tool will be forced to physically *copy* the files. You will lose hundreds of gigabytes of disk space. The UI will display a prominent warning if this occurs.
- **Antivirus Interference:** If your antivirus aggressively blocks the on-the-fly C# wrapper compilation, the tool gracefully falls back to a basic `.bat` launcher (meaning you will have to sync your saves manually).
- **Manual Deletions:** If you manually delete files inside the standalone folder to uninstall mods, you will break the tracking index. Always use the "Clean Standalone" button or let the incremental build handle removals automatically.
- **Paranoia About Load Order:** *"Is this actually identical to MO2?"* **Yes—and this is the core guarantee of the tool.** The tool resolves file overrides by parsing `modlist.txt` and using a dual-layer RAM manifest to guarantee that your physical priority mirrors your virtual load order on a 1:1 basis. This includes loose files, BSA priority, and override behavior exactly as resolved by MO2 at runtime.

### When NOT to Use This Tool:
- **If MO2 already works perfectly for you** without performance drops, memory limit crashes, or external tool conflicts, this tool adds unnecessary complexity to your workflow.
- **If you do not have enough space** on the same drive partition as your MO2 installation.
- **If you switch active profiles five times a day** (rebuilding physical links, even incrementally, introduces more management overhead than staying within the virtual environment).
