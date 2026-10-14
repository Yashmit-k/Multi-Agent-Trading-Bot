"""Persist the daily market-data access token.

Revision ID: 0009_broker_sessions
Revises: 0008_read_indexes
Create Date: 2026-10-15

Kite access tokens are valid until 06:00 IST the next day. Keeping the latest
one lets Core reload it after a restart instead of dropping market data until
someone logs in again.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0009_broker_sessions"
down_revision = "0008_read_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "broker_sessions" not in set(inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "broker_sessions",
            sa.Column("broker", sa.String(32), primary_key=True),
            sa.Column("access_token", sa.String(256), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    if "broker_sessions" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("broker_sessions")
