"""
services/soil_moisture.py - REAL soil moisture via NASA POWER's GWETTOP parameter.

=== What this is, precisely (read before trusting the label) ===
GWETTOP = "Surface Soil Wetness" - a unitless fraction (0=dry, 1=saturated) of
the top ~5cm soil layer's moisture relative to its saturation capacity.

This is a MERRA-2 atmospheric reanalysis-derived land-surface MODEL OUTPUT,
NOT a direct satellite retrieval (unlike, say, raw SMAP/ESA-CCI brightness
temperature inversions) and NOT a physical sensor/IoT reading. It is real,
scientifically produced data from NASA, but the honesty rules for this project
require being precise about *what kind* of real data it is:

    "satellite observation" (SMAP/ESA-CCI)        != what this is
    "reanalysis/land-surface-model output" (this) == correct label
    "IoT/field sensor reading"                     != what this is, ever

=== Why NASA POWER instead of NASA SMAP ===
Real SMAP access requires a NASA Earthdata Login (free, but a registration +
credential-management step this project doesn't have set up) and is served
via NSIDC/AppEEARS, not a simple keyless point-query endpoint. NASA POWER -
which this project already integrates successfully for rainfall with zero
credentials - happens to also publish a real, physically-grounded soil
wetness parameter through the exact same free, keyless API. This is the
higher-confidence, lower-risk real-data choice for this stage; migrating to
true SMAP satellite retrievals remains a documented future upgrade once
Earthdata credentials are set up.

Spatial resolution: ~50km (MERRA-2 native grid) - coarse. Temporal: daily.
Latency: matches the existing NASA POWER rainfall integration (~2 day lag).
Coverage: global, including all 8 NER states.
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def get_soil_moisture(lat: float, lon: float) -> dict:
    """Returns real NASA POWER surface soil wetness (GWETTOP) for a location,
    or an honest 'unavailable' result. Never fabricates a value."""
    try:
        # GWETTOP tends to lag further behind "now" than the rainfall parameter does,
        # so a wider window makes the lookup robust to that lag without ever
        # fabricating a value - if nothing in the window is valid, it still
        # honestly reports unavailable.
        end = datetime.now(timezone.utc) - timedelta(days=2)
        start = end - timedelta(days=10)
        r = requests.get(
            POWER_URL,
            params={
                "parameters": "GWETTOP",
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
        daily = r.json()["properties"]["parameter"]["GWETTOP"]
        valid = [(day, v) for day, v in daily.items() if v not in (-999, None)]
        if not valid:
            raise ValueError("No valid GWETTOP values in response")

        latest_date, latest_value = valid[-1]
        data_end = datetime.strptime(latest_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        return {
            "surface_soil_wetness_fraction": round(latest_value, 3),
            "source": "NASA POWER (MERRA-2 reanalysis land-surface model)",
            "dataset": "GWETTOP",
            "data_type": "reanalysis/land-surface-model output",
            "NOT_a_satellite_observation": True,
            "NOT_an_IoT_sensor": True,
            "resolution": "~50km (MERRA-2 native grid)",
            "data_date": latest_date,
            "lag_days": (datetime.now(timezone.utc) - data_end).days,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "status": "real",
        }
    except Exception as e:
        logger.warning(f"NASA POWER soil moisture fetch failed for ({lat},{lon}): {e}")
        return {
            "surface_soil_wetness_fraction": None,
            "source": "NASA POWER (MERRA-2 reanalysis land-surface model)",
            "dataset": "GWETTOP",
            "data_type": "reanalysis/land-surface-model output",
            "status": "unavailable",
            "error": f"Could not reach NASA POWER: {e}",
        }