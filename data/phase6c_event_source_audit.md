# Phase 6C — Alternative Event-Data Source Audit

Generated: 2026-10-05 | Full structured data: `data/phase6c_event_source_audit.json`

**No model trained. No frontend/backend/model changes. No synthetic events created anywhere.**

---

## COOLR Status

Per your explicit instruction, COOLR is marked **INACCESSIBLE** given your machine's 90-second timeout, and is **not used anywhere in this report**. For context only (not as grounds to override your instruction): this session's own earlier testing (Phase 6B) found the service live and unauthenticated when queried from here — your timeout may reflect a network/firewall condition specific to your environment rather than the service being down. That's noted for your awareness, not asserted as fact, and changes nothing about COOLR's status in this phase.

---

## Sources Audited

| Source | Coverage | Dated events? | Access | Status |
|---|---|---|---|---|
| NRSC/Bhuvan Landslide Atlas | All 8 states | Seasonal only, not per-event | WFS confirmed disabled (Phase 1 finding, reused) | **VISUAL_ONLY** |
| **NESAC Seasonal Landslide Inventory (NER)** | All 8 states, by design | Likely yes (2025 report confirmed to include per-event pre-rainfall) | **robots.txt explicitly blocks automated access** (directly tested this session) — human browser access not restricted | **READY_WITH_MANUAL_ACCESS** |
| GSI Bhukosh/Bhusanket | National | Not verified at bulk scale | No stable public API found (repeated research passes) | **VISUAL_ONLY** |
| ASDMA (Assam) Landslide Damage Report | Assam only | Single report, not a multi-year inventory | Real, directly downloadable PDF | **VISUAL_ONLY** (single state, likely narrative not tabular) |
| Academic Mizoram inventories (778-event; 19-event) | Mizoram only | Yes | Real, proven in actual ML research — but single-state | **VISUAL_ONLY** (exact access method for the 778-event set not confirmed) |
| COOLR | — | — | User-confirmed timeout | **INACCESSIBLE** (per instruction) |

Full per-field detail (all 16 requested fields per source) is in the JSON file.

---

## What's New This Phase

**A concrete, checkable confirmation that NESAC's hosting site blocks automated access specifically** — I directly attempted to fetch `https://www.nerdrr.gov.in` and received `ROBOTS_DISALLOWED: Site disallows automated access`. This is a real, verifiable restriction (robots.txt), not a guess or a timeout. Importantly, this blocks *automated* tools — not necessarily a human browsing the site directly, which is why this is classified `READY_WITH_MANUAL_ACCESS` rather than `INACCESSIBLE`.

**A real peer-reviewed citation confirming NESAC's reports are genuinely used as ML training data**: Badavath, Kumar & Sahoo (2025), published in the journal *Landslides*, cite the exact NESAC-SR-304-2023 report as their data source for a real rainfall-landslide study in Meghalaya. This isn't a dataset that merely *exists* — real researchers have already successfully extracted usable data from it.

**A second real finding**: a peer-reviewed Mizoram-specific study used a 778-event dated landslide inventory, split 70/30 for actual model training and validation. Single-state only, but concrete proof that NER-region historical inventories of meaningful size do exist and have been used exactly the way this project intends.

---

## Final Decision

**A. Do we have a real dated landslide-event dataset that can be extracted now?**
**No.** Every source found this phase is either `VISUAL_ONLY` or requires manual (non-automated) access.

**B. If yes, which exact source?**
N/A.

**C. Strongest candidate, and exact manual access required:**
**NESAC's Seasonal Landslide Inventory for NER** (annual technical reports — confirmed real documents exist for at least 2021, 2023, and 2025, with specific document numbers like NESAC-SR-304-2023). It's the strongest candidate because it's NER-specific by design, confirmed real, actively used in peer-reviewed research, and already pairs events with pre-event rainfall. The only barrier is automated access — a human needs to visit `https://www.nerdrr.gov.in` directly in a standard browser, locate the available annual reports, and download them.

**D. Next concrete action for you:**
Manually browse to `https://www.nerdrr.gov.in` (or `https://nesac.gov.in`) in a regular browser, download whichever Seasonal Landslide Inventory NER reports you can find (2021, 2023, 2025 confirmed to exist — there may be others), and tell me what their actual internal structure looks like: a clean per-event table with dates/coordinates, or narrative text requiring manual transcription. That determines whether Phase 6D can build an automated PDF-table-extraction script, or whether this needs manual data entry instead.

---

## FINAL STATUS: No source is READY_FOR_EXTRACTION this phase.

**Recommended next step: manually retrieve the NESAC NER seasonal inventory PDFs and report their structure back.**
