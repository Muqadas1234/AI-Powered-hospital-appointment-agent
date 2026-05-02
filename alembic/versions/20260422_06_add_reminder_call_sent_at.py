"""add reminder call sent timestamp

Revision ID: 20260422_06
Revises: 20260421_05
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260422_06"
down_revision = "20260421_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "appointments" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("appointments")}
    if "reminder_call_sent_at" not in cols:
        with op.batch_alter_table("appointments") as batch_op:
            batch_op.add_column(sa.Column("reminder_call_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "appointments" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("appointments")}
    if "reminder_call_sent_at" in cols:
        with op.batch_alter_table("appointments") as batch_op:
            batch_op.drop_column("reminder_call_sent_at")
