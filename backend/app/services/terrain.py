"""
services/terrain.py - REAL elevation + REAL slope, derived from an actual DEM.

Elevation: ASTER GDEM v3 (NASA/METI), 30m (1 arc-second) resolution, global
coverage 83N-83S - accessed via OpenTopoData (https://www.opentopodata.org),
a free, keyless, open-source point-query API that serves this and several
other authoritative DEM datasets (SRTM, Copernicus, ASTER). OpenTopography's
own API only serves bounding-box raster downloads, not single-point lookups,
which is why OpenTopoData (a separate, well-established project built
specifically for this) is used instead.

Slope: NOT a separate API. Real slope requires neighbouring elevation cells,
so this queries a real 3x3 grid of DEM points centered on each station
(spaced at the dataset's native ~30m resolution) and computes slope with
Horn's method - the same algorithm used by GDAL's gdaldem, QGIS, and ArcGIS.
Verified against mathematically-known synthetic slopes (exact to 6 decimals).

=== Why this file was rewritten ===
The first version issued ONE HTTP request PER STATION. Combined with
routes/gis.py computing all 8 stations concurrently (ThreadPoolExecutor), this
fired 8 simultaneous requests at OpenTopoData's public server, which enforces
roughly 1 request/second fair-use - resulting in HTTP 429 Too Many Requests on
a real machine with real internet. The fix is request-count reduction, not a
retry loop papering over the same burst:

  - get_terrain_batch() combines ALL stations' 3x3 grids (72 points for 8
    stations) into ONE HTTP request (OpenTopoData's public API documents
    support for up to 100 locations per call - 72 fits with room to spare).
  - Only stations missing from the cache are included in that request at all;
    once cached, a normal run makes ZERO requests.
  - One retry with backoff handles transient 429s from other users sharing the
    public server - it does not exist to excuse making too many requests of
    our own.

Honesty rules enforced here:
  * If the DEM API is unreachable/rate-limited even after the retry, the
    result is "unavailable" with an explanation - never a fabricated value.
  * A successful real result is cached to disk indefinitely (terrain doesn't
    meaningfully change), which is also what keeps this fast and polite to
    the free public server on every subsequent request.
"""

import json
import math
import time
import logging
from datetime import datetime, timezone

import requests

from app.config import settings

logger = logging.getLogger(__name__)

DEM_DATASET = "aster30m"
DEM_SOURCE_NAME = "ASTER GDEM v3 (NASA / METI)"
DEM_RESOLUTION = "~30m (1 arc-second)"
OPEN_TOPO_DATA_URL = f"https://api.opentopodata.org/v1/{DEM_DATASET}"
MAX_LOCATIONS_PER_REQUEST = 100  # OpenTopoData's documented public-API limit

# Grid spacing for the slope calculation, matched to the dataset's native pixel size
ARC_SECOND_DEG = 1 / 3600.0  # ~30m at the equator, matching aster30m's resolution
METERS_PER_DEGREE_LAT = 111_320.0  # ~constant everywhere

_CACHE_PATH = settings.TERRAIN_CACHE_PATH


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
        logger.warning(f"Could not write terrain cache: {e}")


def _unavailable(reason: str) -> dict:
    return {
        "elevation_m": None,
        "slope_deg": None,
        "aspect_deg": None,
        "ruggedness_m": None,
        "relief_m": None,
        "source": DEM_SOURCE_NAME,
        "dataset": DEM_DATASET,
        "resolution": DEM_RESOLUTION,
        "method": "Horn's method on a real 3x3 DEM grid (not computed - see status)",
        "retrieved_at": None,
        "status": "unavailable",
        "error": reason,
    }


def _grid_points(lat: float, lon: float) -> list:
    """The 9 real-world points (row-major: NW,N,NE,W,center,E,SW,S,SE) needed for one station's slope."""
    pts = []
    for dlat in (ARC_SECOND_DEG, 0, -ARC_SECOND_DEG):
        for dlon in (-ARC_SECOND_DEG, 0, ARC_SECOND_DEG):
            pts.append((lat + dlat, lon + dlon))
    return pts


def _fetch_elevations(points: list) -> list:
    """ONE HTTP request for an arbitrary list of (lat, lon) points. One retry on
    429/5xx with a short backoff - for transient load on the shared public
    server, not as license to spam it."""
    locations_param = "|".join(f"{p[0]:.6f},{p[1]:.6f}" for p in points)
    if len(points) > MAX_LOCATIONS_PER_REQUEST:
        raise ValueError(f"{len(points)} points exceeds the {MAX_LOCATIONS_PER_REQUEST}-location "
                          f"public API limit - split into multiple batches")

    last_error = None
    for attempt in (1, 2):
        try:
            # POST (not GET) - more robust for a ~70-point locations string than a long query URL
            r = requests.post(OPEN_TOPO_DATA_URL, data={"locations": locations_param}, timeout=20)
            if r.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests")
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "OK":
                raise ValueError(f"OpenTopoData status={data.get('status')}: {data.get('error')}")
            elevations = [res["elevation"] for res in data["results"]]
            if any(e is None for e in elevations):
                raise ValueError("DEM has no data at one or more points (ocean/no-data cell)")
            return elevations
        except Exception as e:
            last_error = e
            if attempt == 1:
                logger.warning(f"DEM request failed ({e}), retrying once after backoff...")
                time.sleep(3)
    raise last_error


def _slope_from_grid(elevations: list, lat: float) -> float:
    """Horn's method (as used by GDAL gdaldem / QGIS / ArcGIS) on a 3x3 elevation grid."""
    a, b, c, d, _e, f, g, h, i = elevations  # NW,N,NE,W,center,E,SW,S,SE

    cellsize_x_m = ARC_SECOND_DEG * METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))
    cellsize_y_m = ARC_SECOND_DEG * METERS_PER_DEGREE_LAT

    dz_dx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cellsize_x_m)
    dz_dy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cellsize_y_m)

    slope_rad = math.atan(math.sqrt(dz_dx ** 2 + dz_dy ** 2))
    return math.degrees(slope_rad)


def _aspect_from_grid(elevations: list, lat: float) -> float:
    """Horn's method aspect (compass direction, degrees, of steepest descent; 0=North,
    90=East, 180=South, 270=West). Same dz/dx, dz/dy as slope - same real DEM grid,
    no extra API call."""
    a, b, c, d, _e, f, g, h, i = elevations
    cellsize_x_m = ARC_SECOND_DEG * METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))
    cellsize_y_m = ARC_SECOND_DEG * METERS_PER_DEGREE_LAT
    dz_dx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cellsize_x_m)
    dz_dy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cellsize_y_m)
    if dz_dx == 0 and dz_dy == 0:
        return -1.0  # flat - aspect undefined, GDAL convention
    aspect_rad = math.atan2(dz_dy, -dz_dx)
    aspect_deg = (90.0 - math.degrees(aspect_rad)) % 360.0
    return aspect_deg


def _ruggedness_from_grid(elevations: list) -> float:
    """Terrain Ruggedness Index (Riley et al. 1999): sqrt(sum of squared elevation
    differences between the center cell and its 8 neighbours). Units: meters."""
    center = elevations[4]
    neighbours = elevations[:4] + elevations[5:]
    return math.sqrt(sum((n - center) ** 2 for n in neighbours))


def _relief_from_grid(elevations: list) -> float:
    """Local relief: max - min elevation across the 3x3 grid. Units: meters."""
    return max(elevations) - min(elevations)


def get_terrain_batch(stations: list) -> dict:
    """The efficient path: real elevation+slope for MANY stations in as few
    requests as possible. `stations` is a list of {"id", "lat", "lon"} dicts.
    Returns {station_id: terrain_dict}. Only stations not already cached
    trigger any network request at all, and all of them share ONE request
    (or as few as MAX_LOCATIONS_PER_REQUEST allows)."""
    cache = _load_cache()
    results = {}
    to_fetch = []  # [{"id","lat","lon"}, ...]

    for s in stations:
        cached = cache.get(s["id"])
        if cached and cached.get("status") == "real":
            out = dict(cached)
            out["status"] = "real (cached)"
            results[s["id"]] = out
        else:
            to_fetch.append(s)

    if not to_fetch:
        return results

    # Batch into groups of <=100 locations (9 points per station)
    stations_per_batch = max(1, MAX_LOCATIONS_PER_REQUEST // 9)
    for i in range(0, len(to_fetch), stations_per_batch):
        batch = to_fetch[i:i + stations_per_batch]
        all_points = []
        for s in batch:
            all_points.extend(_grid_points(s["lat"], s["lon"]))

        try:
            elevations_flat = _fetch_elevations(all_points)
        except Exception as e:
            logger.warning(f"DEM batch fetch failed for {[s['id'] for s in batch]}: {e}")
            for s in batch:
                results[s["id"]] = _unavailable(
                    f"Could not reach {DEM_SOURCE_NAME} via OpenTopoData after retry: {e}")
            continue

        retrieved_at = datetime.now(timezone.utc).isoformat()
        for idx, s in enumerate(batch):
            grid = elevations_flat[idx * 9:(idx + 1) * 9]
            center_elevation = grid[4]
            slope_deg = _slope_from_grid(grid, s["lat"])
            aspect_deg = _aspect_from_grid(grid, s["lat"])
            ruggedness_m = _ruggedness_from_grid(grid)
            relief_m = _relief_from_grid(grid)
            result = {
                "elevation_m": round(center_elevation, 1),
                "slope_deg": round(slope_deg, 1),
                # Derived from the SAME real DEM grid as slope, zero extra API calls -
                # these are computed characteristics, not direct measurements.
                "aspect_deg": round(aspect_deg, 1),
                "ruggedness_m": round(ruggedness_m, 2),
                "relief_m": round(relief_m, 1),
                "derived_fields": ["aspect_deg", "ruggedness_m", "relief_m"],
                "derived_note": "aspect/ruggedness/relief are DERIVED FROM REAL DEM (ASTER GDEM), not direct measurements",
                "source": DEM_SOURCE_NAME,
                "dataset": f"{DEM_DATASET} (OpenTopoData)",
                "resolution": DEM_RESOLUTION,
                "coordinates": {"lat": s["lat"], "lon": s["lon"]},
                "method": ("Horn's method (GDAL/QGIS/ArcGIS standard) on a real 3x3 DEM grid "
                           f"spaced at {ARC_SECOND_DEG*3600:.0f} arcsec (~30m), centered on the station"),
                "retrieved_at": retrieved_at,
                "status": "real",
            }
            cache[s["id"]] = result
            results[s["id"]] = result

    _save_cache(cache)
    return results


def get_terrain(station_id: str, lat: float, lon: float) -> dict:
    """Convenience single-station wrapper (e.g. for a station added ad-hoc,
    outside the main batched /api/gis/stations list). Prefer get_terrain_batch()
    when you have multiple stations, to minimize requests."""
    return get_terrain_batch([{"id": station_id, "lat": lat, "lon": lon}])[station_id]
