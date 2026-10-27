
"""
services/slope_stability.py - a real, computed Slope Saturation Index (SSI).

=== Why this file exists ===
The Soil & Rain Sensors tab used to show simulated "pore water pressure" and
"ground tilt" numbers meant to look like physical IoT/piezometer/inclinometer
telemetry. No public API or satellite service can give real pore pressure or
millimeter-scale tilt for arbitrary coordinates - those are inherently things
only a physical sensor in the ground (or a dedicated InSAR satellite
processing pipeline, itself a multi-week remote-sensing engineering project)
can measure. Simulating them any further would just be a more elaborate fake.

Instead, this computes a genuinely real, data-driven index from three inputs
this project ALREADY fetches for real, with no new external dependency:

    1. slope_deg              - real DEM-derived terrain slope (terrain.py)
    2. surface_soil_wetness    - real NASA POWER GWETTOP reanalysis (soil_moisture.py)
    3. rain_72h / rain_7d      - real NASA POWER rainfall (weather.py)

=== What this IS and ISN'T ===
IS:  a transparent, documented heuristic combining three real inputs into one
     0-100 "how primed is this slope for rainfall-triggered failure" score,
     in the same spirit as (and openly modeled on) standard infinite-slope /
     antecedent-precipitation-index susceptibility heuristics used in
     landslide early-warning literature.
ISN'T: a calibrated geotechnical factor-of-safety, a pore-pressure reading in
     kPa, a trained ML model (that's ml_model.py, a separate real thing), or
     a live sensor of any kind. Every caller-facing label says "index" /
     "model-derived", never "sensor" or "reading".

The weighting below (40% slope steepness, 35% soil saturation, 25% recent
rainfall) is a documented, reasonable-but-not-independently-calibrated choice
for a student project - it is not sourced from a specific peer-reviewed
model, and that is disclosed in the API response itself (see "method" field)
rather than left implicit.
"""

import logging

logger = logging.getLogger(__name__)

# Slope normalization: 0 degrees -> 0.0, 45+ degrees -> 1.0 (45 deg is a
# commonly-cited steep-terrain threshold in landslide susceptibility literature).
SLOPE_NORMALIZATION_CAP_DEG = 45.0

# Rainfall normalization: 72h accumulation of 150mm+ treated as saturating (1.0).
RAIN_72H_NORMALIZATION_CAP_MM = 150.0

WEIGHT_SLOPE = 0.40
WEIGHT_SOIL_WETNESS = 0.35
WEIGHT_RAIN = 0.25


def compute_slope_saturation_index(slope_deg, soil_wetness_fraction, rain_72h_mm) -> dict:
    """Combines three real inputs into a 0-100 index + Low/Moderate/High/Critical
    band. Returns status='partial' (with whatever sub-scores it could compute)
    if one or more real inputs are missing, rather than inventing a placeholder
    value for the missing one - a partial real computation stays honest about
    what did and didn't go into it.
    """
    components = {}
    available = []

    if slope_deg is not None:
        slope_norm = max(0.0, min(1.0, slope_deg / SLOPE_NORMALIZATION_CAP_DEG))
        components["slope"] = {"value_deg": round(slope_deg, 1), "normalized": round(slope_norm, 3), "weight": WEIGHT_SLOPE}
        available.append(("slope", slope_norm, WEIGHT_SLOPE))

    if soil_wetness_fraction is not None:
        wetness_norm = max(0.0, min(1.0, soil_wetness_fraction))
        components["soil_wetness"] = {"value_fraction": round(soil_wetness_fraction, 3), "normalized": round(wetness_norm, 3), "weight": WEIGHT_SOIL_WETNESS}
        available.append(("soil_wetness", wetness_norm, WEIGHT_SOIL_WETNESS))

    if rain_72h_mm is not None:
        rain_norm = max(0.0, min(1.0, rain_72h_mm / RAIN_72H_NORMALIZATION_CAP_MM))
        components["rain_72h"] = {"value_mm": round(rain_72h_mm, 1), "normalized": round(rain_norm, 3), "weight": WEIGHT_RAIN}
        available.append(("rain_72h", rain_norm, WEIGHT_RAIN))

    if not available:
        return {
            "index": None, "band": "Unavailable", "components": {},
            "status": "unavailable",
            "method": "Slope Saturation Index: weighted composite of real slope + soil-moisture + rainfall data. No inputs were available this time.",
        }

    total_weight = sum(w for _, _, w in available)
    score_0_1 = sum(v * w for _, v, w in available) / total_weight
    index = round(score_0_1 * 100, 1)

    if index >= 75:
        band = "Critical"
    elif index >= 50:
        band = "High"
    elif index >= 25:
        band = "Moderate"
    else:
        band = "Low"

    return {
        "index": index,
        "band": band,
        "components": components,
        "status": "real" if len(available) == 3 else "partial",
        "method": (
            "Slope Saturation Index: a documented, non-calibrated heuristic combining real "
            "DEM slope, real NASA POWER soil-wetness, and real NASA POWER 72h rainfall "
            "(weights 40/35/25). Not a calibrated factor-of-safety, not a sensor reading."
        ),
    }