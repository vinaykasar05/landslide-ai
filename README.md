# AI-Based Landslide Early Warning System (NER India)

Full-stack project: real-data ML risk prediction + location search + alerts,
modeled after the SIH26001 "NER-Alert" reference dashboard.

**Build status:** Backend restructure + real-data foundation complete (this update).
See "Backend architecture" below for the full data flow plan.

**Build status:** Phase 1 (architecture cleanup) complete. See "Roadmap" below.

## Project structure
```
landslide_project/
├── data/
│   ├── fetch_landslide_data.py   # REAL data: NASA GLC + NASA POWER rainfall (run with internet)
│   ├── generate_sample_data.py   # SYNTHETIC starter data (for testing now)
│   └── landslide_training_data.csv
├── model/
│   ├── train_model.py            # trains Random Forest on rainfall features
│   └── landslide_model.pkl       # trained model (already generated)
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app entry - wires everything together
│   │   ├── config.py              # all settings (env vars, thresholds, paths)
│   │   ├── locations_data.py      # the 8 seed NER monitored stations (now with elevation/slope/state/district)
│   │   ├── models/                # SQLAlchemy ORM models (the DB tables)
│   │   ├── database/              # DB connection/session setup (separate from models)
│   │   ├── schemas/                # Pydantic request/response validation
│   │   ├── services/
│   │   │   ├── geocoding.py       # place name -> lat/lon (Nominatim)
│   │   │   ├── weather.py         # real rainfall aggregates (NASA POWER) + forecast - feeds the ML model
│   │   │   ├── open_meteo.py      # real CURRENT weather + hourly precipitation (Open-Meteo) - new
│   │   │   ├── ml_model.py        # loads & runs the trained model
│   │   │   └── notifications.py   # email (SMTP) + SMS (Twilio) alerts
│   │   └── routes/
│   │       ├── locations.py       # GET /locations           (existing, used by current frontend)
│   │       ├── predict.py         # GET /predict, /forecast  (existing, used by current frontend)
│   │       ├── alerts.py          # GET /alerts, POST /alerts/check-and-notify (existing)
│   │       ├── incidents.py       # GET/POST /incidents      (existing)
│   │       ├── health.py          # GET /api/health           (new)
│   │       ├── gis.py             # GET /api/gis/stations     (new)
│   │       └── weather.py         # GET /api/weather          (new)
│   ├── requirements.txt
│   └── .env.example               # copy to .env and fill in real credentials
└── frontend/
    └── index.html                 # dashboard UI (unchanged - talks to the same /locations, /predict, etc.)
```

## Backend architecture (data flow)
```
Frontend
    |
FastAPI Backend
    |
Data Services
    +-- Weather/Rainfall API (NASA POWER - 24h/72h/7d aggregates for the model)
    +-- Current Weather API  (Open-Meteo - temperature/humidity/pressure/wind, new)
    +-- Sensor data          (still frontend-simulated - next phase)
    +-- Database             (SQLite - incidents, alert subscriptions/log)
    |
Feature Engineering (not yet built)
    |
ML Landslide Risk Model (trained Random Forest, already live via /predict)
    |
Risk Score / Risk Level
    |
Frontend
```
**New `/api/*` endpoints are additive** - they don't replace `/locations`, `/predict`,
`/alerts`, `/incidents`, which the current frontend still calls and which still work
exactly as before. The `/api` namespace is where new backend-foundation work lives
until the frontend is ready to switch over to it.

## Real-data environment + monitoring layer (this update)
Nine factors were audited; three were implemented with genuine real sources,
six were deliberately NOT implemented with specific documented reasons
(see the Real-Data Audit spreadsheet and the table below).

**Implemented (real):**
- **Terrain-derived aspect/ruggedness/relief** - computed from the *same*
  real DEM grid already fetched for slope (zero extra API calls). Labeled
  "derived from real DEM", never called a direct measurement.
- **Soil moisture** - NASA POWER's `GWETTOP` parameter (MERRA-2 reanalysis
  surface soil wetness). Reuses the already-proven NASA POWER integration
  with zero new credentials. Explicitly labeled `"data_type": "reanalysis/
  land-surface-model output"` - NOT called a satellite observation, NOT
  called an IoT sensor, anywhere.
- **Current weather** - Open-Meteo, now **batched** (one request for all 8
  stations, following the same fix pattern as the terrain 429 issue) instead
  of one request per station.

**Deliberately not implemented, with reasons:**
| Factor | Why not this round |
|---|---|
| Geology | GSI Bhukosh has no stable public point-query REST API I could verify. Existing hardcoded text now explicitly flagged `"status": "unverified_hardcoded"` in the API, not silently presented as real. |
| Land cover | ESA WorldCover is real and keyless, but point-querying its public COGs requires `rasterio`/GDAL - high risk given this exact machine's earlier scikit-learn/DLL install problems. |
| Pore-water pressure | No public API exists for arbitrary coordinates - fundamentally a site-specific instrumented measurement. Now returns `"status": "unavailable"` with the required real source documented, never a fabricated kPa value. |
| Ground movement | Sentinel-1 InSAR needs real SAR processing (SNAP/ISCE), not a REST call. Returns honest `"unavailable"`, explicitly NOT called an inclinometer. |
| Drainage / rivers | OpenStreetMap Overpass API is real and accessible - scoped out this round as a distinct engineering task, not rushed. |
| Roads / highways | Same as drainage. The existing "Highway Corridors" tab's hardcoded risk values are now visibly labeled "DEMO DATA - NOT REAL" in the UI itself, not just in documentation. |

**Frontend**: Soil Moisture, Pore Water Pressure, and "Inclinometer Tilt"
(renamed "Ground Movement") cards in the Soil & Rain Sensors panel now show
real data or an honest "Data unavailable" message with the required source -
never the old fabricated numbers. The 24h trend chart (which plotted a
fabricated hourly history) was replaced with an honest message, since no real
sub-daily history exists for these factors yet.

**ML model: NOT retrained, NOT touched.** Still rainfall-only, still trained
on synthetic data - none of this round's new real factors were added as
model features, per explicit instruction.

## Fix: HTTP 429 from OpenTopoData (request-burst, not a bad source)
On a real machine, `/api/gis/stations` returned `elevation_m`/`slope_deg: null`
with a `429 Too Many Requests` from OpenTopoData. **Root cause**: the previous
code made one DEM HTTP request *per station*, and `list_stations()` computes
all 8 stations concurrently via `ThreadPoolExecutor` - so 8 simultaneous
requests hit OpenTopoData's public server at once, well over its ~1 req/sec
fair-use limit. ASTER GDEM/OpenTopoData was not the wrong choice; the client
was making far more requests than necessary.

**Fix** (`services/terrain.py`, `routes/gis.py`): all 8 stations' 3x3 DEM grids
(72 points) are now combined into **one** HTTP request (OpenTopoData's public
API documents support for up to 100 locations per call), fetched *before* the
concurrent risk-scoring loop rather than inside it. Combined with the existing
disk cache, a cold start now makes **1 request total** instead of 8, and every
subsequent call makes **0** (served from `terrain_cache.json`). One retry with
a 3s backoff handles transient 429s from other users of the shared public
server - verified it does NOT fabricate data if both attempts fail (returns
honest `"status": "unavailable"`), and correctly recovers to real data if the
retry succeeds (both paths unit-tested).

## What changed in this update (real elevation + real slope)
`elevation_m`/`slope_deg` on the GIS map are no longer hand-written numbers.

- **Elevation**: real DEM lookup via **ASTER GDEM v3** (NASA/METI), 30m (1
  arc-second) resolution, accessed through **OpenTopoData**'s free, keyless
  point-query API (`api.opentopodata.org`). Chosen because OpenTopography's
  own API only serves bounding-box raster downloads, not single-point
  lookups; OpenTopoData is the established open-source tool built
  specifically to query SRTM/ASTER/Copernicus by coordinate.
- **Slope**: real slope requires neighboring elevation cells, not a single
  point. `services/terrain.py` queries a real 3x3 grid of DEM points
  (spaced at ~30m, matching the dataset's native resolution) in one batched
  API call per station, then computes slope with **Horn's method** - the
  same algorithm GDAL's `gdaldem`, QGIS, and ArcGIS use. This was verified
  against mathematically-known synthetic slopes (0deg/10deg/30deg/45deg/60deg
  planes): exact match to 6 decimal places.
- **Caching**: both are static terrain characteristics, so a successful real
  result is cached indefinitely to `backend/terrain_cache.json` (path fixed
  via `TERRAIN_CACHE_PATH` in config - an earlier version of this file
  resolved to the wrong directory; fixed and verified). This is a real
  cached value, not a fake one - it just avoids re-querying unchanging
  terrain on every request, which also keeps `/api/gis/stations` fast
  enough for the frontend's 15s timeout.
- **Honesty**: if OpenTopoData can't be reached, the response is
  `"status": "unavailable"` with `elevation_m`/`slope_deg: null` and an
  explicit error - never a fabricated number. My sandbox can't reach
  `api.opentopodata.org` (same network restriction as NASA POWER/Nominatim
  before it) - verify on your machine, which has real internet.
- **`elevation_m`/`slope_deg` removed** from `locations_data.py` (backend)
  and from `SENSOR_META` (frontend) - both were hand-written placeholders.
  The frontend's Soil & Rain Sensors detail panel (`renderStationDetail()`)
  previously read elevation/slope from the hardcoded `SENSOR_META` object
  and **never actually used** the API's values even when connected - fixed
  to read `loc.elevation_m`/`loc.slope_deg` (now real) instead, showing
  "Unavailable" rather than a fake value if the DEM lookup failed.
- **Still a placeholder, not addressed this round**: `geology` - left
  untouched per scope; it's the next factor needing a real source (GSI
  Bhukosh) per the Real-Data Audit.
- **ML model NOT retrained, NOT changed.** Still rainfall-only
  (`rain_24h`/`rain_72h`/`rain_7d`), still trained on synthetic data -
  elevation/slope are reported for context but do not influence
  `risk_score`, exactly as before.

## What changed in this update (ML model connected to GIS)
`risk_score`/`risk_level` on the GIS map now come from the trained
`RandomForestClassifier` (`model/landslide_model.pkl`), not from hardcoded
`0.0`/`Low` values.

- **`POST /api/prediction/risk`** - the real endpoint: real data (or explicit
  what-if inputs) -> the model's own feature list -> `predict_proba()` ->
  risk_score/level. Returns HTTP 503 (not a fake score) if real rainfall or
  the model itself is unavailable. Rejects (422) any field the model doesn't
  actually use (e.g. `soil_moisture`) instead of silently ignoring it.
- **`GET /api/prediction/model-info`** - inspect the loaded model's type,
  feature order, positive class, and training-data caveats directly.
- **`GET /api/gis/stations`** - unchanged field names, but `risk_score`/
  `risk_level` now come from the same model via the same code path as
  `/api/prediction/risk` (`services/risk.py`), so the two endpoints can never
  disagree. A station whose real rainfall can't be fetched is returned with
  `"prediction_status": "unavailable"` and `risk_score: null` - never an
  invented number.
- **scikit-learn version mismatch (1.8.0 saved vs. 1.9.1 installed)**: verified,
  not silently ignored - loaded the same pickle under both versions and
  compared `predict_proba()` on 11,240 inputs (a full rainfall grid + all 320
  training rows): **0.0 max difference, byte-identical**. Documented in
  `model/model_metadata.json`. The per-tree `InconsistentVersionWarning`
  (~200 lines) is now condensed into one clear log line instead of being
  hidden - the model itself was never touched or retrained.
- **Model facts, in one place**: `model/model_metadata.json` - features
  (`rain_24h`, `rain_72h`, `rain_7d`, in that order - taken from the model's
  own `feature_names_in_`, never assumed), positive class (`1` = landslide
  event), and the training-data caveat below.
- **Frontend**: `index.html` now formats `risk_score`/rainfall with
  null-safe helpers (`fmtPercent`/`fmtNum`) so a legitimate "Unavailable"
  station (real data or model unreachable) renders as "—%" instead of a
  misleading "0%" or crashing. Added a neutral gray style for the
  `Unavailable` risk state. No layout, map, or design changes.

**Important caveat carried over honestly**: the model is trained on
`data/landslide_training_data.csv`, which is **synthetic** (see
`data/generate_sample_data.py`) - every response includes this in
`training_data_provenance` and `caveats` so it's never presented as
validated. Slope and elevation are reported in every response for context
but the current model does not use them (rainfall-only) - this is stated
explicitly in `context_not_used_by_model`.

## What changed in this update (backend foundation)
- **Renamed** `routers/` -> `routes/`, split the old single `database.py` into
  `models/` (ORM table definitions) and `database/` (connection/session setup),
  and turned `schemas.py` into a `schemas/` package - matching the requested
  project layout. All existing imports were updated; nothing broke.
- **`GET /api/health`** - basic liveness check.
- **`GET /api/gis/stations`** - structured station data (station_id, state,
  district, lat/lon, elevation, slope, geology, live risk_score/risk_level,
  rainfall aggregates). Elevation/slope/state/district were previously only
  defined in the frontend's JS - they now live in the backend
  (`locations_data.py`) as the first step of moving data off the frontend.
- **`GET /api/weather?latitude=..&longitude=..`** - real current weather
  (temperature, humidity, pressure, wind, current + hourly precipitation)
  via Open-Meteo (free, no API key). This is separate from the existing NASA
  POWER integration (which feeds the trained model with 24h/72h/7d rainfall
  aggregates) - Open-Meteo adds richer current-conditions data for later use.
- **CORS is now configurable** via `ALLOWED_ORIGINS` in `.env` (comma-separated
  origins), defaulting to `"*"` for local development, since the frontend is a
  static file with no single fixed origin yet.

**Not built yet (intentionally, per the current phase plan):**
- `/api/sensors/{station_id}` (Soil & Rain Sensor data is still 100%
  frontend-simulated - moving it to the backend, clearly labeled as
  simulated vs. real, is the next phase)
- `/api/prediction/risk` (a dedicated endpoint under the `/api` namespace for
  the ML prediction - the model itself already works via the existing
  `/predict` endpoint, this is just about relocating/formalizing it)
- A trained model using real historical landslide data (still pending -
  see "swap in real data" below)

## What changed in Phase 1 (architecture cleanup)
The old `backend/main.py` was a single 250-line file mixing config, database
logic (in-memory Python lists), external API calls, and route handlers all
together. It's now split into proper layers:
- **config.py** - every setting in one place, loaded from a `.env` file
- **database.py** - real SQLite database (via SQLAlchemy) instead of
  in-memory lists, so incident reports and alert history now survive server
  restarts
- **services/** - each external concern (geocoding, weather, ML model,
  notifications) isolated in its own file, so e.g. swapping NASA POWER for
  a different rainfall source only touches one file
- **routers/** - each group of endpoints in its own file

**The API contract is unchanged** - `/locations`, `/predict`, `/alerts`,
`/incidents` all work exactly as before, so the frontend needed zero changes.
Two new endpoints were added: `GET /forecast` (Phase 7 hook) and SMS support
in the alert endpoints (Phase 8 hook, simulated until Twilio is configured).

## IMPORTANT: swap in real data before you submit
Right now the model is trained on `generate_sample_data.py`'s SYNTHETIC data.
Before your final submission:
1. On a machine WITH internet access: `cd data && python fetch_landslide_data.py`
2. Re-train: `cd ../model && python train_model.py`
3. NASA GLC's India coverage may be sparse - also check **GSI Bhukosh**
   (https://bhukosh.gsi.gov.in) and merge into the same format if needed.

## How to run everything

### 1. Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Note the new module path: `app.main:app` (not `main:app` like before, since
the code now lives inside the `app/` package).

Visit http://localhost:8000/docs to test endpoints interactively.

Optional: copy `.env.example` to `.env` and fill in real SMTP credentials to
enable real email alerts (otherwise they're simulated/logged to console).

### 2. Frontend
Unchanged - just open `frontend/index.html` in a browser, or serve it with
VS Code's Live Server. It talks to `http://localhost:8000` automatically and
falls back to demo data if the backend isn't running.

## Roadmap (build order)
- [x] **Phase 1** - Architecture cleanup (this update)
- [ ] **Phase 2** - Real location + weather/rainfall data (partially done -
      NASA POWER integration exists; needs testing with real internet access)
- [ ] **Phase 3** - Historical landslide dataset + terrain data
- [ ] **Phase 4** - Actual ML training + evaluation (on real data)
- [ ] **Phase 5** - Prediction API + risk score (basic version exists)
- [ ] **Phase 6** - GIS map + historical events overlay
- [ ] **Phase 7** - Trends + forecast (basic hook exists via `/forecast`)
- [ ] **Phase 8** - Alerts + field reporting + emergency module (basic
      version exists; SMS hook ready, needs Twilio credentials)
- [ ] **Phase 9** - IoT/sensor integration (currently simulated in frontend)
- [ ] **Phase 10** - Offline/low-network + advanced features

## Features implemented so far
- **Location search (any place)**: `/predict?place=Gangtok` or `/predict?lat=..&lon=..`
- **8 pre-monitored NER stations** with live risk scores (GIS map view)
- **Risk color-coding**: Low/Moderate/High/Critical
- **Historical trend chart** + forecast hook (`/forecast`, simulated until
  `OPENWEATHER_API_KEY` is set in `.env`)
- **Email alerts** via SMTP, **SMS alerts** via Twilio (both simulated/logged
  until real credentials are configured)
- **Citizen incident reporting** - now persisted in a real SQLite database
- **Highway corridor risk** (demo data — swap in OpenStreetMap Overpass API
  for real highway geometry, planned for a later phase)
- **Admin vs public view toggle** (basic role gating in the frontend — real
  JWT auth is a later-phase item)

## What to say in your report about limitations
- IoT sensors (soil moisture, pore pressure, inclinometer tilt) shown in the
  reference video are simulated, tied mathematically to the real
  rainfall-driven risk score - not real physical sensors
- Highway corridor data and forecast are demo/simulated by default - real
  API hooks exist in the code, just need API keys/internet access to activate
- Be upfront about which parts are real (rainfall data, ML prediction,
  database persistence) vs. simulated (IoT sensors, highway data without a
  configured API) - evaluators respect this more than a project that hides it

