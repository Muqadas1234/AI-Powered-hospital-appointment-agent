from datetime import date, time, datetime, timezone as dt_timezone
import hashlib
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from api.deps import verify_tool_api_key
from db.database import get_db
from db.models import Appointment, Slot, User
from schemas.dto import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    AvailabilityOption,
    AppointmentActionResponse,
    BookAppointmentRequest,
    BookAppointmentResponse,
    CancelAppointmentRequest,
    CalendarCheckRequest,
    CalendarCheckResponse,
    FAQRequest,
    FAQResponse,
    ProviderResponse,
    ProviderLookupRequest,
    RescheduleAppointmentRequest,
    SlotResponse,
    SlotLookupRequest,
)
from services.booking_service import (
    add_to_calendar,
    book_appointment,
    cancel_appointment,
    check_calendar_conflict,
    find_service_availability,
    get_available_slots,
    get_providers,
    reschedule_appointment,
)
from services.faq_service import get_faq_answer
from services.notification_service import notify_appointment_event

class ToolGuardedRoute(APIRoute):
    """
    Force standardized tool-failure response so the assistant can reliably
    say "live system unavailable" instead of guessing.
    """

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def custom_handler(request):
            try:
                return await original_handler(request)
            except HTTPException as exc:
                # Preserve caller validation/auth errors (4xx) as-is.
                if 400 <= int(exc.status_code) < 500:
                    raise
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "SYSTEM_UNAVAILABLE",
                        "message": "Live hospital system is temporarily unavailable. Please try again shortly.",
                    },
                )
            except RequestValidationError:
                # Preserve payload/schema validation errors as 422 instead of masking as 503.
                raise
            except Exception:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "SYSTEM_UNAVAILABLE",
                        "message": "Live hospital system is temporarily unavailable. Please try again shortly.",
                    },
                )

        return custom_handler


router = APIRouter(prefix="/api/v1", tags=["appointment-agent"], route_class=ToolGuardedRoute)


def _format_spoken_date(value: date) -> str:
    return value.strftime("%A, %B %d, %Y")


def _format_spoken_time(value: time | None) -> str | None:
    if value is None:
        return None
    display = value.strftime("%I:%M %p")
    return display.lstrip("0")


def _format_spoken_range(start: time, end: time | None) -> str:
    start_text = _format_spoken_time(start) or ""
    end_text = _format_spoken_time(end)
    if end_text:
        return f"{start_text} to {end_text}"
    return start_text


def _to_voice_service_label(raw_service: str) -> str:
    value = (raw_service or "").strip().lower()
    if value == "dentist":
        return "dental checkup"
    if value == "dentistry":
        return "dentistry"
    if value == "dermatologist":
        return "skin consultation"
    if value == "dermatology":
        return "dermatology"
    if value == "general":
        return "Medicine OPD"
    return raw_service


def _normalize_phone_digits(value: str | None) -> str:
    return re.sub(r"\D", "", (value or "").strip())


def _find_users_by_phone(db: Session, raw_phone: str | None) -> list[User]:
    target = _normalize_phone_digits(raw_phone)
    if not target:
        return []
    users = db.query(User).filter(User.phone.is_not(None)).all()
    return [user for user in users if _normalize_phone_digits(user.phone) == target]


@router.post("/tools/get_faq_answer", response_model=FAQResponse)
def get_faq_answer_tool(
    payload: FAQRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    answer = get_faq_answer(db, payload.question)
    return FAQResponse(answer=answer)


@router.get("/tools/get_providers", response_model=list[ProviderResponse])
def get_providers_tool(
    # If service missing/empty, return providers from all active services.
    service: str = Query(default=""),
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    if not service or not str(service).strip():
        service = ""
    providers = get_providers(db, service=service)
    return [
        ProviderResponse(
            id=p.id,
            name=p.name,
            service=_to_voice_service_label(p.service),
            fee_pkr=p.fee_pkr,
        )
        for p in providers
    ]


@router.post("/tools/get_providers", response_model=list[ProviderResponse])
def get_providers_tool_post(
    payload: ProviderLookupRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    service = payload.service if payload.service and payload.service.strip() else ""
    providers = get_providers(db, service=service)
    return [
        ProviderResponse(
            id=p.id,
            name=p.name,
            service=_to_voice_service_label(p.service),
            fee_pkr=p.fee_pkr,
        )
        for p in providers
    ]


@router.get("/tools/get_available_slots", response_model=list[SlotResponse])
def get_available_slots_tool(
    # MVP: if provider_id missing, return empty list instead of hard failure.
    provider_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    if provider_id is None:
        return []

    slots = get_available_slots(db, provider_id=provider_id)
    return [
        SlotResponse(
            id=s.id,
            provider_id=s.provider_id,
            date=s.date,
            time=s.time,
            end_time=s.end_time,
            spoken_date=_format_spoken_date(s.date),
            spoken_time=_format_spoken_time(s.time),
            spoken_end_time=_format_spoken_time(s.end_time),
            spoken_time_range=_format_spoken_range(s.time, s.end_time),
            is_booked=s.is_booked,
        )
        for s in slots
    ]


@router.post("/tools/get_available_slots", response_model=list[SlotResponse])
def get_available_slots_tool_post(
    payload: SlotLookupRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    provider_id = payload.provider_id
    if provider_id is None:
        return []

    slots = get_available_slots(db, provider_id=provider_id)
    return [
        SlotResponse(
            id=s.id,
            provider_id=s.provider_id,
            date=s.date,
            time=s.time,
            end_time=s.end_time,
            spoken_date=_format_spoken_date(s.date),
            spoken_time=_format_spoken_time(s.time),
            spoken_end_time=_format_spoken_time(s.end_time),
            spoken_time_range=_format_spoken_range(s.time, s.end_time),
            is_booked=s.is_booked,
        )
        for s in slots
    ]


@router.post("/tools/check_service_availability", response_model=AvailabilityCheckResponse)
def check_service_availability_tool(
    payload: AvailabilityCheckRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    is_available, detail, best_slot, alternatives = find_service_availability(
        db=db,
        service=payload.service,
        requested_date=payload.date,
        preferred_time=payload.preferred_time,
        time_window=payload.time_window,
        doctor_name=payload.doctor_name,
    )

    def to_option(slot: Slot | None) -> AvailabilityOption | None:
        if slot is None:
            return None
        provider_name = slot.provider.name if slot.provider else "Provider"
        return AvailabilityOption(
            provider_id=slot.provider_id,
            provider_name=provider_name,
            date=slot.date,
            time=slot.time,
            end_time=slot.end_time,
            spoken_date=_format_spoken_date(slot.date),
            spoken_time=_format_spoken_time(slot.time),
            spoken_end_time=_format_spoken_time(slot.end_time),
            spoken_time_range=_format_spoken_range(slot.time, slot.end_time),
            slot_id=slot.id,
        )

    alternative_options: list[AvailabilityOption] = []
    for slot in alternatives:
        option = to_option(slot)
        if option is not None:
            alternative_options.append(option)

    return AvailabilityCheckResponse(
        is_available=is_available,
        detail=detail,
        best_option=to_option(best_slot),
        alternatives=alternative_options,
    )


@router.post("/tools/check_calendar", response_model=CalendarCheckResponse)
def check_calendar_tool(
    payload: CalendarCheckRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    has_conflict = check_calendar_conflict(db, payload.user_phone, payload.date, payload.time)
    if has_conflict:
        return CalendarCheckResponse(
            has_conflict=True,
            detail="You already have an appointment at this time.",
        )
    return CalendarCheckResponse(
        has_conflict=False,
        detail="No conflict found.",
    )


@router.post("/tools/book_appointment", response_model=BookAppointmentResponse)
def book_appointment_tool(
    payload: BookAppointmentRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    if not payload.confirmed_by_user:
        raise HTTPException(
            status_code=400,
            detail=(
                "Booking blocked: patient confirmation is required. "
                "Read back Name, Doctor, Date, Time and ask explicit yes before booking."
            ),
        )
    confirmation_text = (payload.confirmation_text or "").strip().lower()
    if confirmation_text and confirmation_text not in {
        "yes",
        "yes confirm",
        "confirm",
        "confirmed",
        "ok confirm",
        "book it",
        "proceed",
    }:
        raise HTTPException(
            status_code=400,
            detail="Booking blocked: confirmation_text must be an explicit confirmation phrase.",
        )
    try:
        appointment = book_appointment(
            db=db,
            user_name=payload.user_name,
            user_phone=payload.user_phone,
            provider_id=payload.provider_id,
            slot_id=payload.slot_id,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    slot = (
        db.query(Slot)
        .filter(
            Slot.provider_id == appointment.provider_id,
            Slot.date == appointment.date,
            Slot.time == appointment.time,
        )
        .first()
    )
    calendar_status = add_to_calendar(db, appointment)
    notification_status = notify_appointment_event(db, appointment, "booked")
    return BookAppointmentResponse(
        appointment_id=appointment.id,
        provider_name=appointment.provider.name,
        date=appointment.date,
        time=appointment.time,
        end_time=slot.end_time if slot else None,
        spoken_date=_format_spoken_date(appointment.date),
        spoken_time=_format_spoken_time(appointment.time),
        spoken_end_time=_format_spoken_time(slot.end_time if slot else None),
        spoken_time_range=_format_spoken_range(appointment.time, slot.end_time if slot else None),
        status=appointment.status,
        calendar_status=f"{calendar_status} | notifications={notification_status}",
    )


@router.post("/tools/cancel_appointment", response_model=AppointmentActionResponse)
def cancel_appointment_tool(
    payload: CancelAppointmentRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    try:
        appointment = cancel_appointment(
            db=db,
            appointment_id=payload.appointment_id,
            reason=payload.reason,
            cancelled_by="patient",
            cancelled_via="bot",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notify_appointment_event(db, appointment, "cancelled")
    reason = appointment.cancellation_reason or payload.reason or "cancelled by patient through bot"
    return AppointmentActionResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        detail=f"Appointment cancelled successfully. Reason: {reason}",
    )


@router.post("/tools/reschedule_appointment", response_model=AppointmentActionResponse)
def reschedule_appointment_tool(
    payload: RescheduleAppointmentRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_tool_api_key),
):
    try:
        appointment, calendar_detail, did_reschedule = reschedule_appointment(
            db=db,
            appointment_id=payload.appointment_id,
            new_slot_id=payload.new_slot_id,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notification_status: dict[str, str] | None = None
    if did_reschedule:
        notification_status = notify_appointment_event(db, appointment, "rescheduled")
    detail = "Appointment rescheduled successfully."
    if calendar_detail:
        detail = f"{detail} {calendar_detail}"
    if notification_status is not None:
        detail = f"{detail} | notifications={notification_status}"
    return AppointmentActionResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        detail=detail,
    )


@router.get("/public/reminder-action", response_model=AppointmentActionResponse)
def reminder_action(
    token: str = Query(..., min_length=16),
    action: str = Query(...),
    db: Session = Depends(get_db),
):
    action_normalized = (action or "").strip().lower()
    if action_normalized not in {"confirm", "cancel"}:
        raise HTTPException(status_code=400, detail="Action must be confirm or cancel.")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now_utc = datetime.now(dt_timezone.utc)
    appointment = (
        db.query(Appointment)
        .filter(Appointment.reminder_action_token_hash == token_hash)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="This reminder link is invalid or expired.")
    if appointment.reminder_action_used_at is not None:
        return AppointmentActionResponse(
            appointment_id=appointment.id,
            status=appointment.status,
            detail="This reminder link was already used.",
        )
    if appointment.reminder_action_expires_at and appointment.reminder_action_expires_at < now_utc:
        raise HTTPException(status_code=400, detail="This reminder link has expired.")

    if action_normalized == "confirm":
        appointment.patient_response = "confirmed"
        appointment.patient_responded_at = now_utc
        appointment.reminder_action_used_at = now_utc
        db.commit()
        db.refresh(appointment)
        return AppointmentActionResponse(
            appointment_id=appointment.id,
            status=appointment.status,
            detail="Appointment confirmed by patient.",
        )

    if appointment.status != "confirmed":
        appointment.reminder_action_used_at = now_utc
        db.commit()
        db.refresh(appointment)
        return AppointmentActionResponse(
            appointment_id=appointment.id,
            status=appointment.status,
            detail="Appointment is no longer active for cancellation.",
        )

    appointment = cancel_appointment(
        db=db,
        appointment_id=appointment.id,
        reason="Cancelled by patient through reminder link",
        cancelled_by="patient",
        cancelled_via="reminder_link",
    )
    appointment.patient_response = "cancelled"
    appointment.patient_responded_at = now_utc
    appointment.reminder_action_used_at = now_utc
    db.commit()
    db.refresh(appointment)
    return AppointmentActionResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        detail="Appointment cancelled by patient.",
    )


@router.post("/public/reminder-sms-reply")
@router.post("/public/reminder-whatsapp-reply")
def reminder_sms_reply(
    from_phone: str = Form(default="", alias="From"),
    body: str = Form(default="", alias="Body"),
    db: Session = Depends(get_db),
):
    message = (body or "").strip().lower()
    users = _find_users_by_phone(db, from_phone)
    if not users:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Message>We could not find your appointment record for this number.</Message></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    today = datetime.now().date()
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.user_id.in_([user.id for user in users]),
            Appointment.status == "confirmed",
            Appointment.reminder_sent_at.is_not(None),
            Appointment.patient_response.is_(None),
            Appointment.date >= today,
        )
        .order_by(
            Appointment.reminder_sent_at.desc(),
            Appointment.date.desc(),
            Appointment.time.desc(),
            Appointment.id.desc(),
        )
        .first()
    )

    if not appointment:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Message>No active reminder was found for your number.</Message></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    now_utc = datetime.now(dt_timezone.utc)
    if message in {"yes", "y", "confirm", "confirmed", "yes confirm"}:
        appointment.patient_response = "confirmed"
        appointment.patient_responded_at = now_utc
        appointment.reminder_action_used_at = now_utc
        db.commit()
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Message>Thank you. Your appointment is confirmed.</Message></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    if message in {"no", "n", "cancel", "no cancel"}:
        appointment = cancel_appointment(
            db=db,
            appointment_id=appointment.id,
            reason="Cancelled by patient through SMS reply",
            cancelled_by="patient",
            cancelled_via="sms_reply",
        )
        appointment.patient_response = "cancelled"
        appointment.patient_responded_at = now_utc
        appointment.reminder_action_used_at = now_utc
        db.commit()
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Message>Your appointment has been cancelled.</Message></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Message>Please reply YES to confirm or NO to cancel your appointment.</Message></Response>"
    )
    return Response(content=xml, media_type="application/xml")
