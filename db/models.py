from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint, func
from sqlalchemy.orm import relationship

from db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(30), nullable=True)

    appointments = relationship("Appointment", back_populates="user")


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    service = Column(String(80), nullable=False, index=True)
    fee_pkr = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(120), nullable=True, index=True)

    slots = relationship("Slot", back_populates="provider")
    appointments = relationship("Appointment", back_populates="provider")


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        UniqueConstraint("provider_id", "date", "time", name="uq_provider_slot_time"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=True)
    is_booked = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(120), nullable=True, index=True)

    provider = relationship("Provider", back_populates="slots")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(120), unique=True, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    time = Column(Time, nullable=False)
    status = Column(String(30), nullable=False, default="confirmed")
    google_calendar_event_id = Column(String(255), nullable=True, index=True)
    cancelled_by = Column(String(120), nullable=True)
    cancelled_via = Column(String(40), nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True, index=True)
    reminder_call_sent_at = Column(DateTime(timezone=True), nullable=True, index=True)
    reminder_action_token_hash = Column(String(128), nullable=True, index=True)
    reminder_action_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    reminder_action_used_at = Column(DateTime(timezone=True), nullable=True, index=True)
    patient_response = Column(String(30), nullable=True, index=True)  # confirmed | cancelled
    patient_responded_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="appointments")
    provider = relationship("Provider", back_populates="appointments")


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(300), nullable=False, unique=True)
    answer = Column(String(1000), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(120), nullable=True, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="staff")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False, index=True)
    channel = Column(String(30), nullable=False)  # email / sms
    recipient = Column(String(255), nullable=False)
    message = Column(String(1000), nullable=False)
    status = Column(String(30), nullable=False, default="sent")
    error = Column(String(500), nullable=True)
    # booked | cancelled | rescheduled | unknown (legacy rows)
    event_type = Column(String(30), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
