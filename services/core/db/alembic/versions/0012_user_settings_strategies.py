"""User-editable risk settings and user-built strategies.

Revision ID: 0012_user_settings_strategies
Revises: 0011_daily_equity
Create Date: 2026-10-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0012_user_settings_strategies"
down_revision = "0011_daily_equity"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "user_settings" not in tables:
        op.create_table(
            "user_settings",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("payload", _JSON, nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by", sa.String(64), nullable=False),
        )
    if "user_strategies" not in tables:
        op.create_table(
            "user_strategies",
            sa.Column("strategy_id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("payload", _JSON, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    for name in ("user_strategies", "user_settings"):
        if name in tables:
            op.drop_table(name)
