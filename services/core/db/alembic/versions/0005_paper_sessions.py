"""Paper sessions. Legacy rows stay in place and gain the deterministic legacy id.

Revision ID: 0005_paper_sessions
Revises: 0004_backtest_tables
Create Date: 2026-10-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from core_db.models import JSON_VALUE
from core_db.repository import CoreRepository

revision = "0005_paper_sessions"
down_revision = "0004_backtest_tables"
branch_labels = None
depends_on = None

_SESSION_TABLES = (
    "trade_proposals",
    "risk_decisions",
    "orders",
    "executions",
    "portfolio_snapshots",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "paper_sessions" not in tables:
        op.create_table(
            "paper_sessions",
            sa.Column("session_id", sa.String(64), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("starting_cash", sa.Numeric(18, 4), nullable=True),
            sa.Column("peak_equity", sa.Numeric(18, 4), nullable=True),
        )
    for name in _SESSION_TABLES:
        columns = {column["name"] for column in inspect(bind).get_columns(name)}
        if "session_id" not in columns:
            op.add_column(name, sa.Column("session_id", sa.String(64), nullable=True))
    position_columns = {column["name"] for column in inspect(bind).get_columns("positions")}
    if "position_id" not in position_columns:
        op.create_table(
            "positions_v2",
            sa.Column("position_id", sa.String(160), primary_key=True),
            sa.Column("session_id", sa.String(64), nullable=True),
            sa.Column("instrument_id", sa.String(64), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("payload", JSON_VALUE, nullable=False),
            sa.UniqueConstraint("session_id", "instrument_id", name="uq_positions_session_instrument"),
        )
        op.execute(
            sa.text(
                "INSERT INTO positions_v2 (position_id, session_id, instrument_id, symbol, payload) "
                "SELECT 'unassigned:' || instrument_id, NULL, instrument_id, symbol, payload FROM positions"
            )
        )
        op.drop_table("positions")
        op.rename_table("positions_v2", "positions")
    elif "session_id" not in position_columns:
        op.add_column("positions", sa.Column("session_id", sa.String(64), nullable=True))
    CoreRepository(sessionmaker(bind=bind)).assign_legacy_paper_session()


def downgrade() -> None:
    """Remove session tables and columns.

    This does not put ``instrument_id`` back as the primary key of ``positions``.
    Downgrade is not a substitute for restoring the pre-migration backup.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if "paper_sessions" in inspector.get_table_names():
        op.drop_table("paper_sessions")
    for name in _SESSION_TABLES:
        columns = {column["name"] for column in inspect(bind).get_columns(name)}
        if "session_id" in columns:
            op.drop_column(name, "session_id")
