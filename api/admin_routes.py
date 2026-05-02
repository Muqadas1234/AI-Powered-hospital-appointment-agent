from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.auth_deps import get_current_admin_user
from db.database import get_db
from db.models import AdminUser, Appointment, FAQ, NotificationLog, Provider, Slot, User
from schemas.dto import (
    AdminCancelAppointmentRequest,
    AppointmentActionResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AppointmentStatusUpdateRequest,
    AppointmentListItem,
    AppointmentListResponse,
    FAQAdminResponse,
    FAQCreateRequest,
    FAQUpdateRequest,
    NotificationLogItem,
    NotificationLogListResponse,
    ProviderAdminResponse,
    ProviderCreateRequest,
    ProviderUpdateRequest,
    SlotBulkCreateRequest,
    SlotAdminResponse,
    SlotCreateRequest,
    SlotUpdateRequest,
)
from services.auth_service import authenticate_admin_user, create_access_token
from services.booking_service import cancel_appointment
from services.google_calendar_service import delete_google_calendar_event
from services.notification_service import notify_appointment_event

router = APIRouter(prefix="/api/v1", tags=["admin"])


def _latest_whatsapp_reminder_sent_at(db: Session, appointment_id: int):
    latest_row = (
        db.query(NotificationLog.created_at)
        .filter(
            NotificationLog.appointment_id == appointment_id,
            NotificationLog.channel == "whatsapp",
            NotificationLog.event_type == "reminder",
            NotificationLog.status == "sent",
        )
        .order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc())
        .first()
    )
    return latest_row[0] if latest_row else None


def _slot_end_time(start: time, end: time | None, duration_minutes: int = 30) -> time:
    if end is not None:
        return end
    return (datetime.combine(date.today(), start) + timedelta(minutes=duration_minutes)).time()


def _times_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


def _validate_slot_window(start: time, end: time) -> None:
    if end <= start:
        raise HTTPException(status_code=400, detail="end_time must be later than start time.")


@router.post("/auth/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    user = authenticate_admin_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = create_access_token(subject=user.username, role=user.role)
    return AdminLoginResponse(access_token=token, role=user.role)


@router.get("/admin/appointments", response_model=AppointmentListResponse)
def list_appointments(
    status: str | None = Query(default=None),
    user_phone: str | None = Query(default=None),
    provider_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    query = db.query(Appointment).join(User, Appointment.user_id == User.id).join(Provider, Appointment.provider_id == Provider.id)

    if status:
        query = query.filter(Appointment.status == status)
    if user_phone:
        query = query.filter(User.phone.ilike(user_phone.strip()))
    if provider_id:
        query = query.filter(Appointment.provider_id == provider_id)
    if date_from:
        query = query.filter(Appointment.date >= date_from)
    if date_to:
        query = query.filter(Appointment.date <= date_to)

    total = query.count()
    appointments = (
        query.order_by(Appointment.date.desc(), Appointment.time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = [
        AppointmentListItem(
            id=item.id,
            user_name=item.user.name,
            user_phone=item.user.phone,
            provider_name=item.provider.name,
            service=item.provider.service,
            date=item.date,
            time=item.time,
            end_time=(
                db.query(Slot.end_time)
                .filter(Slot.provider_id == item.provider_id, Slot.date == item.date, Slot.time == item.time)
                .scalar()
            ),
            status=item.status,
            reminder_sent_at=item.reminder_sent_at,
            reminder_whatsapp_sent_at=_latest_whatsapp_reminder_sent_at(db, item.id),
            patient_response=item.patient_response,
            patient_responded_at=item.patient_responded_at,
            cancelled_by=item.cancelled_by,
            cancelled_via=item.cancelled_via,
            cancellation_reason=item.cancellation_reason,
        )
        for item in appointments
    ]
    return AppointmentListResponse(total=total, items=items)


@router.get("/admin/appointments/{appointment_id}", response_model=AppointmentListItem)
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return AppointmentListItem(
        id=appointment.id,
        user_name=appointment.user.name,
        user_phone=appointment.user.phone,
        provider_name=appointment.provider.name,
        service=appointment.provider.service,
        date=appointment.date,
        time=appointment.time,
        end_time=(
            db.query(Slot.end_time)
            .filter(
                Slot.provider_id == appointment.provider_id,
                Slot.date == appointment.date,
                Slot.time == appointment.time,
            )
            .scalar()
        ),
        status=appointment.status,
        reminder_sent_at=appointment.reminder_sent_at,
        reminder_whatsapp_sent_at=_latest_whatsapp_reminder_sent_at(db, appointment.id),
        patient_response=appointment.patient_response,
        patient_responded_at=appointment.patient_responded_at,
        cancelled_by=appointment.cancelled_by,
        cancelled_via=appointment.cancelled_via,
        cancellation_reason=appointment.cancellation_reason,
    )


@router.post("/admin/appointments/{appointment_id}/cancel", response_model=AppointmentActionResponse)
def admin_cancel_appointment(
    appointment_id: int,
    payload: AdminCancelAppointmentRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if appointment.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Only confirmed appointments can be cancelled. Use delete only if you must remove a record.",
        )
    reason = (payload.reason or "").strip() or "Cancelled by clinic (admin)."
    try:
        appointment = cancel_appointment(
            db=db,
            appointment_id=appointment_id,
            reason=reason,
            cancelled_by="admin",
            cancelled_via="admin_panel",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notification_status = notify_appointment_event(db, appointment, "cancelled")
    return AppointmentActionResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        detail=f"Appointment cancelled. Calendar updated. Notifications: {notification_status}",
    )


@router.get("/admin/notifications", response_model=NotificationLogListResponse)
def list_notifications(
    channel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    query = db.query(NotificationLog)
    if channel:
        query = query.filter(NotificationLog.channel == channel)
    if status:
        query = query.filter(NotificationLog.status == status)

    total = query.count()
    rows = (
        query.order_by(NotificationLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        NotificationLogItem(
            id=row.id,
            appointment_id=row.appointment_id,
            channel=row.channel,
            recipient=row.recipient,
            status=row.status,
            error=row.error,
            event_type=row.event_type,
        )
        for row in rows
    ]
    return NotificationLogListResponse(total=total, items=items)


@router.delete("/admin/notifications/{notification_id}", response_model=AppointmentActionResponse)
def delete_notification_log(
    notification_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    row = db.query(NotificationLog).filter(NotificationLog.id == notification_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Notification log not found.")
    db.delete(row)
    db.commit()
    return AppointmentActionResponse(
        appointment_id=0,
        status="deleted",
        detail="Notification log removed from database.",
    )


@router.get("/admin/providers", response_model=list[ProviderAdminResponse])
def list_providers(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    query = (
        db.query(
            Provider,
            func.count(Appointment.id).label("active_appointments_count"),
        )
        .outerjoin(
            Appointment,
            (Appointment.provider_id == Provider.id) & (Appointment.status == "confirmed"),
        )
        .group_by(Provider.id)
    )
    if not include_inactive:
        query = query.filter(Provider.is_active.is_(True))

    rows = query.order_by(Provider.id.asc()).all()
    return [
        ProviderAdminResponse(
            id=provider.id,
            name=provider.name,
            service=provider.service,
            fee_pkr=provider.fee_pkr,
            is_active=provider.is_active,
            active_appointments_count=active_count,
            created_by=provider.created_by,
        )
        for provider, active_count in rows
    ]


@router.post("/admin/providers", response_model=ProviderAdminResponse)
def create_provider(
    payload: ProviderCreateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user),
):
    provider = Provider(
        name=payload.name.strip(),
        service=payload.service.strip().lower(),
        fee_pkr=payload.fee_pkr,
        is_active=True,
        created_by=current_admin.username,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return ProviderAdminResponse(
        id=provider.id,
        name=provider.name,
        service=provider.service,
        fee_pkr=provider.fee_pkr,
        is_active=provider.is_active,
        active_appointments_count=0,
        created_by=provider.created_by,
    )


@router.put("/admin/providers/{provider_id}", response_model=ProviderAdminResponse)
def update_provider(
    provider_id: int,
    payload: ProviderUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    if payload.name is not None:
        provider.name = payload.name.strip()
    if payload.service is not None:
        provider.service = payload.service.strip().lower()
    if payload.fee_pkr is not None:
        provider.fee_pkr = payload.fee_pkr
    if payload.is_active is not None:
        provider.is_active = payload.is_active
    db.commit()
    db.refresh(provider)
    active_count = (
        db.query(Appointment)
        .filter(Appointment.provider_id == provider.id, Appointment.status == "confirmed")
        .count()
    )
    return ProviderAdminResponse(
        id=provider.id,
        name=provider.name,
        service=provider.service,
        fee_pkr=provider.fee_pkr,
        is_active=provider.is_active,
        active_appointments_count=active_count,
        created_by=provider.created_by,
    )


@router.delete("/admin/providers/{provider_id}", response_model=AppointmentActionResponse)
def archive_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    active_count = (
        db.query(Appointment)
        .filter(Appointment.provider_id == provider_id, Appointment.status == "confirmed")
        .count()
    )
    if active_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive provider: {active_count} confirmed appointments exist.",
        )
    provider.is_active = False
    db.commit()
    return AppointmentActionResponse(appointment_id=0, status="archived", detail="Provider archived successfully.")


@router.patch("/admin/providers/{provider_id}/restore", response_model=AppointmentActionResponse)
def restore_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    provider.is_active = True
    db.commit()
    return AppointmentActionResponse(appointment_id=0, status="restored", detail="Provider restored successfully.")


@router.get("/admin/providers/{provider_id}/delete-impact", response_model=AppointmentActionResponse)
def provider_delete_impact(
    provider_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    active_count = (
        db.query(Appointment)
        .filter(Appointment.provider_id == provider_id, Appointment.status == "confirmed")
        .count()
    )
    if active_count > 0:
        return AppointmentActionResponse(
            appointment_id=0,
            status="blocked",
            detail=f"Blocked: {active_count} confirmed appointments linked to this provider.",
        )
    return AppointmentActionResponse(appointment_id=0, status="safe", detail="Safe to archive provider.")


@router.delete("/admin/providers/{provider_id}/hard", response_model=AppointmentActionResponse)
def hard_delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    active_appt = db.query(Appointment).filter(Appointment.provider_id == provider_id, Appointment.status == "confirmed").first()
    if active_appt:
        raise HTTPException(status_code=400, detail="Provider has confirmed appointments. Cancel/reschedule them first.")
    db.query(Slot).filter(Slot.provider_id == provider_id).delete()
    db.delete(provider)
    db.commit()
    return AppointmentActionResponse(appointment_id=0, status="deleted", detail="Provider deleted successfully.")


@router.get("/admin/slots", response_model=list[SlotAdminResponse])
def list_slots(
    provider_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    query = db.query(Slot)
    if provider_id:
        query = query.filter(Slot.provider_id == provider_id)
    if date_from:
        query = query.filter(Slot.date >= date_from)
    if date_to:
        query = query.filter(Slot.date <= date_to)

    rows = query.order_by(Slot.date.asc(), Slot.time.asc()).all()
    return [
        SlotAdminResponse(
            id=item.id,
            provider_id=item.provider_id,
            date=item.date,
            time=item.time,
            end_time=item.end_time,
            is_booked=item.is_booked,
            created_by=item.created_by,
        )
        for item in rows
    ]


@router.post("/admin/slots", response_model=SlotAdminResponse)
def create_slot(
    payload: SlotCreateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == payload.provider_id).first()
    if not provider:
        raise HTTPException(status_code=400, detail="Provider not found.")
    if not provider.is_active:
        raise HTTPException(status_code=400, detail="Cannot create slot for archived provider.")

    new_end = _slot_end_time(payload.time, payload.end_time)

    _validate_slot_window(payload.time, new_end)

    existing = (
        db.query(Slot)
        .filter(Slot.provider_id == payload.provider_id, Slot.date == payload.date, Slot.time == payload.time)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Slot already exists for provider/date/time.")

    same_day_slots = (
        db.query(Slot)
        .filter(Slot.provider_id == payload.provider_id, Slot.date == payload.date)
        .all()
    )
    for row in same_day_slots:
        row_end = row.end_time or _slot_end_time(row.time, None)
        if _times_overlap(payload.time, new_end, row.time, row_end):
            raise HTTPException(status_code=400, detail="Slot time overlaps with an existing slot.")

    slot = Slot(
        provider_id=payload.provider_id,
        date=payload.date,
        time=payload.time,
        end_time=new_end,
        is_booked=False,
        created_by=current_admin.username,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return SlotAdminResponse(
        id=slot.id,
        provider_id=slot.provider_id,
        date=slot.date,
        time=slot.time,
        end_time=slot.end_time,
        is_booked=slot.is_booked,
        created_by=slot.created_by,
    )


@router.post("/admin/slots/bulk", response_model=list[SlotAdminResponse])
def create_slots_bulk(
    payload: SlotBulkCreateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user),
):
    provider = db.query(Provider).filter(Provider.id == payload.provider_id).first()
    if not provider:
        raise HTTPException(status_code=400, detail="Provider not found.")

    created_rows: list[Slot] = []
    for day_offset in range(payload.days):
        slot_date = payload.start_date + timedelta(days=day_offset)
        for hhmm in payload.times:
            try:
                parsed_time = datetime.strptime(hhmm, "%H:%M").time()
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid time format: {hhmm}. Use HH:MM") from exc
            parsed_end_time = _slot_end_time(parsed_time, None, payload.duration_minutes)
            _validate_slot_window(parsed_time, parsed_end_time)

            exists = (
                db.query(Slot)
                .filter(Slot.provider_id == payload.provider_id, Slot.date == slot_date, Slot.time == parsed_time)
                .first()
            )
            if exists:
                continue

            overlap_rows = (
                db.query(Slot)
                .filter(Slot.provider_id == payload.provider_id, Slot.date == slot_date)
                .all()
            )
            blocked = False
            for row in overlap_rows:
                row_end = row.end_time or _slot_end_time(row.time, None)
                if _times_overlap(parsed_time, parsed_end_time, row.time, row_end):
                    blocked = True
                    break
            if blocked:
                continue

            row = Slot(
                provider_id=payload.provider_id,
                date=slot_date,
                time=parsed_time,
                end_time=parsed_end_time,
                is_booked=False,
                created_by=current_admin.username,
            )
            db.add(row)
            created_rows.append(row)

    db.commit()
    for row in created_rows:
        db.refresh(row)

    return [
        SlotAdminResponse(
            id=item.id,
            provider_id=item.provider_id,
            date=item.date,
            time=item.time,
            end_time=item.end_time,
            is_booked=item.is_booked,
            created_by=item.created_by,
        )
        for item in created_rows
    ]


@router.delete("/admin/slots/{slot_id}", response_model=AppointmentActionResponse)
def delete_slot(
    slot_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    slot = db.query(Slot).filter(Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found.")
    if slot.is_booked:
        raise HTTPException(status_code=400, detail="Cannot delete booked slot.")
    db.delete(slot)
    db.commit()
    return AppointmentActionResponse(appointment_id=0, status="deleted", detail="Slot deleted successfully.")


@router.put("/admin/slots/{slot_id}", response_model=SlotAdminResponse)
def update_slot(
    slot_id: int,
    payload: SlotUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    if payload.date is None and payload.time is None and payload.end_time is None:
        raise HTTPException(status_code=400, detail="Provide at least one of: date, time, end_time.")

    slot = db.query(Slot).filter(Slot.id == slot_id).with_for_update().first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found.")
    if slot.is_booked:
        raise HTTPException(status_code=400, detail="Cannot edit a booked slot.")

    provider = db.query(Provider).filter(Provider.id == slot.provider_id).first()
    if not provider or not provider.is_active:
        raise HTTPException(status_code=400, detail="Provider missing or archived.")

    new_date = payload.date if payload.date is not None else slot.date
    new_time = payload.time if payload.time is not None else slot.time
    if payload.end_time is not None:
        new_end = _slot_end_time(new_time, payload.end_time)
    elif payload.time is not None and payload.time != slot.time:
        new_end = _slot_end_time(new_time, None)
    else:
        new_end = slot.end_time or _slot_end_time(new_time, None)

    _validate_slot_window(new_time, new_end)

    if new_date != slot.date or new_time != slot.time:
        duplicate = (
            db.query(Slot)
            .filter(
                Slot.provider_id == slot.provider_id,
                Slot.date == new_date,
                Slot.time == new_time,
                Slot.id != slot.id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Another slot already exists for this provider/date/time.")

        same_day = (
            db.query(Slot)
            .filter(Slot.provider_id == slot.provider_id, Slot.date == new_date, Slot.id != slot.id)
            .all()
        )
        for row in same_day:
            row_end = row.end_time or _slot_end_time(row.time, None)
            if _times_overlap(new_time, new_end, row.time, row_end):
                raise HTTPException(status_code=400, detail="Slot time overlaps with an existing slot.")
    elif payload.end_time is not None:
        same_day = (
            db.query(Slot)
            .filter(Slot.provider_id == slot.provider_id, Slot.date == new_date, Slot.id != slot.id)
            .all()
        )
        for row in same_day:
            row_end = row.end_time or _slot_end_time(row.time, None)
            if _times_overlap(new_time, new_end, row.time, row_end):
                raise HTTPException(status_code=400, detail="Slot time overlaps with an existing slot.")

    slot.date = new_date
    slot.time = new_time
    slot.end_time = new_end
    db.commit()
    db.refresh(slot)
    return SlotAdminResponse(
        id=slot.id,
        provider_id=slot.provider_id,
        date=slot.date,
        time=slot.time,
        end_time=slot.end_time,
        is_booked=slot.is_booked,
        created_by=slot.created_by,
    )


@router.get("/admin/faqs", response_model=list[FAQAdminResponse])
def list_faqs(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    query = db.query(FAQ)
    if not include_inactive:
        query = query.filter(FAQ.is_active.is_(True))
    rows = query.order_by(FAQ.id.asc()).all()
    return [
        FAQAdminResponse(
            id=item.id,
            question=item.question,
            answer=item.answer,
            is_active=item.is_active,
            updated_at=item.updated_at,
            created_by=item.created_by,
        )
        for item in rows
    ]


@router.post("/admin/faqs", response_model=FAQAdminResponse)
def create_faq(
    payload: FAQCreateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user),
):
    normalized_question = payload.question.strip().lower()
    existing = db.query(FAQ).filter(FAQ.question.ilike(normalized_question)).first()
    if existing and existing.is_active:
        raise HTTPException(status_code=400, detail="FAQ question already exists.")
    if existing and not existing.is_active:
        existing.answer = payload.answer.strip()
        existing.is_active = True
        existing.created_by = current_admin.username
        db.commit()
        db.refresh(existing)
        return FAQAdminResponse(
            id=existing.id,
            question=existing.question,
            answer=existing.answer,
            is_active=existing.is_active,
            updated_at=existing.updated_at,
            created_by=existing.created_by,
        )

    faq = FAQ(
        question=normalized_question,
        answer=payload.answer.strip(),
        is_active=True,
        created_by=current_admin.username,
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return FAQAdminResponse(
        id=faq.id,
        question=faq.question,
        answer=faq.answer,
        is_active=faq.is_active,
        updated_at=faq.updated_at,
        created_by=faq.created_by,
    )


@router.put("/admin/faqs/{faq_id}", response_model=FAQAdminResponse)
def update_faq(
    faq_id: int,
    payload: FAQUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    if payload.question is not None:
        normalized_question = payload.question.strip().lower()
        duplicate = db.query(FAQ).filter(FAQ.question == normalized_question, FAQ.id != faq.id, FAQ.is_active.is_(True)).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Another active FAQ already uses this question.")
        faq.question = normalized_question
    if payload.answer is not None:
        faq.answer = payload.answer.strip()
    if payload.is_active is not None:
        faq.is_active = payload.is_active
    db.commit()
    db.refresh(faq)
    return FAQAdminResponse(
        id=faq.id,
        question=faq.question,
        answer=faq.answer,
        is_active=faq.is_active,
        updated_at=faq.updated_at,
        created_by=faq.created_by,
    )


@router.delete("/admin/faqs/{faq_id}", response_model=AppointmentActionResponse)
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    db.delete(faq)
    db.commit()
    return AppointmentActionResponse(appointment_id=0, status="deleted", detail="FAQ deleted permanently.")


@router.patch("/admin/appointments/{appointment_id}/status", response_model=AppointmentActionResponse)
def update_appointment_status(
    appointment_id: int,
    payload: AppointmentStatusUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    next_status = payload.status.strip().lower()
    appointment.status = next_status
    if next_status == "cancelled":
        appointment.cancelled_by = "admin"
        appointment.cancelled_via = "admin_panel"
        if not (appointment.cancellation_reason or "").strip():
            appointment.cancellation_reason = "cancelled by admin from dashboard"
    elif next_status == "confirmed":
        appointment.cancelled_by = None
        appointment.cancelled_via = None
        appointment.cancellation_reason = None
    db.commit()
    db.refresh(appointment)
    if next_status in {"cancelled", "confirmed"}:
        event_type = "cancelled" if next_status == "cancelled" else "booked"
        notify_appointment_event(db, appointment, event_type)
    return AppointmentActionResponse(
        appointment_id=appointment.id,
        status=appointment.status,
        detail="Appointment status updated successfully.",
    )


@router.delete("/admin/appointments/{appointment_id}/hard", response_model=AppointmentActionResponse)
def hard_delete_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    # Free linked slot so it can be reused after deletion.
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

    calendar_event_id = (appointment.google_calendar_event_id or "").strip()
    calendar_note = "calendar-not-linked"
    if calendar_event_id:
        _message, deleted = delete_google_calendar_event(calendar_event_id)
        calendar_note = "calendar-event-deleted" if deleted else "calendar-event-delete-failed"
        if deleted:
            appointment.google_calendar_event_id = None

    db.query(NotificationLog).filter(NotificationLog.appointment_id == appointment.id).delete()
    db.delete(appointment)
    db.commit()
    return AppointmentActionResponse(
        appointment_id=appointment_id,
        status="deleted",
        detail=f"Appointment deleted successfully ({calendar_note}).",
    )
