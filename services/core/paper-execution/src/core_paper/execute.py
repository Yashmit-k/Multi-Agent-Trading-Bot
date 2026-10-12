"""Session-aware CNC entry and exit settlement.

Legacy orders without ``policy_version`` are ignored. Cash for a new BUY is
reserved in the same transaction as the order. A fill converts that reservation
once. Expiry, rejection, and cancellation release it once.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from contracts.enums import Exchange, OrderStatus, OrderType, Side, Timeframe, TradingMode
from contracts.schemas.execution import Execution
from contracts.schemas.market import Candle
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from core_db.repository import CoreRepository
from core_paper.charges import (
    ZERODHA_EQUITY_RI,
    EquityChargeSchedule,
    delivery_buy,
    delivery_sell,
    intraday_sell,
    reclassified_buy,
    require_schedule,
    reservation_buy,
)
from core_paper.limits import (
    FILL_MODEL,
    POLICY_VERSION,
    PRODUCT_CNC,
    REFERENCE_RULE,
    SELL_POLICY_VERSION,
    buy_limit,
    limit_fill_price,
)
from core_paper.trading_calendar import IST, CalendarUnverified, assign_entry_window, expected_bar_starts

_DRAWDOWN_QUANTUM = Decimal("0.00000001")
MAX_NOTIONAL = Decimal("100000")


def affordable_quantity(cash: Decimal, limit: Decimal, schedule: EquityChargeSchedule, cap: Decimal = MAX_NOTIONAL) -> int:
    require_schedule(schedule)
    if limit <= 0 or cash <= 0:
        return 0
    quantity = int((cap / limit).to_integral_value(rounding=ROUND_DOWN))
    while quantity >= 1:
        notional = limit * quantity
        fees = delivery_buy(notional, schedule, ceiling=True).total
        if notional + fees <= cap and notional + fees <= cash:
            return quantity
        quantity -= 1
    return 0


def queue_entry(
    repository: CoreRepository,
    proposal,
    as_of: datetime,
    *,
    schedule: EquityChargeSchedule = ZERODHA_EQUITY_RI,
    cap: Decimal = MAX_NOTIONAL,
) -> Order | None:
    """Create one CNC limit order, or a rejected order when the policy cannot be applied."""
    if proposal.side != Side.BUY:
        return None
    if repository.order_for_proposal(proposal.proposal_id) is not None:
        return repository.order_for_proposal(proposal.proposal_id)
    instrument = repository.get_by_symbol(proposal.symbol)
    if instrument is None:
        raise KeyError(proposal.symbol)
    reason = _entry_block(repository, proposal, as_of, instrument.tick_size, schedule, cap)
    if reason is not None:
        order = _order(repository, proposal, as_of, instrument, status=OrderStatus.REJECTED, limit=None, metadata={"reason": reason, "product_type": PRODUCT_CNC})
        repository.commit_policy_order(order, None)
        return order
    daily, candle_id = repository.completed_daily(proposal.symbol, as_of)  # type: ignore[misc]
    window = assign_entry_window(as_of)
    limit = buy_limit(daily.close, instrument.tick_size)
    cash = repository.available_cash(repository.active_paper_session().starting_cash)  # type: ignore[union-attr]
    quantity = affordable_quantity(cash, limit, schedule, cap)
    if quantity < 1:
        order = _order(
            repository,
            proposal,
            as_of,
            instrument,
            status=OrderStatus.REJECTED,
            limit=limit,
            metadata={"reason": "quantity_below_one", "product_type": PRODUCT_CNC, "policy_version": POLICY_VERSION},
        )
        repository.commit_policy_order(order, None)
        return order
    reserve = reservation_buy(limit * quantity, schedule)
    metadata = {
        "reason": "entry",
        "product_type": PRODUCT_CNC,
        "policy_version": POLICY_VERSION,
        "reference_rule": REFERENCE_RULE,
        "reference_price": str(daily.close),
        "reference_candle_end": daily.end.astimezone(timezone.utc).isoformat(),
        "reference_candle_id": candle_id,
        "max_entry_premium_bps": "25",
        "tick_size": str(instrument.tick_size),
        "activation_at": as_of.astimezone(timezone.utc).isoformat(),
        "entry_window_start": window.entry_start_at.astimezone(timezone.utc).isoformat(),
        "entry_window_end": window.expiry_at.astimezone(timezone.utc).isoformat(),
        "entry_session_date": window.session_date.isoformat(),
        "calendar_version": window.calendar_version,
        "calendar_source": window.source,
        "charge_version": schedule.version,
        "fill_model": FILL_MODEL,
        "reserved_amount": str(reserve),
        "decision_end": as_of.astimezone(timezone.utc).isoformat(),
        "evaluated_bars": [],
        "stop_loss": str(proposal.stop_loss),
        "take_profit": str(proposal.take_profit),
    }
    sized = proposal.model_copy(update={"quantity": quantity})
    order = _order(repository, sized, as_of, instrument, status=OrderStatus.OPEN, limit=limit, metadata=metadata, quantity=quantity)
    repository.commit_policy_order(order, reserve)
    return order


def settle_entries(
    repository: CoreRepository,
    *,
    starting_cash: Decimal,
    now: datetime,
    schedule: EquityChargeSchedule = ZERODHA_EQUITY_RI,
) -> list[str]:
    """Settle CNC entry orders. Open orders without a policy version are reported and not filled."""
    review: list[str] = []
    for order in list(repository.list_orders()):
        if order.status != OrderStatus.OPEN:
            continue
        if legacy_review_required(order):
            review.append(order.order_id)
            continue
        if order.metadata.get("policy_version") != POLICY_VERSION or order.metadata.get("product_type") != PRODUCT_CNC:
            continue
        _settle_one(repository, order, starting_cash=starting_cash, now=now, schedule=schedule)
    return review


def legacy_review_required(order: Order) -> bool:
    """An open order that predates the CNC policy must be reviewed before it can do anything."""
    if order.status != OrderStatus.OPEN:
        return False
    return order.metadata.get("policy_version") not in {POLICY_VERSION, SELL_POLICY_VERSION}


def _entry_block(repository, proposal, as_of, tick, schedule, cap) -> str | None:
    try:
        require_schedule(schedule)
    except Exception:
        return "charge_config_missing"
    if tick is None or tick <= 0:
        return "tick_size_unavailable"
    if repository.completed_daily(proposal.symbol, as_of) is None:
        return "reference_price_unavailable"
    try:
        assign_entry_window(as_of)
    except CalendarUnverified:
        return "calendar_unverified"
    if cap != MAX_NOTIONAL:
        return None
    return None


def _settle_one(repository, order: Order, *, starting_cash: Decimal, now: datetime, schedule: EquityChargeSchedule) -> None:
    session_day = datetime.fromisoformat(str(order.metadata["entry_session_date"]) + "T00:00:00").date()
    if not schedule.covers(session_day):
        _expire_if_due(repository, order, now, OrderStatus.EXPIRED, "charge_schedule_not_in_force")
        return
    activation = datetime.fromisoformat(str(order.metadata["activation_at"]))
    expiry = datetime.fromisoformat(str(order.metadata["entry_window_end"]))
    window = assign_entry_window(activation)
    if window.session_date.isoformat() != order.metadata["entry_session_date"]:
        _expire_if_due(repository, order, now, OrderStatus.EXPIRED, "entry_window_mismatch")
        return
    limit = Decimal(str(order.limit_price))
    bars = {bar.start.astimezone(timezone.utc): bar for bar in repository.stored_candles(order.symbol, Timeframe.M5)}
    for start in expected_bar_starts(window, activation):
        key = start.astimezone(timezone.utc).isoformat()
        if repository.bar_already_checked(order.order_id, key):
            continue
        bar = bars.get(start.astimezone(timezone.utc))
        bar_end = start + _five_minutes()
        if bar is None or bar.end.astimezone(timezone.utc) > now.astimezone(timezone.utc):
            if now.astimezone(timezone.utc) >= expiry.astimezone(timezone.utc):
                _terminal(repository, order, now, OrderStatus.EXPIRED_NO_DATA, "expired_no_data", release=True)
            return
        price = limit_fill_price(limit, bar)
        checked = list(order.metadata.get("evaluated_bars") or [])
        checked.append(key)
        if price is None or price > limit:
            pending = order.model_copy(update={"updated_at": bar.end, "metadata": {**order.metadata, "evaluated_bars": checked}})
            repository.commit_policy_transition(pending, bar_keys=[key])
            order = pending
            continue
        if not _fill_buy(repository, order, bar, price, starting_cash, schedule, key, checked):
            return
        return
    if now.astimezone(timezone.utc) >= expiry.astimezone(timezone.utc):
        _terminal(repository, order, now, OrderStatus.EXPIRED, "limit_not_reached", release=True)


def _fill_buy(repository, order, bar: Candle, price: Decimal, starting_cash: Decimal, schedule, key: str, checked: list) -> bool:
    notional = price * order.quantity
    fees = delivery_buy(notional, schedule).total
    debit = notional + fees
    reserved = Decimal(str(order.metadata["reserved_amount"]))
    if price > Decimal(str(order.limit_price)) or notional > MAX_NOTIONAL or debit > reserved:
        return False
    if debit > repository.cash_balance(starting_cash):
        return False
    stamp = bar.end.astimezone(timezone.utc)
    filled = order.model_copy(
        update={"status": OrderStatus.FILLED, "updated_at": stamp, "metadata": {**order.metadata, "evaluated_bars": checked}}
    )
    execution = _execution(order, price, fees, stamp, bar)
    from core_paper.cycle import next_position

    position = next_position(repository.position_for(order.symbol), order.symbol, Side.BUY, order.quantity, price, stamp)
    cash = repository.cash_balance(starting_cash) - debit
    snapshot = _snapshot(repository, stamp, cash, position)
    recorded = repository.commit_policy_transition(
        filled,
        convert_amount=debit,
        execution=execution,
        position=position,
        snapshot=snapshot,
        snapshot_id=execution.execution_id,
        bar_keys=[key],
        ledger=[
            {
                "ledger_id": f"{order.order_id}:booked",
                "kind": "booked",
                "execution_id": execution.execution_id,
                "amount": fees,
                "payload": {"classification": "delivery_buy", "charge_version": schedule.version},
            }
        ],
    )
    if recorded:
        repository.note_peak_equity(snapshot.equity)
    return recorded


def settle_sell(repository: CoreRepository, order: Order, *, starting_cash: Decimal, now: datetime, schedule: EquityChargeSchedule = ZERODHA_EQUITY_RI) -> None:
    if order.status != OrderStatus.OPEN or order.metadata.get("policy_version") != SELL_POLICY_VERSION:
        return
    if order.metadata.get("product_type") != PRODUCT_CNC:
        return
    raw = order.metadata.get("level_price")
    if order.metadata.get("fill_at") == "level" and raw:
        _fill_sell(repository, order, Decimal(str(raw)), datetime.fromisoformat(str(order.metadata["decision_end"])), starting_cash, schedule, bar_key="level")
        return
    decision_end = datetime.fromisoformat(str(order.metadata["decision_end"]))
    later = [
        bar
        for bar in repository.stored_candles(order.symbol, Timeframe.M5)
        if bar.end.astimezone(timezone.utc) > decision_end.astimezone(timezone.utc)
        and bar.end.astimezone(timezone.utc) <= now.astimezone(timezone.utc)
    ]
    if not later:
        return
    bar = sorted(later, key=lambda item: item.end)[0]
    _fill_sell(repository, order, bar.open, bar.end, starting_cash, schedule, bar_key=bar.start.astimezone(timezone.utc).isoformat())


def _fill_sell(repository, order, price: Decimal, stamp: datetime, starting_cash: Decimal, schedule, bar_key: str) -> None:
    if repository.bar_already_checked(order.order_id, bar_key):
        return
    held = repository.held_quantity(order.symbol)
    other_sells = repository.reserved_sell_quantity(order.symbol) - order.quantity
    if other_sells < 0 or order.quantity > held - other_sells:
        return
    day = stamp.astimezone(IST).date().isoformat()
    buys = _same_day_buys(repository, order.symbol, day)
    include_dp = not repository.dp_claimed(day, order.exchange.value, order.symbol)
    matched = min(order.quantity, sum(item[1] for item in buys))
    fee_updates: list[tuple[str, dict]] = []
    extra_cash_delta = Decimal("0")
    if matched > 0 and buys:
        buy_execution, buy_qty, buy_price, _buy_order = buys[0]
        revised = reclassified_buy(buy_price, buy_qty, matched if matched <= buy_qty else buy_qty, schedule)
        delta = revised.total - buy_execution.fees
        extra_cash_delta -= delta
        payload = buy_execution.model_dump(mode="json")
        payload["fees"] = str(revised.total)
        payload["metadata"] = {
            **payload["metadata"],
            "reclassified_to": revised.classification,
            "reclass_delta": str(delta),
            "prior_fees": str(buy_execution.fees),
        }
        fee_updates.append((buy_execution.execution_id, payload))
        quote = intraday_sell(price, order.quantity, buy_price, schedule, include_dp=include_dp)
    else:
        quote = delivery_sell(price * order.quantity, schedule, include_dp=include_dp)
    fees = quote.total
    notional = price * order.quantity
    cash = repository.cash_balance(starting_cash) + notional - fees + extra_cash_delta
    filled = order.model_copy(update={"status": OrderStatus.FILLED, "updated_at": stamp.astimezone(timezone.utc)})
    execution = _execution(order, price, fees, stamp, None)
    from core_paper.cycle import next_position

    updated = next_position(repository.position_for(order.symbol), order.symbol, Side.SELL, order.quantity, price, stamp)
    snapshot = _snapshot(repository, stamp, cash, None if updated.quantity == 0 else updated)
    ledger = [
        {
            "ledger_id": f"{order.order_id}:booked",
            "kind": "booked",
            "execution_id": execution.execution_id,
            "amount": fees,
            "payload": {"classification": quote.classification, "lines": list(quote.lines)},
        }
    ]
    if fee_updates:
        ledger.append(
            {
                "ledger_id": f"{order.order_id}:reclass",
                "kind": "reclass",
                "execution_id": buys[0][0].execution_id,
                "amount": extra_cash_delta,
                "payload": {"reason": "same_day_cnc_square_off", "charge_version": schedule.version},
            }
        )
    dp = None
    if include_dp:
        dp = {
            "dp_id": f"{order.order_id}:{day}",
            "trading_day": day,
            "exchange": order.exchange.value,
            "symbol": order.symbol,
            "amount": schedule.dp_inr_per_scrip,
            "execution_id": execution.execution_id,
        }
    recorded = repository.commit_policy_transition(
        filled,
        execution=execution,
        position=None if updated.quantity == 0 else updated,
        clear_symbol=order.symbol if updated.quantity == 0 else None,
        snapshot=snapshot,
        snapshot_id=execution.execution_id,
        bar_keys=[bar_key],
        ledger=ledger,
        dp=dp,
        fee_updates=fee_updates,
    )
    if recorded:
        repository.note_peak_equity(snapshot.equity)


def _same_day_buys(repository, symbol: str, day: str):
    orders = {item.order_id: item for item in repository.list_orders()}
    rows = []
    for execution in repository.list_executions():
        order = orders.get(execution.order_id)
        if order is None or order.side != Side.BUY or execution.symbol != symbol:
            continue
        if execution.executed_at.astimezone(IST).date().isoformat() != day:
            continue
        rows.append((execution, execution.quantity, execution.price, order))
    return rows


def _expire_if_due(repository, order, now, status, reason: str) -> None:
    expiry = datetime.fromisoformat(str(order.metadata["entry_window_end"]))
    if now.astimezone(timezone.utc) >= expiry.astimezone(timezone.utc):
        _terminal(repository, order, now, status, reason, release=True)


def _terminal(repository, order, now, status, reason: str, *, release: bool) -> None:
    if order.status != OrderStatus.OPEN:
        return
    updated = order.model_copy(
        update={
            "status": status,
            "updated_at": now.astimezone(timezone.utc),
            "metadata": {**order.metadata, "terminal_reason": reason},
        }
    )
    repository.commit_policy_transition(updated, release=release)


def _order(repository, proposal, as_of, instrument, *, status, limit, metadata, quantity=None) -> Order:
    from core_paper.cycle import _digest

    order_id = _digest("order", proposal.proposal_id)
    moment = as_of.astimezone(timezone.utc)
    return Order(
        order_id=order_id,
        client_order_id=order_id,
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        exchange=Exchange(instrument.exchange),
        side=proposal.side,
        order_type=OrderType.LIMIT if limit is not None else OrderType.MARKET,
        quantity=quantity or proposal.quantity,
        limit_price=limit,
        stop_price=None,
        trading_mode=TradingMode.PAPER,
        status=status,
        created_at=moment,
        updated_at=moment,
        metadata=metadata,
    )


def _execution(order: Order, price: Decimal, fees: Decimal, stamp: datetime, bar: Candle | None) -> Execution:
    from core_paper.cycle import _digest

    moment = stamp.astimezone(timezone.utc)
    return Execution(
        execution_id=_digest("execution", order.proposal_id),
        order_id=order.order_id,
        symbol=order.symbol,
        quantity=order.quantity,
        price=price,
        executed_at=moment,
        fees=fees,
        slippage=Decimal("0"),
        venue="PAPER",
        metadata={
            "gross_price": str(price),
            "net_price": str(price),
            "fees": str(fees),
            "slippage": "0",
            "fill_model": FILL_MODEL,
            "fill_assumption": "simulated_ohlc_not_a_broker_execution",
            "product_type": PRODUCT_CNC,
            "charge_version": order.metadata.get("charge_version"),
            "decision_end": moment.isoformat(),
            "reason": order.metadata.get("reason", "entry"),
            "bar_end": None if bar is None else bar.end.astimezone(timezone.utc).isoformat(),
            "stop_loss": order.metadata.get("stop_loss", "0"),
            "take_profit": order.metadata.get("take_profit", "0"),
        },
    )


def _snapshot(repository: CoreRepository, as_of: datetime, cash: Decimal, replacement) -> PortfolioSnapshot:
    positions = [item for item in repository.list_positions() if replacement is None or item.symbol != replacement.symbol]
    if replacement is not None and replacement.quantity != 0:
        positions.append(replacement)
    market_value = sum((item.market_value for item in positions), Decimal("0"))
    realized = sum((item.realized_pnl for item in positions), Decimal("0"))
    unrealized = sum((item.unrealized_pnl for item in positions), Decimal("0"))
    equity = cash + market_value
    book = repository.active_paper_session()
    stored = Decimal("0") if book is None or book.peak_equity is None else book.peak_equity
    peak = stored if stored >= equity else equity
    drawdown = Decimal("0") if peak <= 0 else min(Decimal("1"), max(Decimal("0"), ((peak - equity) / peak).quantize(_DRAWDOWN_QUANTUM)))
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


def _five_minutes():
    from datetime import timedelta

    return timedelta(minutes=5)
