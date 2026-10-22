"""Trade-level risk checks: losses so far, the trade's own risk, price drift, re-entry, evidence quality."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from contracts.enums import TradingMode
from contracts.fixtures import sample_agent_signal
from core_paper.risk_inputs import is_fallback
from core_risk import assess
from core_risk.trade import TradeContext
from tests.test_portfolio_risk import _proposal

NOW = datetime(2026, 10, 21, 4, 30, tzinfo=timezone.utc)
CASH = Decimal("1000000")


def _ctx(**updates) -> TradeContext:
    base = {"now": NOW, "starting_cash": CASH, "equity": CASH, "start_of_day_equity": CASH, "peak_equity": CASH, "last_price": None}
    return TradeContext(**{**base, **updates})


def _failed(context: TradeContext, proposal=None) -> list[str]:
    decision = assess(proposal or _proposal(), mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=0, timestamp=NOW, trade=context)
    return [check.name for check in decision.checks if not check.passed]


def test_a_healthy_book_and_trade_pass_all_seven_checks() -> None:
    decision = assess(_proposal(), mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=0, timestamp=NOW, trade=_ctx())
    assert decision.status.value == "APPROVED"
    assert len(decision.checks) == 13 and decision.metadata["trade_checks"] is True


def test_daily_loss_and_drawdown_limits_stop_new_buys() -> None:
    assert _failed(_ctx(equity=CASH - Decimal("25000"))) == ["daily_loss_limit"]  # -2.5% today
    assert _failed(_ctx(equity=Decimal("880000"), start_of_day_equity=Decimal("880000"), peak_equity=CASH)) == ["drawdown_limit"]  # -12% from peak


def test_risk_per_trade_and_reward_to_risk() -> None:
    wide = _proposal().model_copy(update={"quantity": 200, "stop_loss": Decimal("900")})  # 200 x 100 = 20,000 = 2%
    assert "risk_per_trade" in _failed(_ctx(), wide)
    thin = _proposal().model_copy(update={"take_profit": _proposal().entry_price + Decimal("1")})
    assert _failed(_ctx(), thin) == ["reward_to_risk"]


def test_price_drift_and_stop_out_cooldown() -> None:
    entry = _proposal().entry_price
    assert _failed(_ctx(last_price=entry * Decimal("1.05"))) == ["price_drift"]
    assert _failed(_ctx(last_price=entry * Decimal("1.01"))) == []
    assert _failed(_ctx(last_stop_exit_at=NOW - timedelta(hours=3))) == ["stop_out_cooldown"]
    assert _failed(_ctx(last_stop_exit_at=NOW - timedelta(hours=30))) == []


def test_buys_resting_only_on_fallback_heuristics_are_blocked_unless_switched_off() -> None:
    assert _failed(_ctx(evidence_checked=True, evidence_fallback_only=True)) == ["evidence_quality"]
    assert _failed(_ctx(evidence_checked=True, evidence_fallback_only=True, block_fallback_evidence=False)) == []
    assert _failed(_ctx(evidence_checked=False, evidence_fallback_only=False)) == []


def test_fallback_detection() -> None:
    signal = sample_agent_signal("INFY")
    assert not is_fallback(signal)
    assert is_fallback(signal.model_copy(update={"reason_codes": ["fixture.heuristic"]}))
    assert is_fallback(signal.model_copy(update={"metadata": {"llm": [{"model": "fixture", "fallback": False}]}}))
    assert not is_fallback(signal.model_copy(update={"metadata": {"llm": [{"model": "gemini-3.1-flash-lite", "fallback": False}]}}))


def test_sells_skip_trade_checks() -> None:
    from contracts.enums import Side

    sell = _proposal(side=Side.SELL)
    decision = assess(sell, mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=19, timestamp=NOW, trade=_ctx(equity=Decimal("1")))
    assert decision.status.value == "APPROVED" and len(decision.checks) == 6


def test_the_cycle_rejects_a_buy_backed_only_by_a_fallback_opinion(repository) -> None:
    from contracts.enums import Horizon, RiskStatus, Side
    from contracts.fixtures import FIXTURE_AS_OF, candles_for
    from core_ingestion.service import MemoryEventPublisher, ingest_signal
    from core_paper import run_paper_cycle

    repository.upsert_candles(list(candles_for("RELIANCE")))
    repository.open_paper_session(CASH)
    heuristic = sample_agent_signal("RELIANCE").model_copy(
        update={"signal_id": "sig-fallback", "horizon": Horizon.SWING, "signal": 0.9, "confidence": 0.9, "reason_codes": ["fixture.heuristic"],
                "timestamp": FIXTURE_AS_OF, "as_of": FIXTURE_AS_OF, "valid_until": FIXTURE_AS_OF + timedelta(hours=6)}
    )
    ingest_signal(repository, MemoryEventPublisher(), heuristic, mode=TradingMode.BACKTEST, now=FIXTURE_AS_OF, replay_as_of=FIXTURE_AS_OF, skew_seconds=5)
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH, now=FIXTURE_AS_OF, enforce_entry_window=False)
    [proposal] = [item for item in repository.list_proposals() if item.side == Side.BUY]
    decision = repository.risk_for_proposal(proposal.proposal_id)
    assert decision.status == RiskStatus.REJECTED
    assert [check.name for check in decision.checks if not check.passed] == ["evidence_quality"]
    assert [order for order in repository.list_orders() if order.side == Side.BUY] == []
