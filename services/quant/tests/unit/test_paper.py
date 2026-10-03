from datetime import datetime, timezone

from contracts.enums import Horizon, Timeframe, TradingMode
from contracts.schemas.feature_set import FeatureSet

from quant_agents.paper import publish_symbol_signals
from quant_agents.service import create_app
from quant_agents.settings import QuantSettings


class _MemorySink:
    def __init__(self) -> None:
        self.signals = []

    def submit(self, signal) -> None:
        self.signals.append(signal)


def test_publish_uses_core_features_for_each_agent() -> None:
    moment = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)
    feature_set = FeatureSet(
        symbol="RELIANCE",
        timestamp=moment,
        timeframe=Timeframe.D1,
        feature_version="1.0.0",
        features={
            "return_1": 0.01,
            "momentum_10": 12.0,
            "macd": 0.4,
            "macd_signal": 0.2,
            "last_close": 100.0,
            "last_volume": 1000,
            "volume_mean": 800.0,
            "ema_12": 99.0,
            "ema_26": 97.0,
            "sma_10": 98.0,
            "sma_20": 96.0,
            "vwap": 98.5,
            "rsi_14": 55.0,
            "bollinger_mid": 97.0,
            "bollinger_upper": 110.0,
            "bollinger_lower": 84.0,
        },
        source_data_timestamp=moment,
    )
    sink = _MemorySink()
    assert publish_symbol_signals("RELIANCE", feature_set, sink) == 5
    assert {item.horizon for item in sink.signals} == {Horizon.SWING}
    assert any(item.signal != 0 for item in sink.signals)


def test_paper_credentials_build_a_sink() -> None:
    app = create_app(
        QuantSettings(
            data_source="fixtures",
            trading_mode=TradingMode.PAPER,
            log_level="INFO",
            artifact_dir=None,
            horizons_path=None,
            core_api_url="http://core-api:8000",
            core_api_token="read",
            internal_signal_token="write",
            symbols=("RELIANCE",),
        )
    )
    assert app.state.sink is not None
