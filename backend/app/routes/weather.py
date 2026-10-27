"""
routes/weather.py - GET /api/weather?latitude=..&longitude=..

Real current weather + hourly precipitation for any coordinate, via
Open-Meteo. This is intentionally separate from /predict (which uses NASA
POWER's longer-horizon rainfall aggregates for the trained model) - this
endpoint is for *current conditions* display and future feature engineering.
"""

from fastapi import APIRouter, Query

from app.services.open_meteo import get_current_weather

router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather")
def weather(
    latitude: float = Query(..., description="Latitude of the location"),
    longitude: float = Query(..., description="Longitude of the location"),
):
    return get_current_weather(latitude, longitude)
