from datetime import date, datetime, time
import re
from typing import List
from difflib import get_close_matches

from sqlalchemy.orm import Session, joinedload

from db.models import Appointment, Provider, Slot, User
from services.google_calendar_service import create_google_calendar_event, delete_google_calendar_event


def get_providers(db: Session, service: str) -> List[Provider]:
    raw = (service or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", raw)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    active_providers = (
        db.query(Provider)
        .filter(Provider.is_active.is_(True))
        .order_by(Provider.id.asc())
        .all()
    )
    if not active_providers:
        return []

    if not normalized or normalized in {"all", "all services", "services", "service", "any"}:
        return active_providers

    # If user names a doctor, resolve to that provider first (avoids wrong service family).
    name_hints = [
        ("aisha", "%Aisha%"),
        ("asiha", "%Aisha%"),
        ("ahmed raza", "%Ahmed Raza%"),
        ("ahmed khan", "%Ahmed Khan%"),
        ("sara iqbal", "%Sara Iqbal%"),
        ("sana ali", "%Sana Ali%"),
        ("amna", "%Amna%"),
    ]
    for hint, like in name_hints:
        if hint in normalized:
            named = (
                db.query(Provider)
                .filter(Provider.is_active.is_(True), Provider.name.ilike(like))
                .order_by(Provider.id.asc())
                .all()
            )
            if named:
                return named

    # Future-proof path: match exactly against service names that exist in DB.
    by_exact_service = [p for p in active_providers if (p.service or "").strip().lower() == normalized]
    if by_exact_service:
        return by_exact_service

    # Soft matching against real DB service labels for voice phrasing variations.
    by_contains_service = [
        p
        for p in active_providers
        if normalized in (p.service or "").strip().lower()
        or (p.service or "").strip().lower() in normalized
    ]
    if by_contains_service:
        return by_contains_service

    # Map spoken labels/typos to DB services.
    # Kept only as fallback aliases for common voice intent terms.
    ordered = [
        ("cardiology", ["cardiology", "cardiac", "heart", "cardio"]),
        ("orthopedics", ["orthopedics", "orthopedic", "ortho", "bone", "joint"]),
        ("neurology", ["neurology", "neuro", "brain", "nerve"]),
        ("dermatology", ["dermatology", "dermatologist", "skin consultation", "skin", "derm", "derma"]),
        ("dentistry", ["dentistry", "dental", "dentist", "teeth", "tooth", "cleaning"]),
        ("pediatrics", ["pediatrics", "pediatric", "child", "kids"]),
        ("gynecology", ["gynecology", "gynecologist", "gynae", "women", "obgyn"]),
        ("ent", ["ent", "ear nose throat"]),
    ]
    mapped_service = None
    for target, aliases in ordered:
        if any(alias in normalized for alias in aliases):
            mapped_service = target
            break

    # Fuzzy guard for ASR typos like "consltantion", "dantel", etc.
    if mapped_service is None and normalized:
        all_aliases = [(alias, target) for target, aliases in ordered for alias in aliases]
        closest = get_close_matches(normalized, [a for a, _ in all_aliases], n=1, cutoff=0.72)
        if closest:
            for alias, target in all_aliases:
                if alias == closest[0]:
                    mapped_service = target
                    break

    if mapped_service:
        providers = [p for p in active_providers if (p.service or "").strip().lower() == mapped_service]
        if providers:
            return providers

    # Final fallback: return active providers so assistant can still continue gracefully.
    return active_providers


def get_available_slots(db: Session, provider_id: int) -> List[Slot]:
    active_provider = db.query(Provider).filter(Provider.id == provider_id, Provider.is_active.is_(True)).first()
    if not active_provider:
        return []
    return (
        db.query(Slot)
        .filter(Slot.provider_id == provider_id, Slot.is_booked.is_(False))
        .order_by(Slot.date.asc(), Slot.time.asc())
        .all()
    )


def _parse_preferred_time(value: str | None) -> time | None:
    """Parse voice/API times: 10:00, 10:00:00, 10 AM, 10:00 AM, 10AM."""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    s_am_pm = re.sub(r"\s+", " ", s.upper()).replace("A.M.", "AM").replace("P.M.", "PM")
    for fmt in ("%I:%M %p", "%I %M %p", "%I %p"):
        try:
            return datetime.strptime(s_am_pm, fmt).time()
        except ValueError:
            continue
    compact = re.sub(r"\s+", "", s.upper())
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(AM|PM)$", compact)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ap = m.group(3)
        if ap == "PM" and hour != 12:
            hour += 12
        if ap == "AM" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute, 0)
    return None


def _within_window(slot_time: time, window: str | None) -> bool:
    if not window:
        return True
    normalized = window.strip().lower()
    if normalized == "morning":
        return 8 <= slot_time.hour < 12
    if normalized == "afternoon":
        return 12 <= slot_time.hour < 17
    if normalized == "evening":
        return 17 <= slot_time.hour < 21
    return True


def _normalize_phone_key(value: str | None) -> str:
    raw = (value or "").strip()
    return re.sub(r"\D", "", raw)


def find_service_availability(
    db: Session,
    service: str,
    requested_date: date,
    preferred_time: str | None = None,
    time_window: str | None = None,
    doctor_name: str | None = None,
) -> tuple[bool, str, Slot | None, list[Slot]]:
    providers = get_providers(db, service=service)
    if not providers:
        return False, "No providers found for this service.", None, []

    if doctor_name and str(doctor_name).strip():
        hint = str(doctor_name).strip().lower()
        # Ignore dots/spacing so "Dr Aisha Khan" matches "Dr. Aisha Khan"
        def _norm(name: str) -> str:
            return re.sub(r"[^a-z0-9]+", "", name.lower())

        hint_n = _norm(hint)
        named = [p for p in providers if hint_n and hint_n in _norm(p.name)]
        if not named:
            # Fuzzy fallback for ASR slips like "ayesha khn" vs "aisha khan".
            pool = {_norm(p.name): p for p in providers}
            candidates = list(pool.keys())
            matched = get_close_matches(hint_n, candidates, n=1, cutoff=0.72)
            if matched:
                named = [pool[matched[0]]]
        if named:
            providers = named
        else:
            return False, f"No provider matched '{doctor_name.strip()}' for this service.", None, []

    provider_ids = [provider.id for provider in providers]
    slots = (
        db.query(Slot)
        .filter(
            Slot.provider_id.in_(provider_ids),
            Slot.date == requested_date,
            Slot.is_booked.is_(False),
        )
        .order_by(Slot.time.asc())
        .all()
    )
    slots = [slot for slot in slots if _within_window(slot.time, time_window)]
    if not slots:
        # Offer nearest next-day options for the same service.
        upcoming = (
            db.query(Slot)
            .filter(
                Slot.provider_id.in_(provider_ids),
                Slot.date >= requested_date,
                Slot.is_booked.is_(False),
            )
            .order_by(Slot.date.asc(), Slot.time.asc())
            .limit(30)
            .all()
        )
        upcoming = [slot for slot in upcoming if _within_window(slot.time, time_window)]
        if upcoming:
            return (
                False,
                "No slots available on requested date. Here are the next available options.",
                upcoming[0],
                upcoming[:3],
            )
        return False, "No available slots found for that date/time window.", None, []

    preferred_raw = (preferred_time or "").strip()
    preferred = _parse_preferred_time(preferred_time)
    time_unparsed = bool(preferred_raw and preferred is None)

    # Voice often sends "10 AM" or odd phrasing; never treat as "unavailable" — show real DB slots.
    if time_unparsed:
        return (
            True,
            "Time format was unclear; here are available slots on that date from the system.",
            slots[0],
            slots[:3],
        )

    if preferred:
        for slot in slots:
            if slot.time == preferred:
                return True, "Requested time is available.", slot, slots[:3]

    if preferred:
        alternatives = sorted(
            slots,
            key=lambda slot: abs(
                (slot.time.hour * 60 + slot.time.minute) - (preferred.hour * 60 + preferred.minute)
            ),
        )[:3]
        return False, "Requested time is not available. Here are nearest alternatives.", alternatives[0], alternatives

    return True, "Available slots found.", slots[0], slots[:3]


def check_calendar_conflict(db: Session, user_phone: str, appt_date: date, appt_time: time) -> bool:
    phone_digits = _normalize_phone_key(user_phone)
    if not phone_digits:
        return False

    user = db.query(User).filter(User.phone.is_not(None)).all()
    matched_user = None
    for item in user:
        if _normalize_phone_key(item.phone) == phone_digits:
            matched_user = item
            break
    if not matched_user:
        return False

    existing = (
        db.query(Appointment)
        .filter(
            Appointment.user_id == matched_user.id,
            Appointment.date == appt_date,
            Appointment.time == appt_time,
            Appointment.status == "confirmed",
        )
        .first()
    )
    return existing is not None


def book_appointment(
    db: Session,
    user_name: str,
    user_phone: str | None,
    provider_id: int,
    slot_id: int,
    idempotency_key: str | None = None,
) -> Appointment:
    phone_value = (user_phone or "").strip()
    if not phone_value:
        raise ValueError("Phone number is required.")
    phone_digits = _normalize_phone_key(phone_value)
    if not phone_digits:
        raise ValueError("Invalid phone number.")

    if idempotency_key:
        existing_by_key = (
            db.query(Appointment)
            .filter(Appointment.request_id == idempotency_key)
            .first()
        )
        if existing_by_key:
            return existing_by_key

    provider = db.query(Provider).filter(Provider.id == provider_id, Provider.is_active.is_(True)).first()
    if not provider:
        raise ValueError("Provider not found.")

    slot = (
        db.query(Slot)
        .filter(Slot.id == slot_id, Slot.provider_id == provider_id)
        .with_for_update()
        .first()
    )
    if not slot:
        raise ValueError("Slot not found for provider.")
    if slot.is_booked:
        raise ValueError("Selected slot is already booked.")

    has_conflict = check_calendar_conflict(db, phone_value, slot.date, slot.time)
    if has_conflict:
        raise ValueError("User already has an appointment at this time.")

    users = db.query(User).filter(User.phone.is_not(None)).all()
    user = None
    for item in users:
        if _normalize_phone_key(item.phone) == phone_digits:
            user = item
            break
    if not user:
        user = User(
            name=user_name.strip(),
            phone=phone_value,
        )
        db.add(user)
        db.flush()
    else:
        user.name = user_name.strip() or user.name
        user.phone = phone_value

    appointment = Appointment(
        request_id=idempotency_key,
        user_id=user.id,
        provider_id=provider.id,
        date=slot.date,
        time=slot.time,
        status="confirmed",
    )
    slot.is_booked = True

    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_appointment(
    db: Session,
    appointment_id: int,
    reason: str | None = None,
    cancelled_by: str = "patient",
    cancelled_via: str = "bot",
) -> Appointment:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise ValueError("Appointment not found.")

    calendar_event_id = (appointment.google_calendar_event_id or "").strip() or None

    if appointment.status == "cancelled":
        if calendar_event_id:
            _msg, ok = delete_google_calendar_event(calendar_event_id)
            if ok:
                appointment.google_calendar_event_id = None
                db.commit()
                db.refresh(appointment)
        return appointment

    slot = (
        db.query(Slot)
        .filter(
            Slot.provider_id == appointment.provider_id,
            Slot.date == appointment.date,
            Slot.time == appointment.time,
        )
        .first()
    )
    if slot:
        slot.is_booked = False

    appointment.status = "cancelled"
    appointment.cancelled_by = (cancelled_by or "patient").strip().lower()
    appointment.cancelled_via = (cancelled_via or "bot").strip().lower()
    appointment.cancellation_reason = (reason or "cancelled by patient through bot").strip()
    db.commit()
    db.refresh(appointment)

    if calendar_event_id:
        _msg, ok = delete_google_calendar_event(calendar_event_id)
        if ok:
            appointment.google_calendar_event_id = None
            db.commit()
            db.refresh(appointment)

    return appointment


def reschedule_appointment(
    db: Session,
    appointment_id: int,
    new_slot_id: int,
    idempotency_key: str | None = None,
) -> tuple[Appointment, str, bool]:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise ValueError("Appointment not found.")
    if appointment.status != "confirmed":
        raise ValueError("Only confirmed appointments can be rescheduled.")

    if idempotency_key and appointment.request_id == idempotency_key:
        return appointment, "", False

    old_calendar_event_id = (appointment.google_calendar_event_id or "").strip() or None

    new_slot = db.query(Slot).filter(Slot.id == new_slot_id).with_for_update().first()
    if not new_slot:
        raise ValueError("New slot not found.")
    if new_slot.provider_id != appointment.provider_id:
        raise ValueError("New slot must belong to the same provider.")

    current_slot = (
        db.query(Slot)
        .filter(
            Slot.provider_id == appointment.provider_id,
            Slot.date == appointment.date,
            Slot.time == appointment.time,
        )
        .first()
    )
    if current_slot and current_slot.id == new_slot_id:
        raise ValueError("That is already your current appointment time.")

    if new_slot.is_booked:
        raise ValueError("Requested new slot is already booked.")

    has_conflict = (
        db.query(Appointment)
        .filter(
            Appointment.user_id == appointment.user_id,
            Appointment.date == new_slot.date,
            Appointment.time == new_slot.time,
            Appointment.status == "confirmed",
            Appointment.id != appointment.id,
        )
        .first()
    )
    if has_conflict:
        raise ValueError("User already has another appointment at requested time.")

    old_slot = (
        db.query(Slot)
        .filter(
            Slot.provider_id == appointment.provider_id,
            Slot.date == appointment.date,
            Slot.time == appointment.time,
        )
        .first()
    )
    if old_slot:
        old_slot.is_booked = False

    new_slot.is_booked = True
    appointment.date = new_slot.date
    appointment.time = new_slot.time
    appointment.reminder_sent_at = None
    if idempotency_key:
        appointment.request_id = idempotency_key

    db.commit()
    db.refresh(appointment)

    appointment = (
        db.query(Appointment)
        .options(joinedload(Appointment.provider), joinedload(Appointment.user))
        .filter(Appointment.id == appointment.id)
        .one()
    )

    if old_calendar_event_id:
        _msg, ok = delete_google_calendar_event(old_calendar_event_id)
        if ok:
            appointment.google_calendar_event_id = None
            db.commit()
            db.refresh(appointment)

    calendar_detail = add_to_calendar(db, appointment)
    return appointment, calendar_detail, True


def add_to_calendar(db: Session, appointment: Appointment) -> str:
    start_datetime = datetime.combine(appointment.date, appointment.time)
    slot = (
        db.query(Slot)
        .filter(
            Slot.provider_id == appointment.provider_id,
            Slot.date == appointment.date,
            Slot.time == appointment.time,
        )
        .first()
    )
    end_datetime = None
    if slot and slot.end_time is not None:
        end_datetime = datetime.combine(appointment.date, slot.end_time)

    summary = f"Appointment with {appointment.provider.name}"
    description = (
        f"Service: {appointment.provider.service}\n"
        f"Patient: {appointment.user.name}\n"
        f"Phone: {appointment.user.phone or 'Not provided'}\n"
        f"Appointment ID: {appointment.id}"
    )
    try:
        message, event_id = create_google_calendar_event(
            summary=summary,
            description=description,
            start_datetime=start_datetime,
            duration_minutes=30,
            end_datetime=end_datetime,
        )
        if event_id:
            appointment.google_calendar_event_id = event_id
            db.commit()
            db.refresh(appointment)
        return message
    except Exception as exc:  # noqa: BLE001
        return f"Calendar sync failed: {exc}"
