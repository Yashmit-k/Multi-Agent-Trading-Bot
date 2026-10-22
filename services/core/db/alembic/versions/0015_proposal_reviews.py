"""Portfolio-manager reviews of proposals.

Revision ID: 0015_proposal_reviews
Revises: 0014_agent_signal_daily
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0015_proposal_reviews"
down_revision = "0014_agent_signal_daily"
branch_labels = None
depends_on = None

JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    if "proposal_reviews" in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "proposal_reviews",
        sa.Column("review_id", sa.String(100), primary_key=True),
        sa.Column("proposal_id", sa.String(128), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request", JSON_VALUE, nullable=False),
        sa.Column("steps", JSON_VALUE, nullable=False),
        sa.Column("verdict", JSON_VALUE, nullable=True),
    )
    op.create_index("ix_proposal_reviews_proposal_id", "proposal_reviews", ["proposal_id"])
    op.create_index("ix_proposal_reviews_created_at", "proposal_reviews", ["created_at"])


def downgrade() -> None:
    if "proposal_reviews" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("proposal_reviews")
