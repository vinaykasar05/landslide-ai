"""
schemas/prediction.py - request/response shapes for POST /api/prediction/risk.

extra="forbid": fields the current model does not use (soil_moisture,
pore_pressure, ...) are REJECTED with a clear 422 instead of being silently
ignored - accepting them would imply they influence the score, and they don't.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Where: a known station, or raw coordinates (rainfall is then fetched from NASA POWER)
    station_id: Optional[str] = Field(None, examples=["MEG-SOHRA-01"])
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    # What-if overrides for the model's inputs (mm). Any omitted value is fetched from real data.
    rainfall_24h: Optional[float] = Field(None, ge=0, description="mm - overrides the real 24h value")
    rainfall_72h: Optional[float] = Field(None, ge=0, description="mm - overrides the real 72h value")
    rainfall_7d: Optional[float] = Field(None, ge=0, description="mm - overrides the real 7-day value")

    # Context only - the current model does NOT use these (reported back so that is explicit)
    slope_deg: Optional[float] = None
    elevation_m: Optional[float] = None

    @model_validator(mode="after")
    def _need_location_or_all_rainfall(self):
        has_location = bool(self.station_id) or (self.latitude is not None and self.longitude is not None)
        has_all_rain = None not in (self.rainfall_24h, self.rainfall_72h, self.rainfall_7d)
        if not has_location and not has_all_rain:
            raise ValueError("Provide station_id, or latitude+longitude, or all three rainfall values")
        return self


class RiskResponse(BaseModel):
    station_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    prediction_status: str                      # "ok" | "unavailable"
    risk_score: Optional[float] = None          # model P(landslide event), 0-1
    risk_percent: Optional[int] = None
    risk_level: str                             # Low/Moderate/High/Critical, or "Unavailable"
    model_used: Optional[str] = None
    positive_class: Optional[int] = None
    positive_class_column_index: Optional[int] = None
    features_used: Dict[str, Any] = {}
    context_not_used_by_model: Dict[str, Any] = {}
    data_window: Optional[Dict[str, Any]] = None
    training_data_provenance: Optional[str] = None
    caveats: List[str] = []
    prediction_error: Optional[str] = None
    computed_at: str
