"""
routes/prediction.py

POST /api/prediction/risk       - real data (or explicit what-if inputs) -> trained model -> risk
GET  /api/prediction/model-info - what the loaded model is, what it expects, and its caveats

If real input data or the model is unavailable this returns HTTP 503 with the
reason - it never falls back to a made-up score.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.prediction import RiskRequest, RiskResponse
from app.services import ml_model, risk

router = APIRouter(prefix="/api/prediction", tags=["prediction"])


@router.post("/risk", response_model=RiskResponse)
def predict_risk_for_station(req: RiskRequest):
    try:
        result = risk.assess_risk(
            station_id=req.station_id,
            latitude=req.latitude,
            longitude=req.longitude,
            rainfall_overrides={
                "rain_24h": req.rainfall_24h,
                "rain_72h": req.rainfall_72h,
                "rain_7d": req.rainfall_7d,
            },
            slope_deg=req.slope_deg,
            elevation_m=req.elevation_m,
        )
    except risk.UnknownStationError:
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {req.station_id}")

    if result["prediction_status"] != "ok":
        raise HTTPException(status_code=503, detail=result)
    return result


@router.get("/model-info")
def model_info():
    return ml_model.get_model_info()
