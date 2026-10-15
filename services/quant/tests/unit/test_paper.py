from datetime import datetime, timezone

import httpx

from contracts.enums import Horizon, Timeframe, TradingMode
from contracts.schemas.feature_set import FeatureSet

from quant_agents.paper import publish_symbol_signals, run_paper_pass
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


def _feature_set() -> FeatureSet:
    moment = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)
    return FeatureSet(
        symbol="RELIANCE",
        timestamp=moment,
        timeframe=Timeframe.D1,
        feature_version="1.0.0",
        features={"return_1": 0.01, "last_close": 100.0},
        source_data_timestamp=moment,
    )


def test_refused_health_does_not_fetch_or_submit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sink = _MemorySink()
    written = run_paper_pass(
        "http://core-api:8000",
        "read",
        ("RELIANCE",),
        sink,
        client=client,
        sleep=lambda _delay: None,
        ready_attempts=2,
    )
    assert written == 0
    assert sink.signals == []


def test_health_retry_then_one_feature_fetch() -> None:
    state = {"health": 0, "features": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            state["health"] += 1
            if state["health"] == 1:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path.endswith(("/NIFTY50", "/INDIAVIX")):
            return httpx.Response(404, json={"detail": "no_features"})  # index bars not collected yet
        state["features"] += 1
        if state["features"] == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=_feature_set().model_dump(mode="json"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sink = _MemorySink()
    written = run_paper_pass(
        "http://core-api:8000",
        "read",
        ("RELIANCE",),
        sink,
        client=client,
        sleep=lambda _delay: None,
        ready_attempts=3,
    )
    assert state["health"] == 2
    assert state["features"] == 2
    assert written == 5
    assert len(sink.signals) == 5


def test_index_feature_sets_reach_the_regime_agent() -> None:
    from contracts.enums import AgentName

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        symbol = request.url.path.rsplit("/", 1)[-1]
        body = _feature_set().model_dump(mode="json")
        body["symbol"] = symbol
        return httpx.Response(200, json=body)

    sink = _MemorySink()
    run_paper_pass("http://core-api:8000", "read", ("RELIANCE",), sink, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _d: None)
    regime = next(item for item in sink.signals if item.agent_name == AgentName.REGIME)
    assert "regime.index_features_missing" not in regime.reason_codes
