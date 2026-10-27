"""
services/weather.py - real rainfall data via NASA POWER API (free, no key,
daily data since 1981, any lat/lon on Earth).

Falls back to a plausible simulated value only if the API is unreachable
(e.g. no internet), so the app keeps working for demos, but this is always
logged clearly so it's never silently mistaken for real data.
"""

import random
import logging
from datetime import datetime, timedelta
import requests

from app.config import settings

logger = logging.getLogger(__name__)


def get_recent_rainfall(lat: float, lon: float, allow_simulated_fallback: bool = True) -> dict:
    """Returns real rainfall totals (mm) for the last 24h/72h/7d at a location.

    NOTE: NASA POWER daily data lags real time by ~2+ days, so "24h" here means the
    latest available daily value (see data_end), not the last 24 hours from now.

    allow_simulated_fallback=True (default, legacy behavior): if NASA POWER is
    unreachable, return RANDOM demo values labeled "simulated fallback".
    allow_simulated_fallback=False: return None values with source "unavailable"
    instead, so callers (e.g. the ML risk endpoints) can refuse to score fake data.
    """
    try:
        end = datetime.utcnow() - timedelta(days=2)  # POWER has ~2 day processing lag
        start = end - timedelta(days=7)
        r = requests.get(
            settings.NASA_POWER_URL,
            params={
                "parameters": "PRECTOTCORR",
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
            },
            timeout=10,
        )
        r.raise_for_status()
        daily = r.json()["properties"]["parameter"]["PRECTOTCORR"]
        valid = [(day, v) for day, v in daily.items() if v not in (-999, None)]
        values = [v for _, v in valid]
        if values:
            return {
                "rain_24h": values[-1],
                "rain_72h": sum(values[-3:]),
                "rain_7d": sum(values),
                "data_start": valid[0][0],   # YYYYMMDD of first day used
                "data_end": valid[-1][0],    # YYYYMMDD of latest day used (real-time lag = today - data_end)
                "source": "NASA POWER (real)",
            }
    except Exception as e:
        logger.warning(f"NASA POWER fetch failed for ({lat},{lon}): {e}")

    if not allow_simulated_fallback:
        return {
            "rain_24h": None, "rain_72h": None, "rain_7d": None,
            "data_start": None, "data_end": None,
            "source": "unavailable (NASA POWER unreachable) - no values invented",
        }

    r24 = round(random.uniform(10, 160), 1)
    return {
        "rain_24h": r24,
        "rain_72h": round(r24 + random.uniform(10, 200), 1),
        "rain_7d": round(r24 + random.uniform(50, 300), 1),
        "source": "simulated fallback (NASA POWER unreachable)",
    }


def get_rainfall_history(lat: float, lon: float, days: int = 14) -> dict:
    """Real day-by-day rainfall series (mm) for the last `days` days, via NASA POWER.

    get_recent_rainfall() above calls the same API but collapses the daily series
    into just three numbers (24h/72h/7d totals) and discards the rest. This keeps
    the per-day values instead, for real historical trend charts on the frontend.

    No simulated fallback: if NASA POWER can't be reached this returns an empty
    series with status "unavailable" so the frontend never displays invented
    history as if it were real (same honesty rule as get_recent_rainfall's
    allow_simulated_fallback=False mode).
    """
    try:
        end = datetime.utcnow() - timedelta(days=2)  # POWER has ~2 day processing lag
        start = end - timedelta(days=days)
        r = requests.get(
            settings.NASA_POWER_URL,
            params={
                "parameters": "PRECTOTCORR",
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
            },
            timeout=10,
        )
        r.raise_for_status()
        daily = r.json()["properties"]["parameter"]["PRECTOTCORR"]
        valid = sorted(
            ((day, v) for day, v in daily.items() if v not in (-999, None)),
            key=lambda t: t[0],
        )
        return {
            "days": [{"date": d, "rain_mm": round(v, 1)} for d, v in valid],
            "source": "NASA POWER (real)",
            "status": "real",
        }
    except Exception as e:
        logger.warning(f"NASA POWER history fetch failed for ({lat},{lon}): {e}")
        return {
            "days": [],
            "source": "unavailable (NASA POWER unreachable) - no values invented",
            "status": "unavailable",
        }


def get_forecast(lat: float, lon: float, days: int = 5) -> list:
    """Real short-term rainfall forecast via OpenWeatherMap, if OPENWEATHER_API_KEY
    is configured (Phase 7). Falls back to a simulated projection otherwise, with a
    source label that honestly distinguishes "no key configured" from "a key is
    configured but the live request failed" (network issue, invalid key, OpenWeatherMap
    outage, etc.) - these are different situations and must not be reported as the same
    one, or a configured-but-failing key would look identical to a never-configured one."""
    if settings.OPENWEATHER_API_KEY:
        try:
            r = requests.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"lat": lat, "lon": lon, "appid": settings.OPENWEATHER_API_KEY, "units": "metric"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            daily_totals = {}
            for entry in data.get("list", []):
                day = entry["dt_txt"][:10]
                rain = entry.get("rain", {}).get("3h", 0)
                daily_totals[day] = daily_totals.get(day, 0) + rain
            return [{"date": d, "rain_mm": round(v, 1), "source": "OpenWeatherMap (real)"}
                    for d, v in list(daily_totals.items())[:days]]
        except Exception as e:
            # Full exception (requests embeds the whole request URL, API key included,
            # into connection-error text) goes to the server log only - never into a
            # value that reaches the frontend/API response, or the key would leak.
            logger.warning(f"OpenWeatherMap forecast failed: {e}")
            fallback_reason = "simulated (OPENWEATHER_API_KEY is set, but the live request failed - see server log for details)"
    else:
        fallback_reason = "simulated (no OPENWEATHER_API_KEY set)"

    return [
        {"date": f"day+{i+1}", "rain_mm": round(random.uniform(10, 150), 1), "source": fallback_reason}
        for i in range(days)
    ]