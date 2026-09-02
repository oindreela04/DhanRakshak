"""add promise extraction and reminder fields"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_promise_fields"
down_revision = "20260903_radar_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promises_to_pay", sa.Column("language", sa.String(length=32), nullable=True))
    op.add_column("promises_to_pay", sa.Column("confidence", sa.Numeric(precision=8, scale=4), nullable=True))
    op.add_column("promises_to_pay", sa.Column("reminder_status", sa.String(length=32), nullable=False, server_default="scheduled"))


def downgrade() -> None:
    op.drop_column("promises_to_pay", "reminder_status")
    op.drop_column("promises_to_pay", "confidence")
    op.drop_column("promises_to_pay", "language")