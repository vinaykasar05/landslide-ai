"""
services/notifications.py - sends real email alerts (SMTP) and has an SMS
hook ready for Twilio (Phase 8). Both simulate (log only) if not configured,
so the app never breaks in a demo without real credentials.
"""

import smtplib
import logging
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_email_alert(to_email: str, location_name: str, risk_level: str, score: float) -> bool:
    if not settings.SMTP_USER or not settings.SMTP_PASS:
        logger.info(f"[SIMULATED EMAIL] To: {to_email} | {location_name} risk is {risk_level} ({score})")
        return False

    msg = MIMEText(f"ALERT: {location_name} landslide risk is now {risk_level} (score {score}).")
    msg["Subject"] = f"Landslide Alert: {location_name} - {risk_level}"
    msg["From"] = settings.ALERT_FROM_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.sendmail(settings.ALERT_FROM_EMAIL, [to_email], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_sms_alert(to_phone: str, location_name: str, risk_level: str, score: float) -> bool:
    """SMS via Twilio - Phase 8. Simulates (logs only) until TWILIO_* env vars are set."""
    if not settings.TWILIO_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.info(f"[SIMULATED SMS] To: {to_phone} | {location_name} risk is {risk_level} ({score})")
        return False

    try:
        from twilio.rest import Client  # imported lazily so twilio isn't a hard dependency
        client = Client(settings.TWILIO_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"ALERT: {location_name} landslide risk is now {risk_level} (score {score}).",
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_phone,
        )
        return True
    except ImportError:
        logger.warning("twilio package not installed - run: pip install twilio")
        return False
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return False
