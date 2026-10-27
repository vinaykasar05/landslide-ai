# Phase 6A — Real Historical Landslide Event + Environmental Data Research

Generated: 2026-10-05 | Full structured data: `data/phase6a_event_data_research.json`

**This phase is research only.** No model was trained, no files were modified except these two deliverables, no synthetic data was created anywhere in this report.

---

## 1. Executive Summary

Real, dated, coordinate-level landslide event data for India **does** exist and is freely accessible — the single biggest finding of this phase is **COOLR** (NASA's Cooperative Open Online Landslide Repository), which I verified directly: a live-fetched field schema confirms real `event_date`, `latitude`, `longitude`, and trigger/category fields, and an independently-sourced analysis citing the same database reports **1,735 real India events (2000–2020) with verified coordinates**. This is a materially better picture than this project's earlier (Phase 1) finding that NASA's standalone Global Landslide Catalog was sparse for India — COOLR supersedes that by merging in citizen-science reports and other catalogs.

A second strong lead, **NESAC's Seasonal Landslide Inventory for NER**, is uniquely valuable because it's NER-specific by design and the agency has *already* paired each event with 24-hour pre-event rainfall from GPM — but I could not confirm in this session whether it's released in a machine-readable form or only as a PDF report, and the NESAC geodata portal (NeSDR) blocked automated access.

For environmental data, real historical rainfall at event-appropriate resolution exists via **GPM IMERG** (10km, sub-daily, free with registration) and **CHIRPS** (5km, daily, zero registration). Soil moisture has a real gap: satellite-observed data (SMAP) only goes back to 2015; anything older must rely on reanalysis (ERA5-Land or this project's existing NASA POWER integration), which is real but model-derived, not a direct measurement — this must be labeled accurately, not blurred.

The existing `India_dataset.gpkg` **cannot** supply the dated-event dimension — Phase 3 already established this (124,553 slope-unit polygons with a static label, no event dates) and nothing in this phase's research contradicts that.

**Final decision: PARTIALLY_FEASIBLE.** Nothing found here is a fundamental blocker; what remains is concrete, scoped follow-up work (see Section 13), not a dead end.

---

## 2. Historical Landslide Event Datasets

| Dataset | Org | Status | NER coverage | Notes |
|---|---|---|---|---|
| **COOLR** (Landslide Points/Polygons) | NASA GSFC | VERIFIED_LIVE | India: 1,735 events confirmed (2000-2020); NER-specific subset not yet queried | Real `event_date`/lat/lon/trigger fields confirmed via live schema fetch. Public ArcGIS REST API, no auth observed. Downloadable as CSV/Shapefile/GDB. |
| **NESAC Seasonal Landslide Inventory (NER)** | NESAC / NER-DRR | VERIFIED_CITED | NER-specific by design (374 events, 2025 alone) | Already pairs events with GPM 24h pre-event rainfall. Machine-readable format NOT confirmed - may be PDF-only. NeSDR portal blocked automated access this session. |
| **NRSC/Bhuvan Landslide Atlas** | NRSC/ISRO | VERIFIED_LIVE (Phase 1 finding, reused) | All 8 states listed, but WFS confirmed disabled | Not bulk-accessible - interactive map-click only. Re-confirms Phase 1's finding. |
| **GSI Bhukosh landslide database** | GSI | VERIFIED_CITED | Not verified at bulk scale | Real and used in published research (19-event Mizoram study), but no confirmed bulk API - only demonstrated via manual small-scale compilation. |
| **Academic Mizoram inventory (2016-2025)** | Independent researchers | VERIFIED_LIVE | Mizoram/Aizawl only, not all 8 states | Real data table directly observed (e.g. "LS17, 2024-08-28, Kawnpui, 24.03, 92.62"). Too small/narrow as a primary source; useful as a validation subset. |

**Full details, including every requested field (format, API, license, limitations) per dataset: see the JSON file's `part_a_landslide_event_datasets` array.**

---

## 3. Environmental Datasets (Overview)

Investigated: rainfall, soil moisture, temperature/humidity (bundled with rainfall sources - most rainfall APIs above also report these), elevation/slope/aspect (already real and integrated in this project per earlier phases), land cover/NDVI/geology (confirmed NOT integrated, per Phase 5B's audit - no new finding changes that here), ground movement and pore-water pressure (previously confirmed to have no viable simple API - re-confirmed, no new source found in this phase that changes that conclusion).

Full structured records: JSON `part_b_c_d_environmental_datasets`.

---

## 4. Rainfall Source Comparison (Part C)

| Source | Resolution | Temporal | History | Access | Best for |
|---|---|---|---|---|---|
| NASA POWER (already integrated) | ~50km | Daily | 1981-present | Free, keyless | Already proven in this project; coarse for precise event triggering |
| **GPM IMERG** | **~10km** | **Half-hourly** | 1998/2000-present | Free, Earthdata login required | **Best fit for event-based dynamic ML** - fine enough resolution and sub-daily detail for antecedent-rainfall features |
| ERA5-Land | ~9km | Hourly | 1950-present | Free, CDS API key required | Longest history; reanalysis not direct observation |
| CHIRPS | ~5km | Daily | 1981-present | **Free, zero registration** | Best zero-friction option; good for the STATIC long-term rainfall climatology feature flagged missing in Phase 5B |
| IMD gridded | Varies | Varies | Varies | Access not independently confirmed this session | Most locally authoritative if accessible - needs manual follow-up |

**NASA POWER was deliberately NOT auto-selected just because it's already integrated**, per the task's explicit instruction. For the dynamic model specifically, **GPM IMERG is the better-justified choice** given its resolution and sub-daily granularity - a genuinely different recommendation than what's already in the project.

---

## 5. Soil Moisture Source Comparison (Part D)

| Source | Data type | History | Resolution | Access |
|---|---|---|---|---|
| NASA POWER GWETTOP (integrated) | Reanalysis/land-surface model | 1981-present | ~50km | Free, keyless |
| **NASA SMAP** | **Satellite observation** | **2015-present only** | 9-36km | Free, Earthdata login |
| ERA5-Land soil water | Reanalysis | 1950-present | ~9km | Free, CDS key |

**Critical labeling requirement, consistent with this project's established honesty rules:** SMAP is a genuine satellite *observation*; POWER and ERA5-Land are *model/reanalysis outputs*. These must never be presented interchangeably. For events before 2015, satellite-observed soil moisture simply does not exist — reanalysis is the only real option, and must be labeled as such.

---

## 6. Existing GeoPackage Assessment (Part E)

**Cannot supply the dated-event dimension.** This is not a new finding — Phase 3's methodology audit already established the 124,553 rows are static slope-unit polygons with a presence/absence label, not dated events, and nothing researched in this phase contradicts that. What *can* carry over: the static terrain/environmental covariates (elevation, slope, lithology, etc.) for spatial context, but the event-date dimension must come entirely from Part 2's sources.

---

## 7. Recommended Time-Linked Training-Table Design (Part F)

Only including fields for which a legitimate, verified source exists from this research:

| Field | Source | Status |
|---|---|---|
| `event_id` | COOLR `event_id` / `globalid` | Verified real field exists |
| `event_date` | COOLR `event_date` | Verified real field exists |
| `latitude`, `longitude` | COOLR `latitude`/`longitude` | Verified real fields exist |
| `landslide_label` | Always 1 for COOLR-sourced rows (see Part G for negatives) | — |
| `rainfall_24h`, `rainfall_72h`, `rainfall_7d` | GPM IMERG, aggregated from half-hourly | Real source, access requires registration |
| `antecedent_rainfall` (longer window, e.g. 30-day) | GPM IMERG or CHIRPS | Real source |
| `soil_moisture` | SMAP (events ≥2015) or ERA5-Land/POWER reanalysis (older events, labeled as such) | Real, but type must be tracked per-record |
| `elevation`, `slope`, `aspect` | Already-integrated ASTER GDEM pipeline (point-based — same spatial-support caveat as Phase 5B) | Real, already built |
| `NDVI`, `land_cover`, `geology` | NOT YET INTEGRATED — same gap identified in the Real-Data Audit and Phase 5B | SOURCE_REQUIRED |

**Explicitly NOT included** (no verified source found): ground movement, pore-water pressure — consistent with every prior phase's finding.

---

## 8. Negative-Sample Strategy (Part G) — Recommendation Only, Not Implemented

Research-recommended approach, in order of scientific defensibility:

1. **Spatially matched controls**: for each real event location, sample nearby points with comparable terrain (similar slope/elevation band) but no recorded landslide — defensible because it isolates the rainfall/temporal trigger from terrain-driven susceptibility, which the static model already addresses separately.
2. **Temporal non-event windows at the same locations**: for a location with a known event, sample other real dates (with real rainfall data) when no event was recorded — directly uses the COOLR+IMERG pairing already established above, no new data source needed.
3. **Grid/cell-based sampling** across the NER region, excluded-buffer around all known event locations/dates, weighted by real population/accessibility (to counter the reporting-bias limitation flagged in Section 2).

**Not implemented in this phase, per explicit instruction** — this is a recommendation for Phase 6B or later.

---

## 9. Event/Environment Join Methodology (Part H)

- **Spatial matching**: nearest-grid-cell lookup against the chosen rainfall product's native grid (IMERG: 0.1°/~10km; CHIRPS: 0.05°/~5km) — direct nearest-cell lookup is defensible at these resolutions without interpolation, given COOLR's own location-accuracy field already carries uncertainty of a similar or larger magnitude (exact/1km/5km/etc. per record).
- **Temporal matching**: align to the IMERG/CHIRPS native time grid (half-hourly or daily); for an event at a given `event_date` (and `event_time` where available), aggregate the preceding N hours/days directly from the grid — no interpolation needed given sub-daily data is already available.
- **Timezone handling**: COOLR's `event_date`/`event_time` fields need explicit timezone verification before pairing with UTC-referenced satellite products — NOT verified in this session, flagged as a required check before any real join is built.
- **Missing-data handling**: per this project's established rule throughout every phase — **do not silently fill gaps**. A record with no available rainfall grid cell (e.g. ocean-adjacent coordinate artifact) should be excluded and reported, not imputed.
- **Maximum acceptable spatial/temporal gap**: not yet defined — this is a modeling decision for Phase 6B, informed by COOLR's own `location_accuracy` field (use it to filter out low-precision records rather than silently accepting them).
- **Interpolation**: not recommended for rainfall given IMERG/CHIRPS are already fine-grained relative to COOLR's typical location accuracy — nearest-cell lookup is more defensible than interpolating across what may be a coarser source of positional uncertainty.

---

## 10. Data Quality and Leakage Risks

- **Reporting bias** (Section 2): events near roads/population are overrepresented versus remote slope failures — a real limitation to document in any eventual model's metadata, not a reason to discard the source.
- **Mixing data types without labeling**: satellite-observed soil moisture (SMAP) vs. reanalysis (ERA5-Land/POWER) must never be silently blended as equivalent — same rule already established and enforced in this project's static-model work.
- **Location-accuracy variance**: COOLR's own accuracy field must be used as a filter, not ignored, before any precise spatial join.
- **No leakage risk from the static model's known issues** (lsd/SI/su/ID) applies here — this is an entirely separate dataset construction effort with its own, different leakage surface (e.g., using a value computed *after* an event, like "total rainfall for the event" rather than "rainfall *before* the event," would be a dynamic-model-specific leakage risk to watch for in Phase 6B).

---

## 11. Access/Credential/Download Requirements

| Source | Requirement |
|---|---|
| COOLR | None observed |
| CHIRPS | None |
| NASA POWER (already integrated) | None |
| GPM IMERG (GES DISC route) | Free NASA Earthdata Login (urs.earthdata.nasa.gov) |
| NASA SMAP | Free NASA Earthdata Login |
| ERA5-Land | Free Copernicus CDS account + API key |
| IMD gridded rainfall | Not independently confirmed - likely requires registration via IMD's portal |
| NESAC/NeSDR | Blocked automated access this session - manual browser access or direct agency contact needed to determine real requirement |

---

## 12. Feasibility Assessment (Part I)

**PARTIALLY_FEASIBLE**

Real, verified, accessible event data exists (COOLR, 1,735 real India events). Real, verified, appropriately-resolved rainfall exists (IMERG, CHIRPS). What's missing is not a fundamental data gap but specific, scoped verification work: the NER-specific event subset count, NESAC's exact data format, and pre-2015 soil moisture is reanalysis-only (a real but documented and labelable limitation, not a blocker).

---

## 13. Recommended Next Phase

**Immediate next step**: run a live, geometry-filtered query against the COOLR REST API —

```
https://maps.nccs.nasa.gov/mapping/rest/services/landslide_viewer/Landslide_Points/MapServer/0/query
  ?where=1=1
  &geometry={NER bounding box}
  &geometryType=esriGeometryEnvelope
  &inSR=4326
  &spatialRel=esriSpatialRelIntersects
  &outFields=*
  &f=json
```

This was attempted in this session but blocked by this assistant's own tool permissions, not a real access restriction — it's a simple, free, unauthenticated request your machine can run directly. This single query would resolve the single largest open question in this report (the real NER-specific event count) before any further design work.

**Secondary**: attempt manual browser access to NeSDR / direct NESAC contact to determine whether the Seasonal Landslide Inventory is available in a machine-readable form.

---

## 14. Exact Source URLs

- COOLR viewer: https://landslides.nasa.gov/viewer
- COOLR data/citation page: https://gpm.nasa.gov/landslides/data.html
- COOLR REST API (Polygons): https://maps.nccs.nasa.gov/mapping/rest/services/landslide_viewer/Landslide_Polygons/MapServer
- COOLR REST API (Points): https://maps.nccs.nasa.gov/mapping/rest/services/landslide_viewer/Landslide_Points/MapServer
- NESAC: https://nesac.gov.in/
- NER-DRR programme: https://www.nerdrr.gov.in/
- NeSDR: https://www.nesdr.gov.in/ (blocked automated access this session)
- NRSC Bhuvan landslide portal: https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/landslide/landslide.php
- GSI Bhukosh: https://bhukosh.gsi.gov.in
- GPM IMERG: https://gpm.nasa.gov/data/imerg
- NASA Earthdata registration: https://urs.earthdata.nasa.gov/users/new
- CHIRPS: https://www.chc.ucsb.edu/data/chirps
- Copernicus CDS (ERA5-Land): https://cds.climate.copernicus.eu
- NASA SMAP: https://smap.jpl.nasa.gov
- Academic Mizoram inventory: https://arxiv.org/pdf/2606.23281

---

## FINAL DECISION: PARTIALLY_FEASIBLE

**Recommended next step: run the COOLR NER bounding-box query (Section 13) to resolve the real event count before proceeding to any dataset design work.**
