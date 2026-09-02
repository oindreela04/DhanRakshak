"""add fields required by the revenue leakage radar"""
from alembic import op
import sqlalchemy as sa

revision = "20260903_radar_fields"
down_revision = "20260903_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("segment", sa.String(length=32), nullable=True))
    op.create_index("ix_customers_segment", "customers", ["segment"])
    op.add_column("transactions", sa.Column("payment_method", sa.String(length=32), nullable=True))
    op.add_column("transactions", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_transactions_payment_method", "transactions", ["payment_method"])
    op.create_index("ix_transactions_occurred_at", "transactions", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_transactions_occurred_at", table_name="transactions")
    op.drop_index("ix_transactions_payment_method", table_name="transactions")
    op.drop_column("transactions", "occurred_at")
    op.drop_column("transactions", "payment_method")
    op.drop_index("ix_customers_segment", table_name="customers")
    op.drop_column("customers", "segment")
