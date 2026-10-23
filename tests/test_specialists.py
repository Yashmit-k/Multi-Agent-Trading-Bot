"""Specialist decision mode: each agent has one job in a swing BUY (core_decision.specialists)."""

from datetime import timedelta
from decimal import Decimal

from contracts.enums import AgentName, Horizon, Side, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for, sample_agent_signal
from core_db.repository import CoreRepository
from core_decision.specialists import decide
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_paper import run_paper_cycle
from core_risk.settings import SettingsError, parse_settings

CASH = Decimal("1000000")
RISK_OFF = [{"name": "risk_tilt", "value": -1, "weight": 1.0}, {"name": "index_trend", "value": -1, "weight": 1.0}, {"name": "fear_gauge", "value": -1, "weight": 1.0}]


def _sig(agent: AgentName, score: float, *, confidence: float = 0.8, symbol: str = "RELIANCE", fallback: bool = False, votes=None):
    metadata: dict = {}
    reasons = [f"{agent.value}.evaluated"]
    if fallback:
        metadata["llm"] = [{"model": "fixture", "fallback": True}]
        reasons = ["fixture.heuristic"]
    if votes is not None:
        metadata["votes"] = votes
    return sample_agent_signal(symbol).model_copy(
        update={
            "signal_id": f"sig-{symbol}-{agent.value}-{score}-{fallback}",
            "agent_name": agent,
            "horizon": Horizon.SWING,
            "signal": score,
            "confidence": confidence,
            "timestamp": FIXTURE_AS_OF,
            "as_of": FIXTURE_AS_OF,
            "valid_until": FIXTURE_AS_OF + timedelta(hours=6),
            "reason_codes": reasons,
            "metadata": metadata,
        }
    )


def _outcomes(decision) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {item["agent"]: item["outcome"] for item in decision.verdicts}


def test_a_trigger_with_no_objection_buys_and_every_agent_has_a_verdict() -> None:
    signals = [
        _sig(AgentName.TECHNICAL, 0.5),
        _sig(AgentName.MOMENTUM, 0.1),
        _sig(AgentName.VOLUME, 0.2),
        _sig(AgentName.MEAN_REVERSION, 0.0),
        _sig(AgentName.NEWS, 0.3),
        _sig(AgentName.EARNINGS, 0.0),
        _sig(AgentName.FUNDAMENTAL, -0.6),
        _sig(AgentName.VALUATION, 0.2),
        _sig(AgentName.REGIME, 0.3),
    ]
    decision = decide(signals, as_of=FIXTURE_AS_OF)
    assert decision.buy and decision.size_fraction == 1.0
    assert decision.signal == 0.5 and decision.supporting_signal_ids[0] == signals[0].signal_id
    outcomes = _outcomes(decision)
    assert set(outcomes) == {"technical", "momentum", "volume", "mean_reversion", "news", "earnings", "fundamental", "valuation", "regime"}
    assert outcomes["technical"] == "trigger" and outcomes["fundamental"] == "pass"  # one weak quality view does not block


def test_no_trigger_means_no_buy() -> None:
    decision = decide([_sig(AgentName.TECHNICAL, 0.29), _sig(AgentName.MOMENTUM, 0.9, confidence=0.3)], as_of=FIXTURE_AS_OF)
    assert not decision.buy


def test_each_specialist_can_block() -> None:
    trigger = _sig(AgentName.MOMENTUM, 0.6)
    for blocker in (
        _sig(AgentName.VOLUME, -0.3),
        _sig(AgentName.MEAN_REVERSION, -0.5),
        _sig(AgentName.NEWS, -0.4, confidence=0.3),
        _sig(AgentName.EARNINGS, -0.3, confidence=0.5),
    ):
        decision = decide([trigger, blocker], as_of=FIXTURE_AS_OF)
        assert not decision.buy, blocker.agent_name
        assert _outcomes(decision)[blocker.agent_name.value] == "block"
    both = decide([trigger, _sig(AgentName.FUNDAMENTAL, -0.5), _sig(AgentName.VALUATION, -0.7)], as_of=FIXTURE_AS_OF)
    assert not both.buy
    weak_news = decide([trigger, _sig(AgentName.NEWS, -0.9, confidence=0.2)], as_of=FIXTURE_AS_OF)
    assert weak_news.buy  # bad news needs confidence >= 0.3 to block


def test_fallback_opinions_are_ignored_not_trusted() -> None:
    trigger = _sig(AgentName.TECHNICAL, 0.6)
    decision = decide([trigger, _sig(AgentName.NEWS, -0.9, fallback=True), _sig(AgentName.FUNDAMENTAL, -0.9, fallback=True), _sig(AgentName.VALUATION, -0.9)], as_of=FIXTURE_AS_OF)
    assert decision.buy
    assert _outcomes(decision)["news"] == "ignored_fallback" and _outcomes(decision)["fundamental"] == "ignored_fallback"
    assert _outcomes(decision)["valuation"] == "pass"  # alone it cannot block: the rule needs both


def test_a_risk_off_market_halves_the_size_but_never_blocks() -> None:
    decision = decide([_sig(AgentName.TECHNICAL, 0.6), _sig(AgentName.REGIME, -1.0, votes=RISK_OFF)], as_of=FIXTURE_AS_OF)
    assert decision.buy and decision.size_fraction == 0.5 and _outcomes(decision)["regime"] == "size"


def test_decision_mode_is_a_bounded_setting() -> None:
    assert parse_settings({}).decision_mode == "fusion"
    assert parse_settings({"decision_mode": "specialists"}).decision_mode == "specialists"
    try:
        parse_settings({"decision_mode": "vote"})
    except SettingsError as exc:
        assert "decision_mode" in exc.errors
    else:
        raise AssertionError("an unknown decision_mode was accepted")


# --- the paper cycle ------------------------------------------------------------------------------


def _ingest(repository: CoreRepository, signal) -> None:  # type: ignore[no-untyped-def]
    ingest_signal(repository, MemoryEventPublisher(), signal, mode=TradingMode.BACKTEST, now=FIXTURE_AS_OF, replay_as_of=FIXTURE_AS_OF, skew_seconds=5)


def _book(repository: CoreRepository, mode: str = "specialists") -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    repository.open_paper_session(CASH)
    repository.save_setting("risk", {"decision_mode": mode}, updated_by="test", now=FIXTURE_AS_OF)


def _cycle(repository: CoreRepository) -> None:
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH, now=FIXTURE_AS_OF, enforce_entry_window=False)


def _buy_proposals(repository: CoreRepository):  # type: ignore[no-untyped-def]
    return [item for item in repository.list_proposals() if item.side == Side.BUY]


def test_specialists_mode_buys_on_a_trigger_the_average_would_ignore(repository: CoreRepository) -> None:
    _book(repository)
    _ingest(repository, _sig(AgentName.TECHNICAL, 0.3))  # fusion: weight-1 average 0.3 is below the 0.35 entry bar
    _cycle(repository)
    proposals = _buy_proposals(repository)
    assert len(proposals) == 1
    meta = proposals[0].metadata
    assert meta["decision_mode"] == "specialists" and meta["size_fraction"] == 1.0
    assert {item["agent"] for item in meta["specialists"]} >= {"technical", "news", "regime"}
    assert [order.side for order in repository.list_orders()] == [Side.BUY]


def test_specialists_mode_respects_a_block_and_fusion_mode_is_unchanged(repository: CoreRepository) -> None:
    _book(repository)
    _ingest(repository, _sig(AgentName.TECHNICAL, 0.6))
    _ingest(repository, _sig(AgentName.NEWS, -0.8, confidence=0.5))
    _cycle(repository)
    assert _buy_proposals(repository) == []  # news blocked it


def test_fusion_mode_ignores_the_specialist_rules(repository: CoreRepository) -> None:
    _book(repository, mode="fusion")
    _ingest(repository, _sig(AgentName.TECHNICAL, 0.3))
    _cycle(repository)
    assert _buy_proposals(repository) == []  # 0.3 < the 0.35 fused entry bar, as before


def test_risk_off_halves_the_order_quantity(repository: CoreRepository) -> None:
    _book(repository)
    _ingest(repository, _sig(AgentName.TECHNICAL, 0.6))
    _ingest(repository, _sig(AgentName.REGIME, -1.0, votes=RISK_OFF))
    _cycle(repository)
    full = int(Decimal("20000") // _buy_proposals(repository)[0].entry_price)
    orders = [order for order in repository.list_orders() if order.side == Side.BUY]
    assert len(orders) == 1 and orders[0].quantity <= max(1, full // 2)


def test_a_no_model_answer_is_ignored_like_the_old_fallback() -> None:
    unavailable = _sig(AgentName.NEWS, 0.0).model_copy(update={"signal_id": "sig-news-unavailable", "reason_codes": ["llm_unavailable"], "metadata": {"llm": [{"model": "none", "fallback": True}]}})
    decision = decide([_sig(AgentName.TECHNICAL, 0.6), unavailable], as_of=FIXTURE_AS_OF)
    assert decision.buy and _outcomes(decision)["news"] == "ignored_fallback"
