"""Scripted collector in its own Compose project. Not production and not Zerodha.

Two collector writes land in the isolated database. After that API process
stops, the same database gains no further bar.
"""

from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.checkpoint2.yml"
PROJECT = "dev3-cp2-collector"
DSN = "host=127.0.0.1 port=15432 user=collector password=collector dbname=collector_probe"


def test_scripted_polls_stop_when_the_probe_process_stops() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "core-worker" not in text
    assert "docker-compose.yml" not in text
    assert "127.0.0.1:15432:5432" in text
    assert "127.0.0.1:18000:8000" in text
    assert "collector_probe" in text
    _compose("down", "-v")
    started = _compose("up", "-d", "--build")
    if started.returncode != 0:
        pytest.fail(f"BLOCKED: isolated collector project did not start:\n{started.stderr}")
    try:
        _wait_health()
        names = _compose("ps", "--services").stdout.split()
        assert "collector-api" in names
        assert "core-worker" not in names
        assert _wait_for_bars(3) >= 3
        _compose("stop", "collector-api")
        _wait_stopped()
        settled = _bar_count()
        time.sleep(2)
        assert settled >= 3
        assert _bar_count() == settled
    finally:
        _compose("down", "-v")


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", PROJECT, "-f", str(COMPOSE_FILE), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _wait_health() -> None:
    deadline = time.time() + 180
    last = "probe did not answer"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:18000/", timeout=2) as response:
                if response.status == 200:
                    return
                last = f"status {response.status}"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    logs = _compose("logs", "--tail", "80", "collector-api")
    pytest.fail(f"BLOCKED: {last}\n{logs.stdout}\n{logs.stderr}")


def _wait_stopped() -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        listed = _compose("ps", "--status", "running", "--services")
        if "collector-api" not in listed.stdout.split():
            return
        time.sleep(0.5)
    pytest.fail("BLOCKED: collector-api was still running after stop")


def _wait_for_bars(minimum: int) -> int:
    deadline = time.time() + 60
    last = "isolated database was not ready"
    while time.time() < deadline:
        try:
            count = _bar_count()
        except Exception as exc:
            last = type(exc).__name__
            time.sleep(0.5)
            continue
        if count >= minimum:
            return count
        last = f"bar count {count}"
        time.sleep(0.5)
    pytest.fail(f"BLOCKED: {last}")


def _bar_count() -> int:
    with psycopg.connect(DSN, connect_timeout=2) as connection:
        row = connection.execute("SELECT count(*) FROM candles WHERE timeframe = '5m'").fetchone()
    assert row is not None
    return int(row[0])
