"""Cash reservations, charge ledger, DP charges, and bar-check keys.

Revision ID: 0006_paper_execution
Revises: 0005_paper_sessions
Create Date: 2026-10-12

Existing order and position payloads are not rewritten. A null policy is not
compliance with the CNC limit rules. Downgrade drops the new tables. Ledger,
reservation, DP, and bar-check rows cannot be reconstructed.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from core_db.models import JSON_VALUE

revision = "0006_paper_execution"
down_revision = "0005_paper_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "cash_reservations" not in tables:
        op.create_table(
            "cash_reservations",
            sa.Column("reservation_id", sa.String(128), primary_key=True),
            sa.Column("session_id", sa.String(64), nullable=False),
            sa.Column("order_id", sa.String(128), nullable=False),
            sa.Column("amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("applied_debit", sa.Numeric(18, 4), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("order_id", name="uq_cash_reservations_order"),
        )
    if "charge_ledger" not in tables:
        op.create_table(
            "charge_ledger",
            sa.Column("ledger_id", sa.String(160), primary_key=True),
            sa.Column("session_id", sa.String(64), nullable=False),
            sa.Column("order_id", sa.String(128), nullable=False),
            sa.Column("execution_id", sa.String(128), nullable=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("payload", JSON_VALUE, nullable=False),
            sa.UniqueConstraint("session_id", "order_id", "kind", name="uq_charge_ledger_kind"),
        )
    if "dp_charges" not in tables:
        op.create_table(
            "dp_charges",
            sa.Column("dp_id", sa.String(160), primary_key=True),
            sa.Column("session_id", sa.String(64), nullable=False),
            sa.Column("trading_day", sa.String(10), nullable=False),
            sa.Column("exchange", sa.String(8), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("execution_id", sa.String(128), nullable=False),
            sa.UniqueConstraint("session_id", "trading_day", "exchange", "symbol", name="uq_dp_scrip_day"),
        )
    if "order_bar_checks" not in tables:
        op.create_table(
            "order_bar_checks",
            sa.Column("check_id", sa.String(160), primary_key=True),
            sa.Column("order_id", sa.String(128), nullable=False),
            sa.Column("bar_key", sa.String(64), nullable=False),
            sa.UniqueConstraint("order_id", "bar_key", name="uq_order_bar_check"),
        )


def downgrade() -> None:
    """Drop the execution-policy tables.

    Order payloads, fills, positions, and snapshots stay. Reservation amounts,
    charge-ledger rows, DP accumulator rows, and evaluated bar keys are not
    recoverable after this downgrade.
    """
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for name in ("order_bar_checks", "dp_charges", "charge_ledger", "cash_reservations"):
        if name in tables:
            op.drop_table(name)
