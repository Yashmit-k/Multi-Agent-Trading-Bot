"""Normalized backtest tables beside the JSON payload.

Revision ID: 0004_backtest_tables
Revises: 0003_backtests
Create Date: 2026-10-07
"""

from alembic import op

from core_db.models import Base

revision = "0004_backtest_tables"
down_revision = "0003_backtests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    for name in (
        "backtest_metrics",
        "backtest_portfolio_snapshots",
        "backtest_positions",
        "backtest_fills",
        "backtest_orders",
        "backtest_costs",
    ):
        op.drop_table(name)
