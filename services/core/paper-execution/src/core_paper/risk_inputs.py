"""Builds the risk engine's TradeContext for a new BUY from the paper book and the market."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Side, Timeframe
from contracts.schemas.agent_signal import AgentSignal
from core_db.repository import CoreRepository
from core_risk.trade import TradeContext

STOP_REASONS = {"stop", "strategy_stop", "strategy_trailing_stop"}


def is_fallback(signal: AgentSignal) -> bool:
    """An LLM agent's opinion produced by its fixed heuristic instead of the model."""
    if {"fixture.heuristic", "llm_unavailable"} & set(signal.reason_codes):
        return True
    llm = signal.metadata.get("llm")
    return isinstance(llm, list) and bool(llm) and all(isinstance(item, dict) and (item.get("fallback") or item.get("model") == "fixture") for item in llm)


def _price(repository: CoreRepository, symbol: str) -> Decimal | None:
    candle = repository.latest_candle(symbol, Timeframe.M5) or repository.latest_candle(symbol, Timeframe.D1)
    return None if candle is None else candle.close


def _evidence(repository: CoreRepository, proposal) -> tuple[bool, bool]:
    """(checked, fallback_only). A fallback opinion counts as verified when the same agent later published a real one."""
    signals = repository.signals_for(proposal.symbol)
    by_id = {item.signal_id: item for item in signals}
    supporting = [by_id[sid] for sid in proposal.supporting_signal_ids if sid in by_id]
    if not supporting:
        return False, False
    for item in supporting:
        if not is_fallback(item):
            return True, False
        verified = any(
            other.agent_name == item.agent_name and other.horizon == item.horizon and other.timestamp > item.timestamp and not is_fallback(other)
            for other in signals
        )
        if verified:
            return True, False
    return True, True


def trade_context(repository: CoreRepository, proposal, *, starting_cash: Decimal, now: datetime, settings) -> TradeContext:  # type: ignore[no-untyped-def]
    marked = sum(((_price(repository, item.symbol) or item.average_price) * item.quantity for item in repository.list_positions() if item.quantity > 0), Decimal("0"))
    equity = repository.cash_balance(starting_cash) + marked
    book = repository.active_paper_session()
    history = repository.list_daily_equity(book.session_id) if book is not None else []
    closes = [Decimal(str(row["equity"])) for row in history if row.get("equity") is not None]
    start_of_day = closes[-1] if closes else starting_cash
    peak = max([starting_cash, equity, *closes])
    executions = {item.order_id: item for item in repository.list_executions()}
    stops = [
        executions[order.order_id].executed_at.astimezone(timezone.utc)
        for order in repository.list_orders()
        if order.symbol == proposal.symbol and order.side == Side.SELL and order.metadata.get("reason") in STOP_REASONS and order.order_id in executions
    ]
    checked, fallback_only = _evidence(repository, proposal)
    return TradeContext(
        now=now.astimezone(timezone.utc),
        starting_cash=starting_cash,
        equity=equity,
        start_of_day_equity=start_of_day,
        peak_equity=peak,
        last_price=_price(repository, proposal.symbol),
        last_stop_exit_at=max(stops) if stops else None,
        evidence_checked=checked,
        evidence_fallback_only=fallback_only,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_drawdown_pct=settings.max_drawdown_pct,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        min_reward_risk=settings.min_reward_risk,
        max_price_drift_pct=settings.max_price_drift_pct,
        stop_cooldown_hours=settings.stop_cooldown_hours,
        block_fallback_evidence=settings.block_fallback_evidence,
    )
