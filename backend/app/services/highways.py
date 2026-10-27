"""
services/highways.py - real highway corridor geometry via the OpenStreetMap
Overpass API (free, no key), cross-checked against this project's own
landslide-risk stations.

=== What this replaces ===
The Highway Corridors tab used to show a hardcoded JS array (HIGHWAY_DATA)
with made-up risk levels assigned by hand. This file instead:
  1. Queries Overpass for the REAL geometry of named highways (by their real
     NH/SH route refs) that actually run through the Northeast India states
     this project covers.
  2. Computes the real straight-line distance from each of this project's
     monitoring stations to that highway's actual path.
  3. Flags a corridor "at risk" only when a real monitoring station is
     genuinely close to it (CORRIDOR_PROXIMITY_KM), using that station's own
     real rainfall-driven risk_level - never an invented number.

=== What this IS and ISN'T ===
IS: real OSM road geometry + a real, documented nearest-station distance
    check (great-circle/haversine distance to each geometry vertex - a
    reasonable approximation for corridor-level screening, not survey-grade).
ISN'T: a routing engine, a full road-centerline risk model, or an official
    highway hazard assessment. A corridor with no monitored station nearby is
    reported as "No nearby monitoring station" rather than silently guessing
    Low risk - absence of data is not evidence of safety.

Overpass is rate-limited and sometimes slow/unavailable; every failure here
returns an explicit status="unavailable" entry (never a fabricated one), the
same honesty pattern used throughout this project (see terrain.py,
soil_moisture.py).
"""

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor

import requests

from app.config import settings

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "landslide-early-warning-student-project"

# Overpass's public instance (overpass-api.de) is shared, rate-limited (429s)
# and occasionally down (502s/timeouts) - real road geometry for a given ref
# essentially never changes, though, so there is no reason to re-query it on
# every single /api/gis/highways call. Caching successful lookups to disk
# (same pattern as terrain.py's DEM cache) means Overpass is only hit once
# per ref, ever, instead of once per page load - which is what was making
# this "sometimes show, sometimes not": every call was a fresh gamble against
# a shared public server's rate limit at that exact moment.
_CACHE_PATH = settings.HIGHWAYS_CACHE_PATH


def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not write highways cache: {e}")

# A real station within this distance (km) of a highway's path is considered
# to genuinely overlap that corridor. This is a coarse screening threshold
# for a student project, not a calibrated hazard-exposure radius.
CORRIDOR_PROXIMITY_KM = 30.0

# Real National Highway corridors that pass through the 8 NER states this
# project covers. "ref" is the actual highway reference OSM tags ways with
# (e.g. "NH6"); "name"/"state" are for display only - the risk/geometry
# themselves come from the live Overpass query below, not from here.
KNOWN_NER_CORRIDORS = [
    {"ref": "NH2", "name": "NH-2 (Imphal–Jiribam)", "state": "Manipur"},
    {"ref": "NH6", "name": "NH-6 (Silchar–Aizawl)", "state": "Mizoram/Assam"},
    {"ref": "NH40", "name": "NH-40 (Shillong–Guwahati)", "state": "Meghalaya/Assam"},
    {"ref": "NH29", "name": "NH-29 (Dimapur–Kohima)", "state": "Nagaland"},
    {"ref": "NH10", "name": "NH-10 (Siliguri–Gangtok)", "state": "Sikkim/West Bengal"},
    {"ref": "NH717A", "name": "NH-717A (Haflong–Jatinga)", "state": "Assam"},
]

# Rough bounding box covering all 8 NER states - keeps the Overpass query
# fast and avoids accidentally matching a same-numbered highway elsewhere
# in India.
NER_BBOX = (21.5, 87.5, 29.5, 97.5)  # (south, west, north, east)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _query_overpass_way(ref: str):
    """Fetches real OSM way geometry for a highway ref within the NER bbox.
    Returns a list of (lat, lon) vertices, or None if unreachable/not found.
    """
    s, w, n, e = NER_BBOX
    query = f"""
    [out:json][timeout:25];
        way["highway"]["ref"~"^{ref}$", i]({s},{w},{n},{e});
    out geom;
    """
    try:
        r = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        vertices = []
        for element in data.get("elements", []):
            for pt in element.get("geometry", []):
                vertices.append((pt["lat"], pt["lon"]))
        return vertices if vertices else None
    except Exception as e:
        logger.warning(f"Overpass lookup failed for ref='{ref}': {e}")
        return None


def get_highway_corridors(stations: list) -> list:
    """stations: list of dicts with at least id/name/lat/lon/risk_level/risk_score
    (the same real, rainfall-driven values already computed for the GIS map -
    this function does not recompute risk, it only checks real geographic
    proximity to real road geometry).

    Returns one entry per KNOWN_NER_CORRIDORS item:
      status: "real" (Overpass geometry found) | "unavailable" (Overpass
              unreachable/no matching way found - NOT the same as "safe")
      nearby_station / risk_level / risk_score: the closest real monitored
              station within CORRIDOR_PROXIMITY_KM, or null if none is close
              enough to this corridor's actual path.
    """
    cache = _load_cache()

    # Road geometry doesn't change, so a ref with cached vertices is served
    # straight from disk - zero Overpass calls for it, ever again. Only refs
    # missing from the cache (first run, or a ref that failed every time so
    # far) go to the network at all.
    to_fetch = [c for c in KNOWN_NER_CORRIDORS if not cache.get(c["ref"])]

    # Query the remaining corridors with LIMITED concurrency, not all at once
    # and not fully sequential. Overpass's public instance (overpass-api.de)
    # enforces a small per-IP concurrent-request slot limit (commonly just 2)
    # - firing them all at the same time can get several queued or rejected
    # together, which looked like "every corridor unavailable" even though
    # the service itself was reachable. 2 at a time respects that limit while
    # still being much faster than one-after-another.
    if to_fetch:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fetched = list(pool.map(lambda c: _query_overpass_way(c["ref"]), to_fetch))
        for corridor, vertices in zip(to_fetch, fetched):
            if vertices:
                cache[corridor["ref"]] = vertices
        _save_cache(cache)

    out = []
    for corridor in KNOWN_NER_CORRIDORS:
        vertices = cache.get(corridor["ref"])
        entry = {
            "ref": corridor["ref"],
            "name": corridor["name"],
            "state": corridor["state"],
        }
        if not vertices:
            entry.update({
                "status": "unavailable",
                "note": "OpenStreetMap Overpass API was unreachable or returned no matching way for this ref - this is NOT a statement that the corridor is safe, just that live road geometry could not be fetched this time.",
                "nearby_station": None,
                "risk_level": None,
                "risk_score": None,
            })
            out.append(entry)
            continue

        best = None  # (distance_km, station)
        for st in stations:
            if st.get("lat") is None or st.get("lon") is None:
                continue
            min_d = min(_haversine_km(st["lat"], st["lon"], vlat, vlon) for vlat, vlon in vertices)
            if best is None or min_d < best[0]:
                best = (min_d, st)

        if best and best[0] <= CORRIDOR_PROXIMITY_KM:
            dist, st = best
            entry.update({
                "status": "real",
                "note": f"Real OSM road geometry ({len(vertices)} vertices). Nearest monitored station '{st.get('name')}' is {dist:.1f}km from this corridor's path (within {CORRIDOR_PROXIMITY_KM:.0f}km proximity threshold).",
                "nearby_station": st.get("name"),
                "nearby_station_distance_km": round(dist, 1),
                "risk_level": st.get("risk_level"),
                "risk_score": st.get("risk_score"),
            })
        else:
            entry.update({
                "status": "real_no_nearby_station",
                "note": f"Real OSM road geometry ({len(vertices)} vertices) found, but no monitored station is within {CORRIDOR_PROXIMITY_KM:.0f}km of this corridor's path, so no risk level can be honestly attributed to it yet.",
                "nearby_station": None,
                "nearby_station_distance_km": round(best[0], 1) if best else None,
                "risk_level": None,
                "risk_score": None,
            })
        out.append(entry)
    return out