"""Daily summaries of agent signals, kept after raw signals age out.

Revision ID: 0014_agent_signal_daily
Revises: 0013_agent_signal_agent_index
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0014_agent_signal_daily"
down_revision = "0013_agent_signal_agent_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "agent_signal_daily" not in set(inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "agent_signal_daily",
            sa.Column("day", sa.String(10), primary_key=True),
            sa.Column("agent", sa.String(32), primary_key=True),
            sa.Column("horizon", sa.String(16), primary_key=True),
            sa.Column("version", sa.String(16), primary_key=True),
            sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        )


def downgrade() -> None:
    if "agent_signal_daily" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("agent_signal_daily")
