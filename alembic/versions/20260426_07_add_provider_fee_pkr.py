"""add provider fee in PKR

Revision ID: 20260426_07
Revises: 20260422_06
Create Date: 2026-04-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_07"
down_revision = "20260422_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "providers" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("providers")}
    if "fee_pkr" not in cols:
        with op.batch_alter_table("providers") as batch_op:
            batch_op.add_column(sa.Column("fee_pkr", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "providers" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("providers")}
    if "fee_pkr" in cols:
        with op.batch_alter_table("providers") as batch_op:
            batch_op.drop_column("fee_pkr")
