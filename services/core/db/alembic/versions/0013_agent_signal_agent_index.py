"""Index agent_signals by (agent_name, recorded_at) for "newest signal per agent".

Revision ID: 0013_agent_signal_agent_index
Revises: 0012_user_settings_strategies
Create Date: 2026-10-19
"""

from alembic import op

revision = "0013_agent_signal_agent_index"
down_revision = "0012_user_settings_strategies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_signals_agent_recorded "
            "ON agent_signals ((payload->>'agent_name'), recorded_at DESC)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_agent_signals_agent_recorded")
