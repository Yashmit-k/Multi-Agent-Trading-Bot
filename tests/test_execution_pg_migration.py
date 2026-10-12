"""0006 on disposable PostgreSQL 16. This is not the Compose database.

The test refuses port 5432 and the database name core. A fresh Alembic chain
creates every current table inside revision 0001, so after stopping at 0005 the
four execution tables are removed while the revision stamp stays 0005. That is
the production shape this migration has to upgrade.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.types.json import Json
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "paper-exec-policy-pg-test"
PORT = 55433
PASSWORD = "paper-exec-policy-test"
DATABASE = "paper_exec_0006"
ADMIN_DSN = f"host=127.0.0.1 port={PORT} user=postgres password={PASSWORD} dbname=postgres"
WHEN = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
NEW_TABLES = ("cash_reservations", "charge_ledger", "dp_charges", "order_bar_checks")


def _guard(url: str) -> None:
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("refusing a non-local migration database")
    if parsed.port in {None, 5432}:
        raise RuntimeError("refusing the default Postgres port")
    if parsed.database in {None, "core", "postgres"}:
        raise RuntimeError("refusing a non-disposable database name")


def _url() -> str:
    url = f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:{PORT}/{DATABASE}"
    _guard(url)
    return url


@pytest.fixture(scope="module")
def postgres16():
    if PORT == 5432 or DATABASE in {"core", "postgres"}:
        raise RuntimeError("refusing a production-shaped database")
    subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True, text=True)
    started = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-e",
            f"POSTGRES_PASSWORD={PASSWORD}",
            "-p",
            f"127.0.0.1:{PORT}:5432",
            "postgres:16",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        pytest.skip(f"disposable Postgres did not start: {started.stderr.strip()}")
    try:
        deadline = time.time() + 60
        version = ""
        while time.time() < deadline:
            try:
                with psycopg.connect(ADMIN_DSN, connect_timeout=2) as connection:
                    version = connection.execute("SELECT version()").fetchone()[0]
                break
            except Exception:
                time.sleep(0.5)
        if "PostgreSQL 16" not in version:
            pytest.skip(version or "postgres did not become ready")
        with psycopg.connect(ADMIN_DSN, autocommit=True) as connection:
            connection.execute(f'CREATE DATABASE "{DATABASE}"')
        yield version
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True, text=True)


def test_postgres16_upgrades_and_downgrades_0006(postgres16: str) -> None:
    assert "PostgreSQL 16" in postgres16
    _alembic("upgrade", "0005_paper_sessions")
    with _connect() as connection:
        assert _revision(connection) == "0005_paper_sessions"
        connection.execute(
            "DROP TABLE IF EXISTS order_bar_checks, dp_charges, charge_ledger, cash_reservations"
        )
        connection.commit()
        assert _tables(connection).isdisjoint(NEW_TABLES)
        _seed(connection)
        before = _preserved(connection)
    _alembic("upgrade", "0006_paper_execution")
    with _connect() as connection:
        assert _revision(connection) == "0006_paper_execution"
        assert set(NEW_TABLES) <= _tables(connection)
        assert _preserved(connection) == before
        connection.execute(
            """
            INSERT INTO cash_reservations (
                reservation_id, session_id, order_id, amount, status, applied_debit, created_at, updated_at
            ) VALUES ('reserve-1', 'new-session', 'new-order', 1000, 'HELD', NULL, %s, %s)
            """,
            (WHEN, WHEN),
        )
        connection.execute(
            """
            INSERT INTO charge_ledger (
                ledger_id, session_id, order_id, execution_id, kind, amount, payload
            ) VALUES ('ledger-1', 'new-session', 'new-order', 'new-fill', 'booked', 12.34, %s)
            """,
            (Json({"charge_version": "zerodha-equity-ri-2026-10-12"}),),
        )
        connection.execute(
            """
            INSERT INTO dp_charges (
                dp_id, session_id, trading_day, exchange, symbol, amount, execution_id
            ) VALUES ('dp-1', 'new-session', '2026-10-13', 'NSE', 'RELIANCE', 15.34, 'new-fill')
            """
        )
        connection.commit()
    _alembic("downgrade", "0005_paper_sessions")
    with _connect() as connection:
        assert _revision(connection) == "0005_paper_sessions"
        assert _tables(connection).isdisjoint(NEW_TABLES)
        assert _preserved(connection) == before
    _alembic("upgrade", "0006_paper_execution")
    _alembic("stamp", "0005_paper_sessions")
    _alembic("upgrade", "0006_paper_execution")
    with _connect() as connection:
        assert _revision(connection) == "0006_paper_execution"
        assert set(NEW_TABLES) <= _tables(connection)
        assert _preserved(connection) == before
        assert connection.execute("SELECT count(*) FROM cash_reservations").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM charge_ledger").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM dp_charges").fetchone()[0] == 0


def _seed(connection) -> None:
    connection.execute(
        """
        INSERT INTO paper_sessions (session_id, status, created_at, closed_at, starting_cash, peak_equity)
        VALUES ('legacy-session', 'closed', %s, %s, 100000, 100000),
               ('new-session', 'active', %s, NULL, 1000000, NULL)
        """,
        (WHEN, WHEN, WHEN),
    )
    legacy_order = {
        "order_id": "kotak-order",
        "symbol": "KOTAKBANK",
        "side": "BUY",
        "status": "OPEN",
        "quantity": 226,
        "order_type": "MARKET",
        "metadata": {"fill_at": "next_open", "decision_end": WHEN.isoformat()},
    }
    policy_order = {
        "order_id": "new-order",
        "symbol": "RELIANCE",
        "side": "BUY",
        "status": "OPEN",
        "quantity": 10,
        "order_type": "LIMIT",
        "limit_price": "443.10",
        "metadata": {
            "policy_version": "cnc-limit-v1",
            "product_type": "CNC",
            "reference_price": "442.00",
            "reference_rule": "latest_completed_daily_close_v1",
        },
    }
    connection.execute(
        """
        INSERT INTO orders (order_id, session_id, proposal_id, instrument_id, payload)
        VALUES ('kotak-order', 'legacy-session', 'kotak-proposal', 'NSE:KOTAKBANK', %s),
               ('new-order', 'new-session', 'new-proposal', 'NSE:RELIANCE', %s)
        """,
        (Json(legacy_order), Json(policy_order)),
    )
    connection.execute(
        """
        INSERT INTO executions (execution_id, session_id, order_id, instrument_id, payload)
        VALUES ('kotak-fill', 'legacy-session', 'kotak-order', 'NSE:KOTAKBANK', %s)
        """,
        (Json({"execution_id": "kotak-fill", "price": "418.3500", "quantity": 1, "fees": "0"}),),
    )
    connection.execute(
        """
        INSERT INTO positions (position_id, session_id, instrument_id, symbol, payload)
        VALUES ('legacy-session:NSE:KOTAKBANK', 'legacy-session', 'NSE:KOTAKBANK', 'KOTAKBANK', %s)
        """,
        (Json({"symbol": "KOTAKBANK", "quantity": 1, "average_price": "418.3500"}),),
    )
    connection.execute(
        """
        INSERT INTO portfolio_snapshots (snapshot_id, session_id, timestamp, payload)
        VALUES ('kotak-snap', 'legacy-session', %s, %s)
        """,
        (WHEN, Json({"cash": "99581.6500", "equity": "100000.0000"})),
    )
    connection.commit()


def _preserved(connection) -> dict:
    orders = connection.execute(
        "SELECT order_id, session_id, payload::text FROM orders ORDER BY order_id"
    ).fetchall()
    fills = connection.execute(
        "SELECT execution_id, session_id, payload::text FROM executions ORDER BY execution_id"
    ).fetchall()
    positions = connection.execute(
        "SELECT position_id, session_id, symbol, payload::text FROM positions ORDER BY position_id"
    ).fetchall()
    snapshots = connection.execute(
        "SELECT snapshot_id, session_id, payload::text FROM portfolio_snapshots ORDER BY snapshot_id"
    ).fetchall()
    sessions = connection.execute(
        "SELECT session_id, status, starting_cash FROM paper_sessions ORDER BY session_id"
    ).fetchall()
    return {
        "orders": [tuple(row) for row in orders],
        "fills": [tuple(row) for row in fills],
        "positions": [tuple(row) for row in positions],
        "snapshots": [tuple(row) for row in snapshots],
        "sessions": [(row[0], row[1], str(row[2])) for row in sessions],
    }


def _tables(connection) -> set[str]:
    rows = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    ).fetchall()
    return {row[0] for row in rows}


def _revision(connection) -> str:
    return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def _connect():
    _guard(_url())
    return psycopg.connect(f"host=127.0.0.1 port={PORT} user=postgres password={PASSWORD} dbname={DATABASE}")


def _alembic(*args: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _url()
    try:
        config = Config(str(ROOT / "services/core/db/alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "services/core/db/alembic"))
        config.set_main_option("prepend_sys_path", str(ROOT / "services/core/db/src"))
        if args[0] == "stamp":
            command.stamp(config, args[1])
        elif args[0] == "downgrade":
            command.downgrade(config, args[1])
        else:
            command.upgrade(config, args[1])
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
