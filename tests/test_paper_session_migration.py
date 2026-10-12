"""Run 0005 against a disposable Postgres that starts from the pre-session schema.

The database is a new postgres:16 container on 127.0.0.1:55432. It is not the
Compose Postgres, and the test refuses host port 5432 and database name core.
Downgrade is executed only to show that it does not restore the old positions
primary key. Restoring that shape requires the pre-migration backup.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.types.json import Json
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine.url import make_url

from contracts.enums import Horizon
from core_db.paper_sessions import LEGACY_SESSION_ID
from core_decision import proposal_id_for

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "paper-sessions-migration-pg-test"
PORT = 55432
PASSWORD = "paper-migration-test"
FILL_AT = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
ADMIN_DSN = f"host=127.0.0.1 port={PORT} user=postgres password={PASSWORD} dbname=postgres"

_PRE_SCHEMA = """
CREATE TABLE trade_proposals (
    proposal_id varchar(128) PRIMARY KEY,
    instrument_id varchar(64) NOT NULL,
    symbol varchar(32) NOT NULL,
    horizon varchar(16) NOT NULL,
    as_of timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE risk_decisions (
    risk_decision_id varchar(128) PRIMARY KEY,
    proposal_id varchar(128) NOT NULL UNIQUE,
    instrument_id varchar(64) NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE orders (
    order_id varchar(128) PRIMARY KEY,
    proposal_id varchar(128) NOT NULL UNIQUE,
    instrument_id varchar(64) NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE executions (
    execution_id varchar(128) PRIMARY KEY,
    order_id varchar(128) NOT NULL UNIQUE,
    instrument_id varchar(64) NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE positions (
    instrument_id varchar(64) PRIMARY KEY,
    symbol varchar(32) NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE portfolio_snapshots (
    snapshot_id varchar(128) PRIMARY KEY,
    timestamp timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE runtime_flags (
    flag_id varchar(32) PRIMARY KEY,
    paper_running boolean NOT NULL,
    peak_equity numeric(18, 4)
);
CREATE TABLE audit_logs (
    audit_id varchar(64) PRIMARY KEY,
    action varchar(64) NOT NULL,
    entity_type varchar(64) NOT NULL,
    entity_id varchar(128) NOT NULL,
    recorded_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE alembic_version (
    version_num varchar(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('0004_backtest_tables');
"""


def _guard(url: str) -> None:
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("refusing a non-local migration database")
    if parsed.port in {None, 5432}:
        raise RuntimeError("refusing the default Postgres port")
    if parsed.database in {None, "core", "postgres"}:
        raise RuntimeError("refusing a non-disposable database name")


def _url(database: str) -> str:
    url = f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:{PORT}/{database}"
    _guard(url)
    return url


@pytest.fixture(scope="module")
def migration_postgres():
    if PORT == 5432:
        raise RuntimeError("refusing the default Postgres port")
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
        version = _wait_ready()
        yield version
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True, text=True)


def _wait_ready() -> str:
    deadline = time.time() + 60
    last_error = "not started"
    while time.time() < deadline:
        try:
            with psycopg.connect(ADMIN_DSN, connect_timeout=2) as connection:
                version = connection.execute("SELECT version()").fetchone()[0]
            if "PostgreSQL 16" not in version:
                raise RuntimeError(version)
            return version
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"disposable Postgres did not become ready: {last_error}")


def _create_database(name: str) -> None:
    if name in {"core", "postgres"}:
        raise RuntimeError(name)
    with psycopg.connect(ADMIN_DSN, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')


def _connect(database: str):
    _guard(_url(database))
    return psycopg.connect(f"host=127.0.0.1 port={PORT} user=postgres password={PASSWORD} dbname={database}")


def _install_pre_schema(database: str, *, peak: Decimal | None, executed_at: str, include_order: bool) -> None:
    _create_database(database)
    stamp = FILL_AT.isoformat().replace("+00:00", "Z")
    order = {
        "order_id": "kotak-order",
        "proposal_id": "kotak-proposal",
        "symbol": "KOTAKBANK",
        "side": "BUY",
        "quantity": 1,
    }
    fill = {
        "execution_id": "kotak-fill",
        "order_id": "kotak-order",
        "symbol": "KOTAKBANK",
        "quantity": 1,
        "price": "418.3500",
        "fees": "0",
        "slippage": "0",
        "executed_at": executed_at,
    }
    position = {
        "symbol": "KOTAKBANK",
        "quantity": 1,
        "average_price": "418.3500",
        "market_price": "418.3500",
        "market_value": "418.3500",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
    }
    snapshot = {
        "timestamp": stamp,
        "cash": "99581.6500",
        "equity": "100000.0000",
        "market_value": "418.3500",
        "gross_exposure": "418.3500",
        "net_exposure": "418.3500",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "total_pnl": "0",
        "drawdown": "0",
    }
    with _connect(database) as connection:
        for statement in _PRE_SCHEMA.split(";"):
            if statement.strip():
                connection.execute(statement)
        primary_key = connection.execute(
            """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
            WHERE i.indrelid = 'positions'::regclass AND i.indisprimary
            """
        ).fetchone()[0]
        assert primary_key == "instrument_id"
        connection.execute(
            "INSERT INTO trade_proposals (proposal_id, instrument_id, symbol, horizon, as_of, payload) VALUES (%s, %s, %s, %s, %s, %s)",
            ("kotak-proposal", "NSE:KOTAKBANK", "KOTAKBANK", "SWING", FILL_AT, Json({"proposal_id": "kotak-proposal"})),
        )
        connection.execute(
            "INSERT INTO risk_decisions (risk_decision_id, proposal_id, instrument_id, payload) VALUES (%s, %s, %s, %s)",
            ("kotak-risk", "kotak-proposal", "NSE:KOTAKBANK", Json({"proposal_id": "kotak-proposal"})),
        )
        if include_order:
            connection.execute(
                "INSERT INTO orders (order_id, proposal_id, instrument_id, payload) VALUES (%s, %s, %s, %s)",
                ("kotak-order", "kotak-proposal", "NSE:KOTAKBANK", Json(order)),
            )
        connection.execute(
            "INSERT INTO executions (execution_id, order_id, instrument_id, payload) VALUES (%s, %s, %s, %s)",
            ("kotak-fill", "kotak-order", "NSE:KOTAKBANK", Json(fill)),
        )
        connection.execute(
            "INSERT INTO positions (instrument_id, symbol, payload) VALUES (%s, %s, %s)",
            ("NSE:KOTAKBANK", "KOTAKBANK", Json(position)),
        )
        connection.execute(
            "INSERT INTO portfolio_snapshots (snapshot_id, timestamp, payload) VALUES (%s, %s, %s)",
            ("kotak-fill", FILL_AT, Json(snapshot)),
        )
        connection.execute(
            "INSERT INTO runtime_flags (flag_id, paper_running, peak_equity) VALUES ('paper', true, %s)",
            (peak,),
        )
        connection.commit()


def _upgrade(database: str) -> None:
    url = _url(database)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        config = Config(str(ROOT / "services/core/db/alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "services/core/db/alembic"))
        config.set_main_option("prepend_sys_path", str(ROOT / "services/core/db/src"))
        command.upgrade(config, "0005_paper_sessions")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _downgrade(database: str) -> None:
    url = _url(database)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        config = Config(str(ROOT / "services/core/db/alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "services/core/db/alembic"))
        config.set_main_option("prepend_sys_path", str(ROOT / "services/core/db/src"))
        command.downgrade(config, "0004_backtest_tables")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _session_row(database: str) -> tuple:
    with _connect(database) as connection:
        return connection.execute(
            "SELECT status, starting_cash, peak_equity FROM paper_sessions WHERE session_id = %s",
            (LEGACY_SESSION_ID,),
        ).fetchone()


def _audit(database: str) -> dict:
    with _connect(database) as connection:
        row = connection.execute(
            "SELECT payload FROM audit_logs WHERE action = 'legacy_paper_session'"
        ).fetchone()
    assert row is not None
    return row[0]


def _counts(database: str) -> dict[str, int]:
    with _connect(database) as connection:
        return {
            name: connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for name in ("orders", "executions", "positions", "portfolio_snapshots", "trade_proposals", "risk_decisions")
        }


def test_disposable_postgres_is_version_16(migration_postgres: str) -> None:
    assert migration_postgres.startswith("PostgreSQL 16")
    print(f"POSTGRES_VERSION {migration_postgres}")


def test_valid_legacy_book_migrates_once_and_can_repeat(migration_postgres: str) -> None:
    stamp = FILL_AT.isoformat().replace("+00:00", "Z")
    _install_pre_schema("mig_ok", peak=Decimal("100000"), executed_at=stamp, include_order=True)
    before = _counts("mig_ok")
    _upgrade("mig_ok")
    after = _counts("mig_ok")
    assert after == before
    status, starting_cash, peak = _session_row("mig_ok")
    assert status == "active"
    assert starting_cash == Decimal("100000.0000")
    assert peak == Decimal("100000.0000")
    audit = _audit("mig_ok")
    assert audit["consistent"] is True
    assert audit["peak_complete"] is True
    assert audit["peak_source"] == "runtime_flag"
    with _connect("mig_ok") as connection:
        sessions = connection.execute("SELECT count(*) FROM paper_sessions").fetchone()[0]
        labeled = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM orders WHERE session_id = %s),
                (SELECT count(*) FROM executions WHERE session_id = %s),
                (SELECT count(*) FROM positions WHERE session_id = %s),
                (SELECT count(*) FROM portfolio_snapshots WHERE session_id = %s),
                (SELECT count(*) FROM trade_proposals WHERE session_id = %s),
                (SELECT count(*) FROM risk_decisions WHERE session_id = %s),
                (SELECT count(DISTINCT session_id) FROM orders)
            """,
            (LEGACY_SESSION_ID,) * 6,
        ).fetchone()
        quantity = connection.execute("SELECT payload->>'quantity' FROM positions").fetchone()[0]
        flag = connection.execute("SELECT paper_running, peak_equity FROM runtime_flags WHERE flag_id = 'paper'").fetchone()
        primary_key = connection.execute(
            """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
            WHERE i.indrelid = 'positions'::regclass AND i.indisprimary
            """
        ).fetchone()[0]
    assert sessions == 1
    assert labeled == (1, 1, 1, 1, 1, 1, 1)
    assert quantity == "1"
    assert flag == (True, Decimal("100000.0000"))
    assert primary_key == "position_id"

    with _connect("mig_ok") as connection:
        connection.execute("UPDATE alembic_version SET version_num = '0004_backtest_tables'")
        connection.commit()
    _upgrade("mig_ok")
    assert _counts("mig_ok") == before
    with _connect("mig_ok") as connection:
        assert connection.execute("SELECT count(*) FROM paper_sessions").fetchone()[0] == 1
    assert _session_row("mig_ok") == (status, starting_cash, peak)

    first = proposal_id_for("KOTAKBANK", Horizon.SWING, FILL_AT, session_id="session-a")
    second = proposal_id_for("KOTAKBANK", Horizon.SWING, FILL_AT, session_id="session-b")
    assert first != second
    position = Json({"symbol": "KOTAKBANK", "quantity": 1})
    with _connect("mig_ok") as connection:
        connection.execute(
            "INSERT INTO positions (position_id, session_id, instrument_id, symbol, payload) VALUES (%s, %s, %s, %s, %s)",
            ("session-a:NSE:KOTAKBANK", "session-a", "NSE:KOTAKBANK", "KOTAKBANK", position),
        )
        connection.execute(
            "INSERT INTO positions (position_id, session_id, instrument_id, symbol, payload) VALUES (%s, %s, %s, %s, %s)",
            ("session-b:NSE:KOTAKBANK", "session-b", "NSE:KOTAKBANK", "KOTAKBANK", position),
        )
        connection.execute(
            "INSERT INTO orders (order_id, session_id, proposal_id, instrument_id, payload) VALUES (%s, %s, %s, %s, %s)",
            ("order-a", "session-a", first, "NSE:KOTAKBANK", Json({"proposal_id": first})),
        )
        connection.execute(
            "INSERT INTO orders (order_id, session_id, proposal_id, instrument_id, payload) VALUES (%s, %s, %s, %s, %s)",
            ("order-b", "session-b", second, "NSE:KOTAKBANK", Json({"proposal_id": second})),
        )
        connection.commit()
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO positions (position_id, session_id, instrument_id, symbol, payload) VALUES (%s, %s, %s, %s, %s)",
                ("session-a:duplicate", "session-a", "NSE:KOTAKBANK", "KOTAKBANK", position),
            )
        connection.rollback()
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                "INSERT INTO orders (order_id, session_id, proposal_id, instrument_id, payload) VALUES (%s, %s, %s, %s, %s)",
                ("order-a2", "session-a", first, "NSE:KOTAKBANK", Json({"proposal_id": first})),
            )
        connection.rollback()
    with _connect("mig_ok") as connection:
        assert connection.execute("SELECT count(*) FROM positions WHERE instrument_id = 'NSE:KOTAKBANK'").fetchone()[0] == 3


def test_incomplete_peak_is_explicit(migration_postgres: str) -> None:
    stamp = FILL_AT.isoformat().replace("+00:00", "Z")
    _install_pre_schema("mig_incomplete", peak=None, executed_at=stamp, include_order=True)
    _upgrade("mig_incomplete")
    status, starting_cash, peak = _session_row("mig_incomplete")
    assert status == "active"
    assert starting_cash == Decimal("100000.0000")
    assert peak == Decimal("100000.0000")
    audit = _audit("mig_incomplete")
    assert audit["peak_complete"] is False
    assert audit["peak_source"] == "snapshot_equity"
    assert any("historical peak is incomplete" in item for item in audit["diagnostics"])


def test_inconsistent_snapshot_and_orphan_fill_stay_inactive(migration_postgres: str) -> None:
    late = (FILL_AT.replace(minute=5)).isoformat().replace("+00:00", "Z")
    _install_pre_schema("mig_late", peak=Decimal("100000"), executed_at=late, include_order=True)
    _upgrade("mig_late")
    status, starting_cash, peak = _session_row("mig_late")
    assert status == "closed"
    assert starting_cash is None
    assert peak is None
    assert any("later than the latest snapshot" in item for item in _audit("mig_late")["diagnostics"])
    assert _counts("mig_late")["executions"] == 1
    with _connect("mig_late") as connection:
        flag = connection.execute("SELECT peak_equity FROM runtime_flags WHERE flag_id = 'paper'").fetchone()[0]
        active = connection.execute("SELECT count(*) FROM paper_sessions WHERE status = 'active'").fetchone()[0]
    assert flag == Decimal("100000.0000")
    assert active == 0

    stamp = FILL_AT.isoformat().replace("+00:00", "Z")
    _install_pre_schema("mig_orphan", peak=Decimal("100000"), executed_at=stamp, include_order=False)
    _upgrade("mig_orphan")
    status, starting_cash, peak = _session_row("mig_orphan")
    assert status == "closed"
    assert starting_cash is None
    assert peak is None
    assert any("no matching order" in item for item in _audit("mig_orphan")["diagnostics"])
    with _connect("mig_orphan") as connection:
        assert connection.execute("SELECT count(*) FROM executions").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM paper_sessions WHERE status = 'active'").fetchone()[0] == 0


def test_downgrade_does_not_restore_the_pre_migration_primary_key(migration_postgres: str) -> None:
    stamp = FILL_AT.isoformat().replace("+00:00", "Z")
    _install_pre_schema("mig_down", peak=Decimal("100000"), executed_at=stamp, include_order=True)
    _upgrade("mig_down")
    _downgrade("mig_down")
    engine = create_engine(_url("mig_down"))
    try:
        tables = set(inspect(engine).get_table_names())
        assert "paper_sessions" not in tables
        columns = {column["name"] for column in inspect(engine).get_columns("positions")}
        assert "position_id" in columns
        assert inspect(engine).get_pk_constraint("positions")["constrained_columns"] == ["position_id"]
        assert "session_id" not in {column["name"] for column in inspect(engine).get_columns("orders")}
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM orders")).scalar() == 1
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "0004_backtest_tables"
    finally:
        engine.dispose()
