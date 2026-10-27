"""
services/open_meteo.py - real current weather + hourly precipitation via
Open-Meteo (https://open-meteo.com), free and keyless for non-commercial use.

This is separate from services/weather.py (NASA POWER), which is used for
the longer-horizon rainfall aggregates (24h/72h/7d) that feed the trained
risk model. Open-Meteo instead gives richer *current-conditions* data
(temperature, humidity, pressure, wind) that the model doesn't use yet, but
which the eventual feature-engineering step and frontend "current weather"
display can draw on.
"""

import logging
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_current_weather_batch(stations: list) -> dict:
    """Real current weather for MULTIPLE stations in ONE request. Open-Meteo's
    /forecast endpoint accepts comma-separated latitude/longitude lists and
    returns a JSON array in that case - this avoids firing one request per
    station concurrently (the exact mistake that caused the terrain.py 429s).
    `stations` is a list of {"id","lat","lon"} dicts. Returns {station_id: dict}.
    """
    results = {}
    if not stations:
        return results
    try:
        r = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": ",".join(str(s["lat"]) for s in stations),
                "longitude": ",".join(str(s["lon"]) for s in stations),
                "current": "temperature_2m,relative_humidity_2m,precipitation,surface_pressure,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        entries = data if isinstance(data, list) else [data]  # a single station returns a plain object
        for s, entry in zip(stations, entries):
            current = entry.get("current", {})
            results[s["id"]] = {
                "temperature_c": current.get("temperature_2m"),
                "relative_humidity_pct": current.get("relative_humidity_2m"),
                "current_precipitation_mm": current.get("precipitation"),
                "surface_pressure_hpa": current.get("surface_pressure"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "timestamp": current.get("time"),
                "data_type": "current observation",
                "source": "Open-Meteo (real)",
                "status": "real",
            }
    except Exception as e:
        logger.warning(f"Open-Meteo batch fetch failed for {len(stations)} stations: {e}")
        for s in stations:
            results[s["id"]] = {
                "temperature_c": None, "relative_humidity_pct": None, "current_precipitation_mm": None,
                "surface_pressure_hpa": None, "wind_speed_kmh": None, "timestamp": None,
                "data_type": "current observation", "source": "Open-Meteo",
                "status": "unavailable", "error": str(e),
            }
    return results


def get_current_weather(lat: float, lon: float) -> dict:
    """Returns real current weather + recent/hourly precipitation for a location.
    Falls back to a clearly-labeled simulated response only if the API is
    unreachable, so callers can distinguish real data from a placeholder.
    """
    try:
        r = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,precipitation,surface_pressure,"
                           "wind_speed_10m,wind_direction_10m",
                "hourly": "precipitation",
                "past_days": 1,
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})
        hourly = data.get("hourly", {})
        hourly_times = hourly.get("time", [])
        hourly_precip = hourly.get("precipitation", [])

        # Sum the last 24 hourly readings for a "recent rainfall" figure
        recent_24h = sum(hourly_precip[-24:]) if hourly_precip else None

        return {
            "latitude": lat,
            "longitude": lon,
            "current_precipitation_mm": current.get("precipitation"),
            "recent_rainfall_24h_mm": round(recent_24h, 2) if recent_24h is not None else None,
            "hourly_rainfall_mm": [
                {"time": t, "precipitation_mm": p}
                for t, p in zip(hourly_times, hourly_precip)
            ],
            "temperature_c": current.get("temperature_2m"),
            "relative_humidity_pct": current.get("relative_humidity_2m"),
            "surface_pressure_hpa": current.get("surface_pressure"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "wind_direction_deg": current.get("wind_direction_10m"),
            "timestamp": current.get("time") or datetime.now(timezone.utc).isoformat(),
            "source": "Open-Meteo (real)",
        }
    except Exception as e:
        logger.warning(f"Open-Meteo fetch failed for ({lat},{lon}): {e}")
        return {
            "latitude": lat,
            "longitude": lon,
            "current_precipitation_mm": None,
            "recent_rainfall_24h_mm": None,
            "hourly_rainfall_mm": [],
            "temperature_c": None,
            "relative_humidity_pct": None,
            "surface_pressure_hpa": None,
            "wind_speed_kmh": None,
            "wind_direction_deg": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "unavailable (Open-Meteo unreachable) - not simulated, fields are null",
        }
