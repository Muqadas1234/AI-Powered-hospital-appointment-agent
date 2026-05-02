import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Load project-root `.env` explicitly. `override=True` so a stale Windows/user
# `DATABASE_URL` does not shadow the file (common cause of "wrong" postgres password).
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./appointment_agent.db",
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def apply_runtime_migrations():
    """
    Lightweight runtime migrations for local/dev use.
    For production, prefer Alembic migrations.
    """
    inspector = inspect(engine)
    if "appointments" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("appointments")}
    provider_columns = {col["name"] for col in inspector.get_columns("providers")} if "providers" in inspector.get_table_names() else set()
    faq_columns = {col["name"] for col in inspector.get_columns("faqs")} if "faqs" in inspector.get_table_names() else set()
    slot_columns = {col["name"] for col in inspector.get_columns("slots")} if "slots" in inspector.get_table_names() else set()
    user_columns = {col["name"] for col in inspector.get_columns("users")} if "users" in inspector.get_table_names() else set()
    notification_columns = (
        {col["name"] for col in inspector.get_columns("notification_logs")}
        if "notification_logs" in inspector.get_table_names()
        else set()
    )
    statements = []

    if "request_id" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN request_id VARCHAR(120)")
    if "created_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN created_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
            )
    if "updated_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN updated_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
            )
    if "is_active" not in provider_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE providers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
        else:
            statements.append("ALTER TABLE providers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")
    if "is_active" not in faq_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE faqs ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
        else:
            statements.append("ALTER TABLE faqs ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")
    if "updated_at" not in faq_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE faqs ADD COLUMN updated_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE faqs ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
            )
    if "created_by" not in provider_columns:
        statements.append("ALTER TABLE providers ADD COLUMN created_by VARCHAR(120)")
    if "created_by" not in faq_columns:
        statements.append("ALTER TABLE faqs ADD COLUMN created_by VARCHAR(120)")
    if "created_by" not in slot_columns:
        statements.append("ALTER TABLE slots ADD COLUMN created_by VARCHAR(120)")
    if "end_time" not in slot_columns:
        statements.append("ALTER TABLE slots ADD COLUMN end_time TIME")
    if "phone" not in user_columns:
        statements.append("ALTER TABLE users ADD COLUMN phone VARCHAR(30)")
    if "google_calendar_event_id" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN google_calendar_event_id VARCHAR(255)")
    if "event_type" not in notification_columns and "notification_logs" in inspector.get_table_names():
        statements.append("ALTER TABLE notification_logs ADD COLUMN event_type VARCHAR(30)")
    if "cancelled_by" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN cancelled_by VARCHAR(120)")
    if "cancelled_via" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN cancelled_via VARCHAR(40)")
    if "cancellation_reason" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN cancellation_reason VARCHAR(255)")
    if "reminder_sent_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN reminder_sent_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN reminder_sent_at TIMESTAMP WITH TIME ZONE"
            )
    if "reminder_call_sent_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN reminder_call_sent_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN reminder_call_sent_at TIMESTAMP WITH TIME ZONE"
            )
    if "reminder_action_token_hash" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN reminder_action_token_hash VARCHAR(128)")
    if "reminder_action_expires_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN reminder_action_expires_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN reminder_action_expires_at TIMESTAMP WITH TIME ZONE"
            )
    if "reminder_action_used_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN reminder_action_used_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN reminder_action_used_at TIMESTAMP WITH TIME ZONE"
            )
    if "patient_response" not in existing_columns:
        statements.append("ALTER TABLE appointments ADD COLUMN patient_response VARCHAR(30)")
    if "patient_responded_at" not in existing_columns:
        if DATABASE_URL.startswith("sqlite"):
            statements.append("ALTER TABLE appointments ADD COLUMN patient_responded_at DATETIME")
        else:
            statements.append(
                "ALTER TABLE appointments ADD COLUMN patient_responded_at TIMESTAMP WITH TIME ZONE"
            )

    if not statements:
        return

    with engine.begin() as connection:
        for sql in statements:
            connection.execute(text(sql))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
