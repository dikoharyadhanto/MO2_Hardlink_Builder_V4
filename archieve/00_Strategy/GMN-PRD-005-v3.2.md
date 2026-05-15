# GMN-PRD-005-v3.2
> [!IMPORTANT]
> **Logic Dependencies**: Requires `GMN-PROJ-005-v4.0`.

## 1. Metadata
| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Strategic PRD (PRD) |
| **Version** | v3.2 |
| **Status** | Draft (Refined via Audit) |
| **Lead Architect** | Gemini (GMN) |

---

## 2. Strategic Vision & Value
*   **Problem Statement**: V3's failure to handle environmental instability and its "silent" legacy bugs (Load Order, Save Sync) caused user drop-off.
*   **Proposed Solution**: A "Traceable Mirror" that uses the MO2 API for absolute truth and provides diagnostic evidence for all environment-related fallbacks.
*   **Primary Value Proposition**: **Actual Startup Time Reduction** (Target: < 30s total deployment) while maintaining 100% state parity with MO2.

---

## 3. Functional Requirements

### 3.1. Resilient Integrity (Claude Pillar)
*   **REQ-01: Tiered Verification Policy**:
    *   **Quick**: Metadata (Size/Mtime).
    *   **Sampled**: Random 5% SHA256 check.
    *   **Full**: Full hash pass on manual request.
*   **REQ-02: Explicit Inode Validation**: Log every hardlink-to-copy fallback.
*   **REQ-03: Recoverable Deployment**: Implement `.deployment_state` for "Resume from Checkpoint" logic.
*   **REQ-04: API-Level Truth (mobase)**: Use `mobase` API to prevent V3's "Load Order Reversal" bug and handle MO2 separators correctly.

### 3.2. Legacy Bug Resolution (Critical)
*   **REQ-05: Save Game Sync Fix**: Implement atomic save moves with timestamp verification to prevent "Unread Save" issues in non-standard Documents paths.
*   **REQ-06: Anti-Piracy/Wrapper Compatibility**: The C# Wrapper must use "Stealth Injection" or "Native Swap" (matching the game's original entry point) to avoid conflicts with anti-tamper mods.
*   **REQ-07: Path Normalization**: Use Shell API (SHGetFolderPath) to robustly detect Documents/AppData, resolving V3's failure on relocated system folders.

### 3.3. Technical Boundaries
*   **REQ-08: Python Domain**: All logic mapping, API interaction, and UI.
*   **REQ-09: C# Domain**: High-performance file syncing, low-level process monitoring, and the Native Wrapper.

---

## 4. Success Indicators
*   **Primary Metric**: Deployment time < 30s for a 1000+ modlist (assuming low delta).
*   **User Metric**: 90% reduction in "Load Order Mismatch" reports.
*   **Technical Metric**: 100% Inode parity for supported NTFS volumes.

---

## 5. Document Dependencies
*   **Parent Project**: `00_Strategy/GMN-PROJ-005-v4.0.md`.
*   **Logic Flow**: `00_Strategy/GMN-FLOW-005-v3.2.md`.
