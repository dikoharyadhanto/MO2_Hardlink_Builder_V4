# GMN-PRD-005-v3.3
> [!IMPORTANT]
> **Logic Dependencies**: Requires `GMN-PROJ-005-v4.0`. Incorporates Implementation Warnings from GPT-AUD1-v3.2.

## 1. Metadata
| Field | Value |
| :--- | :--- |
| **Project ID** | 005 |
| **Document Type** | Strategic PRD (PRD) |
| **Version** | v3.2 |
| **Status** | Implementation-Ready |
| **Lead Architect** | Gemini (GMN) |

---

## 2. Strategic Vision & Value
*   **Problem Statement**: V3's failure to handle environmental instability and its "silent" legacy bugs (Load Order, Save Sync) caused user drop-off.
*   **Proposed Solution**: A "Traceable Mirror" that uses the MO2 API for absolute truth and provides diagnostic evidence for all environment-related fallbacks.
*   **Primary Value Proposition**: **Actual Startup Time Reduction** (Target: < 30s total deployment) while maintaining 100% state parity with MO2.

---

## 3. Functional Requirements

### 3.1. Pillar A: Resilient Integrity
*   **REQ-01: Tiered Verification Policy**:
    *   **Quick**: Metadata (Size/Mtime).
    *   **Sampled**: Random 5% SHA256 check (95% confidence interval).
    *   **Full**: Full hash pass on manual request.
*   **REQ-02: Explicit Inode Validation**: Log every hardlink-to-copy fallback.
*   **REQ-03: Recoverable Deployment**: Implement `.deployment_state` with **Self-Validation (Checksum)**. If corrupted, fallback to Full Rebuild.
*   **REQ-04: API-Level Truth (mobase)**: Use `mobase` API. **Mandatory Fallback**: If API is unavailable, halt and report explicit "API Link Failure" to user.

### 3.2. Pillar B: Legacy Bug Resolution
*   **REQ-05: Save Game Sync [PENDING ROOT CAUSE]**: Implement atomic save moves. Implementation contingent on final V3 root cause confirmation.
*   **REQ-06: Wrapper Strategy**: Use "Native Swap" entry points. Specific test cases required for known Anti-Piracy mod conflicts (e.g., Starfield/Skyrim specific loaders).
*   **REQ-07: Path Normalization**: Use Shell API (SHGetFolderPath) to robustly detect Documents/AppData.

### 3.3. Pillar C: Technical & Performance
*   **REQ-08: Domain Boundary**: 
    *   **Python**: Logic, API interaction, UI, and Orchestration.
    *   **C#**: Atomic file syncing, Low-level process monitoring, and the Native Wrapper.
*   **REQ-09: Performance Baseline**: A mandatory "V3 Benchmark" must be taken before refactoring starts to measure improvement.

---

## 4. Success Indicators
*   **Primary Metric**: Deployment time < 30s for a 1000+ modlist (low delta).
*   **User Metric**: 90% reduction in "Load Order Mismatch" reports.
*   **Technical Metric**: 100% Inode parity for supported NTFS volumes.

---

## 5. Document Dependencies
*   **Parent Project**: `00_Strategy/GMN-PROJ-005-v4.0.md`.
*   **Logic Flow**: `00_Strategy/GMN-FLOW-005-v3.3.md`.
