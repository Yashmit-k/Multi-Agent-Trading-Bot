import logging
import re
from datetime import datetime, timedelta, timezone

from contracts.enums import Horizon, Timeframe
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.event import EventEnvelope
from contracts.events import EventType

from quant_agents.agents.mean_reversion import MeanReversionAgent
from quant_agents.agents.momentum import MomentumAgent
from quant_agents.agents.regime import RegimeAgent
from quant_agents.agents.technical import TechnicalAgent
from quant_agents.agents.volume import VolumeAgent
from quant_agents.calendar.static_nse import IST, SESSION_CLOSE, StaticNseCalendar
from quant_agents.clock import ReplayClock
from quant_agents.config import parse_evaluation_config
from quant_agents.errors import ConfigError, LeakageError
from quant_agents.feature_view import FeatureView
from quant_agents.providers.compat import FixtureCompatibilityFeatureProvider
from quant_agents.scoring import score_probability, score_votes
from quant_agents.testing.core_compatible import CoreCompatibleFeatureProvider, engine_key_snapshot
from quant_agents.testing.extended import ExtendedFeatureProvider
from quant_agents.vote import Vote

from quant_agents.testing.harness import INTRADAY_CONFIG, OPEN_AS_OF, SWING_CONFIG, make_context

CODE_PATTERN = re.compile(r"^[a-z0-9_.]+$")
AGENTS = (TechnicalAgent, MomentumAgent, MeanReversionAgent, VolumeAgent, RegimeAgent)


def _eval(agent_cls, provider, clock, calendar, config=None):
    agent = agent_cls(clock, calendar)
    context, calls = make_context(provider, config)
    signal = agent.evaluate("RELIANCE", OPEN_AS_OF, context)
    return signal, calls


def test_horizons_rejects_disallowed_combination() -> None:
    try:
        parse_evaluation_config({"horizon": Horizon.SWING, "timeframe": Timeframe.M1})
    except ConfigError:
        return
    raise AssertionError("expected ConfigError")


def test_scoring_rejects_feature_view_and_dict(calendar, clock) -> None:
    view = FeatureView(
        CoreCompatibleFeatureProvider().get_feature_set("RELIANCE", Timeframe.D1, OPEN_AS_OF)
    )
    try:
        score_votes(view, required=("rsi_14",), missing=())
        raise AssertionError("expected TypeError")
    except TypeError:
        pass
    try:
        score_votes({"rsi_14": 1}, required=("rsi_14",), missing=())
        raise AssertionError("expected TypeError")
    except TypeError:
        pass
    try:
        score_probability(view)
        raise AssertionError("expected TypeError")
    except TypeError:
        pass
    score = score_votes((Vote("x", 1, 1.0),), required=("x",), missing=())
    assert score.signal == 1.0


def test_agents_on_core_and_extended(clock, calendar) -> None:
    core = CoreCompatibleFeatureProvider()
    extended = ExtendedFeatureProvider()
    for agent_cls in AGENTS:
        core_signal, _ = _eval(agent_cls, core, clock, calendar)
        ext_signal, _ = _eval(agent_cls, extended, clock, calendar)
        AgentSignal.model_validate(core_signal.model_dump())
        AgentSignal.model_validate(ext_signal.model_dump())
        if agent_cls is MeanReversionAgent:
            assert any("feature_missing" in code for code in core_signal.reason_codes)
        if agent_cls is VolumeAgent:
            assert any("feature_missing" in code for code in core_signal.reason_codes)
        if agent_cls is RegimeAgent:
            assert "regime.volatility_reference_missing" in core_signal.reason_codes
            assert "HIGH_VOLATILITY" not in core_signal.metadata["regimes"]
            assert "LOW_VOLATILITY" not in core_signal.metadata["regimes"]


def test_regime_omits_risk_without_index(clock, calendar) -> None:
    agent = RegimeAgent(clock, calendar)
    context, _ = make_context(ExtendedFeatureProvider(omit_index=True))
    signal = agent.evaluate("RELIANCE", OPEN_AS_OF, context)
    assert "regime.index_features_missing" in signal.reason_codes
    assert "RISK_ON" not in signal.metadata["regimes"]
    assert "RISK_OFF" not in signal.metadata["regimes"]


def test_all_emitted_reason_codes_match_contract(clock, calendar) -> None:
    codes: list[str] = []
    for provider in (CoreCompatibleFeatureProvider(), ExtendedFeatureProvider()):
        for agent_cls in AGENTS:
            signal, _ = _eval(agent_cls, provider, clock, calendar)
            codes.extend(signal.reason_codes)
    cal = StaticNseCalendar()
    uncovered = datetime.combine(cal.last_covered_date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    stale_provider = CoreCompatibleFeatureProvider()
    stale_provider.set_source("RELIANCE", OPEN_AS_OF, datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc))
    uncovered_clock = ReplayClock(uncovered)
    for agent_cls in AGENTS:
        agent = agent_cls(clock, calendar)
        context, _ = make_context(stale_provider)
        codes.extend(agent.evaluate("RELIANCE", OPEN_AS_OF, context).reason_codes)
        context, _ = make_context(CoreCompatibleFeatureProvider())
        codes.extend(agent_cls(uncovered_clock, calendar).evaluate("RELIANCE", uncovered, context).reason_codes)
    assert codes
    for code in codes:
        assert CODE_PATTERN.fullmatch(code), code


def test_neutral_signals_are_contract_valid(clock, calendar) -> None:
    cal = StaticNseCalendar()
    uncovered = datetime.combine(cal.last_covered_date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    uncovered_clock = ReplayClock(uncovered)
    agent = TechnicalAgent(uncovered_clock, calendar)
    context, _ = make_context(CoreCompatibleFeatureProvider())
    uncovered_signal = agent.evaluate("RELIANCE", uncovered, context)
    assert uncovered_signal.valid_until == uncovered_signal.timestamp
    assert "calendar.not_covered" in uncovered_signal.reason_codes
    AgentSignal.model_validate(uncovered_signal.model_dump())
    stale_provider = CoreCompatibleFeatureProvider()
    stale_provider.set_source("RELIANCE", OPEN_AS_OF, datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc))
    stale_signal = TechnicalAgent(clock, calendar).evaluate("RELIANCE", OPEN_AS_OF, make_context(stale_provider)[0])
    assert stale_signal.valid_until == stale_signal.timestamp
    assert "feature.stale" in stale_signal.reason_codes
    AgentSignal.model_validate(stale_signal.model_dump())


def test_compat_warns_once(clock, calendar, caplog) -> None:
    caplog.set_level(logging.WARNING)
    provider = FixtureCompatibilityFeatureProvider()
    agent = MomentumAgent(clock, calendar)
    context, _ = make_context(provider)
    agent.evaluate("RELIANCE", OPEN_AS_OF, context)
    agent.evaluate("TCS", OPEN_AS_OF, context)
    warnings = [record for record in caplog.records if "FixtureCompatibility" in record.message]
    assert len(warnings) == 1


def test_session_boundaries(calendar) -> None:
    day = datetime(2024, 6, 3, tzinfo=IST)
    open_exact = day.replace(hour=9, minute=15, second=0, microsecond=0)
    before = open_exact.replace(microsecond=0) - timedelta(microseconds=1000)
    almost_close = day.replace(hour=15, minute=29, second=59, microsecond=999000)
    close_exact = day.replace(hour=15, minute=30, second=0, microsecond=0)
    assert calendar.is_session_open(open_exact)
    assert not calendar.is_session_open(before)
    assert calendar.is_session_open(almost_close)
    assert not calendar.is_session_open(close_exact)
    assert calendar.session_close(open_exact) == close_exact.astimezone(timezone.utc)


def test_engine_key_snapshot_matches_committed() -> None:
    keys = engine_key_snapshot()
    assert "rsi_14" in keys
    assert "return_1" in keys
    assert "last_volume" in keys


def test_volume_agent_grades_its_conviction() -> None:
    from quant_agents.agents.volume import VolumeAgent
    from quant_agents.scoring import score_votes

    agent = VolumeAgent.__new__(VolumeAgent)

    class View:
        def __init__(self, features):
            self._features = features

        def get(self, name):
            return self._features.get(name)

    def score(features):
        decision = agent.interpret(View(features), {})
        return score_votes(decision.votes, required=VolumeAgent.required_features, missing=())

    ordinary = score({"last_volume": 120.0, "volume_mean": 100.0, "return_1": 0.01, "relative_volume": 1.2, "price_volume_corr": 0.1})
    surge = score({"last_volume": 250.0, "volume_mean": 100.0, "return_1": 0.03, "relative_volume": 2.5, "price_volume_corr": 0.44})
    extreme = score({"last_volume": 400.0, "volume_mean": 100.0, "return_1": 0.04, "relative_volume": 4.0, "price_volume_corr": 0.6})
    selloff = score({"last_volume": 250.0, "volume_mean": 100.0, "return_1": -0.03, "relative_volume": 2.5, "price_volume_corr": 0.44})
    quiet = score({"last_volume": 80.0, "volume_mean": 100.0, "return_1": 0.02, "relative_volume": 0.8, "price_volume_corr": 0.5})
    assert ordinary.signal == 0.25 and ordinary.confidence == 0.25
    assert surge.signal == 0.75
    assert extreme.signal == 1.0
    assert selloff.signal == -0.75
    assert quiet.signal == 0.0
