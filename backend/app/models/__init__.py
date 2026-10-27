"""
models/__init__.py - SQLAlchemy ORM models (the actual database tables).

Kept separate from app/database/ (connection/session setup) so "what we
store" and "how we connect" don't live in the same file.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class IncidentReport(Base):
    __tablename__ = "incident_reports"
    id = Column(Integer, primary_key=True, index=True)
    reporter_name = Column(String)
    location_name = Column(String)
    lat = Column(Float)
    lon = Column(Float)
    description = Column(String)
    reported_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Added for the Field Incident Report tab (richer citizen/field-officer
    # reporting form). All nullable so older rows (created before this column
    # set existed) still load fine.
    title = Column(String, nullable=True)
    hazard_category = Column(String, nullable=True)
    state = Column(String, nullable=True)
    district = Column(String, nullable=True)
    severity = Column(String, nullable=True)  # Low / Moderate / High / Critical
    highway_blocked = Column(Boolean, nullable=True, default=False)
    people_stranded = Column(Integer, nullable=True)
    reporter_role = Column(String, nullable=True)  # e.g. "Citizen Surveyor", "Field Officer"
    photo_data_url = Column(String, nullable=True)  # real uploaded photo, stored inline as a data: URL (small images only)


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    location_id = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AlertLog(Base):
    __tablename__ = "alert_log"
    id = Column(Integer, primary_key=True, index=True)
    location_name = Column(String)
    risk_level = Column(String)
    risk_score = Column(Float)
    recipient = Column(String)
    channel = Column(String, default="email")
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
