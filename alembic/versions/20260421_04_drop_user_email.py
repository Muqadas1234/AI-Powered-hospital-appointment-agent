"""drop users.email column and constraint

Revision ID: 20260421_04
Revises: 20260418_03
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260421_04"
down_revision = "20260418_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    user_cols = {col["name"] for col in inspector.get_columns("users")}
    if "email" in user_cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("email")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    user_cols = {col["name"] for col in inspector.get_columns("users")}
    if "email" not in user_cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("email", sa.String(length=120), nullable=True))
