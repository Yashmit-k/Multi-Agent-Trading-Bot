"""Widen system_events.event_id for quant signal envelopes.

Revision ID: 0010_system_event_id_length
Revises: 0009_broker_sessions
Create Date: 2026-10-15

"agent.signal:" plus a 64-character quant signal id is 77 characters, longer
than the original VARCHAR(64), so every quant message failed to record.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_system_event_id_length"
down_revision = "0009_broker_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("system_events") as batch:
        batch.alter_column("event_id", type_=sa.String(200), existing_type=sa.String(64), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("system_events") as batch:
        batch.alter_column("event_id", type_=sa.String(64), existing_type=sa.String(200), existing_nullable=False)
