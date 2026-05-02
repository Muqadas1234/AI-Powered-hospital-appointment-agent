import os
import re
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from db.models import Appointment, NotificationLog, Slot


def _normalize_phone_e164ish(raw_phone: str | None) -> str:
    """Normalize common local formats to E.164-like Twilio input."""
    value = (raw_phone or "").strip()
    if not value:
        return ""

    cleaned = re.sub(r"[^\d+]", "", value)
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"

    # Keep explicitly international numbers if they already start with "+".
    if cleaned.startswith("+"):
        return cleaned

    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return ""

    # Pakistan local mobile: 03XXXXXXXXX -> +923XXXXXXXXX
    if len(digits) == 11 and digits.startswith("03"):
        return f"+92{digits[1:]}"

    # Pakistan number without leading 0: 3XXXXXXXXX -> +923XXXXXXXXX
    if len(digits) == 10 and digits.startswith("3"):
        return f"+92{digits}"

    # Fallback: assume caller provided country code digits.
    if len(digits) >= 10:
        return f"+{digits}"

    return ""


def _format_time_ampm(t: time | None) -> str:
    if t is None:
        return ""
    display = t.strftime("%I:%M %p")
    return display.lstrip("0")


def _format_date_for_message(d: date) -> str:
    return d.strftime("%A, %B %d, %Y")


def _whatsapp_enabled() -> bool:
    return (os.getenv("WHATSAPP_REMINDER_ENABLED", "true") or "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def _normalize_whatsapp_from(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("whatsapp:"):
        return raw
    normalized = _normalize_phone_e164ish(raw)
    if not normalized:
        return ""
    return f"whatsapp:{normalized}"


def _slot_end_time(db: Session, appointment: Appointment) -> time | None:
    return (
        db.query(Slot.end_time)
        .filter(
            Slot.provider_id == appointment.provider_id,
            Slot.date == appointment.date,
            Slot.time == appointment.time,
        )
        .scalar()
    )


def _build_appointment_message(
    db: Session,
    appointment: Appointment,
    event_type: str,
    extra_lines: list[str] | None = None,
) -> str:
    end_t = _slot_end_time(db, appointment)
    start_s = _format_time_ampm(appointment.time)
    end_s = _format_time_ampm(end_t) if end_t else ""
    if end_s:
        time_line = f"{start_s} to {end_s}"
    else:
        time_line = start_s

    service_line = (appointment.provider.service or "").strip() or "—"

    patient_name = (appointment.user.name or "").strip() or "Patient"
    event_map = {
        "booked": "Your appointment has been confirmed.",
        "cancelled": "Your appointment has been cancelled.",
        "rescheduled": "Your appointment has been rescheduled.",
        "reminder": "This is a reminder for your upcoming appointment.",
    }
    base = event_map.get(event_type, "Your appointment has been updated.")

    if event_type == "cancelled":
        via = (appointment.cancelled_via or "").lower()
        by = (appointment.cancelled_by or "").lower()
        if via == "admin_panel" or by == "admin":
            reason_text = (appointment.cancellation_reason or "").strip()
            base = "Your appointment has been cancelled by the hospital/clinic."
            if reason_text:
                base = f"{base} Reason: {reason_text}."

    if event_type == "reminder":
        rendered = []
        if extra_lines:
            rendered = [line.strip() for line in extra_lines if line and str(line).strip()]
        details = [
            "Appointment Reminder",
            f"Doctor: {appointment.provider.name}",
            f"Service: {service_line}",
            f"Date: {_format_date_for_message(appointment.date)}",
            f"Time: {time_line}",
            "Please arrive on time for your appointment.",
        ]
        details.extend(rendered)
        return "\n".join(details)

    extra_block = ""
    if extra_lines:
        rendered = [line.strip() for line in extra_lines if line and str(line).strip()]
        if rendered:
            extra_block = "\n\n" + "\n".join(rendered)

    return (
        f"Dear {patient_name},\n"
        f"{base}\n\n"
        "Appointment Details:\n"
        f"- Doctor: {appointment.provider.name}\n"
        f"- Service: {service_line}\n"
        f"- Date: {_format_date_for_message(appointment.date)}\n"
        f"- Time: {time_line}\n"
        f"- Appointment ID: {appointment.id}\n"
        f"- Status: {appointment.status}"
        f"{extra_block}\n\n"
        "Need to reschedule or cancel? Please contact reception/assistant helpline.\n"
        "CareVoice Hospital Appointments Team"
    )


def _log_notification(
    db: Session,
    *,
    appointment_id: int,
    channel: str,
    recipient: str,
    message: str,
    status: str,
    error: str | None = None,
    event_type: str | None = None,
) -> None:
    db.add(
        NotificationLog(
            appointment_id=appointment_id,
            channel=channel,
            recipient=recipient,
            message=message,
            status=status,
            error=error,
            event_type=event_type,
        )
    )
    db.commit()


def send_sms_notification(
    db: Session, appointment: Appointment, message: str, event_type: str
) -> str:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_phone = _normalize_phone_e164ish(os.getenv("TWILIO_FROM_PHONE", "").strip())
    to_phone = _normalize_phone_e164ish(appointment.user.phone)

    if not all([account_sid, auth_token, from_phone, to_phone]):
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="sms",
            recipient=to_phone or "unknown",
            message=message,
            status="skipped",
            error="Twilio or user phone not configured.",
            event_type=event_type,
        )
        return "SMS skipped (Twilio or phone not configured)."

    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {
        "From": from_phone,
        "To": to_phone,
        "Body": message,
    }

    try:
        response = requests.post(endpoint, data=payload, auth=(account_sid, auth_token), timeout=20)
        response.raise_for_status()
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="sms",
            recipient=to_phone,
            message=message,
            status="sent",
            event_type=event_type,
        )
        return "SMS sent."
    except requests.HTTPError as exc:
        details = ""
        try:
            details = f" | twilio={response.text}"
        except Exception:  # noqa: BLE001
            details = ""
        err_text = f"{exc}{details}"
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="sms",
            recipient=to_phone,
            message=message,
            status="failed",
            error=err_text,
            event_type=event_type,
        )
        return f"SMS failed: {err_text}"
    except Exception as exc:  # noqa: BLE001
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="sms",
            recipient=to_phone,
            message=message,
            status="failed",
            error=str(exc),
            event_type=event_type,
        )
        return f"SMS failed: {exc}"


def send_whatsapp_notification(
    db: Session, appointment: Appointment, message: str, event_type: str
) -> str:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_wa = _normalize_whatsapp_from(os.getenv("TWILIO_WHATSAPP_FROM", "").strip())
    to_phone = _normalize_phone_e164ish(appointment.user.phone)
    to_wa = f"whatsapp:{to_phone}" if to_phone else ""

    if not all([account_sid, auth_token, from_wa, to_wa]):
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="whatsapp",
            recipient=to_wa or "unknown",
            message=message,
            status="skipped",
            error="Twilio WhatsApp or user phone not configured.",
            event_type=event_type,
        )
        return "WhatsApp skipped (Twilio WhatsApp or phone not configured)."

    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {
        "From": from_wa,
        "To": to_wa,
        "Body": message,
    }

    try:
        response = requests.post(endpoint, data=payload, auth=(account_sid, auth_token), timeout=20)
        response.raise_for_status()
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="whatsapp",
            recipient=to_wa,
            message=message,
            status="sent",
            event_type=event_type,
        )
        return "WhatsApp sent."
    except requests.HTTPError as exc:
        details = ""
        try:
            details = f" | twilio={response.text}"
        except Exception:  # noqa: BLE001
            details = ""
        err_text = f"{exc}{details}"
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="whatsapp",
            recipient=to_wa,
            message=message,
            status="failed",
            error=err_text,
            event_type=event_type,
        )
        return f"WhatsApp failed: {err_text}"
    except Exception as exc:  # noqa: BLE001
        _log_notification(
            db,
            appointment_id=appointment.id,
            channel="whatsapp",
            recipient=to_wa,
            message=message,
            status="failed",
            error=str(exc),
            event_type=event_type,
        )
        return f"WhatsApp failed: {exc}"


def notify_appointment_event(
    db: Session,
    appointment: Appointment,
    event_type: str,
    extra_lines: list[str] | None = None,
) -> dict[str, str]:
    message = _build_appointment_message(db, appointment, event_type, extra_lines=extra_lines)
    if event_type == "reminder" and _whatsapp_enabled():
        return {
            "whatsapp": send_whatsapp_notification(db, appointment, message, event_type),
        }
    return {
        "sms": send_sms_notification(db, appointment, message, event_type),
    }


def retry_failed_notifications(db: Session) -> int:
    """
    Retry failed SMS notification logs.
    Uses env controls:
      - NOTIFICATION_RETRY_MAX_ATTEMPTS (default: 2)
      - NOTIFICATION_RETRY_BATCH_SIZE (default: 20)
      - NOTIFICATION_RETRY_DELAY_MINUTES (default: 2)
      - NOTIFICATION_RETRY_BACKOFF_MULTIPLIER (default: 1.5)
    """
    max_attempts = max(1, int(os.getenv("NOTIFICATION_RETRY_MAX_ATTEMPTS", "2") or "2"))
    batch_size = max(1, int(os.getenv("NOTIFICATION_RETRY_BATCH_SIZE", "20") or "20"))
    retry_delay_minutes = max(1, int(os.getenv("NOTIFICATION_RETRY_DELAY_MINUTES", "2") or "2"))
    retry_backoff_multiplier = max(
        1.0,
        float(os.getenv("NOTIFICATION_RETRY_BACKOFF_MULTIPLIER", "1.5") or "1.5"),
    )
    now_utc = datetime.now(dt_timezone.utc)

    failed_rows = (
        db.query(NotificationLog)
        .filter(NotificationLog.status == "failed")
        .order_by(NotificationLog.created_at.asc(), NotificationLog.id.asc())
        .limit(batch_size)
        .all()
    )

    retried = 0
    for row in failed_rows:
        failed_attempts = (
            db.query(func.count(NotificationLog.id))
            .filter(
                NotificationLog.appointment_id == row.appointment_id,
                NotificationLog.channel == row.channel,
                NotificationLog.event_type == row.event_type,
                NotificationLog.recipient == row.recipient,
                NotificationLog.status == "failed",
            )
            .scalar()
            or 0
        )
        if failed_attempts >= max_attempts:
            continue
        latest_failed = (
            db.query(NotificationLog.created_at)
            .filter(
                NotificationLog.appointment_id == row.appointment_id,
                NotificationLog.channel == row.channel,
                NotificationLog.event_type == row.event_type,
                NotificationLog.recipient == row.recipient,
                NotificationLog.status == "failed",
            )
            .order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc())
            .first()
        )
        if latest_failed and latest_failed[0] is not None:
            # Retry delay grows per failure attempt (simple exponential-style backoff).
            wait_factor = retry_backoff_multiplier ** max(0, failed_attempts - 1)
            wait_minutes = retry_delay_minutes * wait_factor
            ready_at = latest_failed[0] + timedelta(minutes=wait_minutes)
            if ready_at > now_utc:
                continue

        appointment = (
            db.query(Appointment)
            .options(joinedload(Appointment.user), joinedload(Appointment.provider))
            .filter(Appointment.id == row.appointment_id)
            .first()
        )
        if not appointment:
            _log_notification(
                db,
                appointment_id=row.appointment_id,
                channel=row.channel,
                recipient=row.recipient,
                message=row.message,
                status="skipped",
                error="Retry skipped: appointment not found.",
                event_type=row.event_type,
            )
            continue

        event_type = (row.event_type or "unknown").strip() or "unknown"
        message = (row.message or "").strip() or _build_appointment_message(db, appointment, event_type)

        if row.channel == "sms":
            send_sms_notification(db, appointment, message, event_type)
            retried += 1
            continue
        if row.channel == "whatsapp":
            send_whatsapp_notification(db, appointment, message, event_type)
            retried += 1
            continue

        _log_notification(
            db,
            appointment_id=row.appointment_id,
            channel=row.channel,
            recipient=row.recipient,
            message=message,
            status="skipped",
            error=f"Retry skipped: unsupported channel '{row.channel}'.",
            event_type=event_type,
        )

    return retried
