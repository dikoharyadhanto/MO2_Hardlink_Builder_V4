# Director Manual Testing Report

> [!IMPORTANT]
> **Runtime Gate**: Create this optional document with `delta dir-str new` only after WO, ANT-STR, IMPL, and WALK are all `LOCKED` at the same version. DIR-STR records Director manual testing and does not gate WO, ANT-STR, IMPL, WALK, or PDC.

## 1. Metadata

| Field                 | Value                                     |
|:--------------------- |:----------------------------------------- |
| **Project ID**        | 002                                       |
| **Document Type**     | Director Manual Testing Report (DIR-STR)  |
| **Runtime State**     | PENDING / IN_PROGRESS / COMPLETE / LOCKED |
| **Director**          | DIR                                       |
| **Testing Date**      | [YYYY-MM-DD]                              |
| **WO Reference**      | `ANT-WO-002-v*.md`                        |
| **ANT-STR Reference** | `ANT-STR-002-v*.md`                       |
| **IMPL Reference**    | `CDC-IMPL-002-v*.md`                      |
| **WALK Reference**    | `CDC-WALK-002-v*.md`                      |

---

## 2. Manual Testing Scope

- **Flows tested**: [List product/workflow areas tested manually]
- **Environment used**: [Device/browser/runtime/data]
- **Build or commit tested**: [Identifier]
- **Known exclusions**: [What was not manually tested]

---

## 3. Director Observations

> Capture raw manual testing observations. ANT may later interpret these into technical follow-up work, but this document remains Director-owned evidence.

| Observation ID | Observation                                                                                                                                                                                                            | Expected Behavior                                                                             | Actual Behavior                                                                                                             | Severity |
|:-------------- |:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |:--------------------------------------------------------------------------------------------- |:--------------------------------------------------------------------------------------------------------------------------- |:-------- |
| OBS-001        | File yang sudah digenerate di standalone build hilang, atau sepertinya gagal dikembalikan ke MO2 generated files folder. berpotensi menyebabkan segala setingan saat in game akan hilang saat next incremental updates | Seharusnya Shader files dan kemungkinan file hasil generate lagi tidak perlu digenerate ulang | Buktinya saat saya incremental updates, saat launching skse_loader community shader caches selalu buat ulang dari awal lagi | HIGH     |

---

## 4. Strategic Alignment Assessment

> Does the delivered product still align with `DIR-DI` and the locked `GMN-STRAT`?

- **Intent alignment**: [Aligned / Partial / Misaligned]
- **Scope alignment**: [Aligned / Partial / Misaligned]
- **Success perception**: [Director assessment]
- **Concerns**: [Any concern that should be considered by ANT/GMN]

---

## 5. Manual Test Verdict

| Verdict          | Meaning                                                               |
|:---------------- |:--------------------------------------------------------------------- |
| PASS             | Manual testing found no blocking issue.                               |
| CONDITIONAL_PASS | Product is acceptable with documented limitations or follow-up work.  |
| FIX_AND_RETRY    | Director found issues requiring a new or superseded WO before retest. |
| FAIL             | Product is not acceptable; escalate for rework or strategy review.    |

**Selected Verdict:** [PASS / CONDITIONAL_PASS / FIX_AND_RETRY / FAIL]

**Rationale:** [Why this verdict was selected]

---

## 6. ANT Interpretation Queue

| Director Finding | ANT Technical Interpretation | Follow-Up                                             |
|:---------------- |:---------------------------- |:----------------------------------------------------- |
| OBS-001 | Likely generated runtime files under standalone `Data/` were either not harvested before cleanup, not redeployed from `standalone_generated_files`, or were excluded by path/extension policy. Current code includes `CleanerEngine.harvest_generated_files()` before cleanup and `LinkerExecutor.deploy_generated_overrides()` after main deploy. Scratch QA confirmed a `Data/CommunityShaders/Cache/shader_cache.bin` file is preserved into `mods/standalone_generated_files/CommunityShaders/Cache/` and survives cleanup. | Director retest in real MO2/SKSE flow. If cache still regenerates, open a new WO focused on generated-file path classification / allowlist behavior rather than v0.6 action queue architecture. |

---

## 7. Completeness Checklist

- [ ] Tested flows are listed.
- [ ] Environment/build tested is recorded.
- [ ] Observations distinguish expected vs actual behavior.
- [ ] Verdict is explicit.
- [ ] Strategic alignment assessment references DIR-DI/STRAT.
- [ ] Follow-up queue is clear enough for ANT to act on.

---

## 8. Runtime Lifecycle

```bash
delta dir-str new --file DIR-STR-002-v0.6md
delta dir-str advance
delta dir-str complete
delta audit record --str DIR-STR-002-v0.6md --actor Director --approve --note "Manual testing accepted"
delta dir-str lock --file DIR-STR-002-v0.6md
```

DIR-STR is optional evidence. Project closure is gated by locked PDC, not by DIR-STR.

---

# Quick Reference: Document Metadata & Rules

## Naming Convention

**Format:** `{AGENT_CODE}-{DOCUMENT_CODE}-002-{VERSION}.md`

**Example:** `DIR-STR-002-v0.6md`

## Document Specifics

- **Purpose**: Director manual testing observations and verdict.
- **Created by**: Director.
- **Prerequisite**: WO, ANT-STR, IMPL, and WALK are locked at the same version.
- **Output**: Optional manual testing evidence and follow-up signal.
- **Authority**: Does not override locked STRAT/WO or runtime gates by itself.
