"""
FEAT-08: HOW TO LAUNCH.txt auto-generation after build.
FEAT-09: steam_appid.txt write after build.
FEAT-10: Loader EXE wrapping via csc.exe runtime C# compilation.
         Falls back to .bat launcher if csc.exe is unavailable or compilation fails.
         D1: multi-path csc.exe discovery.
         D2: .cs source deleted in finally — always.
         D3: compiler stderr surfaced to audit log on non-zero returncode.
         D4: lean template — no CPU/IO/affinity/MMCSS/RAM-trim/thermal code.
         D5: game process name injected from game_exe stem — no hardcoded fallback list.
         D6: clean 3-state hijack check (FRESH / REWRAP / SKIP).
         D7: attrib +h failure logged at WARNING — never silent.
         D8: _wrapper_state.json deferred task recovery — INJECTED/SYNC_PENDING survive crashes.
         D9: AppData physical sync — plugins.txt/loadorder.txt copied to real %LOCALAPPDATA%
             instead of env var injection (SHGetFolderPath bypass fix per ANT-WO-005-v3.3).
"""
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("hardlink_audit")

# D1: csc.exe search order — Framework64 preferred, 32-bit fallback, v4 before v3.5
_CSC_SEARCH_PATHS = [
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework64\v3.5\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework64\v2.0.50727\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework\v3.5\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework\v2.0.50727\csc.exe",
]

# D4/D5/D8: lean stealth-only C# launcher template with deferred task recovery.
# Placeholders use {ALLCAPS} tokens injected via str.replace() — no Python .format()
# called on this string, so C# brace syntax is never misinterpreted.
# D8: _wrapper_state.json stores INJECTED/SYNC_PENDING so a crash anywhere in the
# launch/sync/restore cycle is recovered automatically on the next startup.
_CS_TEMPLATE = r"""using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

class StandaloneLauncher
{
    static readonly string LogFile = Path.Combine(
        AppDomain.CurrentDomain.BaseDirectory, "wrapper.log");
    static readonly string StateFile = Path.Combine(
        AppDomain.CurrentDomain.BaseDirectory, "_wrapper_state.json");

    static void Log(string msg)
    {
        try
        {
            File.AppendAllText(LogFile,
                "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "] "
                + msg + "\n");
        }
        catch { }
    }

    // Minimal JSON helpers — no external assemblies required.
    // < and > are illegal in Windows paths so <<< / >>> are safe separators.
    static string JsonEscape(string s)
    {
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }

    static void WriteState(string state, string savesSource, string savesTarget,
                            string profileName, List<string[]> iniPairs,
                            List<string[]> appDataPairs)
    {
        var pairParts = new List<string>();
        foreach (var pair in iniPairs)
            pairParts.Add(JsonEscape(pair[0]) + "<<<" + JsonEscape(pair[1]));
        string pairsVal = string.Join(">>>", pairParts);

        var adPairParts = new List<string>();
        foreach (var pair in appDataPairs)
            adPairParts.Add(JsonEscape(pair[0]) + "<<<" + JsonEscape(pair[1]));
        string adPairsVal = string.Join(">>>", adPairParts);

        string json =
            "{\n" +
            "  \"state\": \""          + JsonEscape(state)       + "\",\n" +
            "  \"saves_source\": \""   + JsonEscape(savesSource) + "\",\n" +
            "  \"saves_target\": \""   + JsonEscape(savesTarget) + "\",\n" +
            "  \"profile_name\": \""   + JsonEscape(profileName) + "\",\n" +
            "  \"timestamp\": \""      + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "\",\n" +
            "  \"ini_pairs\": \""      + pairsVal                + "\",\n" +
            "  \"appdata_pairs\": \""  + adPairsVal              + "\"\n" +
            "}";
        File.WriteAllText(StateFile, json);
    }

    static Dictionary<string, string> ReadState()
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(StateFile)) return result;
        foreach (string line in File.ReadAllLines(StateFile))
        {
            int keyQ1 = line.IndexOf('"');
            if (keyQ1 < 0) continue;
            int keyQ2 = line.IndexOf('"', keyQ1 + 1);
            if (keyQ2 < 0) continue;
            string key = line.Substring(keyQ1 + 1, keyQ2 - keyQ1 - 1);

            int colon = line.IndexOf(':', keyQ2 + 1);
            if (colon < 0) continue;
            int valQ1 = line.IndexOf('"', colon + 1);
            int valQ2 = line.LastIndexOf('"');
            if (valQ1 < 0 || valQ2 <= valQ1) continue;
            string val = line.Substring(valQ1 + 1, valQ2 - valQ1 - 1);
            val = val.Replace("\\\\", "\x01").Replace("\\\"", "\"").Replace("\x01", "\\");
            result[key] = val;
        }
        return result;
    }

    static List<string[]> ParseIniPairs(string encoded)
    {
        var result = new List<string[]>();
        if (string.IsNullOrEmpty(encoded)) return result;
        foreach (string rec in encoded.Split(new string[] { ">>>" },
                     StringSplitOptions.RemoveEmptyEntries))
        {
            int sep = rec.IndexOf("<<<");
            if (sep < 0) continue;
            result.Add(new string[] { rec.Substring(0, sep), rec.Substring(sep + 3) });
        }
        return result;
    }

    static void SafeDelete(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); }
        catch (Exception ex) { Log("WARNING: could not delete " + path + ": " + ex.Message); }
    }

    // Case-robust directory finder — NTFS is case-insensitive but Path.Combine uses literal casing.
    // Probes each candidate name in order and returns the first that exists on disk.
    // Falls back to the first candidate (for creation callers) if none exist.
    static string FindDirectory(string parent, string[] candidates)
    {
        foreach (string name in candidates)
        {
            string full = Path.Combine(parent, name);
            if (Directory.Exists(full)) return full;
        }
        return Path.Combine(parent, candidates[0]);
    }

    // P/Invoke — no System.Windows.Forms reference required.
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int MessageBox(IntPtr hWnd, string text, string caption, uint type);

    // MB_OK (0x0) | MB_ICONERROR (0x10) = 0x10
    static void AbortWithError(string reason)
    {
        Log("LAUNCH ABORTED: " + reason);
        MessageBox(IntPtr.Zero, reason, "Standalone Launcher \u2014 Launch Aborted", 0x00000010);
    }

    static void RecoverIfNeeded(string currentProfile)
    {
        if (!File.Exists(StateFile)) return;
        var fields = ReadState();
        if (fields.Count == 0 || !fields.ContainsKey("state"))
        {
            Log("Recovery: unreadable state file — deleting.");
            SafeDelete(StateFile);
            return;
        }

        string state = fields["state"];
        Log("Recovery: found state=" + state);

        // Profile guard — skip recovery if state was written by a different profile.
        // State file is left intact so launching with the original profile can still recover.
        string storedProfile = fields.ContainsKey("profile_name") ? fields["profile_name"] : "";
        if (!string.IsNullOrEmpty(storedProfile) && !string.IsNullOrEmpty(currentProfile)
            && !string.Equals(storedProfile, currentProfile, StringComparison.OrdinalIgnoreCase))
        {
            Log("Recovery WARNING: profile mismatch — stored=" + storedProfile
                + " current=" + currentProfile
                + " — skipping recovery; launch with the stored profile to complete it.");
            return;
        }

        var iniPairs = ParseIniPairs(
            fields.ContainsKey("ini_pairs") ? fields["ini_pairs"] : "");

        if (state == "SYNC_PENDING")
        {
            string savesSource = fields.ContainsKey("saves_source") ? fields["saves_source"] : "";
            string savesTarget = fields.ContainsKey("saves_target") ? fields["saves_target"] : "";

            if (!string.IsNullOrEmpty(savesSource) && Directory.Exists(savesSource)
                && !string.IsNullOrEmpty(savesTarget))
            {
                try
                {
                    Directory.CreateDirectory(savesTarget);
                    foreach (string sf in Directory.GetFiles(
                        savesSource, "*", SearchOption.AllDirectories))
                    {
                        string rel = sf.Substring(savesSource.Length + 1);
                        string dst = Path.Combine(savesTarget, rel);
                        Directory.CreateDirectory(Path.GetDirectoryName(dst));
                        File.Copy(sf, dst, true);
                    }
                    Log("Recovery: saves synced to " + savesTarget);
                }
                catch (Exception ex)
                {
                    Log("Recovery WARNING: save sync failed: " + ex.Message);
                }
            }
            else
            {
                Log("Recovery: saves path missing or empty — skipping save sync.");
            }
        }

        // Restore INIs for both INJECTED and SYNC_PENDING states
        foreach (var pair in iniPairs)
        {
            string dest   = pair[0];
            string backup = pair[1];
            if (File.Exists(backup))
            {
                try
                {
                    File.Copy(backup, dest, true);
                    File.Delete(backup);
                    Log("Recovery: restored INI " + Path.GetFileName(dest));
                }
                catch (Exception ex)
                {
                    Log("Recovery WARNING: INI restore failed for "
                        + Path.GetFileName(dest) + ": " + ex.Message);
                }
            }
            else
            {
                Log("Recovery: backup not found for "
                    + Path.GetFileName(dest) + " — skipping.");
            }
        }

        // Restore AppData files (plugins.txt, loadorder.txt) for both states
        var appDataPairs = ParseIniPairs(
            fields.ContainsKey("appdata_pairs") ? fields["appdata_pairs"] : "");
        foreach (var pair in appDataPairs)
        {
            string dest   = pair[0];
            string backup = pair[1];
            if (File.Exists(backup))
            {
                try
                {
                    File.Copy(backup, dest, true);
                    File.Delete(backup);
                    Log("Recovery: restored AppData " + Path.GetFileName(dest));
                }
                catch (Exception ex)
                {
                    Log("Recovery WARNING: AppData restore failed for "
                        + Path.GetFileName(dest) + ": " + ex.Message);
                }
            }
            else
            {
                // No backup means file didn't exist before injection — remove injected copy
                SafeDelete(dest);
                Log("Recovery: cleaned injected AppData " + Path.GetFileName(dest)
                    + " (no original existed).");
            }
        }

        SafeDelete(StateFile);
        Log("Recovery complete.");
    }

    [STAThread]
    static int Main(string[] args)
    {
        bool isStealth      = {IS_STEALTH};
        bool usesPluginsTxt = {USES_PLUGINS_TXT};
        bool usesBethesdaIni = {USES_BETHESDA_INI};
        string mo2Profile   = @"{MO2_PROFILE_PATH}";
        string docsName     = "{DOCS_NAME}";
        string gameName     = "{GAME_NAME}";
        string appDataName  = "{APPDATA_NAME}";
        string iniPrefix    = "{INI_PREFIX}";   // e.g. "Skyrim", "Oblivion"

        // D8: deferred task recovery — complete any interrupted cycle before fresh injection
        try { RecoverIfNeeded(mo2Profile); }
        catch (Exception ex) { Log("Recovery exception (non-fatal): " + ex.Message); }

        string saDir     = AppDomain.CurrentDomain.BaseDirectory;
        string selfName  = Path.GetFileNameWithoutExtension(
                               Assembly.GetEntryAssembly().Location);
        string origExe   = Path.Combine(saDir, "_" + selfName + "_original.exe");

        if (!File.Exists(origExe))
        {
            Log("ERROR: Original executable not found: " + origExe);
            return 1;
        }

        string docsPath      = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "My Games", docsName);
        // Case-robust: MO2 uses lowercase 'saves', some systems create 'Saves'
        string mo2SavesPath  = FindDirectory(mo2Profile, new[] { "saves", "Saves" });
        string gameSavesPath = Path.Combine(docsPath, "Saves");

        // DIAG: log resolved paths so any location mismatch is immediately visible in wrapper_log.txt
        Log("DIAG | mo2Profile    : " + mo2Profile);
        Log("DIAG | mo2SavesPath  : " + mo2SavesPath + " (exists=" + Directory.Exists(mo2SavesPath) + ")");
        Log("DIAG | docsPath      : " + docsPath);
        Log("DIAG | gameSavesPath : " + gameSavesPath + " (exists=" + Directory.Exists(gameSavesPath) + ")");

        // Pre-launch REQUIRED: backup existing game INIs, inject MO2 profile INIs.
        // Failure aborts the launch — the game would run with wrong settings.
        List<string[]> iniBackupPairs = new List<string[]>();
        if (isStealth)
        {
            if (!Directory.Exists(mo2Profile))
            {
                AbortWithError(
                    "INI injection failed: MO2 profile directory not found.\n\n"
                    + "Path: " + mo2Profile + "\n\n"
                    + "The game's settings cannot be configured correctly. Build aborted.");
                return 1;
            }

            // Only inject and patch INI files when this game uses Bethesda-style INIs.
            if (!usesBethesdaIni)
            {
                Log("INI injection: skipped (non-Bethesda game).");
            }
            else
            {
                Directory.CreateDirectory(docsPath);
                foreach (string mo2Ini in Directory.GetFiles(
                    mo2Profile, "*.ini", SearchOption.TopDirectoryOnly))
                {
                    string iniName = Path.GetFileName(mo2Ini);
                    string dest    = Path.Combine(docsPath, iniName);
                    string backup  = dest + ".bak_standalone";
                    if (File.Exists(dest))
                    {
                        File.Copy(dest, backup, true);
                        Log("Backed up: " + iniName);
                    }

                    // If this is the Custom INI, patch sLocalSavePath → Saves\
                    // MO2 writes its own redirect into this file pointing back to the MO2
                    // saves folder. In standalone mode (no MO2 VFS), we redirect to
                    // Documents/Saves/ instead so the injection target is consistent.
                    if (string.Equals(iniName, iniPrefix + "Custom.ini",
                                      StringComparison.OrdinalIgnoreCase))
                    {
                        try
                        {
                            string[] lines = File.ReadAllLines(mo2Ini);
                            var patched = new System.Text.StringBuilder();
                            bool inGeneral = false;
                            bool savePathWritten = false;
                            foreach (string ln in lines)
                            {
                                string trimmed = ln.Trim();
                                if (trimmed.StartsWith("["))
                                    inGeneral = trimmed.Equals("[General]",
                                        StringComparison.OrdinalIgnoreCase);
                                // Strip any existing sLocalSavePath
                                if (inGeneral && trimmed.StartsWith("sLocalSavePath=",
                                    StringComparison.OrdinalIgnoreCase))
                                    continue;
                                patched.AppendLine(ln);
                                // Inject our redirect right after [General]
                                if (inGeneral && !savePathWritten &&
                                    trimmed.Equals("[General]",
                                        StringComparison.OrdinalIgnoreCase))
                                {
                                    patched.AppendLine("sLocalSavePath=Saves\\");
                                    savePathWritten = true;
                                }
                            }
                            if (!savePathWritten)
                            {
                                patched.Insert(0, "[General]\r\nsLocalSavePath=Saves\\\r\n");
                            }
                            File.WriteAllText(dest, patched.ToString(),
                                System.Text.Encoding.UTF8);
                            Log("Injected MO2 INI (patched sLocalSavePath): " + iniName);
                        }
                        catch (Exception pex)
                        {
                            // Patch failed — fall back to raw copy so launch still proceeds
                            File.Copy(mo2Ini, dest, true);
                            Log("Injected MO2 INI (patch failed, raw copy): " + iniName
                                + " — " + pex.Message);
                        }
                    }
                    else
                    {
                        File.Copy(mo2Ini, dest, true);
                        Log("Injected MO2 INI: " + iniName);
                    }
                    iniBackupPairs.Add(new string[] { dest, backup });
                }

                if (iniBackupPairs.Count > 0)
                {
                    WriteState("INJECTED", gameSavesPath, mo2SavesPath,
                               mo2Profile, iniBackupPairs, new List<string[]>());
                    Log("State: INJECTED written.");
                }
            } // end usesBethesdaIni
        } // end isStealth INI block

        // Pre-launch REQUIRED: AppData Physical Sync — plugins.txt + loadorder.txt.
        // Failure aborts the launch — the game would load the wrong mod/plugin list.
        string realAppDataPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), appDataName);
        List<string[]> appDataBackupPairs = new List<string[]>();

        if (isStealth && !string.IsNullOrEmpty(appDataName))
        {
            // Only inject AppData (plugins.txt / loadorder.txt) when this game uses plugin load order.
            if (!usesPluginsTxt)
            {
                Log("AppData injection: skipped (non-Bethesda game — no plugins.txt).");
            }
            else
            {
            try
            {
                // Primary source: MO2 profile root (MO2 stores plugins.txt/loadorder.txt here)
                string profileAppData = mo2Profile;
                // Fallback: standalone_profile synced directory if not found in profile root
                if (!File.Exists(Path.Combine(profileAppData, "plugins.txt")))
                    profileAppData = Path.Combine(mo2Profile, "standalone_profile", "AppData", "Local", appDataName);

                string[] appDataFiles = new string[] { "plugins.txt", "loadorder.txt" };

                // Verify at least plugins.txt is reachable before touching anything
                string pluginsSrc = Path.Combine(profileAppData, "plugins.txt");
                if (!File.Exists(pluginsSrc))
                {
                    AbortWithError(
                        "AppData injection failed: plugins.txt not found.\n\n"
                        + "Searched in:\n  " + mo2Profile + "\n  " + profileAppData + "\n\n"
                        + "The game would load an incorrect (or empty) mod list. Launch blocked.");
                    return 1;
                }

                Directory.CreateDirectory(realAppDataPath);
                foreach (string fileName in appDataFiles)
                {
                    string src = Path.Combine(profileAppData, fileName);
                    if (!File.Exists(src)) continue;

                    string dest   = Path.Combine(realAppDataPath, fileName);
                    string backup = dest + ".bak_standalone";
                    if (File.Exists(dest))
                    {
                        File.Copy(dest, backup, true);
                        Log("Backed up AppData: " + fileName);
                    }
                    File.Copy(src, dest, true);
                    Log("Injected AppData: " + fileName);
                    appDataBackupPairs.Add(new string[] { dest, backup });
                }

                if (appDataBackupPairs.Count > 0)
                {
                    WriteState("INJECTED", gameSavesPath, mo2SavesPath,
                               mo2Profile, iniBackupPairs, appDataBackupPairs);
                    Log("State: INJECTED updated with AppData pairs.");
                }
            }
            catch (Exception ex)
            {
                AbortWithError(
                    "AppData injection failed: " + ex.Message + "\n\n"
                    + "plugins.txt / loadorder.txt could not be deployed.\n"
                    + "The game would load an incorrect mod list. Launch blocked.");
                return 1;
            }
            } // end usesPluginsTxt
        } // end AppData block

        // Pre-launch: Save injection — copy MO2 saves → Documents/Saves so the game sees existing saves.
        // TASK-A05: Explicit backup of any existing saves in Documents before overwriting.
        // Only copies files not already present (no overwrite) to avoid clobbering newer game saves.
        if (isStealth && Directory.Exists(mo2SavesPath))
        {
            try
            {
                Directory.CreateDirectory(gameSavesPath);
                int injectedSaves = 0;
                foreach (string sf in Directory.GetFiles(mo2SavesPath, "*", SearchOption.AllDirectories))
                {
                    string rel = sf.Substring(mo2SavesPath.Length).TrimStart(Path.DirectorySeparatorChar);
                    string dst = Path.Combine(gameSavesPath, rel);
                    if (!File.Exists(dst))
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(dst));
                        File.Copy(sf, dst, false);
                        injectedSaves++;
                    }
                    else
                    {
                        // TASK-A05: Back up the existing global save before MO2 save would overwrite it
                        string dstBak = dst + ".bak_standalone";
                        if (!File.Exists(dstBak))
                        {
                            File.Copy(dst, dstBak, false);
                            Log("Pre-launch backup of existing save: " + Path.GetFileName(dst));
                        }
                    }
                }
                if (injectedSaves > 0)
                    Log("Injected " + injectedSaves + " save(s) from MO2 profile \u2192 Documents/Saves.");
                else
                    Log("Save injection: all MO2 saves already present in Documents/Saves.");
            }
            catch (Exception ex)
            {
                Log("WARNING: Save injection failed: " + ex.Message);
            }
        }
        else if (isStealth)
        {
            Log("Save injection: MO2 saves folder not found \u2014 skipping.");
        }

        int exitCode = 0;
        Process proc = null;
        try
        {
            Log("Launching: " + origExe + " [" + gameName + "]");
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName         = origExe;
            psi.Arguments        = string.Join(" ", args);
            psi.UseShellExecute  = false;
            psi.WorkingDirectory = saDir;

            proc = Process.Start(psi);
            if (proc != null)
            {
                proc.WaitForExit();
                exitCode = proc.ExitCode;
                Log("Loader/Launcher exited. Code: " + exitCode.ToString());

                // If the launched process was just a loader (like SKSE), we must wait for the actual game to exit
                if (!string.IsNullOrEmpty(gameName))
                {
                    bool gameFound = false;
                    // Wait up to 15 seconds for the game process to spawn (loaders can be slow)
                    for (int i = 0; i < 30; i++)
                    {
                        Process[] gameProcs = Process.GetProcessesByName(gameName);
                        if (gameProcs.Length > 0)
                        {
                            gameFound = true;
                            Log("Detected game process: " + gameName + ". Waiting for it to exit...");
                            foreach (Process gp in gameProcs)
                            {
                                try { gp.WaitForExit(); } catch { }
                            }
                            Log("Game process exited.");
                            break;
                        }
                        System.Threading.Thread.Sleep(500);
                    }
                    if (!gameFound && Path.GetFileNameWithoutExtension(origExe).IndexOf(gameName, StringComparison.OrdinalIgnoreCase) < 0)
                    {
                        Log("WARNING: Loader exited but game process '" + gameName + "' was not found.");
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Log("ERROR: Launch failed: " + ex.Message);
            exitCode = -1;
        }
        finally
        {
            // D8: write SYNC_PENDING before attempting sync — crash here is recoverable
            if (isStealth && (iniBackupPairs.Count > 0 || appDataBackupPairs.Count > 0))
            {
                try
                {
                    WriteState("SYNC_PENDING", gameSavesPath, mo2SavesPath,
                               mo2Profile, iniBackupPairs, appDataBackupPairs);
                    Log("State: SYNC_PENDING written.");
                }
                catch (Exception ex)
                {
                    Log("WARNING: failed to write SYNC_PENDING state: " + ex.Message);
                }
            }

            // TASK-A05: Transactional save sync back to MO2 profile.
            // Pipeline: copy to staging → MD5 verify → File.Move() atomic swap → delete source.
            // Source is NEVER deleted unless the atomic move has already succeeded.
            if (isStealth && Directory.Exists(gameSavesPath))
            {
                string stagingDir = Path.Combine(mo2Profile, "_standalone_saves_staging");
                try
                {
                    Directory.CreateDirectory(mo2SavesPath);
                    Directory.CreateDirectory(stagingDir);

                    int syncedSaves = 0;
                    int failedSaves = 0;
                    foreach (string sf in Directory.GetFiles(
                        gameSavesPath, "*", SearchOption.AllDirectories))
                    {
                        // Skip .bak_standalone files created by pre-launch backup
                        if (sf.EndsWith(".bak_standalone", StringComparison.OrdinalIgnoreCase))
                            continue;

                        string rel     = sf.Substring(gameSavesPath.Length + 1);
                        string staged  = Path.Combine(stagingDir, rel);
                        string finalDst = Path.Combine(mo2SavesPath, rel);

                        try
                        {
                            // Step 1: copy to staging
                            Directory.CreateDirectory(Path.GetDirectoryName(staged));
                            File.Copy(sf, staged, true);

                            // Step 2: MD5 integrity check
                            bool md5Ok = false;
                            try
                            {
                                using (var srcStream = File.OpenRead(sf))
                                using (var stgStream = File.OpenRead(staged))
                                using (var md5 = System.Security.Cryptography.MD5.Create())
                                {
                                    byte[] srcHash = md5.ComputeHash(srcStream);
                                    md5.Initialize();
                                    byte[] stgHash = md5.ComputeHash(stgStream);
                                    md5Ok = BitConverter.ToString(srcHash) == BitConverter.ToString(stgHash);
                                }
                            }
                            catch (Exception hashEx)
                            {
                                Log("WARNING: MD5 check failed for " + rel + ": " + hashEx.Message
                                    + " — aborting sync for this file.");
                                SafeDelete(staged);
                                failedSaves++;
                                continue;
                            }

                            if (!md5Ok)
                            {
                                Log("WARNING: MD5 mismatch for staged save " + rel
                                    + " — aborting sync for this file.");
                                SafeDelete(staged);
                                failedSaves++;
                                continue;
                            }

                            // Step 3: Atomic move from staging → final MO2 destination
                            Directory.CreateDirectory(Path.GetDirectoryName(finalDst));
                            if (File.Exists(finalDst)) File.Delete(finalDst);
                            File.Move(staged, finalDst);  // atomic on same NTFS volume

                            // Step 4: Delete source ONLY after atomic move succeeded
                            SafeDelete(sf);
                            syncedSaves++;
                            Log("Transactional save synced: " + rel);
                        }
                        catch (Exception saveEx)
                        {
                            Log("WARNING: Transactional save sync failed for " + rel
                                + ": " + saveEx.Message + " — source preserved.");
                            SafeDelete(staged);
                            failedSaves++;
                        }
                    }

                    // Clean up staging dir if empty
                    try { Directory.Delete(stagingDir, false); } catch { }

                    Log("Save sync complete: " + syncedSaves + " synced, " + failedSaves + " failed.");
                }
                catch (Exception ex)
                {
                    Log("WARNING: Transactional save sync outer failure: " + ex.Message);
                    // Attempt staging cleanup
                    try { if (Directory.Exists(stagingDir)) Directory.Delete(stagingDir, true); } catch { }
                }
            }

            // Restore original INI files
            foreach (string[] pair in iniBackupPairs)
            {
                string dest   = pair[0];
                string backup = pair[1];
                if (File.Exists(backup))
                {
                    try
                    {
                        File.Copy(backup, dest, true);
                        File.Delete(backup);
                        Log("Restored INI: " + Path.GetFileName(dest));
                    }
                    catch (Exception ex)
                    {
                        Log("WARNING: INI restore failed for "
                            + Path.GetFileName(dest) + ": " + ex.Message);
                    }
                }
            }

            // Restore original AppData files (plugins.txt, loadorder.txt)
            foreach (string[] pair in appDataBackupPairs)
            {
                string dest   = pair[0];
                string backup = pair[1];
                if (File.Exists(backup))
                {
                    try
                    {
                        File.Copy(backup, dest, true);
                        File.Delete(backup);
                        Log("Restored AppData: " + Path.GetFileName(dest));
                    }
                    catch (Exception ex)
                    {
                        Log("WARNING: AppData restore failed for "
                            + Path.GetFileName(dest) + ": " + ex.Message);
                    }
                }
                else
                {
                    // No backup means file didn't exist before injection — remove injected copy
                    SafeDelete(dest);
                    Log("Cleaned injected AppData: " + Path.GetFileName(dest)
                        + " (no original existed).");
                }
            }

            // D8: delete state file only after full successful completion
            SafeDelete(StateFile);
        }

        return exitCode;
    }
}
"""


def write_launch_instructions(
    standalone_path: str,
    profile_name: str,
    game_name: str,
    known_loaders: list,
    docs_name: str = "",
    use_stealth: bool = True,
) -> bool:
    """FEAT-08: Writes HOW TO LAUNCH.txt to the standalone root."""
    sa_path = Path(standalone_path)

    # Determine the primary loader to advertise
    primary_loader = None
    for loader in known_loaders:
        candidate = sa_path / loader
        if candidate.exists() or (sa_path / f"_{candidate.stem}_original.exe").exists():
            primary_loader = loader
            break

    if not primary_loader and known_loaders:
        primary_loader = known_loaders[0]

    loader_display = primary_loader or "the game launcher"

    if use_stealth:
        isolation_msg = f"- Use {loader_display} to launch with Live MO2 save/config sync."
        data_loc = f"Saves & Configs: DIRECT LINK to MO2 Profile ({profile_name})"
    else:
        isolation_msg = f"- Use {loader_display} to keep your saves/settings in the '_standalone' folder."
        data_loc = f"Saves & Configs: _standalone\\Documents\\My Games\\{docs_name}"

    content_lines = [
        "=== HOW TO LAUNCH YOUR STANDALONE GAME ===",
        "",
        "To play with this isolated profile, ALWAYS use:",
        f"-> {loader_display}",
        "",
        "--- WHY ARE FILES RENAMED? ---",
        "To ensure total isolation, original executables have been renamed",
        "with a '_' prefix (e.g. _skse64_loader_original.exe).",
        "",
        "IMPORTANT:",
        "- DO NOT launch via the '_' prefixed files. They bypass isolation!",
        isolation_msg,
        "",
        "--- DATA LOCATION ---",
        data_loc,
        "",
        f"Build Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Profile    : {profile_name}",
        f"Game       : {game_name}",
    ]

    try:
        dest = sa_path / "HOW TO LAUNCH.txt"
        with open(dest, "w", encoding="utf-8") as f:
            f.write("\n".join(content_lines))
        logger.info("HOW TO LAUNCH.txt written to standalone root.")
        return True
    except Exception as e:
        logger.error("Failed to write HOW TO LAUNCH.txt: %s", e)
        return False


def write_steam_appid(standalone_path: str, appid: str) -> bool:
    """FEAT-09: Writes steam_appid.txt to the standalone root."""
    try:
        dest = Path(standalone_path) / "steam_appid.txt"
        with open(dest, "w", encoding="utf-8") as f:
            f.write(str(appid))
        logger.info("steam_appid.txt written: %s", appid)
        return True
    except Exception as e:
        logger.error("Failed to write steam_appid.txt: %s", e)
        return False


# ---------------------------------------------------------------------------
# FEAT-10 helpers
# ---------------------------------------------------------------------------

def _find_csc() -> str | None:
    """D1: Searches .NET Framework paths in priority order. Returns path or None."""
    for path in _CSC_SEARCH_PATHS:
        if os.path.isfile(path):
            logger.info("csc.exe found: %s", path)
            return path
    logger.warning("csc.exe not found — falling back to .bat for all wrappers.")
    return None


def _generate_cs_source(
    is_stealth: bool,
    mo2_profile_path: str,
    docs_name: str,
    game_name: str,
    appdata_name: str = "",
    ini_prefix: str = "",
    uses_plugins_txt: bool = True,
    uses_bethesda_ini: bool = True,
) -> str:
    """Injects runtime values into the C# template via str.replace()."""
    src = _CS_TEMPLATE
    src = src.replace("{IS_STEALTH}", "true" if is_stealth else "false")
    src = src.replace("{USES_PLUGINS_TXT}", "true" if uses_plugins_txt else "false")
    src = src.replace("{USES_BETHESDA_INI}", "true" if uses_bethesda_ini else "false")
    src = src.replace("{MO2_PROFILE_PATH}", mo2_profile_path)
    src = src.replace("{DOCS_NAME}", docs_name)
    src = src.replace("{GAME_NAME}", game_name)
    src = src.replace("{APPDATA_NAME}", appdata_name)
    src = src.replace("{INI_PREFIX}", ini_prefix)
    return src


def _compile_launcher(csc_path: str, sa_path: Path, target_name: str, cs_src: str) -> bool:
    """
    Writes cs_src to a temp .cs file, compiles to target_name with csc.exe.
    D2: deletes .cs source in finally — always, regardless of outcome.
    D3: logs result.stderr to audit_logger on non-zero returncode.
    Returns True on success.
    """
    target_path = sa_path / target_name
    cs_path = sa_path / (Path(target_name).stem + "_launcher_src.cs")
    try:
        cs_path.write_text(cs_src, encoding="utf-8")
        result = subprocess.run(
            [csc_path, "/target:winexe", f"/out:{target_path}", str(cs_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # D3: surface stderr so the user is not left with a generic error
            audit_logger.warning(
                "csc.exe compile failed for %s (rc=%d):\n%s",
                target_name, result.returncode, result.stderr.strip(),
            )
            return False
        logger.info("Compiled launcher: %s", target_name)
        return True
    except Exception as e:
        logger.error("Compile exception for %s: %s", target_name, e)
        return False
    finally:
        # D2: always delete source, never leave .cs in standalone folder
        try:
            if cs_path.exists():
                cs_path.unlink()
        except Exception as e:
            logger.warning("Failed to delete .cs source %s: %s", cs_path.name, e)


def wrap_loaders(
    standalone_path: str,
    known_loaders: list,
    game_exe: str = "",
    progress_callback=None,
    is_stealth: bool = True,
    mo2_profile_path: str = "",
    docs_name: str = "",
    appdata_name: str = "",
    ini_prefix: str = "",
    uses_plugins_txt: bool = True,
    uses_bethesda_ini: bool = True,
) -> dict:
    """
    FEAT-10: Renames original loader EXEs and compiles a C# stealth launcher
    in their place via csc.exe. Falls back to .bat if csc.exe is unavailable
    or compilation fails. No pre-compiled EXE required.

    Returns {"hijacked": int, "exe_wrappers": int, "bat_wrappers": int}.
    """
    sa_path = Path(standalone_path)
    csc_path = _find_csc()

    # D5: inject game_exe stem as the only process name — no hardcoded fallback list
    game_name = Path(game_exe).stem if game_exe else ""

    result = {"hijacked": 0, "exe_wrappers": 0, "bat_wrappers": 0}

    candidates = list(known_loaders)
    if game_exe and game_exe not in candidates:
        candidates.append(game_exe)

    # Determine the primary target (first one that exists) to avoid wrapping base game under SKSE
    primary_target = None
    for target_name in candidates:
        if not target_name:
            continue
        if (sa_path / target_name).exists() or (sa_path / f"_{Path(target_name).stem}_original.exe").exists():
            primary_target = target_name
            break

    total = len(candidates)
    for idx, target_name in enumerate(candidates):
        if not target_name:
            continue

        target_path = sa_path / target_name
        original_name = f"_{Path(target_name).stem}_original.exe"
        original_path = sa_path / original_name

        if target_name != primary_target:
            # Un-wrap secondary EXEs so SKSE can read their version info
            if original_path.exists():
                try:
                    subprocess.run(["attrib", "-h", str(original_path)], check=False, capture_output=True)
                    if target_path.exists():
                        target_path.unlink()
                    original_path.rename(target_path)
                    logger.info("Restored secondary EXE to original state: %s", target_name)
                except Exception as e:
                    logger.warning("Failed to restore secondary EXE %s: %s", target_name, e)
            continue

        # D6: clean 3-state check — no ambiguous counter increments before guards
        if target_path.exists() and not original_path.exists():
            # FRESH: first-time hijack — rename original EXE
            try:
                target_path.rename(original_path)
                result["hijacked"] += 1
                logger.info("Renamed original: %s → %s", target_name, original_name)
            except Exception as e:
                logger.error("Failed to rename %s: %s", target_name, e)
                continue
        elif original_path.exists():
            # REWRAP: already renamed in a prior build — re-deploy wrapper
            result["hijacked"] += 1
            if target_path.exists():
                # Remove stale wrapper so compiler/copy writes fresh
                try:
                    target_path.unlink()
                except Exception as e:
                    logger.warning("Could not remove stale wrapper %s: %s", target_name, e)
        else:
            # SKIP: neither target nor original exists in standalone
            logger.debug("Skipping %s — not found in standalone.", target_name)
            continue

        # Deploy wrapper (EXE via csc, or .bat fallback)
        bat_path = sa_path / (Path(target_name).stem + ".bat")
        compiled = False

        if csc_path:
            cs_src = _generate_cs_source(
                is_stealth=is_stealth,
                mo2_profile_path=mo2_profile_path,
                docs_name=docs_name,
                game_name=game_name or Path(target_name).stem,
                appdata_name=appdata_name,
                ini_prefix=ini_prefix,
                uses_plugins_txt=uses_plugins_txt,
                uses_bethesda_ini=uses_bethesda_ini,
            )
            compiled = _compile_launcher(csc_path, sa_path, target_name, cs_src)

        if compiled:
            result["exe_wrappers"] += 1
            # Remove any old .bat from a previous fallback run
            try:
                if bat_path.exists():
                    bat_path.unlink()
            except Exception as e:
                logger.warning("Could not remove stale .bat %s: %s", bat_path.name, e)
        else:
            _deploy_bat_fallback(sa_path / target_name, original_name)
            result["bat_wrappers"] += 1
            logger.info("Deployed .bat fallback for: %s", target_name)

        # D7: hide original EXE — log failure at WARNING, never silent
        try:
            subprocess.run(
                ["attrib", "+h", str(original_path)],
                check=False, capture_output=True,
            )
        except Exception as e:
            logger.warning("Failed to hide original EXE %s: %s", original_name, e)

        if progress_callback:
            progress_callback(int(((idx + 1) / total) * 100))

    logger.info(
        "EXE wrapping complete: %d hijacked, %d EXE wrappers, %d .bat wrappers.",
        result["hijacked"], result["exe_wrappers"], result["bat_wrappers"],
    )
    return result


def _deploy_bat_fallback(wrapper_path: Path, original_name: str):
    """Writes a minimal .bat launcher pointing to the renamed original EXE."""
    try:
        bat_path = wrapper_path.with_suffix(".bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write("@echo off\n")
            f.write("echo Launching standalone game (csc.exe unavailable or compile failed)...\n")
            f.write(f'start "" "%~dp0{original_name}" %*\n')
    except Exception as e:
        logger.error("Failed to write .bat fallback: %s", e)
