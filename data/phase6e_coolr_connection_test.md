# Phase 6E — NASA Earthdata COOLR Connection Test

Generated: 2026-10-05

**No model trained. No frontend/backend changes. No full dataset downloaded.**

---

## Important: what I could and couldn't execute myself

**Step 2 (base service verification) — I actually did this live, successfully, in this session.** My conversational fetch tool reached `https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/COOLR_Events_Points/FeatureServer/0` directly and got a genuine response (reported below, not simulated).

**Steps 3-4 (India count query, 5 sample records) — I could not execute these.** Two tools tested:
- Code sandbox: direct `requests.get()` to `gis.earthdata.nasa.gov` returned `HTTP 403` with header `x-deny-reason: host_not_allowed` — confirmed by inspecting the response header itself.
- Conversational fetch tool: the base resource URL worked, but the parameterized `/query?where=...` endpoint was blocked by the same URL-indexing restriction seen in every prior phase (Phase 6B against COOLR's older endpoint, Phase 6D against Bhuvan).

**I'm not claiming PASS on anything I didn't actually verify.** `data/test_coolr_earthdata_connection.py` performs all 4 steps for you to run from your own unrestricted network.

---

## Step 2 Results (Genuinely Live, Verified This Session)

```
HTTP status: 200
Service name: COOLR_Events_Points
Geometry type: esriGeometryPoint
Spatial reference: EPSG:4326
MaxRecordCount: 2000
Supports Pagination: true
Supports Advanced Queries: true
Supports Statistics: true
```

**Full field list (22 fields, all confirmed real)**:
`objectid`, `source_name`, `source_link`, `event_id`, `event_date`, `event_time`, `event_title`, `event_description`, `location_description`, `landslide_category`, `landslide_trigger`, `storm_name`, `comments`, `method`, `image_type`, `sat_date_before`, `sat_date_after`, `country_name`, `country_code`, `citation`, `latitude`, `longitude`

This confirms every field you asked about in Step 5 of your task actually exists on this live service: `event_id`, `event_date`, `latitude`, `longitude`, `country_name`, `location_description`, `landslide_category`, `landslide_trigger`, `source_name`, `source_link`, `citation` — all present, all real, directly confirmed.

**Extent confirmed**: roughly -96.5 to 128.9 longitude, -30.6 to 40.1 latitude — consistent with a global dataset with some concentration toward Asia/global coverage, consistent with what Phase 6B's independent corroborating source reported (1,735 India events).

**Dataset description (from the live service metadata)**: this is NASA's newer, consolidated hosting of COOLR on the Earthdata GIS platform — same underlying data (GLC + Landslide Reporter citizen science + contributed inventories), same methodology as documented in the peer-reviewed citations in the `citation` field (Kirschbaum et al. 2010/2015, Juang et al. 2019, Amatya et al. 2021).

---

## Steps 3-4: Pending Your Script Run

Not executed in this session — genuinely unknown until you run `test_coolr_earthdata_connection.py`.

---

## How to Run

```bash
cd data
pip install requests
python test_coolr_earthdata_connection.py
```

The script prints each step's status as it runs, and writes the full result (including the 5 sample records if successful) to `data/coolr_earthdata_test_result.json`. Send that file back.

---

## FINAL STATUS (This Session)

**NASA_COOLR_CONNECTION: PASS** *(verified live — the base service responded with real, matching schema)*

**INDIA_QUERY: NOT YET TESTED** *(blocked by this assistant's own tool limitations — not a finding about the service itself; your script run will determine the real PASS/FAIL and, if PASS, the actual India event count and 5 real sample records)*
