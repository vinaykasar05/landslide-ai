from fastapi import APIRouter
from app.locations_data import NER_LOCATIONS
from app.services.weather import get_recent_rainfall
from app.services.ml_model import predict_risk

router = APIRouter(tags=["locations"])


@router.get("/locations")
def list_locations():
    """Predefined NER monitored locations, each with a live risk score."""
    results = []
    for loc in NER_LOCATIONS:
        rain = get_recent_rainfall(loc["lat"], loc["lon"])
        score, level = predict_risk(rain["rain_24h"], rain["rain_72h"], rain["rain_7d"])
        results.append({**loc, "risk_score": score, "risk_level": level, **rain})
    return results
