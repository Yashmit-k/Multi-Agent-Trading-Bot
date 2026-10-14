"""Checkpoint 3 reads. In-process only. Does not start the worker or call a running API."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_ingestion.service import MemoryEventPublisher
from core_worker.heartbeat import heartbeat_view, publish_heartbeat

UTC = timezone.utc
HEADERS = {"Authorization": "Bearer core"}


def test_daily_performance_stays_unavailable() -> None:
    client = TestClient(_app())
    response = client.get("/api/v1/paper/daily-performance", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "unavailable", "reason": "no_daily_equity_history"}
    assert "realized_pnl" not in body
    assert "sharpe" not in body
    assert "drawdown" not in body
    assert "total_return" not in body
    backtest = client.get("/api/v1/performance", headers=HEADERS)
    assert backtest.status_code == 404
    assert backtest.json()["detail"] == "no_backtest"


def test_heartbeat_is_unavailable_until_a_fresh_beat() -> None:
    moment = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    assert heartbeat_view(None, moment, 30) == {"status": "unavailable"}
    assert heartbeat_view(moment - timedelta(seconds=30), moment, 30)["status"] == "available"
    assert heartbeat_view(moment - timedelta(seconds=31), moment, 30) == {"status": "unavailable"}

    app = _app()
    client = TestClient(app)
    missing = client.get("/api/v1/worker/heartbeat", headers=HEADERS)
    assert missing.json() == {"status": "unavailable"}

    posted = client.post(
        "/api/v1/worker/heartbeat",
        headers=HEADERS,
        json={"heartbeat_at": datetime.now(UTC).isoformat(), "interval_seconds": 30},
    )
    assert posted.status_code == 200
    assert posted.json()["status"] == "available"
    fresh = client.get("/api/v1/worker/heartbeat", headers=HEADERS)
    assert fresh.json()["status"] == "available"

    app.state.worker_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
    app.state.worker_heartbeat_interval_seconds = 30
    stale = client.get("/api/v1/worker/heartbeat", headers=HEADERS)
    assert stale.json() == {"status": "unavailable"}


def test_publish_heartbeat_posts_once_and_ignores_a_down_api() -> None:
    seen: list[tuple[str, bytes]] = []

    def _urlopen(request, timeout):
        seen.append((request.full_url, request.data))
        return _Response()

    moment = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    assert publish_heartbeat("http://core-api:8000", "core", moment, interval_seconds=30, urlopen=_urlopen) is True
    assert seen[0][0] == "http://core-api:8000/api/v1/worker/heartbeat"
    assert b"2026-10-13T10:00:00+00:00" in seen[0][1]
    assert publish_heartbeat("", "core", moment, urlopen=_urlopen) is False
    assert len(seen) == 1

    def _down(request, timeout):
        raise TimeoutError("down")

    assert publish_heartbeat("http://core-api:8000", "core", moment, urlopen=_down) is False


def test_worker_loop_calls_the_helper_without_this_test_importing_main() -> None:
    source = Path("services/core/worker/src/core_worker/__main__.py").read_text(encoding="utf-8")
    loop = source.split("while True:", 1)[1]
    assert "publish_heartbeat(" in loop
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = [
        f"{node.module}.{alias.name}"
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert "core_worker.__main__" not in imported


def _app():
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
    )
    return create_app(settings, CoreRepository(create_schema("sqlite://")), MemoryEventPublisher())


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None
