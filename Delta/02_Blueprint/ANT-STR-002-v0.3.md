# ANT-STR-002-v0.3 — Test Strategy: True Incremental Updates

> [!IMPORTANT]
> **Logic Dependencies**: `ANT-WO-002-v0.3`
> **Context**: Validates the Inode Fast-Path skipper and Surgical Orphan Cleanup to ensure deployments are perfectly accurate with zero false positives (i.e., it never skips a file that actually changed).

---

## 1. Metadata

| Field | Value |
| :--- | :--- |
| **Project ID** | 002 |
| **Document Type** | Strategic Test Plan (STR) |
| **Version** | v0.3 |
| **Issued By** | ANT — Technical Foreman |
| **Execution** | Automated Simulation / Hybrid |

---

## 2. Test Cases

### STR-INC-01: Baseline Full Build (Control)

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Create a simulated MO2 profile with dummy files. | Profile populated. |
| 2 | Execute a "Clean Deploy" (Full Rebuild). | `LinkerExecutor` processes all files. |
| 3 | Measure execution time. | Baseline time established. |

---

### STR-INC-02: Zero-Delta Incremental Build

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Trigger deployment without changing any files. | `ManifestDeltaAnalyzer` reports `Delta 0.0%`. |
| 2 | `LinkerExecutor` executes. | The Inode Fast-Path skips all files instantly. Time must be < 2 seconds. |

---

### STR-INC-03: Condition 1 & 2 — Add and Remove Files

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Delete 3 existing files from the MO2 profile (Condition 2: Removal). | Files removed from source. |
| 2 | Add 3 brand new files to the MO2 profile (Condition 1: Addition). | Files added to source. |
| 3 | Execute deployment. | Incremental branch triggered. |
| 4 | Verify Filesystem | The 3 removed files are surgically deleted. The 3 new files are hardlinked. All other files are skipped. Second build time is significantly faster than baseline. |

---

### STR-INC-04: Condition 3 — Modify / Priority Change

| Step | Procedure | Expected Result |
| :--- | :--- | :--- |
| 1 | Simulate a MO2 modlist priority change (e.g., Mod B now wins over Mod A for `texture.dds`). | Manifest source path for `texture.dds` changes. |
| 2 | Manually modify the content of another file (e.g., user edits `config.ini`). | Source file inode/content changes. |
| 3 | Execute deployment. | Incremental branch triggered. |
| 4 | Verify Target Files | The Inode Fast-Path detects the mismatch. `texture.dds` is correctly relinked to Mod B. `config.ini` is correctly relinked to the modified version. |

---

## 3. UAT Sync (Golden Pass Requirements)

- **Technical Verdict**: PENDING implementation of `ANT-WO-002-v0.3`.
- **Director Override**: Awaiting manual verification reports.

*Golden Pass will be issued when all STR-INC tests pass, proving that the Fast-Path never creates a false positive (skipping a file that actually needed an update).*
