"""
schemas.py - Pydantic models defining the shape of API requests/responses.

Keeping these separate from the database models (database.py) is standard
practice: DB models describe what's stored, schemas describe what the API
accepts and returns - they're allowed to differ.
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class LocationRisk(BaseModel):
    id: Optional[str] = None
    name: str
    lat: float
    lon: float
    risk_score: float
    risk_level: str
    rain_24h: float
    rain_72h: float
    rain_7d: float
    source: str


class IncidentCreate(BaseModel):
    reporter_name: str
    location_name: str
    lat: float
    lon: float
    description: str
    # Added for the Field Incident Report tab's full report form - all optional
    # so the original simple fields still work on their own if ever called directly.
    title: Optional[str] = None
    hazard_category: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    severity: Optional[str] = None
    highway_blocked: Optional[bool] = False
    people_stranded: Optional[int] = None
    reporter_role: Optional[str] = None
    photo_data_url: Optional[str] = None


class IncidentOut(IncidentCreate):
    id: int
    reported_at: datetime

    class Config:
        from_attributes = True


class AlertSubscriptionCreate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    location_id: str


class AlertCheckResult(BaseModel):
    alert_sent: bool
    level: str
    score: float
