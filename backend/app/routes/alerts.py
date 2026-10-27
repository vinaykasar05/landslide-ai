from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AlertLog as AlertLogModel
from app.schemas import AlertSubscriptionCreate, AlertCheckResult
from app.locations_data import NER_LOCATIONS
from app.services.weather import get_recent_rainfall
from app.services.ml_model import predict_risk
from app.services.notifications import send_email_alert, send_sms_alert
from app.config import settings

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    """Current threshold breaches + recent alert history (from the database)."""
    current_breaches = []
    for loc in NER_LOCATIONS:
        rain = get_recent_rainfall(loc["lat"], loc["lon"])
        score, level = predict_risk(rain["rain_24h"], rain["rain_72h"], rain["rain_7d"])
        if level in settings.ALERT_TRIGGER_LEVELS:
            current_breaches.append({
                **loc, "risk_score": score, "risk_level": level,
                "rain_24h": rain["rain_24h"], "rain_72h": rain["rain_72h"], "rain_7d": rain["rain_7d"],
                "source": rain["source"],
            })

    recent_logs = db.query(AlertLogModel).order_by(AlertLogModel.sent_at.desc()).limit(50).all()
    alert_log = [
        {
            "location": log.location_name, "level": log.risk_level, "score": log.risk_score,
            "recipient": log.recipient, "channel": log.channel, "sent": log.sent,
            "time": log.sent_at.isoformat(),
        }
        for log in recent_logs
    ]
    return {"current_breaches": current_breaches, "alert_log": alert_log}


@router.post("/alerts/check-and-notify", response_model=AlertCheckResult)
def check_and_notify(sub: AlertSubscriptionCreate, db: Session = Depends(get_db)):
    """Manually trigger a check for one location; sends email/SMS if risk is High/Critical,
    and logs the attempt to the database. In production, schedule this with
    APScheduler to run automatically (see run_alert_scheduler.py)."""
    loc = next((l for l in NER_LOCATIONS if l["id"] == sub.location_id), None)
    if not loc:
        raise HTTPException(status_code=404, detail="Unknown location_id")

    rain = get_recent_rainfall(loc["lat"], loc["lon"])
    score, level = predict_risk(rain["rain_24h"], rain["rain_72h"], rain["rain_7d"])

    if level in settings.ALERT_TRIGGER_LEVELS:
        sent = False
        if sub.email:
            sent = send_email_alert(sub.email, loc["name"], level, score)
            db.add(AlertLogModel(location_name=loc["name"], risk_level=level, risk_score=score,
                                  recipient=sub.email, channel="email", sent=sent))
        if sub.phone:
            sms_sent = send_sms_alert(sub.phone, loc["name"], level, score)
            sent = sent or sms_sent
            db.add(AlertLogModel(location_name=loc["name"], risk_level=level, risk_score=score,
                                  recipient=sub.phone, channel="sms", sent=sms_sent))
        db.commit()
        return {"alert_sent": sent, "level": level, "score": score}

    return {"alert_sent": False, "level": level, "score": score}


@router.post("/alerts/broadcast")
def broadcast_warning(db: Session = Depends(get_db)):
    """Admin-triggered manual broadcast from the Alerts & Siren Dispatch tab.

    This writes a genuine, real database record for every station currently at
    High/Critical risk - an audit log of "an admin manually dispatched a warning
    for this breach" - using live rainfall-driven risk, same as /alerts above.

    It is NOT a real public SMS/push/CAP/WhatsApp broadcast: no such mass-notification
    channel is wired up in this project. For a real per-recipient email/SMS send
    (subject to SMTP_*/TWILIO_* configuration), use /alerts/check-and-notify instead
    (what the "Subscribe to Alerts" form calls).
    """
    logged = []
    for loc in NER_LOCATIONS:
        rain = get_recent_rainfall(loc["lat"], loc["lon"])
        score, level = predict_risk(rain["rain_24h"], rain["rain_72h"], rain["rain_7d"])
        if level in settings.ALERT_TRIGGER_LEVELS:
            db.add(AlertLogModel(
                location_name=loc["name"], risk_level=level, risk_score=score,
                recipient="manual broadcast (admin)", channel="manual_broadcast", sent=True,
            ))
            logged.append({"location": loc["name"], "level": level, "score": score})
    db.commit()
    return {"broadcasted": logged, "count": len(logged)}
