from datetime import datetime, timedelta, timezone

from contracts.enums import Horizon, Timeframe, TradingMode
from contracts.events import EventType
from contracts.fakes import FakeSignalSink
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.event import EventEnvelope

from quant_agents.agents.technical import TechnicalAgent
from quant_agents.clock import ReplayClock, SystemClock
from quant_agents.errors import LeakageError
from quant_agents.replay import replay
from quant_agents.runner import Runner
from quant_agents.testing.core_compatible import CoreCompatibleFeatureProvider

from quant_agents.testing.harness import INTRADAY_CONFIG, OPEN_AS_OF, SWING_CONFIG, make_context


def test_provider_call_audit_and_no_market_data(clock, calendar) -> None:
    provider = CoreCompatibleFeatureProvider()
    agent = TechnicalAgent(clock, calendar)
    context, calls = make_context(provider)
    agent.evaluate("RELIANCE", OPEN_AS_OF, context)
    assert calls
    for call in calls:
        assert call.requested_time <= OPEN_AS_OF
        assert call.provider != "market"
    assert not any(call.method.startswith("get_quote") for call in calls)


def test_future_poisoning_does_not_change_signal(clock, calendar) -> None:
    clean = CoreCompatibleFeatureProvider()
    poisoned = CoreCompatibleFeatureProvider(poison_after=OPEN_AS_OF, poison_value=9999.0)
    a = TechnicalAgent(clock, calendar).evaluate("RELIANCE", OPEN_AS_OF, make_context(clean)[0])
    b = TechnicalAgent(clock, calendar).evaluate("RELIANCE", OPEN_AS_OF, make_context(poisoned)[0])
    assert a.signal == b.signal
    assert a.features["last_close"] == b.features["last_close"]


def test_point_in_time_guard_raises(clock, calendar) -> None:
    provider = CoreCompatibleFeatureProvider()
    original = provider.get_feature_set

    def future_set(symbol, timeframe, as_of):
        item = original(symbol, timeframe, as_of)
        return item.model_copy(update={"timestamp": as_of + timedelta(days=1)})

    provider.get_feature_set = future_set  # type: ignore[method-assign]
    try:
        TechnicalAgent(clock, calendar).evaluate("RELIANCE", OPEN_AS_OF, make_context(provider)[0])
    except LeakageError:
        return
    raise AssertionError("expected LeakageError")


def test_schema_round_trip(clock, calendar) -> None:
    signal = TechnicalAgent(clock, calendar).evaluate(
        "RELIANCE", OPEN_AS_OF, make_context(CoreCompatibleFeatureProvider())[0]
    )
    dumped = signal.model_dump(mode="json")
    again = AgentSignal.model_validate(dumped)
    envelope = EventEnvelope(
        event_id="e1",
        event_type=EventType.AGENT_SIGNAL,
        timestamp=signal.timestamp,
        source="test",
        correlation_id=signal.signal_id,
        payload=again,
    )
    EventEnvelope.model_validate(envelope.model_dump(mode="json"))


def test_replay_determinism(clock, calendar) -> None:
    def factory(symbol, as_of, horizon):
        config = dict(SWING_CONFIG)
        config["horizon"] = horizon
        return make_context(CoreCompatibleFeatureProvider(), config)[0]

    agents = [TechnicalAgent(ReplayClock(OPEN_AS_OF), calendar)]
    first = replay(agents, symbols=["RELIANCE"], horizons=[Horizon.SWING], as_of_points=[OPEN_AS_OF], context_factory=factory)
    second = replay(
        [TechnicalAgent(ReplayClock(OPEN_AS_OF), calendar)],
        symbols=["RELIANCE"],
        horizons=[Horizon.SWING],
        as_of_points=[OPEN_AS_OF],
        context_factory=factory,
    )
    assert [item.signal_id for item in first["signals"]] == [item.signal_id for item in second["signals"]]


def test_intraday_signal_not_generated_after_session_close(calendar) -> None:
    closed = datetime(2024, 6, 3, 10, 1, tzinfo=timezone.utc)

    class Frozen:
        def now(self):
            return closed

    sink = FakeSignalSink()

    def factory(symbol, as_of, horizon):
        config = dict(INTRADAY_CONFIG)
        config["horizon"] = horizon
        return make_context(CoreCompatibleFeatureProvider(), config)[0]

    runner = Runner(
        [TechnicalAgent(Frozen(), calendar)],
        sink,
        Frozen(),
        calendar,
        factory,
        TradingMode.PAPER,
    )
    signals = runner.run(["RELIANCE"], [Horizon.INTRADAY], closed)
    assert signals == []
    assert "intraday_session_closed" in runner.skipped


def test_runner_rejects_future_as_of(calendar) -> None:
    class Frozen:
        def now(self):
            return OPEN_AS_OF

    runner = Runner(
        [TechnicalAgent(Frozen(), calendar)],
        FakeSignalSink(),
        Frozen(),
        calendar,
        lambda symbol, as_of, horizon: make_context(CoreCompatibleFeatureProvider())[0],
        TradingMode.PAPER,
    )
    future = OPEN_AS_OF + timedelta(hours=1)
    assert runner.run(["RELIANCE"], [Horizon.SWING], future) == []
    assert "as_of_after_clock" in runner.skipped


def test_runner_isolates_agent_failure(calendar) -> None:
    class Boom:
        agent_name = "boom"

        def evaluate(self, symbol, as_of, context):
            raise RuntimeError("boom")

    runner = Runner(
        [Boom(), TechnicalAgent(ReplayClock(OPEN_AS_OF), calendar)],
        FakeSignalSink(),
        ReplayClock(OPEN_AS_OF),
        calendar,
        lambda symbol, as_of, horizon: make_context(CoreCompatibleFeatureProvider())[0],
        TradingMode.BACKTEST,
    )
    signals = runner.run(["RELIANCE"], [Horizon.SWING], OPEN_AS_OF)
    assert len(signals) == 1
    assert signals[0].agent_name.value == "technical"
