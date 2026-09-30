from datetime import datetime, timezone

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from quant_agents.service import create_app
from quant_agents.settings import QuantSettings


def test_health_degraded_without_sink() -> None:
    app = create_app(
        QuantSettings(data_source="fixtures", trading_mode=TradingMode.BACKTEST, log_level="INFO", artifact_dir=None, horizons_path=None),
        sink=None,
    )
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["reason"] == "no_signal_sink"


def test_refuses_live_without_sink() -> None:
    try:
        create_app(
            QuantSettings(data_source="fixtures", trading_mode=TradingMode.PAPER, log_level="INFO", artifact_dir=None, horizons_path=None),
            sink=None,
        )
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")
