from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.services.geocoding import geocode_place
from app.services.weather import get_recent_rainfall, get_forecast
from app.services.ml_model import predict_risk, model_is_loaded

router = APIRouter(tags=["predict"])


@router.get("/predict")
def predict(lat: float = None, lon: float = None, place: str = None):
    """Predict landslide risk for ANY location - by coordinates or place name."""
    if place and (lat is None or lon is None):
        lat, lon = geocode_place(place)
        if lat is None:
            raise HTTPException(status_code=404, detail=f"Could not find location: {place}")

    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="Provide either lat & lon, or a place name")

    rain = get_recent_rainfall(lat, lon)
    score, level = predict_risk(rain["rain_24h"], rain["rain_72h"], rain["rain_7d"])

    return {
        "lat": lat, "lon": lon,
        "risk_score": score, "risk_level": level,
        **rain,
        "checked_at": datetime.utcnow().isoformat(),
    }


@router.get("/forecast")
def forecast(lat: float, lon: float, days: int = 5):
    """5-day rainfall forecast for a location (Phase 7)."""
    return {"lat": lat, "lon": lon, "forecast": get_forecast(lat, lon, days)}


@router.get("/forecast/risk")
def forecast_with_risk(lat: float, lon: float, days: int = 5):
    """Per-day risk estimate for the upcoming forecast window, used by the
    Trends & Forecast tab's 5-day outlook strip.

    IMPORTANT (data-leakage note): each day's 72h/7d rolling windows are built
    ONLY from forecast rainfall values, never blended with today's already-measured
    real rainfall - mixing a measured total into a forecast window would make early
    forecast days look artificially consistent with "now" instead of reflecting what
    was actually predicted. Because of this, day+1's 72h/7d windows only cover 1 day
    of forecast (not a true 3/7-day sum) - window_days_used says how many forecast
    days actually went into each number, so the frontend can show that honestly
    instead of implying a full window exists where it doesn't.

    This also means the resulting risk_level is a FORECAST-RAINFALL-DRIVEN ESTIMATE
    using the same model as /api/gis/stations - not a live sensor reading, and not
    directly comparable to a station's current real risk_level.
    """
    fc = get_forecast(lat, lon, days)
    rain_values = [d["rain_mm"] for d in fc]
    out = []
    for i, d in enumerate(fc):
        window72 = rain_values[max(0, i - 2):i + 1]
        window7 = rain_values[max(0, i - 6):i + 1]
        rain_24h = d["rain_mm"]
        rain_72h = round(sum(window72), 1)
        rain_7d = round(sum(window7), 1)
        score, level = predict_risk(rain_24h, rain_72h, rain_7d)
        out.append({
            **d,
            "rain_24h": rain_24h, "rain_72h": rain_72h, "rain_7d": rain_7d,
            "window_days_used": {"72h": len(window72), "7d": len(window7)},
            "risk_score": score, "risk_level": level,
        })
    return {
        "lat": lat, "lon": lon, "forecast": out,
        "model_used": "trained model" if model_is_loaded() else "rule-based fallback (no trained model loaded)",
        "note": "risk_level is a forecast-rainfall-driven estimate, not a live sensor reading.",
    }
