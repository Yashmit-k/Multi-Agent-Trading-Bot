"""Initial core tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-29
"""

from alembic import op

from core_db.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
