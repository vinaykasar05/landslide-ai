"""
Phase 6F — Extract NASA COOLR landslide EVENT records for India, and identify
candidate records within the 8 Northeast India (NER) states.

PURPOSE
-------
This script fetches REAL point-event data from the NASA COOLR
(Cooperative Open Online Landslide Repository) ArcGIS FeatureServer.
It does NOT generate, simulate, or substitute any synthetic data.
If the live service cannot be reached, or returns fewer records than
expected, the script reports that honestly instead of inventing rows.

WHY THIS SCRIPT EXISTS SEPARATELY FROM test_coolr_earthdata_connection.py
--------------------------------------------------------------------------
The earlier connection test only confirmed reachability and pulled a small
sample (5 records). This script performs the FULL extraction:
  1. All India event records (paginated, not just a sample).
  2. A preliminary, clearly-labeled geographic candidate-filter for the
     8 NER states (bounding-box based, since no authoritative state
     boundary polygons are bundled with this script).
  3. Full validation (pagination completeness, duplicates, missing dates,
     invalid coordinates, date range, timestamp conversion).
  4. A written audit report with the real, actual counts obtained.

ENDPOINT DISCREPANCY — RESOLVED BY AUTO-DETECTION
--------------------------------------------------
Two endpoint paths have appeared across this project's history:
  (A) https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/COOLR_Events_Points/FeatureServer/0
  (B) https://gis.earthdata.nasa.gov/portal/rest/services/Landslides/COOLR_Events_Points/FeatureServer/0
(A) is the exact URL hardcoded in this project's own
data/test_coolr_earthdata_connection.py -- the script actually run to
obtain the 176-India-record result. (B) was the path mentioned in a later
message but does not appear in any script actually executed. This script
tries (A) FIRST since it has real, executed-script verification behind it,
and falls back to (B) only if (A) fails. The report records exactly which
endpoint actually served the data — nothing is assumed silently.

IMPORTANT ON THE NER GEOGRAPHIC FILTER
----------------------------------------
No authoritative NER state boundary polygon dataset is bundled with this
script. The filter below is a PRELIMINARY bounding-box filter built from
the approximate combined extent of the 8 NER states:
    latitude:  21.5 to 29.5
    longitude: 87.5 to 97.5
This bounding box is deliberately generous (it will include some
non-NER territory, e.g. parts of northern West Bengal / Bihar / Bhutan
border areas) so that it does not silently exclude genuine NER events.
Records inside this box are labeled "ner_bbox_candidate" = True. This is
NOT a verified state assignment. A record being inside the box does NOT
mean it has been confirmed to lie in one of the 8 NER states, only that
it is geographically plausible and warrants manual/GIS-boundary review.
This limitation is repeated in the generated report.

USAGE
-----
    pip install requests pandas
    python extract_coolr_ner_events.py

OUTPUTS
-------
    data/raw/coolr_india_events.csv       (all India records obtained)
    data/raw/coolr_ner_events.csv         (NER bbox candidates only)
    data/coolr_event_extraction_report.md (full audit report)
    data/coolr_event_extraction_report.json (same findings, structured)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENDPOINTS = [
    {
        "label": "gis05_rest",
        "url": "https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/COOLR_Events_Points/FeatureServer/0",
        "note": "Hardcoded in this project's own test_coolr_earthdata_connection.py; the script actually run to get the 176-India-record result.",
    },
    {
        "label": "portal_rest",
        "url": "https://gis.earthdata.nasa.gov/portal/rest/services/Landslides/COOLR_Events_Points/FeatureServer/0",
        "note": "Mentioned in a later message but not present in any script actually executed. Fallback only.",
    },
]

PAGE_SIZE = 500          # <= documented MaxRecordCount of 2000; conservative to reduce timeout risk
REQUEST_TIMEOUT = 30
MAX_RETRIES_PER_PAGE = 3
RETRY_SLEEP_SECONDS = 3

# All 22 documented fields (confirmed from FeatureServer/0 service description)
OUT_FIELDS = "*"

# NER preliminary bounding box (see module docstring — NOT a verified boundary)
NER_BBOX = {"lat_min": 21.5, "lat_max": 29.5, "lon_min": 87.5, "lon_max": 97.5}

NER_STATES = [
    "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Sikkim", "Tripura",
]

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPT_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

INDIA_CSV = RAW_DIR / "coolr_india_events.csv"
NER_CSV = RAW_DIR / "coolr_ner_events.csv"
REPORT_MD = SCRIPT_DIR / "coolr_event_extraction_report.md"
REPORT_JSON = SCRIPT_DIR / "coolr_event_extraction_report.json"


# ---------------------------------------------------------------------------
# Step 1: pick a working endpoint
# ---------------------------------------------------------------------------

def detect_working_endpoint():
    """
    Try each candidate endpoint's service description (?f=json, no query
    params) and return the first one that responds with HTTP 200 and a
    JSON body containing expected service metadata. Does NOT fabricate
    a working endpoint if both fail -- raises with full detail instead.
    """
    results = []
    for ep in ENDPOINTS:
        try:
            r = requests.get(ep["url"], params={"f": "json"}, timeout=REQUEST_TIMEOUT)
            ok = False
            detail = f"HTTP {r.status_code}"
            if r.status_code == 200:
                try:
                    body = r.json()
                    if "error" in body:
                        detail += f" but service returned error: {body['error']}"
                    elif "maxRecordCount" in body or "fields" in body:
                        ok = True
                        detail += " - valid service description"
                    else:
                        detail += " - response did not look like a FeatureServer layer description"
                except ValueError:
                    detail += " - response was not valid JSON"
            results.append({"endpoint": ep["label"], "url": ep["url"], "ok": ok, "detail": detail})
            if ok:
                return ep, results
        except requests.exceptions.RequestException as e:
            results.append({
                "endpoint": ep["label"], "url": ep["url"], "ok": False,
                "detail": f"{type(e).__name__}: {e}",
            })
    return None, results


# ---------------------------------------------------------------------------
# Step 2: paginated query for all India records
# ---------------------------------------------------------------------------

def get_india_total_count(base_url):
    """Ask the service for the authoritative total count of India records."""
    params = {
        "f": "json",
        "where": "country_name='India'",
        "returnCountOnly": "true",
    }
    r = requests.get(f"{base_url}/query", params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if "count" not in body:
        raise RuntimeError(f"Count query did not return a count field. Raw response: {body}")
    return body["count"]


def fetch_india_page(base_url, offset, page_size):
    params = {
        "f": "json",
        "where": "country_name='India'",
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "orderByFields": "objectid ASC",
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES_PER_PAGE + 1):
        try:
            r = requests.get(f"{base_url}/query", params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(f"Service returned error at offset {offset}: {body['error']}")
            if "features" not in body:
                raise RuntimeError(f"No 'features' key in response at offset {offset}. Raw: {body}")
            return body["features"], body.get("exceededTransferLimit", False)
        except (requests.exceptions.RequestException, RuntimeError, ValueError) as e:
            last_err = e
            if attempt < MAX_RETRIES_PER_PAGE:
                time.sleep(RETRY_SLEEP_SECONDS)
    raise RuntimeError(f"Failed to fetch page at offset {offset} after {MAX_RETRIES_PER_PAGE} attempts: {last_err}")


def fetch_all_india_records(base_url, expected_total):
    all_rows = []
    offset = 0
    pages_fetched = 0
    while True:
        features, exceeded = fetch_india_page(base_url, offset, PAGE_SIZE)
        if not features:
            break
        for feat in features:
            all_rows.append(feat.get("attributes", {}))
        pages_fetched += 1
        n = len(features)
        print(f"  page {pages_fetched}: offset={offset} got={n} running_total={len(all_rows)}")
        offset += n
        if n < PAGE_SIZE and not exceeded:
            break
        if expected_total and len(all_rows) >= expected_total and not exceeded:
            break
        if offset > 50000:  # sanity guard against runaway pagination
            raise RuntimeError("Pagination exceeded 50,000 records without terminating — aborting as a safety check.")
    return all_rows


# ---------------------------------------------------------------------------
# Step 3: validation
# ---------------------------------------------------------------------------

def convert_unix_ms(value):
    """Convert a Unix-millisecond timestamp to an ISO date string.
    Returns None if the value is missing/invalid. Original value is NEVER
    discarded by the caller -- this only produces an additional column."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return None


def validate_coordinates(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if lat == 0 and lon == 0:
        return False  # classic null-island placeholder
    return -90 <= lat <= 90 and -180 <= lon <= 180


def run_validation(df):
    report = {}

    # Duplicate event_id check
    if "event_id" in df.columns:
        dup_mask = df["event_id"].duplicated(keep=False)
        report["duplicate_event_ids"] = {
            "count": int(dup_mask.sum()),
            "ids": sorted(set(df.loc[dup_mask, "event_id"].dropna().astype(str).tolist()))[:50],
        }
    else:
        report["duplicate_event_ids"] = {"count": None, "note": "event_id field not present in response"}

    # Missing event_date
    if "event_date" in df.columns:
        missing_date_mask = df["event_date"].isna()
        report["missing_event_date"] = {"count": int(missing_date_mask.sum())}
    else:
        report["missing_event_date"] = {"count": None, "note": "event_date field not present in response"}

    # Invalid coordinates
    if "latitude" in df.columns and "longitude" in df.columns:
        valid_mask = df.apply(lambda r: validate_coordinates(r.get("latitude"), r.get("longitude")), axis=1)
        report["invalid_coordinates"] = {"count": int((~valid_mask).sum())}
    else:
        valid_mask = pd.Series([True] * len(df))
        report["invalid_coordinates"] = {"count": None, "note": "latitude/longitude fields not present"}

    return report, valid_mask


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("PHASE 6F — COOLR NER EVENT EXTRACTION")
    print("=" * 70)

    report = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint_detection": None,
        "endpoint_used": None,
        "india_total_count_reported_by_service": None,
        "india_records_fetched": None,
        "pagination_complete": None,
        "validation": None,
        "ner_bbox_candidates": None,
        "ner_bbox_definition": NER_BBOX,
        "errors": [],
    }

    # --- Step 1: endpoint detection
    print("\n[1/6] Detecting working endpoint...")
    working_ep, detection_results = detect_working_endpoint()
    report["endpoint_detection"] = detection_results
    for res in detection_results:
        print(f"  {res['endpoint']}: ok={res['ok']} detail={res['detail']}")

    if working_ep is None:
        report["errors"].append("Both candidate endpoints failed. No real data could be fetched.")
        write_outputs(None, None, report, failure=True)
        print("\nFAILED: No working COOLR endpoint. See report for exact errors.")
        sys.exit(1)

    base_url = working_ep["url"]
    report["endpoint_used"] = working_ep["label"]
    print(f"  Using endpoint: {working_ep['label']} ({base_url})")

    # --- Step 2: authoritative count
    print("\n[2/6] Querying authoritative India record count...")
    try:
        expected_total = get_india_total_count(base_url)
        report["india_total_count_reported_by_service"] = expected_total
        print(f"  Service reports {expected_total} India records.")
    except Exception as e:
        report["errors"].append(f"Count query failed: {e}")
        write_outputs(None, None, report, failure=True)
        print(f"\nFAILED at count query: {e}")
        sys.exit(1)

    # --- Step 3: paginated fetch
    print(f"\n[3/6] Fetching all India records via pagination (page size {PAGE_SIZE})...")
    try:
        rows = fetch_all_india_records(base_url, expected_total)
    except Exception as e:
        report["errors"].append(f"Pagination failed: {e}")
        write_outputs(None, None, report, failure=True)
        print(f"\nFAILED during pagination: {e}")
        sys.exit(1)

    report["india_records_fetched"] = len(rows)
    report["pagination_complete"] = (len(rows) == expected_total)
    print(f"  Fetched {len(rows)} records (service-reported total: {expected_total}).")
    if not report["pagination_complete"]:
        print(f"  WARNING: fetched count does not match service-reported total. "
              f"Reporting this honestly rather than silently adjusting.")

    if len(rows) == 0:
        report["errors"].append("Zero India records were returned by pagination despite a non-zero count query. Reporting honestly.")
        write_outputs(pd.DataFrame(), pd.DataFrame(), report, failure=False)
        print("\nZERO RECORDS obtained. See report.")
        sys.exit(0)

    df = pd.DataFrame(rows)

    # --- Step 4: date conversion (preserving originals)
    print("\n[4/6] Converting Unix-ms event_date to readable dates (original column preserved)...")
    if "event_date" in df.columns:
        df["event_date_unix_ms_original"] = df["event_date"]
        df["event_date_readable"] = df["event_date"].apply(convert_unix_ms)
    if "sat_date_before" in df.columns:
        df["sat_date_before_readable"] = df["sat_date_before"].apply(convert_unix_ms)
    if "sat_date_after" in df.columns:
        df["sat_date_after_readable"] = df["sat_date_after"].apply(convert_unix_ms)

    # --- Step 5: validation
    print("\n[5/6] Running validation checks (duplicates, missing dates, invalid coords)...")
    validation, valid_coord_mask = run_validation(df)
    report["validation"] = validation
    print(f"  duplicate_event_ids: {validation['duplicate_event_ids']['count']}")
    print(f"  missing_event_date: {validation['missing_event_date']['count']}")
    print(f"  invalid_coordinates: {validation['invalid_coordinates']['count']}")

    if "event_date_readable" in df.columns:
        dates = pd.to_datetime(df["event_date_readable"], errors="coerce").dropna()
        if len(dates) > 0:
            report["date_range"] = {"min": str(dates.min().date()), "max": str(dates.max().date())}
        else:
            report["date_range"] = {"min": None, "max": None, "note": "no valid dates found"}

    # --- Step 6: NER bbox candidate filter
    print("\n[6/6] Applying PRELIMINARY NER bounding-box candidate filter (not a verified boundary)...")
    if "latitude" in df.columns and "longitude" in df.columns:
        lat = pd.to_numeric(df["latitude"], errors="coerce")
        lon = pd.to_numeric(df["longitude"], errors="coerce")
        bbox_mask = (
            (lat >= NER_BBOX["lat_min"]) & (lat <= NER_BBOX["lat_max"]) &
            (lon >= NER_BBOX["lon_min"]) & (lon <= NER_BBOX["lon_max"])
        )
        df["ner_bbox_candidate"] = bbox_mask.fillna(False)
        ner_df = df[df["ner_bbox_candidate"]].copy()
        report["ner_bbox_candidates"] = int(df["ner_bbox_candidate"].sum())
        print(f"  {report['ner_bbox_candidates']} of {len(df)} India records fall inside the NER bounding box.")
    else:
        df["ner_bbox_candidate"] = False
        ner_df = df.iloc[0:0].copy()
        report["ner_bbox_candidates"] = 0
        report["errors"].append("latitude/longitude fields missing; NER bbox filter could not be applied.")

    write_outputs(df, ner_df, report, failure=False)
    print("\nDONE. See coolr_event_extraction_report.md for full details.")


def write_outputs(india_df, ner_df, report, failure):
    if india_df is not None:
        india_df.to_csv(INDIA_CSV, index=False)
        print(f"\nWrote {len(india_df)} rows -> {INDIA_CSV}")
    if ner_df is not None:
        ner_df.to_csv(NER_CSV, index=False)
        print(f"Wrote {len(ner_df)} rows -> {NER_CSV}")

    with open(REPORT_JSON, "w") as f:
        json.dump(report, f, indent=2, default=str)

    md = build_markdown_report(report, india_df, ner_df, failure)
    with open(REPORT_MD, "w") as f:
        f.write(md)
    print(f"Wrote report -> {REPORT_MD}")


def build_markdown_report(report, india_df, ner_df, failure):
    lines = []
    lines.append("# COOLR Event Extraction Report (Phase 6F)")
    lines.append("")
    lines.append(f"Run timestamp (UTC): {report['run_timestamp_utc']}")
    lines.append("")
    lines.append("## Endpoint detection")
    lines.append("")
    for res in (report["endpoint_detection"] or []):
        lines.append(f"- **{res['endpoint']}** (`{res['url']}`): ok={res['ok']} — {res['detail']}")
    lines.append("")
    lines.append(f"**Endpoint actually used for data extraction:** {report['endpoint_used']}")
    lines.append("")

    if failure:
        lines.append("## Result: FAILED")
        lines.append("")
        for err in report["errors"]:
            lines.append(f"- {err}")
        lines.append("")
        lines.append("No fabricated data was produced. Fix the error above and re-run.")
        return "\n".join(lines)

    lines.append("## India record counts")
    lines.append("")
    lines.append(f"- Service-reported authoritative count (`returnCountOnly`): {report['india_total_count_reported_by_service']}")
    lines.append(f"- Records actually fetched via pagination: {report['india_records_fetched']}")
    lines.append(f"- Pagination complete (fetched == service count): {report['pagination_complete']}")
    lines.append("")

    if report.get("date_range"):
        lines.append("## Date range (event_date_readable, converted from Unix ms)")
        lines.append("")
        lines.append(f"- Min: {report['date_range'].get('min')}")
        lines.append(f"- Max: {report['date_range'].get('max')}")
        lines.append("")

    lines.append("## Validation results")
    lines.append("")
    v = report.get("validation") or {}
    if v.get("duplicate_event_ids"):
        lines.append(f"- Duplicate event_id count: {v['duplicate_event_ids'].get('count')}")
    if v.get("missing_event_date"):
        lines.append(f"- Missing event_date count: {v['missing_event_date'].get('count')}")
    if v.get("invalid_coordinates"):
        lines.append(f"- Invalid coordinates count: {v['invalid_coordinates'].get('count')}")
    lines.append("")

    lines.append("## NER geographic candidate filter — IMPORTANT LIMITATION")
    lines.append("")
    lines.append(
        "No authoritative NER state boundary polygon data is bundled with this script. "
        "The filter applied is a PRELIMINARY bounding box covering the approximate combined "
        "extent of the 8 NER states:"
    )
    lines.append("")
    bb = report["ner_bbox_definition"]
    lines.append(f"- Latitude: {bb['lat_min']} to {bb['lat_max']}")
    lines.append(f"- Longitude: {bb['lon_min']} to {bb['lon_max']}")
    lines.append("")
    lines.append(
        "This bounding box is deliberately generous and WILL include some non-NER territory "
        "(e.g. northern West Bengal, parts of Bihar, Bhutan/Myanmar border areas). A record "
        "falling inside this box is labeled `ner_bbox_candidate = True` in the output CSV. "
        "**This is NOT a verified state assignment.** It only means the record is geographically "
        "plausible for NER and requires manual or GIS-boundary-based review before being treated "
        "as a confirmed NER event."
    )
    lines.append("")
    lines.append(f"**NER bbox candidate count: {report['ner_bbox_candidates']} out of {report['india_records_fetched']} India records.**")
    lines.append("")

    if report["ner_bbox_candidates"] == 0:
        lines.append(
            "### Zero NER candidates found\n\n"
            "This is reported honestly. No records were broadened, relabeled, or fabricated "
            "to produce a non-zero count. If this is unexpected, verify the bounding box against "
            "a real NER extent map, or check whether COOLR simply has sparse coverage of this "
            "region (consistent with earlier Phase 6A/6C findings that NER-specific landslide "
            "event archives are thin compared to Himalayan-belt/NW-India coverage)."
        )
        lines.append("")

    lines.append("## Readiness for dynamic early-warning model training")
    lines.append("")
    lines.append(
        "This extraction alone is NOT sufficient to declare the dataset ready for training a "
        "dynamic rainfall-triggered early-warning model. Before any such training:"
    )
    lines.append("")
    lines.append("- [ ] Verify NER bbox candidates against real state boundaries (not this script's filter).")
    lines.append("- [ ] Assess how many candidate events have a valid, specific `event_date` (not just a year).")
    lines.append("- [ ] Check whether matching historical rainfall/soil-moisture data (e.g. NASA POWER) exists "
                 "for each event's date and location, with enough lead time before the event to build features.")
    lines.append("- [ ] Assess whether the number of usable (dated + located + covariate-matched) NER events "
                 "is large enough to support any defensible training split.")
    lines.append("- [ ] This assessment has NOT yet been performed in this script; it must be done once the "
                 "actual NER candidate records and their date quality are known.")
    lines.append("")

    lines.append("## Output files")
    lines.append("")
    lines.append(f"- `data/raw/coolr_india_events.csv` — {len(india_df) if india_df is not None else 0} rows (all India records)")
    lines.append(f"- `data/raw/coolr_ner_events.csv` — {len(ner_df) if ner_df is not None else 0} rows (NER bbox candidates only)")
    lines.append("")

    lines.append("## Data provenance")
    lines.append("")
    lines.append("Source: NASA COOLR (Cooperative Open Online Landslide Repository), served via the "
                  "NASA Earthdata GIS ArcGIS FeatureServer. This is real, live-queried point-event data, "
                  "not a static download or synthetic dataset.")
    lines.append("")

    if report["errors"]:
        lines.append("## Non-fatal issues encountered")
        lines.append("")
        for err in report["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
