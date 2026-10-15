"""End-of-day paper book, one row per session and IST trading day.

Revision ID: 0011_daily_equity
Revises: 0010_system_event_id_length
Create Date: 2026-10-15

Implements docs/dev3-snapshot-writer-design.md: written after the cash close,
realized P&L from the fill ledger, no row for a day that did not trade.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision = "0011_daily_equity"
down_revision = "0010_system_event_id_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "daily_equity" not in set(inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "daily_equity",
            sa.Column("daily_id", sa.String(100), primary_key=True),
            sa.Column("session_id", sa.String(64), nullable=False),
            sa.Column("trading_day", sa.String(10), nullable=False),
            sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
            sa.UniqueConstraint("session_id", "trading_day", name="uq_daily_equity_session_day"),
        )


def downgrade() -> None:
    if "daily_equity" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("daily_equity")
