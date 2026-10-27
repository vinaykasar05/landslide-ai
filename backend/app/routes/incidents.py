from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IncidentReport as IncidentModel
from app.schemas import IncidentCreate, IncidentOut
from app.services.geocoding import reverse_geocode

router = APIRouter(tags=["incidents"])


@router.post("/incidents", response_model=IncidentOut)
def report_incident(report: IncidentCreate, db: Session = Depends(get_db)):
    entry = IncidentModel(**report.dict())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/incidents", response_model=List[IncidentOut])
def list_incidents(db: Session = Depends(get_db)):
    return db.query(IncidentModel).order_by(IncidentModel.reported_at.desc()).limit(100).all()


@router.get("/geocode/reverse")
def geocode_reverse(lat: float, lon: float):
    """Real reverse geocoding (OpenStreetMap Nominatim) for the Field Incident
    Report form's "Auto-Detect GPS Landmark" button."""
    name: Optional[str] = reverse_geocode(lat, lon)
    if name:
        return {"display_name": name, "status": "real"}
    return {"display_name": None, "status": "unavailable (Nominatim unreachable or no match)"}
