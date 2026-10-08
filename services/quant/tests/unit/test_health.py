from datetime import datetime, timezone

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from quant_agents.service import create_app
from quant_agents.settings import QuantSettings


def test_default_horizon_stays_swing_daily() -> None:
    settings = QuantSettings(data_source="fixtures", trading_mode=TradingMode.BACKTEST, log_level="INFO", artifact_dir=None, horizons_path=None)
    assert settings.horizon == "SWING"
    assert settings.timeframe == "1d"


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


def test_refuses_publish_modes_without_sink() -> None:
    for mode in (TradingMode.PAPER, TradingMode.SHADOW, TradingMode.LIVE):
        try:
            create_app(
                QuantSettings(data_source="fixtures", trading_mode=mode, log_level="INFO", artifact_dir=None, horizons_path=None),
                sink=None,
            )
        except RuntimeError:
            continue
        raise AssertionError(f"expected RuntimeError for {mode.value}")


def test_injected_sink_is_the_object_paper_publishes_through() -> None:
    sink = object()
    app = create_app(
        QuantSettings(data_source="fixtures", trading_mode=TradingMode.BACKTEST, log_level="INFO", artifact_dir=None, horizons_path=None),
        sink=sink,
    )
    assert app.state.sink is sink
