"""Six-entry lock on disposable PostgreSQL 16. Not the Compose database.

Two connections start from five qualifying CNC entries. Exactly one more may commit.
If Docker or PostgreSQL is unavailable the test fails as BLOCKED. It does not skip.
"""

from __future__ import annotations

import subprocess
import threading
import time
from decimal import Decimal
from urllib.parse import urlparse

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema
from core_paper.execute import queue_entry
from test_daily_entry_cap import _enter, _put_daily, _symbols
from test_execution_policy import CASH, DECISION, _proposal

PORT = 55434
DATABASE = "dev3_entry_gate"
PASSWORD = "dev3-entry-gate"
CONTAINER = "dev3-entry-gate-pg"
URL = f"postgresql+psycopg://postgres:{PASSWORD}@127.0.0.1:{PORT}/{DATABASE}"


def _refuse(url: str) -> None:
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("BLOCKED: refusing a non-local database")
    if parsed.port in {None, 5432}:
        raise RuntimeError("BLOCKED: refusing port 5432")
    if parsed.path.strip("/") in {"", "core", "postgres"}:
        raise RuntimeError("BLOCKED: refusing a production database name")


def test_two_connections_can_add_only_one_entry_past_five() -> None:
    _refuse(URL)
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
            "-e",
            f"POSTGRES_DB={DATABASE}",
            "-p",
            f"127.0.0.1:{PORT}:5432",
            "postgres:16",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        pytest.fail(f"BLOCKED: disposable Postgres did not start: {started.stderr.strip()}")
    try:
        _wait_ready()
        factory = create_schema(URL)
        repository = CoreRepository(factory)
        load_seed(repository)
        repository.open_paper_session(CASH)
        symbols = _symbols(repository, 7)
        stored = [_enter(repository, symbol, DECISION, f"seed-{symbol}") for symbol in symbols[:5]]
        assert all(item is not None for item in stored)
        assert repository.daily_entry_count(DECISION) == 5
        for symbol, name in zip(symbols[5:], ("race-a", "race-b"), strict=True):
            _put_daily(repository, symbol, Decimal("99.76"), DECISION)
            proposal = _proposal(symbol, DECISION).model_copy(
                update={"proposal_id": name, "entry_price": Decimal("99.76"), "quantity": 5000}
            )
            repository.insert_proposal(proposal)
        barrier = threading.Barrier(2)
        outcomes: list[object] = []
        errors: list[BaseException] = []

        def _attempt(symbol: str, name: str) -> None:
            try:
                engine = create_engine(URL, poolclass=NullPool)
                local = CoreRepository(sessionmaker(bind=engine, expire_on_commit=False))
                proposal = local.get_proposal(name)
                assert proposal is not None
                barrier.wait(timeout=15)
                outcomes.append(queue_entry(local, proposal, DECISION))
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_attempt, args=(symbols[5], "race-a")),
            threading.Thread(target=_attempt, args=(symbols[6], "race-b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert sum(item is not None for item in outcomes) == 1
        assert repository.daily_entry_count(DECISION) == 6
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True, text=True)


def _wait_ready() -> None:
    deadline = time.time() + 60
    last = "postgres did not become ready"
    while time.time() < deadline:
        try:
            with psycopg.connect(
                f"host=127.0.0.1 port={PORT} user=postgres password={PASSWORD} dbname={DATABASE}",
                connect_timeout=2,
            ) as connection:
                version = connection.execute("SELECT version()").fetchone()
            if version and "PostgreSQL 16" in version[0]:
                return
            last = str(version)
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(0.5)
    pytest.fail(f"BLOCKED: {last}")
