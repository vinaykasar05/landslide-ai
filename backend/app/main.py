"""
main.py - FastAPI application entry point.

This used to be one large file with everything mixed together. Now it just
initializes the app, sets up the database, and mounts each router - all the
actual logic lives in services/ and routes/.

Run with:
    uvicorn app.main:app --reload --port 8000
(run this from inside the backend/ folder)
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import locations, predict, alerts, incidents, health, gis, weather, prediction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Landslide Early Warning System",
    version="0.4.0",
    description="Real-data landslide risk prediction for North-East India (NER-Alert)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database ready.")


@app.get("/", tags=["root"])
def root():
    return {"status": "ok", "message": "AI Landslide Early Warning System API", "version": "0.4.0"}


# Existing endpoints (used by the current frontend - unchanged, not renamed under /api
# so nothing in index.html breaks)
app.include_router(locations.router)
app.include_router(predict.router)
app.include_router(alerts.router)
app.include_router(incidents.router)

# New /api endpoints (backend-foundation phase - not yet wired into the frontend)
app.include_router(health.router)
app.include_router(gis.router)
app.include_router(weather.router)
app.include_router(prediction.router)
