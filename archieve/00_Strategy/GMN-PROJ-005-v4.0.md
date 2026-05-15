# GMN-PROJ-005-v4.0
> [!IMPORTANT]
> **Logic Dependencies**: Technical Review V3 + ChatGPT Audit v3.1 + User Strategic Directive.

## 1. Project Metadata
| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Project Name** | MO2 Hardlink Builder |
| **Version** | v4.0 |
| **Status** | Active |
| **Architect** | Gemini (GMN) |

---

## 2. Executive Summary
> **Purpose & Value:** MO2 Hardlink Builder v4.0 evolves from a fragile utility into an **Observable Deterministic Mirror**. The goal is not to guarantee a "perfect" world, but to guarantee a **traceable, consistent, and accountable** standalone environment. By acknowledging environment instability (AV, OneDrive, permissions) as a core challenge, v4.0 provides the diagnostic evidence needed to bridge the gap between "It should work" and "Why it didn't."

---

## 3. Strategic Goals
*   **Primary Objective**: Implement **"The Traceable Mirror"** — a system that maintains a deterministic link to the MO2 state and provides observable evidence for every operation.
*   **Goal 1: Reliable Delta Integrity**: Replace "guessing" with **Evidence-Based Delta Verification** (using inodes and targeted hashes) to ensure local files match the source intent.
*   **Goal 2: Environment-Aware Diagnostics**: Elevate failure attribution to a core pillar. The tool must sense and report external interference (AV blocks, OneDrive locks) rather than failing silently or ambiguously.
*   **Goal 3: Core Engine Abstraction**: Refactor for a game-agnostic core (`game_profiles.json`) to stabilize the architecture before scaling to new titles (Skyrim, Fallout, Starfield).

---

## 4. Core Constraints & Strategic Pillars
*   **Pillar: Resilience to Hostile Environments**: Assume the OS (OneDrive/AV) is actively interfering. Strategy: Preflight sensing and explicit "Hostile Environment" alerts.
*   **Pillar: Absolute Transparency**: No "Black Box" logic. Every hardlink, copy, and sync must be logged with its verification method (Inode match/Hash match).
*   **Technical Stack**: Python 3.10+, PySide/PyQt, C# (for high-performance Wrapper/Sync), Windows/NTFS.
*   **Architecture**: Strict MVC to allow for future CLI operation and automated integration testing.

---

## 5. Success Indicators (The "User-Trust" Metrics)
*   **Metric 1: Ambiguity Reduction**: 90% reduction in "Ambiguous Launch Failures" through explicit failure attribution (Tool vs. Mod vs. Environment).
*   **Metric 2: Verification Velocity**: Re-verification of 50k+ files in <3 minutes with a clear "Integrity Proof" report.
*   **Metric 3: Fallback Awareness**: 100% visibility into hardlink-to-copy fallback events; no more silent pseudo-hardlinks.

---

## 6. Single Source of Truth (SSoT) Location
*   **Main Directory**: `I:\Works\005 - MO2 Hardlink Builder V4\`
*   **Primary PRD**: `00_Strategy/GMN-PRD-005-v4.0.md`
*   **Logic Flow**: `00_Strategy/GMN-FLOW-005-v4.0.md`
*   **Archive**: `03_Build/archieve/MO2_Hardlink_Builder V3/`

---

## 7. Version History (v4.0 Roadmap)
*   **v4.0-A**: Core Abstraction & MVC Refactoring (Stability).
*   **v4.0-B**: Evidence-Based Verification & Transactional Deployment (Integrity).
*   **v4.0-C**: Diagnostic Layer & Environment Sensing (Transparency).
*   **v4.0-RC**: Final Report Generator & Game Profile Onboarding.
