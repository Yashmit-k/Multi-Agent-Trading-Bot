"""GET /api/v1/momentum-trial serves the paper trial's report, read-only and behind the user token."""

import json

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher


def _client(repository: CoreRepository) -> TestClient:
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
    )
    return TestClient(create_app(settings, repository, MemoryEventPublisher()))


def test_report_is_served_and_needs_the_token(repository: CoreRepository, tmp_path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("MOMENTUM_TRIAL_REPORT", str(report))
    client = _client(repository)
    headers = {"Authorization": "Bearer core"}
    assert client.get("/api/v1/momentum-trial", headers=headers).json() == {"status": "not started"}
    report.write_text(json.dumps({"status": "running", "return": 0.018}))
    assert client.get("/api/v1/momentum-trial", headers=headers).json()["return"] == 0.018
    assert client.get("/api/v1/momentum-trial").status_code in (401, 403)
    report.write_text("{broken")
    assert client.get("/api/v1/momentum-trial", headers=headers).status_code == 503
