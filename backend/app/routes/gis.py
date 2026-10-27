"""
routes/gis.py - GET /api/gis/stations

Returns the monitoring stations shown on the GIS Risk Map. Every existing field
is preserved. risk_score/risk_level come from the trained ML model fed with
real NASA POWER rainfall (services/risk.py). Terrain (elevation/slope/aspect/
ruggedness/relief) comes from a real DEM (services/terrain.py). Soil moisture
comes from NASA POWER's reanalysis soil-wetness parameter (services/soil_moisture.py).
Current weather comes from Open-Meteo, batched (services/open_meteo.py).

Factors with NO legitimate automatable real source yet (pore-water pressure,
ground movement/inclinometer, geology, land cover, drainage, road proximity)
are returned with an explicit honest status instead of a fabricated or hidden
value - see the project's Real-Data Audit for the reasoning behind each.
"""

from concurrent.futures import ThreadPoolExecutor
import logging

from fastapi import APIRouter

from app.locations_data import NER_LOCATIONS
from app.services.risk import assess_risk
from app.services.terrain import get_terrain_batch
from app.services.soil_moisture import get_soil_moisture
from app.services.open_meteo import get_current_weather_batch
from app.services.weather import get_rainfall_history
from app.services.slope_stability import compute_slope_saturation_index
from app.services.highways import get_highway_corridors

router = APIRouter(prefix="/api/gis", tags=["gis"])
logger = logging.getLogger(__name__)


def _unavailable_factor(required_source: str, note: str = "") -> dict:
    """Standard honest shape for a factor with no connected real source yet."""
    return {"status": "unavailable", "required_source": required_source, "note": note}


def _station_payload(loc: dict, terrain: dict, weather: dict) -> dict:
    try:
        r = assess_risk(station_id=loc["id"])
    except Exception as e:  # one station failing must not take down the whole map
        logger.exception(f"Risk assessment crashed for {loc['id']}")
        r = {"prediction_status": "unavailable", "risk_score": None, "risk_percent": None,
             "risk_level": "Unavailable", "prediction_error": f"Internal error: {e}", "features_used": {}}

    try:
        soil_moisture = get_soil_moisture(loc["lat"], loc["lon"])
    except Exception as e:
        logger.exception(f"Soil moisture lookup crashed for {loc['id']}")
        soil_moisture = {"surface_soil_wetness_fraction": None, "status": "unavailable", "error": str(e)}

    feats = r.get("features_used", {})
    value = lambda name: feats.get(name, {}).get("value")
    rain_source = feats.get("rain_24h", {}).get("source", "unavailable")

    payload = {
        "station_id": loc["id"],
        "station_name": loc.get("place", loc["name"]),
        "state": loc.get("state"),
        "district": loc.get("district"),
        "latitude": loc["lat"],
        "longitude": loc["lon"],

        # --- CURRENT / CHANGING CONDITIONS ---
        "rainfall": {
            "rain_24h_mm": value("rain_24h"),
            "rain_72h_mm": value("rain_72h"),
            "rain_7d_mm": value("rain_7d"),
            "source": rain_source,
            "data_end": (r.get("data_window") or {}).get("end"),
            "status": "real" if rain_source and "real" in rain_source else "unavailable",
        },
        "soil_moisture": soil_moisture,  # real (NASA POWER GWETTOP, reanalysis - see service docstring)
        "pore_water_pressure": _unavailable_factor(
            required_source="Physical piezometer/pore-pressure sensor installed at the site",
            note="No public API provides this for arbitrary coordinates - it is inherently a site-specific instrumented measurement, not satellite/model-derivable. See slope_saturation_index for a real, computed stand-in."
        ),
        "ground_movement": _unavailable_factor(
            required_source="Sentinel-1 InSAR time series (requires SAR processing, e.g. ESA SNAP/ISCE) or a real inclinometer",
            note="Not an IoT inclinometer reading. Satellite-derived deformation (InSAR) is a real option but requires substantial additional processing not yet built; no pre-computed product confirmed available for these exact coordinates."
        ),
        # Real, computed replacement for the old simulated pore-pressure/tilt panel -
        # see services/slope_stability.py for exactly what this is and isn't.
        "slope_saturation_index": compute_slope_saturation_index(
            terrain.get("slope_deg"),
            soil_moisture.get("surface_soil_wetness_fraction"),
            value("rain_72h"),
        ),
        "current_weather": weather,  # real (Open-Meteo), current conditions only - NOT forecast

        # --- ENVIRONMENT / TERRAIN CHARACTERISTICS ---
        "terrain": terrain,  # real (ASTER GDEM): elevation_m, slope_deg + derived aspect/ruggedness/relief
        "elevation_m": terrain.get("elevation_m"),  # mirrored at top level for existing frontend compatibility
        "slope_deg": terrain.get("slope_deg"),
        "geology": {
            "value": loc.get("geology"),
            "status": "unverified_hardcoded",
            "note": "Manually entered placeholder text, NOT from an authoritative geological survey. GSI Bhukosh has no stable public point-query API found; requires manual lookup or a confirmed ArcGIS REST endpoint.",
        },
        "land_cover": _unavailable_factor(
            required_source="ESA WorldCover (public COGs on AWS S3) via rasterio/GDAL point extraction, or a hosted point-query API",
            note="Technically accessible without a key, but requires rasterio/GDAL - not added this round due to GDAL's known fragility on Windows installs."
        ),
        "drainage": _unavailable_factor(
            required_source="OpenStreetMap Overpass API (waterway proximity) or HydroSHEDS",
            note="Real and accessible, but not yet implemented - scoped as a future addition."
        ),
        "road_proximity": _unavailable_factor(
            required_source="OpenStreetMap Overpass API (highway proximity)",
            note="Not yet computed per-station here. A related but different real computation now exists: GET /api/gis/highways finds, for each known highway corridor, the nearest monitored station - see services/highways.py. This per-station 'nearest road' direction (station -> road) is still a future addition."
        ),

        "risk_score": r["risk_score"],
        "risk_level": r["risk_level"],
        "risk_percent": r["risk_percent"],
        "prediction_status": r["prediction_status"],
        "model_used": r.get("model_used"),
    }
    if r["prediction_status"] != "ok":
        payload["prediction_error"] = r.get("prediction_error")
    return payload


@router.get("/stations")
def list_stations():
    station_refs = [{"id": loc["id"], "lat": loc["lat"], "lon": loc["lon"]} for loc in NER_LOCATIONS]

    # Both of these batch ALL stations into one (or few) requests - never one request
    # per station fired concurrently (that pattern caused the earlier terrain.py 429s).
    try:
        terrain_by_station = get_terrain_batch(station_refs)
    except Exception:
        logger.exception("Batched terrain lookup crashed")
        terrain_by_station = {}

    try:
        weather_by_station = get_current_weather_batch(station_refs)
    except Exception:
        logger.exception("Batched weather lookup crashed")
        weather_by_station = {}

    def _fallback_terrain(reason): return {"elevation_m": None, "slope_deg": None, "status": "unavailable", "error": reason}
    def _fallback_weather(reason): return {"status": "unavailable", "error": reason}

    # NASA POWER rainfall + soil moisture: same per-station concurrent pattern already
    # proven to work for rainfall in production (unlike OpenTopoData, NASA POWER has not
    # shown rate-limit problems under this concurrency in testing or prior real-machine use).
    with ThreadPoolExecutor(max_workers=len(NER_LOCATIONS)) as pool:
        return list(pool.map(
            lambda loc: _station_payload(
                loc,
                terrain_by_station.get(loc["id"]) or _fallback_terrain("Not returned by batch lookup"),
                weather_by_station.get(loc["id"]) or _fallback_weather("Not returned by batch lookup"),
            ),
            NER_LOCATIONS,
        ))


@router.get("/highways")
def highway_corridors():
    """Real Highway Corridors data for the Highway Corridors tab: real OpenStreetMap
    road geometry (via Overpass) cross-checked against this project's own real,
    rainfall-driven station risk levels - see services/highways.py for exactly how.
    Replaces the old hardcoded HIGHWAY_DATA array in the frontend.
    """
    station_refs = [
        {"id": loc["id"], "name": loc.get("place", loc["name"]), "lat": loc["lat"], "lon": loc["lon"]}
        for loc in NER_LOCATIONS
    ]
    # Reuse the same real risk assessment as the main stations endpoint.
    stations_with_risk = []
    for ref in station_refs:
        try:
            r = assess_risk(station_id=ref["id"])
            stations_with_risk.append({**ref, "risk_level": r["risk_level"], "risk_score": r["risk_score"]})
        except Exception:
            logger.exception(f"Risk assessment crashed for {ref['id']} (highways endpoint)")
            stations_with_risk.append({**ref, "risk_level": None, "risk_score": None})

    return get_highway_corridors(stations_with_risk)


@router.get("/history")
def station_history(station_id: str, days: int = 14):
    """Real day-by-day rainfall history for one station (NASA POWER), used by the
    Trends & Forecast tab's compare chart. Not a forecast - see /forecast/risk for that.
    """
    loc = next((l for l in NER_LOCATIONS if l["id"] == station_id), None)
    if loc is None:
        return {"station_id": station_id, "days": [], "status": "unknown_station",
                "source": f"No station with id '{station_id}'"}
    hist = get_rainfall_history(loc["lat"], loc["lon"], days=days)
    return {
        "station_id": station_id,
        "station_name": loc.get("place", loc["name"]),
        "state": loc.get("state"),
        **hist,
    }