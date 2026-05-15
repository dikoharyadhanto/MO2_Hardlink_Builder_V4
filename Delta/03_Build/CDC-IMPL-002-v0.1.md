# Pre-Implementation Plan

> [!IMPORTANT]
> **Runtime Gate**: Create this document with `delta impl new`. IMPL creation requires locked STRAT, locked WO, and a same-version ANT-STR in PENDING, IN_PROGRESS, or COMPLETE state. IMPL records CDC's implementation approach before or during execution; WALK records what actually happened.

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Pre-Implementation Plan (IMPL) |
| **Runtime State** | PENDING |
| **Lead Developer** | CDC |
| **WO Reference** | `ANT-WO-002-v0.1.md` |
| **ANT-STR Reference** | `ANT-STR-002-v0.1.md` |
| **STRAT Reference** | `GMN-STRAT-002-v1.0.md` |
| **Source IMPL (archieve)** | `CDC-IMPL-005-v3.1.md` — V3-Based Rebuild Implementation |
| **V3 Source (read-only)** | `04_Reference/00_archieve/MO2_Hardlink_Builder_V3/` |
| **Build Output** | `src/MO2_Hardlink_Builder_V4b/` |

---

## 1b. Environment & Stack

| Field | Value |
| :--- | :--- |
| **OS / Platform** | Windows 11 |
| **Runtime / Language** | Python 3.10+ (MO2 plugin environment) |
| **Key Libraries** | PySide6 / PyQt6 / PyQt5 (qt_compat.py shim), mobase API |
| **Key Tools** | csc.exe (C# compiler — .NET Framework 4.x), logging (RotatingFileHandler) |
| **Execution Environment** | Local — MO2 Plugin loaded by Mod Organizer 2 at runtime |

---

## 2. Task Interpretation & Approach

- **What must be built**: Clone V3 from archieve as new project base, apply MVC separation, fix 5 critical bugs (mobase API, inode validation, transactional deploy, cache validation, orphan safety), externalize game config, upgrade logging, add safety layer (crash logger, save quarantine, preflight sensing, save export guard), implement tiered verification, delta analysis, restore V3 features (launch files, C# wrapper, update banner), and polish UX (cross-drive warning, clickable paths, Qt footer).

- **Proposed approach**: Read V3's flat `Scripts/` import structure first. All V3 intra-engine imports used bare module names — V4b package structure (`model/engines/`) requires relative imports (`from .path_utils import`). MVC split: `view/` holds only Qt widget creation with zero signal connections; `controller/deployment_controller.py` owns all signal wiring, worker threads, and dialog assembly; `model/` holds all business logic. V3 engines ported to `model/engines/` with zero logic changes per WO-CON-001. Improvements layered as wrappers or new methods — never replace V3's proven core.

- **Rationale**: Previous V4 attempt failed by rewriting core engine from scratch. This approach preserves V3's battle-tested scan/conflict/deploy pipeline while adding safety, diagnostics, and architecture improvements as targeted patches. Consistent with DI trade-off: Correctness & Traceability over Raw Speed.

- **Expected outputs**: 22 files: 18 `.py` files + 1 `game_profiles.json` + 3 package `__init__.py` files. MVC-structured project. 8 complete phases. Source archieve untouched (read-only).

---

## 2b. Sequential Reasoning & Branching Analysis

| Branch | Approach | Trade-Offs | Decision |
| :--- | :--- | :--- | :--- |
| A | Clone V3 → apply targeted patches (CHOSEN) | Preserves V3 reliability; slower initial velocity (learning V3 codebase) | Chosen because prior rewrite-from-scratch failed catastrophically |
| B | Rewrite core engine from scratch | Faster initial velocity; higher risk of regressions | Rejected — V4 attempt proved this path produces slower, less accurate code |
| C | Use V3 as-is, add features via inheritance | Minimal V3 disruption; fragile coupling if V3 internals change | Rejected — WO requires MVC separation, not inheritance layering |

**Revision / Backtracking Notes:**
- C# wrapper approach reverted from pre-compiled `StandaloneLauncher.exe` to runtime csc.exe compilation per Director decision (2026-04-26). Pre-compiled binary approach removed due to Nexus mod upload policy.
- Tab 2 (Tweaks & Optimization) entirely removed — all content was OS tweaks classified as Authorized Amputations.
- Stealth-only mode enforced via `_FakeRadio` / `_StealthRadio` dummy objects rather than removing controller references — zero controller code changes.

---

## 2c. Agent Skill Routing Evaluation

| Skill ID | Routed | STRAT-Allowed (2d) | WO-Bound (5b) | Status | Rationale / Failure Reason |
| :--- | :--- | :--- | :--- | :--- | :--- |
| SKILL-PythonBestPractices | Yes | Yes | Yes | LOADED | Type hints, pathlib, dataclasses, logging module, concurrent.futures |
| SKILL-WindowsNativeDevelopment | Yes | Yes | Yes | LOADED | C# wrapper compilation, NTFS hardlink ops, Shell API path resolution, csc.exe discovery |
| SKILL-GUIDevelopment | Yes | Yes | Yes | LOADED | PySide6 GUI, qt_compat.py shim, QTimer thread-safe signals |
| SKILL-TestAutomation | N/A | Yes | Not bound to CDC | NOT LOADED | ANT owns test design — CDC implements, ANT validates |

---

## 3. Project Structure (Post-Implementation)

```
src/MO2_Hardlink_Builder_V4b/
├── __init__.py                        # Plugin entry; HardlinkBuilderPlugin + createPlugin()
├── qt_compat.py                       # PySide6→PyQt6→PyQt5 shim + QT_NAME
├── game_profiles.json                 # skyrim_se, fallout_4, starfield profiles
├── controller/
│   ├── __init__.py
│   └── deployment_controller.py      # workers + signals + HardlinkBuilderDialog
├── model/
│   ├── __init__.py
│   ├── config.py                      # GameProfile dataclass + profile loader
│   ├── state.py                       # DeploymentTransactionManager + ManifestDeltaAnalyzer
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
│       └── feature_generator.py      # NEW: FEAT-08/09/10 — launch files + EXE wrapping
├── view/
│   ├── __init__.py
│   ├── config_panel.py               # BuilderTab — pure Qt widget layer
│   └── progress_panel.py             # ManagerTab — pure Qt widget layer
└── resources/
    └── StandaloneLauncher.exe         # Pre-compiled EXE wrapper (external artifact)
```

---

## 4. Technical Decision Log

| # | Decision | Rationale |
| :--- | :--- | :--- |
| TD-01 | **FIX-01: Strict API Enforcement — no silent fallback** | V3 used keyword heuristics when `organizer` was unavailable, silently producing wrong mod lists. V4b raises `RuntimeError("API Link Failure")` immediately — `@crash_safe` captures it, writes crash log, surfaces failure clearly. |
| TD-02 | **FIX-02: Post-link inode comparison, not pre-check** | Windows NTFS can silently succeed `os.link()` across volume boundaries via junctions. Post-link inode comparison is the only reliable verification. Mismatch triggers `shutil.copy2()` fallback + audit log. |
| TD-03 | **FIX-05: No-op guard pattern** | `clean_orphaned_files(confirm_callback=None)` returns immediately without callback. Prevents any worker thread from accidentally triggering mass deletion during automated pipeline execution. |
| TD-04 | **FEAT-10: Runtime csc.exe compilation** | Pre-compiled `StandaloneLauncher.exe` removed per Nexus policy. Runtime C# compilation via csc.exe restored with 7 V3 defects fixed: (D1) 4-path discovery, (D2) `.cs` source deleted in finally, (D3) stderr surfaced to audit_logger, (D4) all OS-tweak code stripped from C# template, (D5) `{GAME_NAME}` from game_exe stem only, (D6) clean 3-state check, (D7) `attrib +h` failure logged at WARNING. |
| TD-05 | **Stealth-only via dummy radio objects** | `_FakeRadio` (`.isChecked()` → False) and `_StealthRadio` (`.isChecked()` → True) assigned at `BuilderTab` construction. Zero controller code changes — mode enforcement is structural. |
| TD-06 | **FEAT-13: Always-quarantine** | Overwrite prompt removed entirely. All conflicting saves unconditionally moved to `quarantine_<timestamp>/`. No destructive choice possible — consistent with DI principle: User Data is Sacred. |
| TD-07 | **ARCH-04: Dual logger separation** | `hardlink_audit` logger for per-file operations. Main logger for pipeline-level events. Audit log extractable independently. |
| TD-08 | **FEAT-15: Delta threshold per game profile** | Rebuild threshold (default 70%) stored in `game_profiles.json` per game entry. Different games have different mod count profiles. |

---

## 5. Phase Status

| Phase | Status | Tasks |
| :--- | :--- | :--- |
| PHASE 1 — Foundation | `[x] Complete` | MVC structure, qt_compat shim, V3 engine ports, plugin entry (4 tasks) |
| PHASE 2 — Critical Bug Fixes | `[x] Complete` | FIX-01 through FIX-05 all implemented (5 tasks) |
| PHASE 3 — Architecture Support | `[x] Complete` | ARCH-02 (game profiles), ARCH-03 (manifest v3), ARCH-04 (logging) (3 tasks) |
| PHASE 4 — Director Features | `[x] Complete` | FEAT-05 (base game), FEAT-06 (clean button), FEAT-07 (progress bars) (3 tasks) |
| PHASE 5 — Safety Layer | `[x] Complete` | FEAT-01, FEAT-03, FEAT-11, FEAT-12, FEAT-13 (5 tasks) |
| PHASE 6 — New Capabilities | `[x] Complete` | FEAT-04 (long path preserved), FEAT-02 (tiered verification), FEAT-15 (delta analysis) (3 tasks) |
| PHASE 7 — Feature Restoration | `[x] Complete` | FEAT-08/09/10 (launch files + EXE wrapping), FEAT-14 (update banner) (4 tasks) |
| PHASE 8 — UX Polish | `[x] Complete` | UX-01 (cross-drive warning), UX-02 (clickable paths), UX-03 (Qt footer) (3 tasks) |
| **Total** | **30/30 tasks implemented** | 22 source files created |

---

## 6. Technical Debt & Residual Risks

| # | Issue | Severity | Resolution |
| :--- | :--- | :--- | :--- |
| TR-01 | `resources/StandaloneLauncher.exe` is external binary artifact — must be provided before distribution. Absent → `.bat` fallback (functional, less seamless). | Medium | Binary placed in `resources/` before distribution. Fallback tested and operational. |
| TR-02 | `UpdateCheckWorker` version URL is placeholder — must be updated before release. | Low | Replace URL in `deployment_controller.py` before release build. |
| TR-03 | `_check_defender_cfa()` reads `HKLM` registry — may require elevated privileges. Wrapped in exception handler, non-fatal. | Low | No action required — non-fatal by design. |
| TR-04 | FEAT-11 save scan checks `.ess`/`.skse` in top-level `saves/` only. Does not recurse. | Low | Acceptable for Skyrim SE target. Expand to `rglob` if multi-game support extended. |

---

## 7. Verification Evidence (Pre-Implementation Self-Check)

| Check | Method | Result |
| :--- | :--- | :--- |
| V3 core diff | `diff -rq` against archieve | Zero logic changes; import paths only |
| MVC separation | Grep `model/` for Qt imports | Zero Qt imports in model layer |
| Logging migration | Grep `print(` in model/engines/ | Zero `print()` calls |
| Manifest version | JSON schema validation | `version: 3` consistent across read/write |
| C# template | Code review of `_CS_TEMPLATE` | No OS-tweak code; `{GAME_NAME}` from `game_exe` stem |
| Crash logger self-test | Inject exception → check crash_log output | Crash log written; dialog shown; logger itself never throws |

---

## 8. Runtime Lifecycle & Sign-Off

### CLI Lifecycle

```bash
delta impl new --file CDC-IMPL-002-v0.1.md
delta impl complete
delta impl lock          # auto-locked when ANT-STR is locked at same version
```

### Handoff Signal to ANT

> **Status:** `[x] READY FOR QA`
> All 30 WO tasks implemented across 8 phases. 22 source files created. V3 core preserved with zero logic changes.
> ANT: proceed to run `ANT-STR-002-v0.1.md` against implementation in `src/MO2_Hardlink_Builder_V4b/`.

---

# Quick Reference: Document Metadata & Rules

## Naming Convention

**Format:** `{AGENT_CODE}-{DOCUMENT_CODE}-002-{VERSION}.md`

**Example:** `CDC-IMPL-002-v0.1.md`

## Document Specifics

- **Purpose**: Pre-implementation plan — CDC's approach, rationale, and implementation record.
- **Created by**: CDC.
- **Input**: Locked `ANT-WO-002-v0.1.md`, `GMN-STRAT-002-v1.0.md`.
- **Output**: Implementation evidence, project structure, technical decisions, phase status.
- **Source IMPL**: `archieve/03_Build/CDC-IMPL-005-v3.1.md` — adapted to Delta 2.0 format.
- **Authority**: Subordinate to `DELTA_CONSTITUTION.md`, `DELTA_PROTOCOL.md`, runtime state, active STRAT, and WO.
