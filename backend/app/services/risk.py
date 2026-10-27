"""
services/risk.py - REAL DATA -> FEATURES -> ML MODEL -> RISK SCORE / LEVEL.

The single place where a station's risk is computed, so the POST
/api/prediction/risk endpoint and the GET /api/gis/stations endpoint can never
disagree with each other.

Honesty rules enforced here:
  * Rainfall comes from NASA POWER, or from values the caller explicitly
    supplied (labelled "user_supplied"). Simulated/random rainfall is NEVER fed
    to the model - if real data can't be fetched, the result is "unavailable".
  * If the model can't run, the result is "unavailable" - no rule-based
    stand-in score is substituted.
  * Slope/elevation are reported for context but the current model does not
    use them; the response says so explicitly.
"""

from datetime import datetime, timezone
from typing import Optional

from app.locations_data import NER_LOCATIONS
from app.services import ml_model
from app.services.weather import get_recent_rainfall

# request-field name -> model feature name
RAINFALL_REQUEST_FIELDS = {"rain_24h": "rainfall_24h", "rain_72h": "rainfall_72h", "rain_7d": "rainfall_7d"}


class UnknownStationError(Exception):
    pass


def _unavailable(base: dict, reason: str) -> dict:
    base.update({
        "prediction_status": "unavailable",
        "risk_score": None,
        "risk_percent": None,
        "risk_level": "Unavailable",
        "prediction_error": reason,
    })
    return base


def assess_risk(
    station_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    rainfall_overrides: Optional[dict] = None,   # keys: rain_24h / rain_72h / rain_7d
    slope_deg: Optional[float] = None,
    elevation_m: Optional[float] = None,
) -> dict:
    station = None
    if station_id:
        station = next((s for s in NER_LOCATIONS if s["id"] == station_id), None)
        if station is None:
            raise UnknownStationError(station_id)

    lat = latitude if latitude is not None else (station["lat"] if station else None)
    lon = longitude if longitude is not None else (station["lon"] if station else None)
    overrides = {k: v for k, v in (rainfall_overrides or {}).items() if v is not None}

    info = ml_model.get_model_info()
    result = {
        "station_id": station_id,
        "latitude": lat,
        "longitude": lon,
        "model_used": info["model_used"],
        "positive_class": info["positive_class"],
        "training_data_provenance": info["training_data_provenance"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    # ---- 1. Gather the features the model actually expects (names come from the model) ----
    needed = ml_model.model_feature_names()
    if not needed:
        return _unavailable(result, "Trained model is not loaded")

    features, rain = {}, None
    still_needed = [f for f in needed if overrides.get(f) is None]
    if still_needed:
        if lat is None or lon is None:
            return _unavailable(result, "No coordinates available to fetch rainfall")
        rain = get_recent_rainfall(lat, lon, allow_simulated_fallback=False)

    for f in needed:
        if overrides.get(f) is not None:
            features[f] = {"value": overrides[f], "unit": "mm", "source": "user_supplied"}
        else:
            features[f] = {"value": rain.get(f) if rain else None, "unit": "mm",
                           "source": rain["source"] if rain else "unavailable"}
    result["features_used"] = features

    if rain is not None and rain.get("data_end"):
        end = datetime.strptime(rain["data_end"], "%Y%m%d").replace(tzinfo=timezone.utc)
        result["data_window"] = {
            "start": rain["data_start"], "end": rain["data_end"],
            "lag_days": (datetime.now(timezone.utc) - end).days,
            "note": "NASA POWER daily data - not live. '24h' = latest available daily value.",
        }

    # ---- 2. Context features: reported, but the current model does not use them ----
    result["context_not_used_by_model"] = {
        "slope_deg": {"value": slope_deg if slope_deg is not None else (station or {}).get("slope_deg"),
                      "source": "user_supplied" if slope_deg is not None else "station registry"},
        "elevation_m": {"value": elevation_m if elevation_m is not None else (station or {}).get("elevation_m"),
                        "source": "user_supplied" if elevation_m is not None else "station registry"},
        "note": "The current model was trained on rainfall only; these do NOT influence risk_score.",
    }

    # ---- 3. Refuse to score if any required feature is missing (never invent one) ----
    missing = [f for f, v in features.items() if v["value"] is None]
    if missing:
        return _unavailable(result, f"Real data unavailable for: {missing} - no prediction made")

    # ---- 4. Run the trained model ----
    try:
        out = ml_model.predict_with_model({f: v["value"] for f, v in features.items()})
    except ml_model.ModelUnavailableError as e:
        return _unavailable(result, str(e))

    result.update({
        "prediction_status": "ok",
        "risk_score": out["risk_score"],
        "risk_percent": out["risk_percent"],
        "risk_level": out["risk_level"],
        "positive_class_column_index": out["positive_class_column_index"],
    })

    caveats = []
    if info["training_data_provenance"] == "synthetic":
        caveats.append("Model was trained on SYNTHETIC data - risk_score is not a validated landslide probability.")
    if any(v["source"] == "user_supplied" for v in features.values()):
        caveats.append("Some inputs were supplied by the caller (what-if), not measured.")
    result["caveats"] = caveats
    return result
