"""
config.py - centralized settings for the whole backend.

All environment-specific values (API keys, file paths, thresholds) live here
instead of being scattered across files. Reads from a .env file if present
(see .env.example), otherwise falls back to sensible defaults so the app
still runs out of the box.
"""

import os
from pathlib import Path

# Load .env file if python-dotenv is installed and a .env file exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional - app still works with plain env vars or defaults

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

class Settings:
    # --- Paths ---
    MODEL_PATH = os.environ.get("MODEL_PATH", str(BASE_DIR.parent / "model" / "landslide_model.pkl"))
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "landslide_app.db"))
    TERRAIN_CACHE_PATH = os.environ.get("TERRAIN_CACHE_PATH", str(BASE_DIR / "terrain_cache.json"))
    HIGHWAYS_CACHE_PATH = os.environ.get("HIGHWAYS_CACHE_PATH", str(BASE_DIR / "highways_cache.json"))

    # --- External APIs (all free, no key required by default) ---
    NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")  # optional, for Phase 7 forecast

    # --- Email alerts (SMTP) ---
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")
    ALERT_FROM_EMAIL = os.environ.get("ALERT_FROM_EMAIL", SMTP_USER)

    # --- SMS alerts (Twilio) - optional, Phase 8 ---
    TWILIO_SID = os.environ.get("TWILIO_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

    # --- Risk thresholds (score 0-1 -> level) ---
    RISK_LOW_MAX = 0.25
    RISK_MODERATE_MAX = 0.5
    RISK_HIGH_MAX = 0.75
    ALERT_TRIGGER_LEVELS = ("High", "Critical")

    # --- CORS ---
    # Defaults to "*" for local development convenience (the frontend is a static
    # HTML file that may be opened via file://, VS Code Live Server on a random
    # port, or similar - there's no single fixed origin to lock to yet).
    # To restrict this for a real deployment, set ALLOWED_ORIGINS in .env to a
    # comma-separated list, e.g.: ALLOWED_ORIGINS=https://your-frontend-domain.com
    _origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
    ALLOWED_ORIGINS = ["*"] if not _origins_env or _origins_env == "*" else [o.strip() for o in _origins_env.split(",")]

settings = Settings()
