# CLD Audit Critique — Implementation Warning Report
> [!IMPORTANT]
> **Logic Dependencies**: Requires `GMN-PROJ-005-v4.0` + `GMN-PRD-005-v3.2` + `GMN-FLOW-005-v3.2`

## Metadata

**Project ID:** 005
**Product Name:** MO2 Hardlink Builder
**Product Type:** CLI Tool / Automation / UI App
**Target Type (TPR):** MIXED (PROJ + PRD + FLOW)
**Type of Audit (AUD*):** Strategy (AUD1)
**Version:** v3.2
**Reviewer:** Claude (Backup Auditor)
**File:** `GPT-AUD1-MIXED-005-v3.2.md`

**Audit Mode:** Implementation Warning (Post-Revision)

**Audit Date:** 2026-04-18

---

# Context

Versi ini adalah audit pasca-revisi dari v3.1. Dokumen sudah diperbaiki dan status adalah **PASS**. Tujuan dokumen ini adalah menyampaikan **peringatan implementasi** yang harus diingat oleh Antigravity saat membuat action plan dan menerjemahkan dokumen ini ke task list.

---

# 1. Peringatan Kritis

## WARN-01: 70% Delta Threshold Tidak Punya Justifikasi Empiris

**Lokasi:** FLOW v3.2 Phase 2 Step 6

Angka 70% ditentukan secara arbitrary. Definisinya sudah diperjelas (70% of total file count) tapi tidak ada data yang membuktikan angka ini optimal.

**Risiko:** Jika angka ini terlalu tinggi, user yang update banyak mod sekaligus akan selalu dipaksa Full Rebuild meskipun delta masih bisa ditangani. Jk-a terlalu rendah, delta engine tidak efektif.

**Action for Antigravity:** Tentukan angka ini berdasarkan uji empiris di V4.0-B. Jangan hardcode 70% — jadikan konfigurabel per game profile.

---

## WARN-02: `mobase` API Dependency Tidak Punya Fallback

**Lokasi:** PRD v3.2 REQ-04, FLOW v3.2 Phase 2 Step 4

Seluruh sistem bergantung pada `mobase` API sebagai satu-satunya sumber kebenaran load order. FLOW menyebut "No heuristic guessing" tapi tidak ada path yang mendefinisikan apa yang terjadi jika `mobase` tidak bisa diquery (MO2 versi lama, MO2 tidak terinstall, atau API breaking change).

**Risiko:** Silent failure tanpa diagnosis, atau crash tanpa atribusi yang jelas.

**Action for Antigravity:** Definisikan explicit failure path untuk `mobase` unavailable — minimal log error dan halt dengan pesan yang jelas sebelum melanjutkan ke phase berikutnya.

---

## WARN-03: `.deployment_state` Tidak Punya Self-Validation

**Lokasi:** PRD v3.2 REQ-03, FLOW v3.2 Phase 0 dan Phase 3 Step 9

Sistem bergantung pada `.deployment_state` sebagai checkpoint, tapi tidak ada validasi integritas file state itu sendiri. Jika file ini corrupt (misalnya ditulis setengah karena power off atau AV interference), sistem kemungkinan akan behave secara unpredictable.

**Risiko:** Resume from Checkpoint yang menggunakan state corrupt akan menghasilkan build yang salah tanpa error yang terdeteksi.

**Action for Antigravity:** Implementasikan hash checksum atau schema validation saat membaca `.deployment_state`. Jika invalid, fallback ke Full Rebuild tanpa prompt tambahan.

---

# 2. Peringatan Major

## WARN-04: REQ-06 Anti-Piracy — "Stealth Injection" Adalah Asumsi Teknis Besar

**Lokasi:** PRD v3.2 REQ-06

PRD menyebut "Stealth Injection" atau "Native Swap" sebagai solusi tanpa mendefinisikan mod anti-piracy spesifik mana yang ditarget. Setiap mod anti-piracy bisa punya mekanisme deteksi yang berbeda. Ini bukan masalah programming biasa — ini reverse engineering territory.

**Risiko:** Solusi yang bekerja untuk satu mod anti-piracy mungkin gagal untuk mod lain. Tanpa test case spesifik per mod, REQ-06 hanya aspirasional.

**Action for Antigravity:** Identifikasi minimal 2-3 mod anti-piracy yang diketahui bermasalah di V3 dan jadikan sebagai test case explicit di V4.0-C. Jangan asumsikan satu solusi cover semua kasus.

---

## WARN-05: REQ-05 Save Game Sync — Akar Masalah Belum Dikonfirmasi

**Lokasi:** PRD v3.2 REQ-05

PRD mendefinisikan solusi ("atomic save moves with timestamp verification") tapi analisis akar masalah save game tidak terbaca di V3 belum selesai. Ini diakui sendiri oleh project owner.

**Risiko:** Solusi yang diimplementasikan mungkin miss akar masalah sebenarnya, menghasilkan bug yang sama dalam form berbeda di V4.

**Action for Antigravity:** Tandai REQ-05 sebagai **Pending Root Cause Analysis** di action plan. Implementasikan solusinya di V4.0-C setelah root cause dikonfirmasi, bukan di V4.0-B.

---

## WARN-06: Labeling "Claude Pillar / ChatGPT Pillar" Masih Ada di PRD

**Lokasi:** PRD v3.2 Section 3.1

Ini adalah artefak proses desain yang seharusnya sudah dihapus dari dokumen produksi. Claude Code saat membaca dokumen ini bisa menginterpretasi label ini sebagai ownership atau scope yang lebih loose dari yang dimaksudkan.

**Risiko:** Ambiguitas ownership antar layer implementasi.

**Action for Antigravity:** Hapus labeling ini dari PRD sebelum mengirim ke Claude Code. Ganti dengan label netral seperti "Pillar A: Resilient Integrity" dan "Pillar B: Observability".

---

# 3. Peringatan Minor

## WARN-07: Scope Fallout/Starfield Masih di PROJ v4.0

PROJ v4.0 masih menyebut ekspansi ke Fallout dan Starfield sebagai Goal 3. Ini belum diisolasi ke roadmap terpisah.

**Risiko:** Antigravity bisa mengalokasikan upaya untuk abstraksi multi-game di V4.0-A padahal V3 masih punya bug aktif.

**Action for Antigravity:** Treat Goal 3 sebagai roadmap item post-V4.0-RC, bukan scope aktif di V4.0-[B-C].

---

## WARN-08: Primary Metric "<30 Detik" Belum Ada Baseline Pengukuran

**Lokasi:** PRD v3.2 Success Indicators

Target deployment <30 detik untuk 1000+ modlist adalah metric yang konkret, tapi tidak ada baseline V3 yang terdokumentasi sebagai pembanding.

**Risiko:** Tidak bisa membuktikan improvement V4 vs V3 secara objektif saat rilis.

**Action for Antigravity:** Sertakan benchmark V3 deployment time sebagai task awal di V4.0-A sebelum refactoring dimulai. Ini data yang harus diambil sekarang, bukan nanti.

---

# 4. Ringkasan Warning untuk Action Plan

| ID | Severity | Phase Target | Status |
|---|---|---|---|
| WARN-01 | Kritis | V4.0-B | Perlu uji empiris sebelum hardcode |
| WARN-02 | Kritis | V4.0-A | Fallback path untuk mobase harus didefinisikan |
| WARN-03 | Kritis | V4.0-B | Self-validation untuk .deployment_state |
| WARN-04 | Major | V4.0-C | Test case anti-piracy spesifik dibutuhkan |
| WARN-05 | Major | V4.0-C | Root cause save game harus dikonfirmasi dulu |
| WARN-06 | Major | Pre-V4.0-A | Hapus label Pillar dari PRD sekarang |
| WARN-07 | Minor | Post-RC | Isolasi scope Fallout/Starfield |
| WARN-08 | Minor | V4.0-A | Ambil baseline V3 sebelum refactoring |

---

# 5. Gatekeeper Signal

**PASS** → Execution allowed

Antigravity boleh mulai V4.0-A. WARN-02, WARN-06, dan WARN-08 harus diselesaikan **sebelum V4.0-A selesai**. WARN-01 dan WARN-03 harus diselesaikan **sebelum V4.0-B dimulai**.

---

# 6. Confidence Score

**Understanding:** 8/10
**Logic:** 7/10
**UX:** 6/10
**Execution readiness:** 7/10

**Overall:** 7/10
