"""Backtest runs.

Revision ID: 0003_backtests
Revises: 0002_paper
Create Date: 2026-10-07
"""

from alembic import op

from core_db.models import Base

revision = "0003_backtests"
down_revision = "0002_paper"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    op.drop_table("backtest_runs")
