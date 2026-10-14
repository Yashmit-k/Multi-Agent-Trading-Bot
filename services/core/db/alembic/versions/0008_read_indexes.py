"""Indexes for the dashboard and worker read paths.

Revision ID: 0008_read_indexes
Revises: 0007_entry_day_gates
Create Date: 2026-10-15

latest_candle and candles_until filter candles by symbol and timeframe and
order by end. Without this index each lookup scans every stored bar
(2.5 million 5-minute rows). The signal and trace lists order by
recorded_at. Indexes only; no data changes.
"""

from alembic import op
from sqlalchemy import inspect

revision = "0008_read_indexes"
down_revision = "0007_entry_day_gates"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_candles_symbol_timeframe_end", "candles", ["symbol", "timeframe", "end"]),
    ("ix_agent_signals_recorded_at", "agent_signals", ["recorded_at"]),
    ("ix_agent_signals_symbol", "agent_signals", ["symbol"]),
    ("ix_system_events_recorded_at", "system_events", ["recorded_at"]),
)


def _existing(table: str) -> set[str]:
    return {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    for name, table, columns in INDEXES:
        if name not in _existing(table):
            op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in INDEXES:
        if name in _existing(table):
            op.drop_index(name, table_name=table)
