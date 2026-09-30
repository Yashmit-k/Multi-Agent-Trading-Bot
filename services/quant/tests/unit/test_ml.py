from datetime import datetime, timezone
from pathlib import Path

from contracts.enums import Timeframe

from quant_agents.agents.technical import TechnicalAgent
from quant_agents.ml.agent import MlAgent
from quant_agents.ml.artifact import file_sha256, write_artifact
from quant_agents.ml.dataset import FEATURE_COLUMNS, build_dataset
from quant_agents.ml.model import make_model
from quant_agents.ml.registry import ModelRegistry
from quant_agents.ml.splits import WalkForwardSplitter, chronological_split
from quant_agents.ml.train import train
from quant_agents.replay import replay
from quant_agents.testing.history import HistoryFeatureProvider

from quant_agents.testing.harness import OPEN_AS_OF, SWING_CONFIG, make_context


def test_embargo_at_least_label_horizon() -> None:
    split = chronological_split(40, label_horizon=2, embargo_bars=2)
    assert split.embargo_bars >= 2
    try:
        chronological_split(40, label_horizon=3, embargo_bars=1)
    except AssertionError:
        pass
    else:
        raise AssertionError("expected embargo assertion")
    folds = WalkForwardSplitter(train_size=10, test_size=5, label_horizon=2).split(40)
    assert folds


def test_label_cutoff_drops_future_rows() -> None:
    provider = HistoryFeatureProvider()
    start = datetime(2024, 2, 1, 10, 0, tzinfo=timezone.utc)
    points = [start.replace(day=min(28, 1 + i)) if False else start.fromordinal(start.toordinal() + i).replace(tzinfo=timezone.utc) for i in range(10)]
    cutoff = points[4]
    result = build_dataset(
        provider,
        symbol="RELIANCE",
        timeframe=Timeframe.D1,
        as_of_points=points,
        label_horizon=1,
        training_data_cutoff=cutoff,
    )
    assert result.dropped_cutoff > 0
    assert all(stamp <= cutoff for stamp in result.as_of_list) or result.rows


def test_train_registry_and_inference_determinism(tmp_path, clock, calendar) -> None:
    cutoff = datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)
    directory = tmp_path / "model"
    train(output_dir=directory, cutoff=cutoff)
    registry = ModelRegistry(tmp_path)
    agent = MlAgent(clock, calendar, registry)
    context, _ = make_context(HistoryFeatureProvider(), {**SWING_CONFIG})
    first = agent.evaluate("RELIANCE", OPEN_AS_OF, context)
    second = agent.evaluate("RELIANCE", OPEN_AS_OF, context)
    assert first.signal_id == second.signal_id
    assert first.metadata.get("baseline") is True
    daily = registry.eligible(as_of=OPEN_AS_OF, timeframe="1d")
    assert daily is not None
    assert registry.eligible(as_of=OPEN_AS_OF, timeframe="5m") is None


def test_artifact_corrupt_and_hash_cache(tmp_path, clock, calendar, monkeypatch) -> None:
    cutoff = datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc)
    directory = tmp_path / "model"
    train(output_dir=directory, cutoff=cutoff)
    model_path = directory / "model.joblib"
    data = bytearray(model_path.read_bytes())
    data[0] = data[0] ^ 0xFF
    model_path.write_bytes(bytes(data))
    agent = MlAgent(clock, calendar, ModelRegistry(tmp_path))
    signal = agent.evaluate("RELIANCE", OPEN_AS_OF, make_context(HistoryFeatureProvider())[0])
    assert "ml.artifact_corrupt" in signal.reason_codes
    assert signal.valid_until == signal.timestamp

    train(output_dir=directory, cutoff=cutoff)
    registry = ModelRegistry(tmp_path)
    calls = {"n": 0}
    original = file_sha256

    def counted(path: Path) -> str:
        calls["n"] += 1
        return original(path)

    monkeypatch.setattr("quant_agents.ml.registry.file_sha256", counted)
    registry.load(directory)
    registry.load(directory)
    assert calls["n"] == 1


def test_replay_out_of_sample_flag(calendar) -> None:
    from contracts.enums import Horizon
    from quant_agents.clock import ReplayClock

    cutoff = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

    def factory(symbol, as_of, horizon):
        return make_context(HistoryFeatureProvider(), {**SWING_CONFIG, "horizon": horizon})[0]

    output = replay(
        [TechnicalAgent(ReplayClock(OPEN_AS_OF), calendar)],
        symbols=["RELIANCE"],
        horizons=[Horizon.SWING],
        as_of_points=[OPEN_AS_OF],
        context_factory=factory,
        ml_training_data_cutoff=cutoff,
    )
    assert output["out_of_sample"] is True
