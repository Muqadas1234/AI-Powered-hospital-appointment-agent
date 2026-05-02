from datetime import date, datetime, time
import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field


class FAQRequest(BaseModel):
    question: str = Field(..., min_length=2)


class FAQResponse(BaseModel):
    answer: str


class ProviderResponse(BaseModel):
    id: int
    name: str
    service: str
    fee_pkr: Optional[int] = None


class ProviderLookupRequest(BaseModel):
    service: str = Field(default="all services")


class SlotResponse(BaseModel):
    id: int
    provider_id: int
    date: date
    time: time
    end_time: Optional[time] = None
    spoken_date: Optional[str] = None
    spoken_time: Optional[str] = None
    spoken_end_time: Optional[str] = None
    spoken_time_range: Optional[str] = None
    is_booked: bool


class SlotLookupRequest(BaseModel):
    provider_id: Optional[int] = None


class AvailabilityCheckRequest(BaseModel):
    service: str = Field(..., min_length=2)
    date: date
    preferred_time: Optional[str] = Field(default=None, description="HH:MM or HH:MM:SS")
    time_window: Optional[str] = Field(default=None, description="morning/afternoon/evening")
    doctor_name: Optional[str] = Field(
        default=None,
        description="Optional: named doctor (e.g. Dr Aisha Khan) to narrow providers.",
    )


class AvailabilityOption(BaseModel):
    provider_id: int
    provider_name: str
    date: date
    time: time
    end_time: Optional[time] = None
    spoken_date: Optional[str] = None
    spoken_time: Optional[str] = None
    spoken_end_time: Optional[str] = None
    spoken_time_range: Optional[str] = None
    slot_id: int


class AvailabilityCheckResponse(BaseModel):
    is_available: bool
    detail: str
    best_option: Optional[AvailabilityOption] = None
    alternatives: list[AvailabilityOption] = []


class CalendarCheckRequest(BaseModel):
    user_phone: str = Field(..., min_length=8, max_length=30)
    date: date
    time: time


class CalendarCheckResponse(BaseModel):
    has_conflict: bool
    detail: str


class BookAppointmentRequest(BaseModel):
    user_name: str = Field(..., min_length=2)
    user_phone: str = Field(..., min_length=8, max_length=30)
    provider_id: int
    slot_id: int
    confirmed_by_user: bool = Field(
        default=False,
        description="Must be true only after reading full booking details and receiving explicit yes/confirm from patient.",
    )
    confirmation_text: Optional[str] = Field(
        default=None,
        max_length=120,
        description='Exact patient confirmation words, e.g. "yes confirm".',
    )
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=120)


class BookAppointmentResponse(BaseModel):
    appointment_id: int
    provider_name: str
    date: date
    time: time
    end_time: Optional[time] = None
    spoken_date: Optional[str] = None
    spoken_time: Optional[str] = None
    spoken_end_time: Optional[str] = None
    spoken_time_range: Optional[str] = None
    status: str
    calendar_status: Optional[str] = None


class AppointmentActionResponse(BaseModel):
    appointment_id: int
    status: str
    detail: str


class CancelAppointmentRequest(BaseModel):
    appointment_id: int
    reason: Optional[str] = Field(default="cancelled by user", max_length=200)


class RescheduleAppointmentRequest(BaseModel):
    appointment_id: int
    new_slot_id: int
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=120)


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class AppointmentListItem(BaseModel):
    id: int
    user_name: str
    user_phone: Optional[str] = None
    provider_name: str
    service: str
    date: date
    time: time
    end_time: Optional[time] = None
    status: str
    reminder_sent_at: Optional[datetime] = None
    reminder_whatsapp_sent_at: Optional[datetime] = None
    patient_response: Optional[str] = None
    patient_responded_at: Optional[datetime] = None
    cancelled_by: Optional[str] = None
    cancelled_via: Optional[str] = None
    cancellation_reason: Optional[str] = None


class AppointmentListResponse(BaseModel):
    total: int
    items: list[AppointmentListItem]


class NotificationLogItem(BaseModel):
    id: int
    appointment_id: int
    channel: str
    recipient: str
    status: str
    error: Optional[str] = None
    event_type: Optional[str] = None


class NotificationLogListResponse(BaseModel):
    total: int
    items: list[NotificationLogItem]


class ProviderCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    service: str = Field(..., min_length=2, max_length=80)
    fee_pkr: Optional[int] = Field(default=None, ge=0)


class ProviderAdminResponse(BaseModel):
    id: int
    name: str
    service: str
    fee_pkr: Optional[int] = None
    is_active: bool
    active_appointments_count: int = 0
    created_by: Optional[str] = None


class SlotCreateRequest(BaseModel):
    provider_id: int
    date: date
    time: time
    end_time: time


class SlotAdminResponse(BaseModel):
    id: int
    provider_id: int
    date: date
    time: time
    end_time: Optional[time] = None
    is_booked: bool
    created_by: Optional[str] = None


class FAQCreateRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=300)
    answer: str = Field(..., min_length=2, max_length=1000)


class FAQAdminResponse(BaseModel):
    id: int
    question: str
    answer: str
    is_active: bool
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    service: Optional[str] = Field(default=None, min_length=2, max_length=80)
    fee_pkr: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class SlotBulkCreateRequest(BaseModel):
    provider_id: int
    start_date: date
    days: int = Field(default=7, ge=1, le=60)
    times: list[str] = Field(default_factory=list, min_length=1)
    duration_minutes: int = Field(default=30, ge=5, le=240)


class FAQUpdateRequest(BaseModel):
    question: Optional[str] = Field(default=None, min_length=3, max_length=300)
    answer: Optional[str] = Field(default=None, min_length=2, max_length=1000)
    is_active: Optional[bool] = None


class SlotUpdateRequest(BaseModel):
    date: Optional[dt.date] = None
    time: Optional[dt.time] = None
    end_time: Optional[dt.time] = None


class AppointmentStatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=3, max_length=30)


class AdminCancelAppointmentRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)
