"""
services/geocoding.py - real geocoding via OpenStreetMap Nominatim (free, no API key).
"""

import requests
import logging
from app.config import settings

logger = logging.getLogger(__name__)


def geocode_place(place_name: str):
    """Returns (lat, lon) for a place name, or (None, None) if not found/unreachable."""
    try:
        r = requests.get(
            settings.NOMINATIM_URL,
            params={"q": place_name, "format": "json", "limit": 1},
            headers={"User-Agent": "landslide-early-warning-student-project"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.warning(f"Geocoding failed for '{place_name}': {e}")
    return None, None


def reverse_geocode(lat: float, lon: float):
    """Real reverse geocoding via OpenStreetMap Nominatim's /reverse endpoint
    (same free, no-key service as geocode_place above). Used by the Field
    Incident Report form's "Auto-Detect GPS Landmark" button: the browser's
    real GPS gives lat/lon, this turns that into a human-readable place name.

    Returns a display-name string, or None if unreachable/not found - callers
    should fall back to showing the raw coordinates rather than inventing a name.
    """
    try:
        r = requests.get(
            settings.NOMINATIM_URL.replace("/search", "/reverse"),
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 16},
            headers={"User-Agent": "landslide-early-warning-student-project"},
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()
        return result.get("display_name")
    except Exception as e:
        logger.warning(f"Reverse geocoding failed for ({lat},{lon}): {e}")
    return None
