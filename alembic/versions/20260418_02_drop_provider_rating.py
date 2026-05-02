"""drop provider rating column

Revision ID: 20260418_02
Revises: 20260415_01
Create Date: 2026-04-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260418_02"
down_revision = "20260415_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("providers") as batch_op:
        batch_op.drop_column("rating")


def downgrade() -> None:
    with op.batch_alter_table("providers") as batch_op:
        batch_op.add_column(sa.Column("rating", sa.Float(), nullable=False, server_default="4.0"))

