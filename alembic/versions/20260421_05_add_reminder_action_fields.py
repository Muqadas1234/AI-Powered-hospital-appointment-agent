"""add reminder action and patient response fields

Revision ID: 20260421_05
Revises: 20260421_04
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260421_05"
down_revision = "20260421_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "appointments" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("appointments")}
    with op.batch_alter_table("appointments") as batch_op:
        if "reminder_action_token_hash" not in cols:
            batch_op.add_column(sa.Column("reminder_action_token_hash", sa.String(length=128), nullable=True))
        if "reminder_action_expires_at" not in cols:
            batch_op.add_column(sa.Column("reminder_action_expires_at", sa.DateTime(timezone=True), nullable=True))
        if "reminder_action_used_at" not in cols:
            batch_op.add_column(sa.Column("reminder_action_used_at", sa.DateTime(timezone=True), nullable=True))
        if "patient_response" not in cols:
            batch_op.add_column(sa.Column("patient_response", sa.String(length=30), nullable=True))
        if "patient_responded_at" not in cols:
            batch_op.add_column(sa.Column("patient_responded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "appointments" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("appointments")}
    with op.batch_alter_table("appointments") as batch_op:
        if "patient_responded_at" in cols:
            batch_op.drop_column("patient_responded_at")
        if "patient_response" in cols:
            batch_op.drop_column("patient_response")
        if "reminder_action_used_at" in cols:
            batch_op.drop_column("reminder_action_used_at")
        if "reminder_action_expires_at" in cols:
            batch_op.drop_column("reminder_action_expires_at")
        if "reminder_action_token_hash" in cols:
            batch_op.drop_column("reminder_action_token_hash")
