"""Upgrade and downgrade 0006 on a disposable SQLite file. Production is not contacted."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC = ROOT / "services" / "core" / "db"


def test_execution_migration_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "paper-execution.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database}"
    env.pop("PYTHONPATH", None)
    _alembic(env, "upgrade", "head")
    engine = create_engine(env["DATABASE_URL"])
    names = set(inspect(engine).get_table_names())
    assert {"cash_reservations", "charge_ledger", "dp_charges", "order_bar_checks"} <= names
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO orders (order_id, session_id, proposal_id, instrument_id, payload) "
                "VALUES ('legacy', 'sess', 'prop', 'NSE:KOTAKBANK', '{\"status\":\"OPEN\",\"fill_at\":\"next_open\"}')"
            )
        )
    _alembic(env, "downgrade", "-1")
    gone = set(inspect(engine).get_table_names())
    assert "cash_reservations" not in gone
    assert "charge_ledger" not in gone
    _alembic(env, "upgrade", "head")
    with engine.connect() as connection:
        payload = connection.execute(text("SELECT payload FROM orders WHERE order_id = 'legacy'")).scalar_one()
    assert "next_open" in payload
    assert "cnc-limit-v1" not in payload


def _alembic(env: dict[str, str], *args: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ALEMBIC,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
