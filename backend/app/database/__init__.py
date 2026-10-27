"""
database/__init__.py - SQLite connection/session setup via SQLAlchemy.

Separated from the ORM model definitions (see app/models/) so this file is
purely about *how* we connect to the database, not *what* we store in it.

Why SQLite (for now): zero setup, file-based, ships with Python's standard
library driver, and easily handles this project's current write volume
(incident reports, alert logs). If the project later needs concurrent
multi-user writes at real scale, swapping the engine URL here for Postgres
is a one-line change - the rest of the app (models, routes) doesn't need to
change, since SQLAlchemy abstracts the underlying database.
"""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base

engine = create_engine(f"sqlite:///{settings.DATABASE_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Columns added to incident_reports after the table already existed in some
# deployments' db files. Base.metadata.create_all() only creates missing
# TABLES, not missing COLUMNS on a table that's already there - so new columns
# need an explicit, idempotent ALTER TABLE migration, run once at startup.
_INCIDENT_REPORTS_NEW_COLUMNS = {
    "title": "VARCHAR",
    "hazard_category": "VARCHAR",
    "state": "VARCHAR",
    "district": "VARCHAR",
    "severity": "VARCHAR",
    "highway_blocked": "BOOLEAN",
    "people_stranded": "INTEGER",
    "reporter_role": "VARCHAR",
    "photo_data_url": "VARCHAR",
}


def _migrate_incident_reports_columns():
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(incident_reports)"))}
        for col, col_type in _INCIDENT_REPORTS_NEW_COLUMNS.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE incident_reports ADD COLUMN {col} {col_type}"))
        conn.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Only needed if the table already existed before the columns above were added.
    try:
        _migrate_incident_reports_columns()
    except Exception:
        logging.getLogger(__name__).exception("incident_reports column migration failed")


def get_db():
    """FastAPI dependency - yields a DB session and always closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
