"""
routes/health.py - simple liveness check for the backend.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "NER-Alert Backend"}
