# CDC-IMPL-005-v3.1 — Implementation Log: MO2 Hardlink Builder (V3-Based Rebuild)

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-005-v3.1.md`
> **V3 Source (read-only):** `04_Reference/00_archieve/MO2_Hardlink_Builder_V3/`
> **Build Output:** `03_Build/MO2_Hardlink_Builder_V4b/`

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Implementation Log (IMPL) |
| **Version** | v3.1 |
| **Status** | Complete — Pending ANT QA |
| **Lead Developer** | CDC — Claude Code |
| **Work Order Ref** | `ANT-WO-005-v3.1.md` |
| **Test Plan Ref** | `ANT-STR-005-v3.1.md` |
| **Completion Date** | 2026-04-26 |

---

## 1b. Environment & Stack

| Field | Value |
| :--- | :--- |
| **OS / Platform** | Windows 11 |
| **Runtime / Language** | Python 3.x (MO2 plugin environment) |
| **Key Libraries** | PySide6 / PyQt6 / PyQt5 (compat shim), mobase API |
| **Environment** | MO2 Plugin — loaded by Mod Organizer 2 at runtime |

---

## 2. Project Structure

```
03_Build/MO2_Hardlink_Builder_V4b/
├── __init__.py                        # Plugin entry; HardlinkBuilderPlugin + createPlugin()
├── qt_compat.py                       # ARCH-05: PySide6→PyQt6→PyQt5 shim + QT_NAME
├── game_profiles.json                 # ARCH-02: skyrim_se, fallout_4, starfield profiles
├── controller/
│   ├── __init__.py
│   └── deployment_controller.py      # ARCH-01: workers + signals + HardlinkBuilderDialog
├── model/
│   ├── __init__.py
│   ├── config.py                      # ARCH-02: GameProfile dataclass + profile loader
│   ├── state.py                       # FIX-03: DeploymentTransactionManager; FEAT-15: ManifestDeltaAnalyzer
│   └── engines/
│       ├── __init__.py
│       ├── path_utils.py              # V3 PRESERVED: ensure_long_path(), clean_path_for_display()
│       ├── state_manager.py           # V3 PRESERVED + FIX-04: ConflictManager v2 cache validation
│       ├── scanner_engine.py          # V3 PRESERVED + FIX-01 + FEAT-05 + ARCH-03
│       ├── linker_executor.py         # V3 PRESERVED + FIX-02 + FIX-05 + FEAT-05
│       ├── profile_sync.py            # V3 PRESERVED + FEAT-13: always-quarantine conflicts
│       ├── verification_engine.py     # V3 PRESERVED + FEAT-02: TieredVerificationEngine
│       ├── cleaner_engine.py          # V3 PRESERVED + ARCH-04: print()→logging
│       ├── crash_logger.py            # NEW: FEAT-03 — write_crash_log() + @crash_safe
│       ├── diagnostics.py             # NEW: FEAT-01 — EnvironmentSensor
│       └── feature_generator.py      # NEW: FEAT-08/09/10
├── view/
│   ├── __init__.py
│   ├── config_panel.py               # ARCH-01: BuilderTab — pure Qt widget layer, Tab 1
│   └── progress_panel.py             # ARCH-01: ManagerTab — pure Qt widget layer, Tab 2
└── resources/
    └── StandaloneLauncher.exe         # Pre-compiled EXE wrapper (external artifact)
```

---

## 3. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **FIX-01: Strict API Enforcement — no silent fallback** | V3 used keyword heuristics on mod folder names when `organizer` was unavailable. This silently produced wrong mod lists and corrupt deployments. V4b raises `RuntimeError("API Link Failure")` immediately — the `@crash_safe` decorator captures it and writes a crash log, surfacing the failure clearly instead of hiding it. |
| TD-02 | **FIX-02: Post-link inode comparison, not pre-check** | Windows NTFS can silently succeed `os.link()` across volume boundaries, returning a copy rather than a true hardlink. A pre-check on drive letters is insufficient (junction points, volume mounts). Post-link inode comparison is the only reliable verification. Mismatch triggers `shutil.copy2()` fallback + `PSEUDO-HARDLINK DETECTED` audit log entry. |
| TD-03 | **FIX-05: No-op guard pattern** | `clean_orphaned_files(confirm_callback=None)` returns immediately without callback. This prevents any worker thread from accidentally triggering mass deletion during automated pipeline execution. The pattern makes the safety constraint visible in the function signature itself. |
| TD-04 | **FEAT-10: Runtime csc.exe compilation (reverted from pre-compiled EXE)** | Pre-compiled `StandaloneLauncher.exe` was removed from the distribution package due to Nexus mod upload policy (EXE quarantine). Runtime C# compilation via `csc.exe` is restored — identical to V3 strategy, but with 7 V3 defects corrected. (D1) csc.exe is discovered by searching four .NET Framework paths in priority order rather than a single hardcoded v4.0.30319 path. (D2) The `.cs` source file is deleted in a `finally` block — always, regardless of compile outcome. (D3) `csc.exe` stderr is surfaced to `audit_logger` on non-zero returncode instead of emitting a generic error. (D4) C# template stripped of all Authorized Amputation code: no CPU priority, IO priority, affinity mask, MMCSS, RAM trim, or thermal failsafe. (D5) `{GAME_NAME}` injected from `game_exe` stem only — hardcoded fallback process name list removed entirely. (D6) Rewritten as a clean 3-state check (FRESH / REWRAP / SKIP) eliminating the V3 ambiguity where `hijacked_count` was incremented before a `continue` guard. (D7) `attrib +h` failure is now logged at WARNING level instead of a bare `except: pass`. |
| TD-05 | **Stealth-only via dummy radio objects** | V3 had 3 radio button modes (Isolated, Documents, Stealth). V4b enforces stealth only. Rather than removing the `rb_mode_*` attribute references throughout the controller, `_FakeRadio` (`.isChecked()` → False) and `_StealthRadio` (`.isChecked()` → True) dummy objects are assigned at `BuilderTab` construction. Zero controller code changes required; mode enforcement is structural. |
| TD-06 | **FEAT-13: Always-quarantine, overwrite prompt removed** | V3 conditionally offered a user prompt to overwrite conflicting saves during sync. In an automated build pipeline, a prompt from a background worker risks deadlock and allows destructive choices under time pressure. V4b always creates `quarantine_<timestamp>/` for conflicts — no data is ever silently overwritten. |
| TD-07 | **ARCH-04: Dual logger separation** | `hardlink_audit` logger handles per-file operations (every link, copy, pseudo-hardlink detection). Main `logger` handles pipeline-level events (stage transitions, errors, warnings). Audit log can be extracted and analyzed independently without grepping through debug noise from the orchestration layer. |
| TD-08 | **FEAT-15: Delta threshold per game profile** | The rebuild threshold (default 70%) is stored in `game_profiles.json` per game entry. Different games have different mod count profiles — Skyrim SE typically has 500+ mods; Starfield far fewer. Storing threshold in the profile config allows future tuning without code changes. |

---

## 4. Files Modified & Created

| File Path | Action | Phase | Purpose |
| :--- | :--- | :--- | :--- |
| `__init__.py` | CREATED | PHASE 1 | Plugin entry; `HardlinkBuilderPlugin(mobase.IPluginTool)` + `createPlugin()` |
| `qt_compat.py` | CREATED | PHASE 1 | ARCH-05: PySide6 → PyQt6 → PyQt5 shim; exports `QT_NAME` and all Qt symbols |
| `game_profiles.json` | CREATED | PHASE 3 | ARCH-02: Game profile data — appids, known_loaders, blacklist_files, delta_rebuild_threshold |
| `model/__init__.py` | CREATED | PHASE 1 | Package init |
| `model/config.py` | CREATED | PHASE 3 | ARCH-02: `@dataclass GameProfile`, `DeploymentConfig`; `load_game_profiles()`, `get_profile_for_game()` |
| `model/state.py` | CREATED | PHASE 2 | FIX-03: `DeploymentTransactionManager` (`.deployment_state` checkpoint file); FEAT-15: `ManifestDeltaAnalyzer` |
| `model/engines/__init__.py` | CREATED | PHASE 1 | Package init |
| `model/engines/path_utils.py` | CREATED | PHASE 1 | V3 PRESERVED: `ensure_long_path()`, `to_path()`, `clean_path_for_display()` |
| `model/engines/state_manager.py` | CREATED | PHASE 2 | V3 PRESERVED + FIX-04: `ConflictManager` validates `CACHE_VERSION = 2`; corrupted cache → rebuild from scratch |
| `model/engines/scanner_engine.py` | CREATED | PHASE 2 | V3 PRESERVED + FIX-01 + FEAT-05 + ARCH-03: mobase API enforcement, base game scan, manifest v3 |
| `model/engines/linker_executor.py` | CREATED | PHASE 2 | V3 PRESERVED + FIX-02 + FIX-05 + FEAT-05: inode validation, orphan safety guard, base game deploy |
| `model/engines/profile_sync.py` | CREATED | PHASE 5 | V3 PRESERVED + FEAT-13: always-quarantine conflict resolution; `deploy_mo2_profile()` new method |
| `model/engines/verification_engine.py` | CREATED | PHASE 6 | V3 PRESERVED + FEAT-02: `TieredVerificationEngine` wrapping original; Quick/Sampled/Full policies |
| `model/engines/cleaner_engine.py` | CREATED | PHASE 1 | V3 PRESERVED + ARCH-04: all `print()` → `logging`; zero logic changes |
| `model/engines/crash_logger.py` | CREATED | PHASE 5 | FEAT-03: `write_crash_log()` (never-raise) + `@crash_safe` worker decorator |
| `model/engines/diagnostics.py` | CREATED | PHASE 5 | FEAT-01: `EnvironmentSensor` — OneDrive path + winreg, Defender CFA, PID lock checks |
| `model/engines/feature_generator.py` | CREATED | PHASE 7 | FEAT-08/09/10: `HOW TO LAUNCH.txt`, `steam_appid.txt`, EXE wrapping with `.bat` fallback |
| `view/__init__.py` | CREATED | PHASE 1 | Package init |
| `view/config_panel.py` | CREATED | PHASE 1 | ARCH-01: `DropLineEdit` + `BuilderTab` — all Tab 1 widgets; zero business logic |
| `view/progress_panel.py` | CREATED | PHASE 1 | ARCH-01: `ManagerTab` — all Tab 2 widgets; `setOpenExternalLinks(True)` (UX-02) |
| `controller/__init__.py` | CREATED | PHASE 1 | Package init |
| `controller/deployment_controller.py` | CREATED | PHASE 1 | ARCH-01: `SynchronousMessenger`, `UpdateCheckWorker`, `CleanWorker`, `BuildWorker`, `HardlinkBuilderDialog` |

**Total files created: 22** (18 `.py` files + 1 `.json` + 3 package `__init__.py` files)

---

## 5. Phase Status

| Phase | Status | Notes |
| :--- | :--- | :--- |
| PHASE 1 — Foundation | `[x] Complete` | MVC structure, qt_compat shim, V3 engine ports, plugin entry |
| PHASE 2 — Critical Bug Fixes | `[x] Complete` | FIX-01 through FIX-05 all implemented |
| PHASE 3 — Architecture Support | `[x] Complete` | ARCH-02 (game profiles), ARCH-03 (manifest v3), ARCH-04 (logging) |
| PHASE 4 — Director Features | `[x] Complete` | FEAT-05 (base game), FEAT-06 (clean button), FEAT-07 (progress bars) |
| PHASE 5 — Safety Layer | `[x] Complete` | FEAT-01, FEAT-03, FEAT-11, FEAT-12, FEAT-13 all implemented |
| PHASE 6 — New Capabilities | `[x] Complete` | FEAT-04 (long path preserved), FEAT-02 (tiered verification), FEAT-15 (delta analysis) |
| PHASE 7 — Feature Restoration | `[x] Complete` | FEAT-08/09/10 (launch files + EXE wrapping), FEAT-14 (update banner) |
| PHASE 8 — UX Polish | `[x] Complete` | UX-01 (cross-drive warning), UX-02 (clickable paths), UX-03 (Qt footer) |

---

## 6. Technical Debt & Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | `resources/StandaloneLauncher.exe` is not a source artifact — it must be provided as an external pre-compiled binary. If absent, `wrap_loaders()` falls back to `.bat` launcher (functional but less transparent to users). | Medium | Pre-compiled binary must be placed in `resources/` before distribution. `wrap_loaders()` `.bat` fallback is already implemented and operational. |
| TR-02 | `UpdateCheckWorker` remote version URL is a placeholder and must be updated to the production endpoint before public release. Silent-fail behavior means no user impact if URL is wrong. | Low | Update URL to point to production version manifest before distribution. |
| TR-03 | `_check_defender_cfa()` reads `HKLM` registry keys which may require elevated privileges on locked-down systems. Wrapped in `except (ImportError, FileNotFoundError, OSError): pass` — failure is silent and non-blocking. | Low | No action required — non-fatal by design. Log entry sufficient for diagnostics. |
| TR-04 | FEAT-11 save export guard checks only `.ess` and `.skse` file extensions in the top-level profile `saves/` directory. Does not recurse into subdirectories. | Low | Acceptable for Skyrim SE target. If other games store saves in subdirs, `_find_saves()` will need a recursive glob. |
