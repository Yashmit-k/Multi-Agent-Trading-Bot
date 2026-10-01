"""Paper cycle. as_of is the latest stored candle end for the horizon timeframe.

Fees and slippage are zero until a cost model exists. Do not treat these fills as
evidence for live trading. Quantity stays 1 until position sizing exists.
order.created is not emitted. The stored order is FILLED.
The kill switch is a no-op until shadow or live.
"""

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from contracts.enums import Exchange, Horizon, OrderStatus, OrderType, RiskStatus, Side, Timeframe, TradingMode
from contracts.events import EventType, channel_for
from contracts.schemas.event import EventEnvelope
from contracts.schemas.execution import Execution
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from core_db.repository import CoreRepository
from core_decision import build_proposal, proposal_id_for
from core_fusion import fuse
from core_risk import assess

HORIZON_TIMEFRAME: dict[Horizon, Timeframe] = {
    Horizon.INTRADAY: Timeframe.M5,
    Horizon.SWING: Timeframe.D1,
    Horizon.LONG_TERM: Timeframe.D1,
}
# Placeholder until fee and slippage modeling exists.
FILL_FEES = Decimal("0")
FILL_SLIPPAGE = Decimal("0")
_DRAWDOWN_QUANTUM = Decimal("0.00000001")


class EventPublisher(Protocol):
    def publish(self, channel: str, payload: str) -> None:
        """Send one Redis message."""


def kill_switch() -> None:
    """No-op. Flattening and blocking new risk approvals arrive before shadow or live."""
    return None


def run_paper_cycle(
    repository: CoreRepository,
    publisher: EventPublisher,
    *,
    mode: TradingMode,
    starting_cash: Decimal,
    weights: dict | None = None,
) -> int:
    kill_switch()
    if not repository.paper_running():
        return 0
    written = 0
    for instrument in repository.list_instruments():
        for horizon, timeframe in HORIZON_TIMEFRAME.items():
            candle = repository.latest_candle(instrument.symbol, timeframe)
            if candle is None:
                continue
            as_of = candle.end.astimezone(timezone.utc)
            proposal_id = proposal_id_for(instrument.symbol, horizon, as_of)
            proposal = repository.get_proposal(proposal_id)
            if proposal is None:
                aggregate = fuse(repository.signals_for(instrument.symbol), horizon=horizon, as_of=as_of, weights=weights)
                if aggregate is None:
                    continue
                proposal = build_proposal(aggregate, candle, as_of)
                if proposal is None:
                    continue
                if repository.insert_proposal(proposal):
                    _publish(publisher, EventType.DECISION_CREATED, f"decision.created:{proposal.proposal_id}", as_of, proposal.proposal_id, proposal)
                    written += 1
            if repository.risk_for_proposal(proposal.proposal_id) is None:
                members = {item.symbol for item in repository.members_at(as_of)}
                decision = assess(
                    proposal,
                    mode=mode,
                    in_universe=proposal.symbol in members,
                    cash=repository.cash_balance(starting_cash),
                    held_quantity=repository.held_quantity(proposal.symbol),
                    timestamp=as_of,
                )
                if repository.insert_risk_decision(decision):
                    event_type = EventType.RISK_APPROVED if decision.status == RiskStatus.APPROVED else EventType.RISK_REJECTED
                    _publish(publisher, event_type, f"{event_type.value}:{decision.risk_decision_id}", as_of, proposal.proposal_id, decision)
            else:
                decision = repository.risk_for_proposal(proposal.proposal_id)
            if decision is None or decision.status != RiskStatus.APPROVED:
                continue
            if repository.order_for_proposal(proposal.proposal_id) is not None:
                continue
            _fill(repository, publisher, proposal_id=proposal.proposal_id, as_of=as_of, starting_cash=starting_cash)
    return written


def _fill(
    repository: CoreRepository,
    publisher: EventPublisher,
    *,
    proposal_id: str,
    as_of: datetime,
    starting_cash: Decimal,
) -> None:
    proposal = repository.get_proposal(proposal_id)
    if proposal is None:
        return
    instrument = repository.get_by_symbol(proposal.symbol)
    if instrument is None:
        raise KeyError(proposal.symbol)
    order_id = _digest("order", proposal.proposal_id)
    order = Order(
        order_id=order_id,
        client_order_id=order_id,
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        exchange=Exchange(instrument.exchange),
        side=proposal.side,
        order_type=OrderType.MARKET,
        quantity=proposal.quantity,
        limit_price=None,
        stop_price=None,
        trading_mode=TradingMode.PAPER,
        status=OrderStatus.FILLED,
        created_at=as_of,
        updated_at=as_of,
        metadata={"instant_fill": True, "skipped_states": "VALIDATED,SUBMITTED,OPEN"},
    )
    if not repository.insert_order(order):
        return
    execution = Execution(
        execution_id=_digest("execution", proposal.proposal_id),
        order_id=order.order_id,
        symbol=proposal.symbol,
        quantity=proposal.quantity,
        price=proposal.entry_price,
        executed_at=as_of,
        fees=FILL_FEES,
        slippage=FILL_SLIPPAGE,
        venue="PAPER",
        metadata={"fee_model": "placeholder_zero", "slippage_model": "placeholder_zero"},
    )
    repository.insert_execution(execution)
    position = _position_after(repository, proposal.symbol, proposal.side, proposal.quantity, proposal.entry_price, as_of)
    repository.save_position(position)
    snapshot = _snapshot(repository, as_of, starting_cash)
    repository.insert_snapshot(execution.execution_id, snapshot)
    _publish(publisher, EventType.ORDER_FILLED, f"order.filled:{execution.execution_id}", as_of, proposal.proposal_id, execution)
    _publish(publisher, EventType.POSITION_UPDATED, f"position.updated:{execution.execution_id}", as_of, proposal.proposal_id, position)
    _publish(publisher, EventType.PORTFOLIO_UPDATED, f"portfolio.updated:{execution.execution_id}", as_of, proposal.proposal_id, snapshot)


def _position_after(
    repository: CoreRepository,
    symbol: str,
    side: Side,
    quantity: int,
    price: Decimal,
    as_of: datetime,
) -> Position:
    current = repository.position_for(symbol)
    signed = quantity if side == Side.BUY else -quantity
    if current is None:
        opened_at = as_of
        average = price
        realized = Decimal("0")
        net_quantity = signed
    else:
        opened_at = current.opened_at
        realized = current.realized_pnl
        net_quantity = current.quantity + signed
        if side == Side.SELL:
            realized += (price - current.average_price) * quantity
            average = current.average_price if net_quantity != 0 else price
        elif current.quantity > 0:
            average = ((current.average_price * current.quantity) + (price * quantity)) / (current.quantity + quantity)
        else:
            average = price
    unrealized = (price - average) * net_quantity
    return Position(
        symbol=symbol,
        quantity=net_quantity,
        average_price=average,
        market_price=price,
        market_value=price * net_quantity,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        opened_at=opened_at,
        updated_at=as_of,
    )


def _snapshot(repository: CoreRepository, as_of: datetime, starting_cash: Decimal) -> PortfolioSnapshot:
    positions = repository.list_positions()
    market_value = sum((item.market_value for item in positions), Decimal("0"))
    realized = sum((item.realized_pnl for item in positions), Decimal("0"))
    unrealized = sum((item.unrealized_pnl for item in positions), Decimal("0"))
    cash = _cash_from_fills(repository, starting_cash)
    equity = cash + market_value
    peak = repository.note_peak_equity(equity)
    if peak <= 0:
        drawdown = Decimal("0")
    else:
        drawdown = ((peak - equity) / peak).quantize(_DRAWDOWN_QUANTUM)
        if drawdown < 0:
            drawdown = Decimal("0")
        if drawdown > 1:
            drawdown = Decimal("1")
    return PortfolioSnapshot(
        timestamp=as_of,
        cash=cash,
        equity=equity,
        market_value=market_value,
        gross_exposure=sum((abs(item.market_value) for item in positions), Decimal("0")),
        net_exposure=market_value,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=realized + unrealized,
        drawdown=drawdown,
    )


def _cash_from_fills(repository: CoreRepository, starting_cash: Decimal) -> Decimal:
    cash = starting_cash
    orders = {order.order_id: order for order in repository.list_orders()}
    for execution in repository.list_executions():
        order = orders[execution.order_id]
        notional = execution.price * execution.quantity
        if order.side == Side.BUY:
            cash -= notional + execution.fees
        else:
            cash += notional - execution.fees
    return cash


def _publish(publisher: EventPublisher, event_type: EventType, event_id: str, timestamp: datetime, correlation_id: str, payload: object) -> None:
    envelope = EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        source="paper-execution",
        correlation_id=correlation_id,
        payload=payload,  # type: ignore[arg-type]
    )
    publisher.publish(channel_for(event_type).value, envelope.model_dump_json())


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
