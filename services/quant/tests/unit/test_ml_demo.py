from datetime import datetime, timezone

import httpx
import pytest
from sklearn.linear_model import LogisticRegression

from contracts.enums import Timeframe, TradingMode
from contracts.fakes import FakeFundamentalProvider, FakeMarketDataProvider, FakeNewsProvider
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.feature_set import FeatureSet

from quant_agents.agents.technical import TechnicalAgent
from quant_agents.calendar.static_nse import StaticNseCalendar
from quant_agents.clock import ReplayClock
from quant_agents.errors import ConfigError
from quant_agents.ml.agent import MlAgent
from quant_agents.ml.demo import (
    DEMO_COLUMNS,
    finite_row,
    finite_value,
    prepare_demo_artifact,
    synthetic_dataset,
)
from quant_agents.ml.registry import ModelRegistry
from quant_agents.paper import _SWING, _OneFeatureProvider, publish_symbol_signals, run_paper_pass
from quant_agents.scoring import score_probability
from quant_agents.settings import QuantSettings

AS_OF = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)


class _Sink:
    def __init__(self) -> None:
        self.signals = []

    def submit(self, signal) -> None:
        self.signals.append(signal)


def _features(**updates: float | None) -> FeatureSet:
    values: dict[str, float] = {
        "return_1": 0.01,
        "rsi_14": 55.0,
        "macd": 0.2,
        "last_close": 2500.0,
    }
    for key, value in updates.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value
    return FeatureSet(
        symbol="RELIANCE",
        timestamp=AS_OF,
        timeframe=Timeframe.D1,
        feature_version="1.1.0",
        features=values,
        source_data_timestamp=AS_OF,
    )


def _context(feature_set: FeatureSet) -> AgentContext:
    return AgentContext(
        market_data_provider=FakeMarketDataProvider(),
        feature_provider=_OneFeatureProvider(feature_set),
        news_provider=FakeNewsProvider(),
        fundamental_provider=FakeFundamentalProvider(),
        configuration=_SWING,
    )


def test_finite_values_reject_missing_and_non_finite() -> None:
    with pytest.raises(ValueError):
        finite_value(None, "rsi_14")
    with pytest.raises(ValueError):
        finite_value(float("nan"), "rsi_14")
    with pytest.raises(ValueError):
        finite_value(float("inf"), "last_close")
    with pytest.raises(ValueError):
        finite_row([0.01, float("nan"), 0.2, 2500.0])


def test_validation_slice_is_not_fit(monkeypatch, tmp_path) -> None:
    seen: dict[str, list[int]] = {}
    real = LogisticRegression.fit

    def spy(self, X, y, **kwargs):
        seen["y"] = [int(item) for item in y]
        return real(self, X, y, **kwargs)

    monkeypatch.setattr(LogisticRegression, "fit", spy)
    prepare_demo_artifact(tmp_path)
    _rows, labels = synthetic_dataset()
    assert seen["y"] == labels[:24]
    assert len(labels) > 24
    prepare_demo_artifact(tmp_path)
    assert seen["y"] == labels[:24]


def test_repeated_inference_matches_score_probability(tmp_path) -> None:
    registry = prepare_demo_artifact(tmp_path)
    feature_set = _features()
    clock = ReplayClock(AS_OF)
    calendar = StaticNseCalendar()
    agent = MlAgent(clock, calendar, registry)
    first = agent.evaluate("RELIANCE", AS_OF, _context(feature_set))
    second = agent.evaluate("RELIANCE", AS_OF, _context(feature_set))
    loaded = registry.load(tmp_path)
    row = [feature_set.features[name] for name in DEMO_COLUMNS]
    probability = float(loaded.model.predict_proba([row])[0][1])
    assert first.signal == second.signal == score_probability(probability).signal
    assert first.signal_id == second.signal_id
    assert first.metadata["training_positive_rate"] != 0.5
    assert loaded.model.named_steps["scale"].n_samples_seen_ == 24
    restored = AgentSignal.model_validate(first.model_dump(mode="json"))
    assert restored.metadata["demo"] is True
    assert restored.metadata["training_data"] == "synthetic_unvalidated_demo"
    assert not any(code.startswith("ml.feature_missing.") for code in first.reason_codes)


def test_ml_id_differs_from_a_rule_agent(tmp_path) -> None:
    registry = prepare_demo_artifact(tmp_path)
    feature_set = _features()
    context = _context(feature_set)
    clock = ReplayClock(AS_OF)
    calendar = StaticNseCalendar()
    ml_signal = MlAgent(clock, calendar, registry).evaluate("RELIANCE", AS_OF, context)
    rule_signal = TechnicalAgent(clock, calendar).evaluate("RELIANCE", AS_OF, context)
    assert ml_signal.signal_id != rule_signal.signal_id
    assert ml_signal.agent_name.value == "ml"


def test_missing_demo_feature_skips_without_legacy_codes(tmp_path) -> None:
    registry = prepare_demo_artifact(tmp_path)
    feature_set = _features(rsi_14=None)
    signal = MlAgent(ReplayClock(AS_OF), StaticNseCalendar(), registry).evaluate(
        "RELIANCE", AS_OF, _context(feature_set)
    )
    assert "ml.feature_invalid" in signal.reason_codes
    assert not any(code.startswith("ml.feature_missing.") for code in signal.reason_codes)
    sink = _Sink()
    assert publish_symbol_signals("RELIANCE", feature_set, sink, ml_registry=registry, ml_demo=True) == 5
    assert [item.agent_name.value for item in sink.signals].count("ml") == 0


def test_normal_artifact_keeps_its_own_schema(tmp_path) -> None:
    from quant_agents.ml.dataset import FEATURE_COLUMNS
    from quant_agents.ml.train import train
    from quant_agents.testing.harness import OPEN_AS_OF, SWING_CONFIG, make_context
    from quant_agents.testing.history import HistoryFeatureProvider

    cutoff = datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)
    train(output_dir=tmp_path / "model", cutoff=cutoff)
    registry = ModelRegistry(tmp_path)
    provider = HistoryFeatureProvider()
    context, _ = make_context(provider, {**SWING_CONFIG})
    clock = ReplayClock(OPEN_AS_OF)
    calendar = StaticNseCalendar()
    signal = MlAgent(clock, calendar, registry).evaluate("RELIANCE", OPEN_AS_OF, context)
    assert "ml.feature_invalid" not in signal.reason_codes
    assert not any(code.startswith("ml.feature_missing.") for code in signal.reason_codes)
    assert signal.metadata.get("demo") is not True

    original = provider.get_feature_set("RELIANCE", Timeframe.D1, OPEN_AS_OF)
    incomplete = original.model_copy(update={"features": {key: value for key, value in original.features.items() if key != "sma_10"}})
    assert "sma_10" in FEATURE_COLUMNS
    sink = _Sink()
    written = publish_symbol_signals(
        "RELIANCE",
        incomplete,
        sink,
        clock=clock,
        calendar=calendar,
        ml_registry=registry,
        ml_demo=False,
    )
    assert written == 5
    assert [item.agent_name.value for item in sink.signals].count("ml") == 0


def test_incompatible_or_missing_features_are_not_submitted(tmp_path) -> None:
    prepare_demo_artifact(tmp_path)
    registry = ModelRegistry(tmp_path)
    sink = _Sink()
    assert publish_symbol_signals("RELIANCE", _features(rsi_14=None), sink, ml_registry=registry, ml_demo=True) == 5
    assert all(signal.agent_name.value != "ml" for signal in sink.signals)

    manifest_path = tmp_path / "manifest.json"
    text = manifest_path.read_text(encoding="utf-8")
    swapped = text.replace('[\n    "return_1",\n    "rsi_14"', '[\n    "rsi_14",\n    "return_1"')
    manifest_path.write_text(swapped, encoding="utf-8")
    sink = _Sink()
    assert publish_symbol_signals("RELIANCE", _features(), sink, ml_registry=ModelRegistry(tmp_path), ml_demo=True) == 5

    versioned = swapped.replace('"feature_version": "1.1.0"', '"feature_version": "9.9.9"', 1)
    manifest_path.write_text(versioned, encoding="utf-8")
    sink = _Sink()
    assert publish_symbol_signals("RELIANCE", _features(), sink, ml_registry=ModelRegistry(tmp_path), ml_demo=True) == 5

    model_path = tmp_path / "model.joblib"
    payload = bytearray(model_path.read_bytes())
    payload[0] ^= 0xFF
    model_path.write_bytes(bytes(payload))
    sink = _Sink()
    assert publish_symbol_signals("RELIANCE", _features(), sink, ml_registry=ModelRegistry(tmp_path), ml_demo=True) == 5


def test_ml_failure_does_not_block_rule_agents() -> None:
    class _Boom:
        def eligible(self, **_kwargs):
            raise RuntimeError("boom")

    sink = _Sink()
    written = publish_symbol_signals("RELIANCE", _features(), sink, ml_registry=_Boom(), ml_demo=True)
    assert written == 5
    assert [signal.agent_name.value for signal in sink.signals].count("ml") == 0


def test_demo_settings_fail_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("QUANT_ML_DEMO", raising=False)
    monkeypatch.delenv("QUANT_ML_DEMO_DIR", raising=False)
    monkeypatch.delenv("QUANT_ARTIFACT_DIR", raising=False)
    monkeypatch.setenv("QUANT_TRADING_MODE", "PAPER")
    assert QuantSettings.from_env().ml_demo is False

    monkeypatch.setenv("QUANT_ML_DEMO", "true")
    monkeypatch.setenv("QUANT_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("QUANT_ML_DEMO_DIR", str(tmp_path))
    with pytest.raises(ConfigError):
        QuantSettings.from_env()

    monkeypatch.setenv("QUANT_TRADING_MODE", "PAPER")
    monkeypatch.setenv("QUANT_ARTIFACT_DIR", str(tmp_path / "normal"))
    with pytest.raises(ConfigError):
        QuantSettings.from_env()


def test_disabled_demo_does_not_train(monkeypatch, tmp_path) -> None:
    def _refuse(*_args, **_kwargs):
        raise AssertionError("demo training ran")

    monkeypatch.setattr("quant_agents.ml.demo.prepare_demo_artifact", _refuse)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    written = run_paper_pass(
        "http://core-api:8000",
        "read",
        ("RELIANCE",),
        _Sink(),
        client=client,
        sleep=lambda _delay: None,
        ready_attempts=1,
        ml_demo=False,
        ml_demo_dir=str(tmp_path),
    )
    assert written == 0
    assert not (tmp_path / "model.joblib").exists()
