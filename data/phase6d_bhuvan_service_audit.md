# Phase 6D — Bhuvan Landslide Inventory Service Audit

Generated: 2026-10-05 | Full structured data: `data/phase6d_bhuvan_service_audit.json`

**No model trained. No frontend/backend/model changes. No bulk data downloaded. No synthetic events created.**

---

## 1. Page Inspection

Directly fetched and inspected `https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/landslide/landslide.php?uname=empty`. Two separate products exist on this page, and it's important not to conflate them:

- **Seasonal Landslide Inventory** (2014/2017/2023 seasons) — all 8 NER states individually listed, each with an "Identify Features" click icon. No visible download or webservice link for this product.
- **Landslide Hazard Zones** (a different, static-susceptibility product) — state dropdown limited to only Himachal Pradesh, Meghalaya, Uttarakhand (just one NER state). This one *does* expose a "Webservice URLS" menu item and a working WMS call referencing a real layer (`disaster:RUOKKE_LHZ_01`).

**This distinction matters**: the hazard-zones product having some web-service exposure does not mean the seasonal event inventory does — and it's the event inventory we actually need.

## 2-3. Delivery Mechanism

**WFS is confirmed disabled — and this session found stronger evidence than before that it's platform-wide, not just this one layer.** Two independent sources:
1. This project's own Phase 1 direct test (`Service WFS is disabled`)
2. **New this phase**: an independent open-source project (a QGIS plugin cataloging 342 real Bhuvan layers) states directly: *"Bhuvan's WFS is switched off and answers HTTP 200 with an OWS exception body... The plugin never offers WFS."*

So this isn't a quirk of the landslide layer specifically — it's how Bhuvan's entire GeoServer backend is configured. The only live mechanism is **WMS**, and specifically **GetFeatureInfo** (point-click querying), consistent with the page's own "Identify Features" UI.

## 4. Exact Service URLs for 2014/2023 NER Layers

**Not confirmed for any NER state.** But I found something useful: a second independent real project directly queried Bhuvan's WMS and confirmed real, working layer names for Uttarakhand — `UK_SLIM_2017`, `ls_Uttarakhand_2014_SLIM` — suggesting a plausible naming pattern (`{STATE_CODE}_SLIM_{YEAR}`). **This is a credible, evidence-based hypothesis to test, not a confirmed fact for NER states** — the test script below attempts to discover the real names via GetCapabilities rather than guessing blindly.

## 5. Fields/Attributes Exposed

**Cannot be determined without executing a real query against an actual feature.** The same independent project's own GetFeatureInfo test (against Uttarakhand) returned an empty result at their test coordinate — a real, honest outcome (no feature at that exact point), not a failure of the mechanism. It confirms the query method *works*, but doesn't tell us the field schema when a feature *is* hit.

## 6-7. Small Test Query

**I attempted this myself and could not complete it** — documented precisely, not glossed over:

- **Conversational fetch tool**: successfully reached a WMS `GetLegendGraphic` call (confirms the service is live), but a parameterized `GetFeatureInfo` query was blocked by the same URL-indexing restriction encountered against COOLR in Phase 6B.
- **Code sandbox**: direct HTTP request returned `403` with header `x-deny-reason: host_not_allowed` — **confirmed via the response header itself**, this is my sandbox's own network whitelist blocking the domain, not NRSC rejecting the request.

Both tools tested, both blocked, for reasons specific to this assistant's environment — not evidence the service itself is inaccessible.

## 9. Pagination/Record Limits

Not really applicable in the way WFS/REST pagination works — GetFeatureInfo is inherently a **per-click, per-coordinate** query. There's no "fetch the next page of records" concept; you'd need to query many known coordinates individually, which is fundamentally unsuited to *discovering* an inventory of unknown locations (it's useful for *confirming* a landslide at a coordinate you already have from elsewhere).

## 10. Programmatic Download Feasibility

**No.** No WFS, no bulk REST export, no direct file download for the event records themselves found. GetFeatureInfo could theoretically help *cross-validate* events found via another source (like NESAC), but cannot *discover* an inventory on its own.

---

## Readiness Criteria (per your explicit decision rule)

| Criterion | Met? |
|---|---|
| 1. Can access actual inventory records | **No** |
| 2. Usable geometry/coordinates | Unconfirmed (plausible, not demonstrated) |
| 3. Can identify relevant NER states | **Yes** |
| 4. Programmatic/reproducible retrieval | **No** |
| 5. Clear NRSC/ISRO/Bhuvan provenance | **Yes** |

**Not all five criteria are met.**

---

## FINAL DECISION: NOT_READY_FOR_PHASE_6E

Bhuvan's seasonal inventory has clear, real provenance and covers the right states by name, but has no confirmed bulk-programmatic or reproducible retrieval path — only point-by-point querying against *already-known* coordinates. That's a structural limitation of the service (independently corroborated by two real third-party projects), not just this session's tool access.

**This doesn't change Phase 6C's conclusion**: NESAC remains the strongest candidate (`READY_WITH_MANUAL_ACCESS`). Bhuvan stays `VISUAL_ONLY`/point-query-only, now with stronger evidence for exactly why.

### Exact next action
Run `data/test_bhuvan_landslide_query.py` from your own unrestricted network to: (1) fetch the real WMS GetCapabilities document and search it for actual NER-state landslide layer names (replacing the Uttarakhand-pattern hypothesis with confirmed names), (2) attempt a GetFeatureInfo test at a real, already-known landslide coordinate in Meghalaya or Assam (e.g., from NESAC's or ASDMA's reports), (3) report back whatever comes back — even an empty response, like the independent project found, is useful information.
