"""Paper cycle. as_of is the latest stored candle end for the horizon timeframe.

A market decision on candle t stays open until a later stored bar exists, then
fills at that bar's open. Stops use the same same-bar rule as the backtester.
When no cost schedule is passed, the research cost is 2 bp. It is never zero
unless the caller sets that schedule explicitly.
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
from core_paper.costs import CostSchedule, fee_on, slipped_price
from core_risk import assess

HORIZON_TIMEFRAME: dict[Horizon, Timeframe] = {
    Horizon.INTRADAY: Timeframe.M5,
    Horizon.SWING: Timeframe.D1,
    Horizon.LONG_TERM: Timeframe.D1,
}
_DRAWDOWN_QUANTUM = Decimal("0.00000001")
_CENT = Decimal("0.01")
MAX_NOTIONAL = Decimal("100000")


class EventPublisher(Protocol):
    def publish(self, channel: str, payload: str) -> None:
        """Send one Redis message."""


def kill_switch(repository: CoreRepository | None = None, *, armed: bool = True) -> bool:
    """Arm or clear the kill flag. Flattening happens on the next paper cycle."""
    if repository is None:
        return False
    return repository.set_kill_switch(armed)


def paper_schedule(schedule: CostSchedule | None) -> CostSchedule:
    """Use the caller's schedule. The unconfigured default is 2 bp, never zero."""
    if schedule is not None:
        return schedule
    return CostSchedule.research(Decimal("2"), Decimal("0"))


def run_paper_cycle(
    repository: CoreRepository,
    publisher: EventPublisher,
    *,
    mode: TradingMode,
    starting_cash: Decimal,
    weights: dict | None = None,
    schedule: CostSchedule | None = None,
) -> int:
    if not repository.paper_running():
        return 0
    costs = paper_schedule(schedule)
    _settle_open_orders(repository, publisher, costs, starting_cash)
    _monitor_brackets(repository, publisher, costs, starting_cash, mode)
    _settle_open_orders(repository, publisher, costs, starting_cash)
    if repository.kill_switch_armed():
        _queue_flattens(repository, publisher, costs, starting_cash, mode)
        _settle_open_orders(repository, publisher, costs, starting_cash)
        return 0
    written = 0
    for instrument in repository.list_instruments():
        for horizon, timeframe in HORIZON_TIMEFRAME.items():
            candle = repository.latest_candle(instrument.symbol, timeframe)
            if candle is None or repository.held_quantity(instrument.symbol) > 0:
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
                proposal = _sized(proposal, repository.cash_balance(starting_cash), costs)
                proposal = proposal.model_copy(update={"metadata": {**proposal.metadata, "stops_monitored": True, "same_bar_exit": "stop_first"}})
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
            _queue(repository, proposal, as_of, reason="entry", fill_at="next_open")
    _settle_open_orders(repository, publisher, costs, starting_cash)
    return written


def _sized(proposal, cash: Decimal, schedule: CostSchedule):
    from core_paper.backtest import _shares

    if proposal.side != Side.BUY:
        return proposal
    quantity = _shares(cash, proposal.entry_price, MAX_NOTIONAL, schedule)
    if quantity < 1:
        return proposal
    return proposal.model_copy(
        update={"quantity": quantity, "metadata": {**proposal.metadata, "quantity_model": "cash_and_notional_cap"}}
    )


def _queue(repository: CoreRepository, proposal, as_of: datetime, *, reason: str, fill_at: str, raw_price: Decimal | None = None) -> None:
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
        status=OrderStatus.OPEN,
        created_at=as_of,
        updated_at=as_of,
        metadata={
            "reason": reason,
            "fill_at": fill_at,
            "decision_end": as_of.isoformat(),
            "same_bar_exit": "stop_first",
            "level_price": None if raw_price is None else str(raw_price),
        },
    )
    repository.insert_order(order)


def _settle_open_orders(repository: CoreRepository, publisher: EventPublisher, schedule: CostSchedule, starting_cash: Decimal) -> None:
    for order in repository.list_orders():
        if order.status != OrderStatus.OPEN:
            continue
        proposal = repository.get_proposal(order.proposal_id)
        if proposal is None:
            continue
        decision_end = datetime.fromisoformat(str(order.metadata["decision_end"]))
        if order.metadata.get("fill_at") == "level" and order.metadata.get("level_price"):
            _execute(repository, publisher, order, proposal, Decimal(str(order.metadata["level_price"])), decision_end, schedule, starting_cash)
            continue
        nxt = _next_bar(repository, order.symbol, _timeframe_for(proposal), decision_end)
        if nxt is None:
            continue
        raw = nxt.open
        _execute(repository, publisher, order, proposal, raw, nxt.end, schedule, starting_cash)


def _monitor_brackets(repository, publisher, schedule, starting_cash, mode: TradingMode) -> None:
    from core_paper.backtest import exit_on_bar

    for position in repository.list_positions():
        if position.quantity <= 0:
            continue
        entry = _entry_execution(repository, position.symbol)
        if entry is None:
            continue
        stop = Decimal(str(entry.metadata["stop_loss"]))
        target = Decimal(str(entry.metadata["take_profit"]))
        opened = datetime.fromisoformat(str(entry.metadata["decision_end"]))
        bar = repository.latest_candle(position.symbol, _timeframe_for_symbol(repository, position.symbol))
        if bar is None or bar.end.astimezone(timezone.utc) <= opened:
            continue
        reason = exit_on_bar(Side.BUY, stop, target, bar)
        if reason is None:
            continue
        price = stop if reason == "stop" else target
        _exit_proposal(repository, publisher, position, price, bar.end, reason, schedule, starting_cash, mode, fill_at="level")


def _queue_flattens(repository, publisher, schedule, starting_cash, mode: TradingMode) -> None:
    for position in list(repository.list_positions()):
        if position.quantity <= 0:
            continue
        bar = repository.latest_candle(position.symbol, _timeframe_for_symbol(repository, position.symbol))
        if bar is None:
            continue
        _exit_proposal(
            repository,
            publisher,
            position,
            bar.open,
            bar.end,
            "kill_switch",
            schedule,
            starting_cash,
            mode,
            fill_at="next_open",
        )


def _exit_proposal(repository, publisher, position, price, as_of, reason, schedule, starting_cash, mode, *, fill_at: str) -> None:
    from contracts.schemas.trade_proposal import TradeProposal

    moment = as_of.astimezone(timezone.utc)
    proposal_id = _digest("exit", f"{position.symbol}|{reason}|{moment.isoformat()}")
    if repository.order_for_proposal(proposal_id) is not None:
        return
    proposal = TradeProposal(
        proposal_id=proposal_id,
        symbol=position.symbol,
        timestamp=moment,
        horizon=Horizon.SWING,
        side=Side.SELL,
        quantity=position.quantity,
        entry_price=price,
        stop_loss=(price * Decimal("1.02")).quantize(_CENT),
        take_profit=(price * Decimal("0.96")).quantize(_CENT),
        strategy_id="paper-fusion",
        strategy_version="1.0.0",
        aggregated_signal=-1,
        aggregated_confidence=1,
        supporting_signal_ids=[proposal_id],
        metadata={"reason": reason, "stops_monitored": True, "same_bar_exit": "stop_first"},
    )
    repository.insert_proposal(proposal)
    decision = assess(
        proposal,
        mode=mode,
        in_universe=True,
        cash=repository.cash_balance(starting_cash),
        held_quantity=position.quantity,
        timestamp=moment,
    )
    repository.insert_risk_decision(decision)
    if decision.status != RiskStatus.APPROVED:
        return
    _queue(repository, proposal, moment, reason=reason, fill_at=fill_at, raw_price=price)


def _execute(repository, publisher, order: Order, proposal, raw: Decimal, stamp: datetime, schedule: CostSchedule, starting_cash: Decimal) -> None:
    fill = slipped_price(order.side, raw, schedule.slippage_bps).quantize(_CENT)
    notional = fill * order.quantity
    fees = fee_on(notional, schedule).quantize(_CENT)
    slip = (abs(fill - raw) * order.quantity).quantize(_CENT)
    if order.side == Side.BUY and notional + fees > repository.cash_balance(starting_cash):
        return
    filled = order.model_copy(update={"status": OrderStatus.FILLED, "updated_at": stamp})
    repository.save_order(filled)
    execution = Execution(
        execution_id=_digest("execution", proposal.proposal_id),
        order_id=order.order_id,
        symbol=order.symbol,
        quantity=order.quantity,
        price=fill,
        executed_at=stamp,
        fees=fees,
        slippage=slip,
        venue="PAPER",
        metadata={
            "gross_price": str(raw),
            "net_price": str(fill),
            "fees": str(fees),
            "slippage": str(slip),
            "stop_loss": str(proposal.stop_loss),
            "take_profit": str(proposal.take_profit),
            "decision_end": stamp.isoformat(),
            "same_bar_exit": "stop_first",
            "reason": order.metadata.get("reason", "entry"),
        },
    )
    repository.insert_execution(execution)
    current = repository.position_for(order.symbol)
    updated = next_position(current, order.symbol, order.side, order.quantity, fill, stamp)
    if updated.quantity == 0:
        repository.clear_position(order.symbol)
    else:
        repository.save_position(updated)
    snapshot = _snapshot(repository, stamp, starting_cash)
    repository.insert_snapshot(execution.execution_id, snapshot)
    _publish(publisher, EventType.ORDER_FILLED, f"order.filled:{execution.execution_id}", stamp, proposal.proposal_id, execution)


def _next_bar(repository: CoreRepository, symbol: str, timeframe: Timeframe, decision_end: datetime):
    moment = decision_end.astimezone(timezone.utc)
    later = [bar for bar in repository.stored_candles(symbol, timeframe) if bar.end.astimezone(timezone.utc) > moment]
    later.sort(key=lambda bar: bar.end)
    return later[0] if later else None


def _timeframe_for(proposal) -> Timeframe:
    return HORIZON_TIMEFRAME.get(proposal.horizon, Timeframe.D1)


def _timeframe_for_symbol(repository: CoreRepository, symbol: str) -> Timeframe:
    for timeframe in (Timeframe.M5, Timeframe.D1):
        if repository.latest_candle(symbol, timeframe) is not None:
            return timeframe
    return Timeframe.D1


def _entry_execution(repository: CoreRepository, symbol: str):
    rows = [item for item in repository.list_executions() if item.symbol == symbol and item.metadata.get("reason") == "entry"]
    return rows[-1] if rows else None


def next_position(
    current: Position | None,
    symbol: str,
    side: Side,
    quantity: int,
    price: Decimal,
    as_of: datetime,
) -> Position:
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


def _position_after(
    repository: CoreRepository,
    symbol: str,
    side: Side,
    quantity: int,
    price: Decimal,
    as_of: datetime,
) -> Position:
    return next_position(repository.position_for(symbol), symbol, side, quantity, price, as_of)


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
