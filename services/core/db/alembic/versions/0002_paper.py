"""Paper trading tables.

Revision ID: 0002_paper
Revises: 0001_initial
Create Date: 2026-09-30
"""

from alembic import op

from core_db.models import Base

revision = "0002_paper"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_PAPER_TABLES = (
    "portfolio_snapshots",
    "positions",
    "executions",
    "orders",
    "risk_decisions",
    "trade_proposals",
    "runtime_flags",
)


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    for table in _PAPER_TABLES:
        op.drop_table(table)
