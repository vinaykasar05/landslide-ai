"""
test_bhuvan_landslide_query.py - Phase 6D

Run this on YOUR machine. This assistant's tools could not execute this
live - the conversational fetch tool's URL-indexing restriction blocked a
parameterized GetFeatureInfo query, and the code sandbox's network
whitelist directly returned 403 'host_not_allowed' for bhuvan-vec2.nrsc.gov.in
(confirmed via the response header itself, not assumed). Both are limitations
of this assistant's environment, not confirmed evidence that Bhuvan itself is
unreachable.

=== What this script does ===

STEP 1: Fetches the real WMS GetCapabilities document from bhuvan-vec2 and
searches it for landslide-related layer names containing NER state codes
(AS, AR, MN, ML, MZ, NL, SK, TR) and "SLIM" (the naming pattern found via
independent research for Uttarakhand's real layer: UK_SLIM_2017). This
REPLACES guessing with actual discovery - whatever layer names are found,
real or not, are reported exactly as found, nothing invented.

STEP 2: For any matching layer found, attempts a small GetFeatureInfo test
query against ONE known real landslide coordinate (editable below - default
is a placeholder near Shillong, Meghalaya; replace with an actual NESAC- or
ASDMA-documented event coordinate for a meaningful test, since GetFeatureInfo
can only confirm a feature AT a point you already suspect has one).

STEP 3: Reports the raw response exactly as returned - including if it's
empty (a real "no feature here" result, same honest outcome an independent
researcher doing this exact test for Uttarakhand found).

This script does NOT attempt bulk download - per Phase 6D's explicit scope,
only a small test query.

Install: pip install requests
"""

import requests
import re
import json
from pathlib import Path
from datetime import datetime, timezone

OUT_PATH = Path(__file__).parent / "bhuvan_test_query_result.json"

WMS_BASE = "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms"
GET_CAPABILITIES_URL = f"{WMS_BASE}?service=WMS&version=1.1.1&request=GetCapabilities"

NER_STATE_CODES = ["AR", "AS", "MN", "ML", "MZ", "NL", "SK", "TR"]  # plausible codes, not confirmed

# EDIT THIS before running for a meaningful test - use a real, documented
# landslide coordinate (e.g. from an ASDMA or NESAC report you've found).
# The placeholder below is only an approximate Shillong-area coordinate, NOT
# a confirmed landslide location - a query against it proves the MECHANISM
# works, not that a specific real event is findable.
TEST_LATITUDE = 25.5788
TEST_LONGITUDE = 91.8933
TEST_LOCATION_LABEL = "PLACEHOLDER near Shillong, Meghalaya - REPLACE with a real documented event coordinate"


def log(msg):
    print(msg)


def discover_layers():
    log(f"STEP 1: fetching WMS GetCapabilities from {WMS_BASE} (this document is reportedly 7-10MB, allow up to a minute)...")
    try:
        r = requests.get(GET_CAPABILITIES_URL, timeout=90)
        r.raise_for_status()
    except Exception as e:
        return {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}

    text = r.text
    log(f"  Retrieved {len(text)} characters.")

    # Find all <Name>...</Name> entries that look landslide-related and contain an NER state code
    all_names = re.findall(r"<Name>([^<]+)</Name>", text)
    landslide_candidates = [n for n in all_names if "slim" in n.lower() or "landslide" in n.lower() or "ls_" in n.lower()]
    ner_candidates = [n for n in landslide_candidates if any(code in n.upper() for code in NER_STATE_CODES)]

    log(f"  Total layers in capabilities doc: {len(all_names)}")
    log(f"  Landslide-related layers (any state): {len(landslide_candidates)}")
    log(f"  Landslide-related layers matching an NER state code: {len(ner_candidates)}")
    for n in ner_candidates:
        log(f"    - {n}")

    return {
        "status": "SUCCESS",
        "total_layers_in_capabilities": len(all_names),
        "all_landslide_related_layers": landslide_candidates,
        "ner_state_code_matches": ner_candidates,
        "note": "ner_state_code_matches uses a simple substring match on plausible 2-letter state codes - verify each manually, this is a candidate list, not a confirmed one.",
    }


def test_getfeatureinfo(layer_name, lat, lon):
    log(f"\nSTEP 2: testing GetFeatureInfo on layer '{layer_name}' at ({lat}, {lon})...")
    # Small bounding box around the point, standard GetFeatureInfo pattern
    delta = 0.01
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetFeatureInfo",
        "LAYERS": layer_name, "QUERY_LAYERS": layer_name,
        "SRS": "EPSG:4326", "BBOX": bbox, "WIDTH": 256, "HEIGHT": 256,
        "X": 128, "Y": 128, "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": 10,
    }
    try:
        r = requests.get(WMS_BASE, params=params, timeout=30)
        r.raise_for_status()
        log(f"  Response status: {r.status_code}")
        log(f"  Response body (first 1000 chars): {r.text[:1000]}")
        return {"status": "SUCCESS", "http_status": r.status_code, "raw_response": r.text}
    except Exception as e:
        return {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}


def main():
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "test_coordinate": {"lat": TEST_LATITUDE, "lon": TEST_LONGITUDE, "label": TEST_LOCATION_LABEL}}

    discovery = discover_layers()
    result["step1_layer_discovery"] = discovery

    if discovery.get("status") == "SUCCESS" and discovery.get("ner_state_code_matches"):
        test_results = {}
        for layer in discovery["ner_state_code_matches"][:3]:  # test up to 3, keep it small per the task's instruction
            test_results[layer] = test_getfeatureinfo(layer, TEST_LATITUDE, TEST_LONGITUDE)
        result["step2_getfeatureinfo_tests"] = test_results
    else:
        result["step2_getfeatureinfo_tests"] = "SKIPPED - no NER-matching layer names discovered in Step 1"

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    log(f"\nDone. Full result written to {OUT_PATH}")
    log("Send this file back - even an empty/no-feature GetFeatureInfo result is useful, honest information.")


if __name__ == "__main__":
    main()
