"""Manual paper orders placed by the operator from the UI.

A manual order goes through the same path as an agent order: a TradeProposal (strategy
"manual"), the same risk checks, then the same CNC limit entry or next-open exit. The operator
may override the portfolio limits (positions, sector, exposure, per stock, entries per day) but
never the order checks: PAPER mode, universe, cash, the per-order cap and no shorting.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Horizon, RiskStatus, Side, Timeframe, TradingMode
from contracts.events import EventType
from contracts.schemas.trade_proposal import TradeProposal
from core_db.repository import CoreRepository
from core_ingestion.service import EventPublisher
from core_paper.cycle import _CENT, _order_event, _publish, _queue, load_risk_settings, portfolio_context
from core_paper.execute import queue_entry
from core_risk import assess

MANUAL_STRATEGY = "manual"


class ManualOrderRejected(ValueError):
    def __init__(self, code: str, detail: object = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def place_manual_order(
    repository: CoreRepository,
    publisher: EventPublisher,
    *,
    symbol: str,
    side: Side,
    quantity: int | None,
    limit_price: Decimal | None,
    override_limits: bool,
    operator: str,
    note: str,
    now: datetime,
) -> dict[str, object]:
    book = repository.active_paper_session()
    if book is None or book.starting_cash is None:
        raise ManualOrderRejected("no_active_paper_session")
    symbol = symbol.strip().upper()
    if repository.get_by_symbol(symbol) is None:
        raise ManualOrderRejected("unknown_symbol")
    if quantity is not None and quantity < 1:
        raise ManualOrderRejected("quantity_must_be_positive")
    bar = repository.latest_candle(symbol, Timeframe.M5)
    if bar is None:
        raise ManualOrderRejected("no_price")
    as_of = bar.end.astimezone(timezone.utc)
    held = repository.held_quantity(symbol)
    settings = load_risk_settings(repository)
    if side == Side.SELL:
        if held <= 0:
            raise ManualOrderRejected("not_held")
        quantity = held if quantity is None else quantity
    elif quantity is None:
        quantity = max(1, int(settings.max_order_notional // bar.close))
    price = bar.close
    digest = hashlib.sha256(f"{book.session_id}|{symbol}|{side.value}|{now.isoformat()}|{operator}".encode()).hexdigest()[:24]
    proposal_id = f"manual-{digest}"
    stop_pct, target_pct = settings.stop_loss_pct / 100, settings.take_profit_pct / 100
    if side == Side.BUY:
        stop, target = price * (1 - stop_pct), price * (1 + target_pct)
    else:
        stop, target = price * Decimal("1.02"), price * Decimal("0.96")
    proposal = TradeProposal(
        proposal_id=proposal_id,
        symbol=symbol,
        timestamp=as_of,
        horizon=Horizon.INTRADAY,
        side=side,
        quantity=quantity,
        entry_price=price,
        stop_loss=stop.quantize(_CENT),
        take_profit=target.quantize(_CENT),
        strategy_id=MANUAL_STRATEGY,
        strategy_version="1.0.0",
        aggregated_signal=1 if side == Side.BUY else -1,
        aggregated_confidence=1,
        supporting_signal_ids=[proposal_id],
        metadata={
            "source": "manual",
            "operator": operator,
            "note": note[:200],
            "override_limits": override_limits,
            "requested_limit": None if limit_price is None else str(limit_price),
            "stops_monitored": True,
            "same_bar_exit": "stop_first",
            "decided_at": now.isoformat(),
        },
    )
    members = {item.symbol for item in repository.members_at(as_of)}
    decision = assess(
        proposal,
        mode=TradingMode.PAPER,
        in_universe=symbol in members,
        cash=repository.available_cash(book.starting_cash),
        held_quantity=held,
        timestamp=as_of,
        max_notional=settings.max_order_notional,
        portfolio=None if override_limits else portfolio_context(repository, book.starting_cash, now, settings),
    )
    repository.insert_proposal(proposal)
    _publish(publisher, EventType.DECISION_CREATED, f"decision.created:{proposal_id}", as_of, proposal_id, proposal)
    repository.insert_risk_decision(decision)
    event_type = EventType.RISK_APPROVED if decision.status == RiskStatus.APPROVED else EventType.RISK_REJECTED
    _publish(publisher, event_type, f"{event_type.value}:{decision.risk_decision_id}", as_of, proposal_id, decision)
    result: dict[str, object] = {
        "proposal": proposal.model_dump(mode="json"),
        "risk": decision.model_dump(mode="json"),
        "order": None,
    }
    if decision.status != RiskStatus.APPROVED:
        return result
    if side == Side.SELL:
        _queue(repository, proposal, as_of, reason="manual", fill_at="next_open")
        order = repository.order_for_proposal(proposal_id)
    else:
        order = queue_entry(
            repository,
            proposal,
            as_of,
            placed_at=now,
            cap=settings.max_order_notional,
            daily_limit=10_000 if override_limits else settings.daily_entry_limit,
            limit_override=limit_price,
            quantity_limit=quantity,
        )
    if order is not None:
        kind = _order_event(order)
        _publish(publisher, kind, f"{kind.value}:{order.order_id}", as_of, proposal_id, order)
        result["order"] = order.model_dump(mode="json")
    return result
