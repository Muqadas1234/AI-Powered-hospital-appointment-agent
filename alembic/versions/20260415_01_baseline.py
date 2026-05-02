"""baseline schema for production phase 2

Revision ID: 20260415_01
Revises:
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_01"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("email", sa.String(length=120), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=True),
        )
        op.create_index("ix_users_id", "users", ["id"])
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not _has_table(inspector, "providers"):
        op.create_table(
            "providers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("service", sa.String(length=80), nullable=False),
            sa.Column("rating", sa.Float(), nullable=False, server_default="4.0"),
        )
        op.create_index("ix_providers_id", "providers", ["id"])
        op.create_index("ix_providers_service", "providers", ["service"])

    if not _has_table(inspector, "slots"):
        op.create_table(
            "slots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("time", sa.Time(), nullable=False),
            sa.Column("is_booked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("provider_id", "date", "time", name="uq_provider_slot_time"),
        )
        op.create_index("ix_slots_id", "slots", ["id"])
        op.create_index("ix_slots_date", "slots", ["date"])

    if not _has_table(inspector, "appointments"):
        op.create_table(
            "appointments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_id", sa.String(length=120), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("time", sa.Time(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="confirmed"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_appointments_id", "appointments", ["id"])
        op.create_index("ix_appointments_date", "appointments", ["date"])
        op.create_index("ix_appointments_request_id", "appointments", ["request_id"], unique=True)
    else:
        if not _has_column(inspector, "appointments", "request_id"):
            op.add_column("appointments", sa.Column("request_id", sa.String(length=120), nullable=True))
            op.create_index("ix_appointments_request_id", "appointments", ["request_id"], unique=True)
        if not _has_column(inspector, "appointments", "created_at"):
            op.add_column(
                "appointments",
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
            )
        if not _has_column(inspector, "appointments", "updated_at"):
            op.add_column(
                "appointments",
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
            )

    if not _has_table(inspector, "faqs"):
        op.create_table(
            "faqs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("question", sa.String(length=300), nullable=False),
            sa.Column("answer", sa.String(length=1000), nullable=False),
        )
        op.create_index("ix_faqs_id", "faqs", ["id"])
        op.create_index("ix_faqs_question", "faqs", ["question"], unique=True)

    if not _has_table(inspector, "admin_users"):
        op.create_table(
            "admin_users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False, server_default="staff"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_admin_users_id", "admin_users", ["id"])
        op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)

    if not _has_table(inspector, "notification_logs"):
        op.create_table(
            "notification_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=False),
            sa.Column("channel", sa.String(length=30), nullable=False),
            sa.Column("recipient", sa.String(length=255), nullable=False),
            sa.Column("message", sa.String(length=1000), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="sent"),
            sa.Column("error", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_notification_logs_id", "notification_logs", ["id"])
        op.create_index("ix_notification_logs_appointment_id", "notification_logs", ["appointment_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in [
        "notification_logs",
        "admin_users",
        "faqs",
        "appointments",
        "slots",
        "providers",
        "users",
    ]:
        if table_name in inspector.get_table_names():
            op.drop_table(table_name)
