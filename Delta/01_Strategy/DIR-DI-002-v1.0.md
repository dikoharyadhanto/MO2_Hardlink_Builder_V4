# Director's Intent & Decision Constraints

> **Purpose**: This document captures the Director's strategic vision AND the decision constraints that control how the system will execute. It serves as the foundational control layer for all downstream strategy documents (STRAT, WO, IMPL, WALK).

---

## 1. Project Identity

**Project Name**: MO2 Hardlink Builder V4

**Brief Description** (1-2 sentences): A zero-space NTFS hardlink-based tool that mirrors a Mod Organizer 2 profile into a standalone physical game folder — enabling heavily-modded games (2000+ mods) to run outside MO2's VFS without disk duplication, while preserving exact load order, save file safety, and crash resilience.

---

## 2. Strategic Vision

**Why are we doing this? What problem does it solve?**

MO2's Virtual File System (VFS) is a masterpiece of mod management but hits physical limits: external tools (DynDOLOD, xLODGen, ENBs) refuse VFS injection, massive modlists cause performance degradation, and users lose hours of progress when things break silently.

We are building an **escape hatch**: a tool that creates a real, physical game folder from an MO2 profile using NTFS hardlinks (zero additional disk space), with defensive safety mechanisms that assume the OS is hostile (AV interference, OneDrive locks) and protect the user's save files and load order from corruption — even during crashes.

---

## 3. What Success Looks Like

### Concrete Outcome

A heavy modder with a 1000+ modlist can:

1. Build a standalone game folder from their MO2 profile in one click
2. Launch and play the game with exact load order parity
3. Update incrementally in seconds when mods change
4. Have their save files automatically synced back to MO2
5. Receive clear, actionable diagnostic messages when something fails — never a silent, ambiguous failure

### Success Threshold

- **Deployment time**: <30 seconds for incremental updates on a 1000+ modlist
- **Ambiguity reduction**: 90% reduction in "ambiguous launch failures" through explicit failure attribution
- **Verification velocity**: Re-verify 50,000+ files in under 3 minutes
- **State parity**: 100% load order parity between MO2 profile and standalone folder

### Measurement Method

- Timing benchmarks on reference modlists (100, 500, 1000+ mods)
- User-reported "load order mismatch" bug count (target: 90% reduction from V3 baseline)
- Automated integrity test suite (ANT-STR) validating inode parity and ownership correctness
- Manual Director testing (DIR-STR) on real-world Skyrim/Fallout profiles

---

## 4. Core Principles & Values

1. **Transparency over Magic**: Every operation must be traceable. No black-box decisions. If a hardlink falls back to a copy, the user must know exactly why.
2. **Defensive by Default**: Assume the OS is hostile (AV, OneDrive, file locks). Detect, report, and offer recovery paths — never fail silently.
3. **Deterministic Correctness**: The standalone folder must mirror the MO2 load order on a 1:1 basis. Priority resolution errors are fatal bugs.
4. **User Data is Sacred**: Save files, INI settings, and load order files must never be silently overwritten or corrupted. Quarantine, don't destroy.
5. **Performance is a Feature**: Incremental updates must be fast enough that users don't dread re-running the tool. Target: seconds, not minutes.

---

## 5. Strategic Trade-Offs (MANDATORY)

**We explicitly choose these priorities:**

### Primary Trade-Off

We prioritize **Correctness & Traceability** over **Raw Speed**

> A slightly slower build that provides a complete diagnostic trail is vastly preferable to a fast build that fails silently and leaves the user guessing.

### Secondary Trade-Offs

- We are willing to sacrifice **cross-platform support** to gain **deep NTFS integration** (hardlinks are NTFS-only; Windows is the target platform)
- We are willing to sacrifice **multi-profile session switching** to gain **deterministic single-profile integrity**
- We are willing to sacrifice **automatic mod conflict resolution** to gain **faithful 1:1 MO2 mirroring** (the tool mirrors MO2; it does not fix broken mods)

**Why these trade-offs matter:**
The core value proposition is trust. The user must believe that what they see in the standalone folder is exactly what MO2 would have loaded. Any deviation — even for convenience — breaks that trust permanently. These trade-offs keep scope tight and the trust guarantee intact.

---

## 6. Risk Appetite (CRITICAL)

**How much risk is acceptable for this project?**

### Fatal Risk Tolerance

How many unmitigated fatal risks can we accept?

- [x] Zero (cannot launch if any fatal risk unmitigated)

> Silent load order corruption, save file destruction, or hardlink-to-copy fallback without user notification are fatal risks. None may remain unmitigated.

### Degrading Risk Tolerance

What level of degraded capability is acceptable at launch?

- [x] Low (must work fully; zero degradation)

> The tool must work correctly for the core workflow (Build → Launch → Play → Save Sync). Degraded fallback modes (e.g., batch file launcher instead of C# wrapper) are acceptable ONLY when triggered by hostile environment conditions beyond our control, and must be explicitly communicated to the user.

### Uncertainty Tolerance

How much "unknown" can we live with?

- [x] Low (require high confidence in all critical paths)

> Critical paths — load order resolution, save file sync, crash detection — require high confidence before release. Non-critical paths (UI polish, report formatting) may proceed with medium confidence.

---

## 7. Primary Failure Concern (CRITICAL)

**What is the worst realistic outcome we want to avoid?**

### The Failure

A user runs the builder, launches the game, plays for 200 hours — and then discovers their save files were never synced back to MO2, OR their load order was silently corrupted, OR the tool overwrote their MO2 profile saves with corrupted data.

### Why This Matters

The target user is a heavy modder who may have invested hundreds of hours into a single playthrough. Losing that progress — or discovering the tool silently broke their setup — destroys trust not just in the tool but in the entire concept of escaping MO2's VFS. One catastrophic data-loss report kills adoption.

### How We'll Guard Against It

1. **Crash Detection**: Wrapper detects game crash and intentionally skips exit sync to prevent corrupted memory from writing back to MO2
2. **Save Quarantine**: Conflicting saves are moved to a quarantine folder, never overwritten silently
3. **Atomic Operations**: Load order injection (plugins.txt, loadorder.txt) is atomic — if injection fails, the game is blocked from launching
4. **Preflight Checks**: Active file locks, AV blocks, and OneDrive conflicts are detected BEFORE the build starts
5. **Transactional Deployment**: Checkpoints every 500 files; if deployment is interrupted, resume from checkpoint rather than restart from zero
6. **ANT-STR Test Suite**: Automated tests must validate invariant correctness (ownership stacks, fallback resolution, idempotency) before any release

---

## 8. Scope Definition

### What IS In Scope

- Reading MO2 profiles (modlist, load order, mod metadata) via MO2 API (`mobase`)
- Resolving file conflicts strictly by MO2 priority order into a dual-layer RAM manifest
- Deploying files via NTFS hardlinks (with explicit copy fallback + user notification)
- Incremental updates using tri-gate change detection (avoiding unnecessary I/O)
- Generating a C# wrapper executable for runtime load order injection and save syncing
- Preflight environment sensing (AV interference, OneDrive, file locks, cross-drive detection)
- HTML deployment report with categorized results (linked, skipped, failed)
- Transactional deployment with checkpoint resumption
- Crash-aware save sync (detect game crash, skip sync, quarantine conflicts)

### What IS NOT In Scope

- Fixing broken mods, missing masters, or load order conflicts
- Cross-platform support (Linux, macOS) — NTFS hardlinks are Windows-only
- Multi-profile simultaneous management
- Automated mod downloading or installation
- In-game overlay or runtime mod configuration UI
- Networked/cloud save synchronization
- Supporting games that don't use the standard Bethesda AppData/Documents pattern (without explicit game profile configuration)

### Why This Boundary Matters

Every feature added beyond "faithful mirror + defensive safety" dilutes the core trust guarantee. The tool's value is precision and safety — expanding scope into mod management, conflict resolution, or multi-platform support risks introducing the exact silent failures we're trying to eliminate.

---

## 9. Timeline & Constraints

**Target completion date or phase**: V4.0-RC (Release Candidate)

**Key milestones**:

| Milestone | Focus                                                              |
| --------- | ------------------------------------------------------------------ |
| v4.0-A    | Core Abstraction & MVC Refactoring (Stability)                     |
| v4.0-B    | Evidence-Based Verification & Transactional Deployment (Integrity) |
| v4.0-C    | Diagnostic Layer & Environment Sensing (Transparency)              |
| v4.0-RC   | Final Report Generator & Game Profile Onboarding                   |

**Resource constraints**: Single developer (CDC) + AI agents (GMN, ANT, GPT, PPX). Platform: Windows 10/11, NTFS only. Languages: Python 3.10+ (core engine, UI), C# (wrapper/sync), PySide/PyQt (GUI). Dependency: MO2 must be installed; tool reads from MO2's profile system via `mobase` API.

**Non-negotiable hard constraints**: Must NOT require administrator privileges. Must NOT modify MO2's internal files or profile data. Target folder MUST be on the same NTFS drive as MO2 mods (hardlink limitation). C# wrapper compilation must work even if .NET SDK is not installed (embed or fallback to batch launcher).

---

## 10. Explicit Non-Goals (Optional but Powerful)

**We will NOT do the following (even if suggested):**

- [x] We will NOT build multi-language support
- [x] We will NOT optimize for non-NTFS filesystems (exFAT, FAT32)
- [x] We will NOT implement a mod manager or replace MO2's core functionality
- [x] We will NOT add network features (cloud sync, remote deployment)
- [x] We will NOT support Linux/Wine or macOS
- [x] We will NOT build an automated test suite for non-Windows platforms

---

## 11. Decision Authority

**Who makes final decisions in case of conflict?**

- Strategic conflicts → **Director (Diko Hary Adhanto)**
- Technical conflicts → **Lead Developer (CDC)**, escalated to Director if unresolved
- Risk acceptance → **Director**
- Architecture / strategy pivots → **GMN (Global Architect)**, approved by Director

---

# Quick Reference: Document Metadata & Rules

## Naming Convention

**Format:** `{AGENT_CODE}-{DOCUMENT_CODE}-002-{VERSION}.md`

**Example:** `DIR-DI-002-v1.0.md`

**Components:**

- **AGENT_CODE**: DIR (Director role)
- **DOCUMENT_CODE**: DI (Director's Intent)
- **PROJECT_ID**: 002
- **VERSION**: v1.0 (Tier 1 Major Version)

## Document Specifics (DIR-DI)

- **Purpose**: Strategic Intent & Decision Constraint Layer (Tier 1, Foundation Document)
- **Created by**: Director
- **Input**: Director's strategic thinking, risk tolerance, and decision boundaries
- **Output**: Control layer that constrains GMN-STRAT
- **Approval**: Not audited; serves as authoritative source-of-truth for entire ecosystem
- **Critical to**: Ensuring consistent decision-making across all strategy documents
- **Impact on downstream**: GMN uses DI to ground STRAT; ANT uses STRAT + DI to scope WO; CDC uses WO for implementation
