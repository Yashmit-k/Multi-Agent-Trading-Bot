"""Paper cycle. New equity buys are CNC limit orders.

A buy records the latest completed daily close as its reference price and can
fill only on a completed five-minute bar inside its entry window, at or below
the limit. Orders that do not carry the CNC policy version are left unchanged.
When no research schedule is passed, backtest helpers still use 2 bp. The CNC
path uses the versioned Zerodha schedule and does not fall back to 2 bp.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from contracts.enums import Exchange, Horizon, OrderStatus, OrderType, RiskStatus, Side, Timeframe, TradingMode
from contracts.events import EventType, channel_for
from contracts.schemas.event import EventEnvelope
from contracts.schemas.execution import Execution
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from core_db.repository import DAILY_ENTRY_LIMIT, CoreRepository
from core_risk.settings import DEFAULTS as DEFAULT_SETTINGS, RiskSettings, parse_settings
from core_decision import build_proposal, proposal_id_for
from core_fusion import fuse
from core_paper.costs import CostSchedule, fee_on, slipped_price
from core_paper.execute import MAX_NOTIONAL, queue_entry, settle_entries, settle_sell
from core_paper.limits import PRODUCT_CNC, SELL_POLICY_VERSION
from core_paper.charges import ZERODHA_EQUITY_RI
from core_paper.trading_calendar import paper_test_entry_window
from core_risk import assess
from core_risk.portfolio import PortfolioContext

HORIZON_TIMEFRAME: dict[Horizon, Timeframe] = {
    Horizon.INTRADAY: Timeframe.M5,
    Horizon.SWING: Timeframe.D1,
    Horizon.LONG_TERM: Timeframe.D1,
}
_DRAWDOWN_QUANTUM = Decimal("0.00000001")
_CENT = Decimal("0.01")
logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, channel: str, payload: str) -> None:
        """Send one Redis message."""


def _candle_is_fresh(stored_end: datetime, timeframe: Timeframe, now: datetime) -> bool:
    from core_market_data.schedule import candle_is_fresh

    return candle_is_fresh(stored_end, timeframe, now)


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
    require_fresh: bool = False,
    now: datetime | None = None,
    max_new_orders: int | None = None,
    enforce_entry_window: bool = True,
    require_universe_fresh: bool = False,
    broker_authenticated: bool = True,
    allow_test_extension: bool = False,
    portfolio_limits: bool = True,
) -> int:
    if max_new_orders is not None and max_new_orders < 0:
        raise ValueError("max_new_orders must be zero or positive")
    if not repository.paper_running():
        return 0
    book = repository.active_paper_session()
    if book is None or book.starting_cash is None:
        return 0
    starting_cash = book.starting_cash
    moment = now or datetime.now(timezone.utc)
    costs = paper_schedule(schedule)
    _settle_open_orders(repository, publisher, costs, starting_cash, now=moment)
    _monitor_brackets(repository, publisher, costs, starting_cash, mode)
    _manage_strategy_exits(repository, publisher, costs, starting_cash, mode, moment)
    _settle_open_orders(repository, publisher, costs, starting_cash, now=moment)
    if repository.kill_switch_armed():
        _queue_flattens(repository, publisher, costs, starting_cash, mode)
        _settle_open_orders(repository, publisher, costs, starting_cash, now=moment)
        return 0
    written = 0
    settings = load_risk_settings(repository)
    blocked = _new_entry_block(
        repository,
        moment,
        mode=mode,
        enforce_entry_window=enforce_entry_window,
        require_universe_fresh=require_universe_fresh,
        broker_authenticated=broker_authenticated,
        allow_test_extension=allow_test_extension,
        settings=settings,
    )
    if blocked is not None:
        logger.info("new_entries_blocked reason=%s", blocked)
        return written
    created_orders = 0
    capped = False
    applied = _applied_strategy(repository)
    extension = paper_test_entry_window(moment) if allow_test_extension and mode == TradingMode.PAPER else None
    for instrument in repository.list_instruments():
        if capped:
            break
        for horizon, timeframe in HORIZON_TIMEFRAME.items():
            if max_new_orders is not None and created_orders >= max_new_orders:
                capped = True
                break
            candle = repository.latest_candle(instrument.symbol, timeframe)
            if candle is None:
                continue
            # Held stocks are still scored so a bearish turn can exit them; they only skip new BUYs below.
            if require_fresh and not _candle_is_fresh(candle.end, timeframe, moment):
                continue
            as_of = candle.end.astimezone(timezone.utc)
            proposal_id = proposal_id_for(instrument.symbol, horizon, as_of, session_id=book.session_id)
            proposal = repository.get_proposal(proposal_id)
            if proposal is None:
                aggregate = fuse(repository.signals_for(instrument.symbol), horizon=horizon, as_of=as_of, weights=weights)
                if aggregate is None:
                    continue
                proposal = build_proposal(aggregate, candle, as_of, session_id=book.session_id)
                if proposal is None:
                    continue
                # Long-only book: a bearish view on a stock we do not hold is not an order to propose.
                held = repository.held_quantity(instrument.symbol)
                if proposal.side == Side.SELL and held <= 0:
                    continue
                if proposal.side == Side.BUY and held > 0:
                    continue  # one position per stock: no adding to an existing holding
                if proposal.side == Side.BUY and applied:
                    continue  # an applied Strategy-lab strategy replaces agent entries
                if proposal.side == Side.SELL and applied and _is_strategy_position(repository, instrument.symbol):
                    continue  # the strategy manages its own exits
                if proposal.side == Side.BUY and horizon == Horizon.INTRADAY and not settings.intraday_auto_entries:
                    continue  # intraday entries are off (Settings); intraday exits of holdings still run
                if proposal.side == Side.SELL:
                    proposal = proposal.model_copy(update={"quantity": held})  # a signal exit sells the whole holding
                proposal = _with_brackets(_sized(proposal, repository.available_cash(starting_cash), costs, settings.max_order_notional), settings)
                proposal = proposal.model_copy(update={"metadata": {**proposal.metadata, "stops_monitored": True, "same_bar_exit": "stop_first", "decided_at": moment.isoformat()}})
                if repository.insert_proposal(proposal):
                    _publish(publisher, EventType.DECISION_CREATED, f"decision.created:{proposal.proposal_id}", as_of, proposal.proposal_id, proposal)
                    written += 1
            if repository.risk_for_proposal(proposal.proposal_id) is None:
                members = {item.symbol for item in repository.members_at(as_of)}
                decision = assess(
                    proposal,
                    mode=mode,
                    in_universe=proposal.symbol in members,
                    cash=repository.available_cash(starting_cash),
                    held_quantity=repository.held_quantity(proposal.symbol),
                    timestamp=as_of,
                    max_notional=settings.max_order_notional,
                    portfolio=portfolio_context(repository, starting_cash, moment, settings) if portfolio_limits else None,
                    # Intraday only: on swing, risk-off days were followed by the best next-day returns (tuning study).
                    market_ok=None if proposal.side != Side.BUY or horizon != Horizon.INTRADAY else not market_risk_off(repository, instrument.symbol, horizon, as_of),
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
            if proposal.side == Side.SELL:
                # Agents turned bearish on a held stock: sell at the next bar's open, like a stop or target exit.
                _queue(repository, proposal, as_of, reason="signal", fill_at="next_open")
                continue
            before = {item.order_id for item in repository.list_orders()}
            queue_entry(repository, proposal, as_of, entry_window=extension, placed_at=moment, cap=settings.max_order_notional, daily_limit=settings.daily_entry_limit)
            queued = [item for item in repository.list_orders() if item.order_id not in before]
            created_orders += len(queued)
            for order in queued:
                event_type = _order_event(order)
                _publish(publisher, event_type, f"{event_type.value}:{order.order_id}", as_of, proposal.proposal_id, order)
    if applied and not capped:
        from core_paper.strategy_live import strategy_entries

        try:
            strategy_entries(repository, publisher, starting_cash=starting_cash, moment=moment, settings=settings, mode=mode)
        except Exception:
            logger.exception("strategy_entries_failed")
    if capped:
        logger.info("new_order_cap cap=%s created=%s", max_new_orders, created_orders)
    _settle_open_orders(repository, publisher, costs, starting_cash, now=moment)
    return written


_PENDING = {OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.RISK_APPROVED, OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


def load_risk_settings(repository: CoreRepository) -> RiskSettings:
    """The user's saved paper risk settings over the defaults; a bad stored value falls back to its default."""
    stored = repository.get_setting("risk")
    return parse_settings(stored["payload"] if stored else None, strict=False)


def _with_brackets(proposal, settings: RiskSettings):
    """Stop and target from the user's percentages, around the same entry price as before."""
    if proposal.side != Side.BUY or (settings.stop_loss_pct == DEFAULT_SETTINGS.stop_loss_pct and settings.take_profit_pct == DEFAULT_SETTINGS.take_profit_pct):
        return proposal
    entry = proposal.entry_price
    cent = Decimal("0.01")
    stop = (entry * (1 - settings.stop_loss_pct / 100)).quantize(cent)
    target = (entry * (1 + settings.take_profit_pct / 100)).quantize(cent)
    return proposal.model_copy(update={"stop_loss": stop, "take_profit": target, "metadata": {**proposal.metadata, "brackets": "user_settings"}})


def portfolio_context(repository: CoreRepository, starting_cash: Decimal, moment: datetime, settings: RiskSettings | None = None) -> PortfolioContext:
    """The active book for portfolio risk checks: held shares at cost plus BUYs queued but not filled."""
    exposure: dict[str, Decimal] = {}
    for position in repository.list_positions():
        if position.quantity > 0:
            exposure[position.symbol] = exposure.get(position.symbol, Decimal("0")) + position.average_price * position.quantity
    for order in repository.list_orders():
        if order.side == Side.BUY and order.status in _PENDING:
            price = order.limit_price or Decimal(str(order.metadata.get("reference_price") or "0"))
            exposure[order.symbol] = exposure.get(order.symbol, Decimal("0")) + price * order.quantity
    limits = settings or DEFAULT_SETTINGS
    return PortfolioContext(
        starting_cash=starting_cash,
        exposure=exposure,
        entries_today=repository.daily_entry_count(moment),
        max_positions=limits.max_open_positions,
        max_per_sector=limits.max_per_sector,
        max_exposure_fraction=limits.max_exposure_fraction,
        max_per_stock=limits.max_per_stock,
        daily_entry_limit=limits.daily_entry_limit,
    )


class CycleRefused(RuntimeError):
    """The one-shot preflight refused to start a cycle."""


REQUIRED_MEMBER_COUNT = 50
FEED_LAG_TOLERANCE = timedelta(minutes=5)


def _new_entry_block(
    repository: CoreRepository,
    now: datetime,
    *,
    mode: TradingMode,
    enforce_entry_window: bool,
    require_universe_fresh: bool,
    broker_authenticated: bool,
    allow_test_extension: bool,
    settings: RiskSettings | None = None,
) -> str | None:
    """Why this cycle must not submit a new buy. Settlement has already run."""
    limits = settings or DEFAULT_SETTINGS
    if not limits.auto_entries:
        return "auto_entries_off"
    if not broker_authenticated:
        return "broker_unauthenticated"
    if enforce_entry_window:
        try:
            require_entry_window(now, mode=mode, allow_extension=allow_test_extension)
        except CycleRefused as exc:
            return str(exc)
    if require_universe_fresh:
        try:
            require_fresh_constituents(repository, now)
        except CycleRefused as exc:
            return str(exc)
    if repository.daily_entry_count(now) >= limits.daily_entry_limit:
        return "daily_entry_cap"
    return None


def require_fresh_constituents(repository: CoreRepository, now: datetime) -> None:
    """Fail closed unless every current member has a fresh five-minute bar in the database.

    Freshness is `candle_is_fresh`, which uses `expected_completed_end` and the
    90-second publication delay. The ingestion status snapshot is not read.
    """
    members = repository.members_at(now)
    if len(members) != REQUIRED_MEMBER_COUNT:
        raise CycleRefused(f"NIFTY50 membership is {len(members)}, required {REQUIRED_MEMBER_COUNT}")
    # The market-wide feed check tolerates one bar of lag: the collector walks 50 symbols in turn, so a
    # strict "every symbol has the newest bar" test is false for most of each 5-minute window. The symbol
    # being traded still needs its own newest bar (require_fresh in run_paper_cycle).
    tolerance = now - FEED_LAG_TOLERANCE
    for item in members:
        bar = repository.latest_candle(item.symbol, Timeframe.M5)
        if bar is None or not _candle_is_fresh(bar.end, Timeframe.M5, tolerance):
            raise CycleRefused(f"stale or missing 5m bar for {item.symbol}")


def require_ordinary_entry_window(now: datetime) -> None:
    """Ordinary cash session, 09:20 inclusive to ENTRY_END exclusive IST (10:30 by default)."""
    require_entry_window(now, mode=TradingMode.PAPER, allow_extension=False)


def require_entry_window(now: datetime, *, mode: TradingMode, allow_extension: bool) -> None:
    """New-entry gate. The 11:00 end applies only to the opted-in 13 October 2026 paper test."""
    from datetime import time

    from core_paper.trading_calendar import ENTRY_END, ENTRY_START, IST, paper_test_entry_window, session_for

    local = now.astimezone(IST)
    window = session_for(local.date())
    label = f"{ENTRY_START.strftime('%H:%M')}-{ENTRY_END.strftime('%H:%M')}"
    if window is None or (window.entry_start, window.entry_end) != (ENTRY_START, ENTRY_END):
        raise CycleRefused(f"session is not an ordinary {label} entry window")
    end = ENTRY_END
    if allow_extension and mode == TradingMode.PAPER:
        extended = paper_test_entry_window(now)
        if extended is not None:
            end = extended.entry_end
    end_at = datetime.combine(window.session_date, end, tzinfo=IST)
    if not (window.entry_start_at <= local < end_at):
        if end == time(11, 0):
            raise CycleRefused("outside the 13 October 2026 paper entry window ending 11:00 IST")
        raise CycleRefused(f"outside {label.replace('-', ' inclusive to ')} exclusive IST")


def _sized(proposal, cash: Decimal, schedule: CostSchedule, max_notional: Decimal = MAX_NOTIONAL):
    from core_paper.backtest import _shares

    if proposal.side != Side.BUY:
        return proposal
    quantity = _shares(cash, proposal.entry_price, max_notional, schedule)
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
            "product_type": PRODUCT_CNC,
            "policy_version": SELL_POLICY_VERSION,
            "charge_version": ZERODHA_EQUITY_RI.version,
        },
    )
    repository.insert_order(order)


def _settle_open_orders(repository: CoreRepository, publisher: EventPublisher, schedule: CostSchedule, starting_cash: Decimal, *, now: datetime | None = None) -> None:
    moment = now or datetime.now(timezone.utc)
    before = {item.execution_id for item in repository.list_executions()}
    for order_id in settle_entries(repository, starting_cash=starting_cash, now=moment):
        logger.info("legacy_order_review_required order_id=%s", order_id)
    for order in repository.list_orders():
        if order.metadata.get("policy_version") == SELL_POLICY_VERSION:
            settle_sell(repository, order, starting_cash=starting_cash, now=moment)
    del schedule
    fresh = [item for item in repository.list_executions() if item.execution_id not in before]
    if not fresh:
        return
    orders = {item.order_id: item for item in repository.list_orders()}
    for execution in fresh:
        order = orders.get(execution.order_id)
        correlation = order.proposal_id if order is not None else execution.order_id
        _publish(publisher, EventType.ORDER_FILLED, f"order.filled:{execution.execution_id}", execution.executed_at, correlation, execution)
        position = repository.position_for(execution.symbol)
        if position is not None:
            _publish(publisher, EventType.POSITION_UPDATED, f"position.updated:{execution.execution_id}", execution.executed_at, correlation, position)


def _monitor_brackets(repository, publisher, schedule, starting_cash, mode: TradingMode) -> None:
    from core_paper.backtest import exit_on_bar

    for position in repository.list_positions():
        if position.quantity <= 0:
            continue
        if _is_strategy_position(repository, position.symbol):
            continue  # managed by core_paper.strategy_live (targets, breakeven, trailing, time exits)
        entry = _entry_execution(repository, position.symbol)
        if entry is None:
            continue
        if "stop_loss" not in entry.metadata or "take_profit" not in entry.metadata:
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


def market_risk_off(repository: CoreRepository, symbol: str, horizon: Horizon, as_of: datetime) -> bool:
    """Risk-off when the newest valid Regime signal shows NIFTY in a downtrend *and* India VIX rising.

    Regime reads only market-wide data, so it is a filter on new agent buys, not a per-stock vote
    (its fusion weight is 0). No valid Regime signal: not risk-off (the filter fails open).
    """
    moment = as_of.astimezone(timezone.utc)
    candidates = [
        item
        for item in repository.signals_for(symbol)
        if item.agent_name.value == "regime" and item.horizon == horizon and item.timestamp.astimezone(timezone.utc) <= moment and item.valid_until.astimezone(timezone.utc) >= moment
    ]
    if not candidates:
        return False
    newest = max(candidates, key=lambda item: item.timestamp)
    votes = {str(vote.get("name")): vote.get("value") for vote in newest.metadata.get("votes", []) if isinstance(vote, dict)}
    return votes.get("index_trend") == -1 and votes.get("fear_gauge") == -1


def _applied_strategy(repository: CoreRepository) -> bool:
    from core_paper.strategy_live import active_strategy

    return active_strategy(repository) is not None


def _is_strategy_position(repository: CoreRepository, symbol: str) -> bool:
    from core_paper.strategy_live import is_strategy_position

    return is_strategy_position(repository, symbol)


def _manage_strategy_exits(repository, publisher, schedule, starting_cash, mode: TradingMode, moment: datetime) -> None:
    from core_paper.strategy_live import manage_strategy_positions

    try:
        manage_strategy_positions(repository, publisher, schedule, starting_cash, mode, moment)
    except Exception:
        logger.exception("strategy_exits_failed")


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
    book = repository.active_paper_session()
    if book is None:
        return
    proposal_id = _digest("exit", f"{book.session_id}|{position.symbol}|{reason}|{moment.isoformat()}")
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
        cash=repository.available_cash(starting_cash),
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


def _order_event(order: Order) -> EventType:
    if order.status == OrderStatus.CREATED:
        return EventType.ORDER_CREATED
    if order.status == OrderStatus.REJECTED:
        return EventType.ORDER_REJECTED
    return EventType.ORDER_UPDATED


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
