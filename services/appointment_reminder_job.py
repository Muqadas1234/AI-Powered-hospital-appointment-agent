"""
Send reminder before confirmed appointments (runs on a schedule).
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from db.models import Appointment, NotificationLog
from services.notification_service import _build_appointment_message, send_sms_notification, send_whatsapp_notification

logger = logging.getLogger(__name__)


def _app_tz():
    name = (os.getenv("APP_TIMEZONE", "Asia/Karachi") or "Asia/Karachi").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Karachi")


def _whatsapp_enabled() -> bool:
    return (os.getenv("WHATSAPP_REMINDER_ENABLED", "true") or "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def run_due_reminders(db: Session) -> int:
    """
    Reminder flow:
      - T-24h (configurable): send simple SMS reminder.
      - T-1h (configurable): send second reminder via WhatsApp.
    Returns count of actions triggered.
    """
    sms_lead_minutes = int(os.getenv("REMINDER_SMS_LEAD_MINUTES", "1440") or "1440")
    sms_lead_minutes = max(1, sms_lead_minutes)
    whatsapp_lead_minutes = int(os.getenv("REMINDER_WHATSAPP_LEAD_MINUTES", "1440") or "1440")
    whatsapp_lead_minutes = max(1, whatsapp_lead_minutes)

    tz = _app_tz()
    now = datetime.now(tz)
    today = date.today()

    appointments = (
        db.query(Appointment)
        .options(joinedload(Appointment.user), joinedload(Appointment.provider))
        .filter(
            Appointment.status == "confirmed",
            Appointment.date >= today,
        )
        .all()
    )

    sent = 0
    for appt in appointments:
        appt_dt = datetime.combine(appt.date, appt.time, tzinfo=tz)
        if appt_dt <= now:
            continue
        sms_reminder_at = appt_dt - timedelta(minutes=sms_lead_minutes)
        whatsapp_reminder_at = appt_dt - timedelta(minutes=whatsapp_lead_minutes)

        try:
            response = (appt.patient_response or "").strip().lower()
            has_response = response in {"confirmed", "cancelled"}

            if not has_response and appt.reminder_sent_at is None and now >= sms_reminder_at:
                sms_message = _build_appointment_message(
                    db,
                    appt,
                    "reminder",
                    extra_lines=["This is your 24-hour appointment reminder."],
                )
                send_sms_notification(db, appt, sms_message, "reminder")
                appt.reminder_sent_at = datetime.now(dt_timezone.utc)
                db.commit()
                sent += 1
                continue

            if (
                _whatsapp_enabled()
                and not has_response
                and appt.reminder_sent_at is not None
                and now >= whatsapp_reminder_at
            ):
                whatsapp_already_sent = (
                    db.query(NotificationLog.id)
                    .filter(
                        NotificationLog.appointment_id == appt.id,
                        NotificationLog.channel == "whatsapp",
                        NotificationLog.event_type == "reminder",
                    )
                    .first()
                    is not None
                )
                if whatsapp_already_sent:
                    continue
                whatsapp_message = _build_appointment_message(
                    db,
                    appt,
                    "reminder",
                    extra_lines=[
                        "Second reminder via WhatsApp.",
                        "Reply YES to confirm or NO to cancel your appointment.",
                    ],
                )
                send_whatsapp_notification(db, appt, whatsapp_message, "reminder")
                db.commit()
                sent += 1
        except Exception:
            db.rollback()
            logger.exception("Failed to send reminder for appointment %s", appt.id)

    return sent
