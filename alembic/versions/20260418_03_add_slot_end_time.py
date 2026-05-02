"""add end_time to slots

Revision ID: 20260418_03
Revises: 20260418_02
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20260418_03"
down_revision = "20260418_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    slot_cols = {col["name"] for col in inspector.get_columns("slots")}
    if "end_time" not in slot_cols:
        with op.batch_alter_table("slots") as batch_op:
            batch_op.add_column(sa.Column("end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    slot_cols = {col["name"] for col in inspector.get_columns("slots")}
    if "end_time" in slot_cols:
        with op.batch_alter_table("slots") as batch_op:
            batch_op.drop_column("end_time")

