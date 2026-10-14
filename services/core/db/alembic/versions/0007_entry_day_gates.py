"""Lock row for the IST daily entry cap.

Revision ID: 0007_entry_day_gates
Revises: 0006_paper_execution
Create Date: 2026-10-13

The row is a mutex. The count of CNC entry orders is derived from order
payloads, so this table does not store the cap and does not rewrite orders.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007_entry_day_gates"
down_revision = "0006_paper_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "entry_day_gates" not in set(inspect(bind).get_table_names()):
        op.create_table(
            "entry_day_gates",
            sa.Column("trading_day", sa.String(10), primary_key=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "entry_day_gates" in set(inspect(bind).get_table_names()):
        op.drop_table("entry_day_gates")
