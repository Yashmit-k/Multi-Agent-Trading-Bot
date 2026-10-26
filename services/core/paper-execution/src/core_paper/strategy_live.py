"""Apply a Strategy-lab strategy to live paper trading.

When a strategy is applied (user_settings["active_strategy"], with a frozen copy of its definition),
it replaces agent entries (or, per the strategy_mode setting, trades alongside them or only with their agreement): each cycle it evaluates its entry rule on the latest completed bars and
proposes BUYs through the normal risk checks and CNC limit entry. Agents keep publishing signals
and their existing positions still exit as before.

Positions opened by the strategy are managed here, not by the generic 2%/4% bracket monitor:
stop, up to three targets (partial sells), breakeven after the first target, trailing stop,
maximum hold, 15:15 square-off for intraday strategies, and the exit rule. Levels are checked on
the latest 5-minute bar, every cycle.
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from contracts.enums import AgentName, Horizon, OrderStatus, RiskStatus, Side, Timeframe, TradingMode
from contracts.events import EventType
from contracts.schemas.trade_proposal import TradeProposal
from core_db.repository import CoreRepository
from core_risk.settings import agree_agent_names
from core_paper.strategy_engine import (
    INTRADAY,
    IST,
    TIMEFRAME_MINUTES,
    Bars,
    Context,
    StrategyDefinition,
    bars_from_rows,
    context_for,
    evaluate,
    operand_values,
    add_on_target,
    planned_targets,
    rebase_plan,
    resample,
    stop_price,
    target_prices,
)

logger = logging.getLogger(__name__)
SETTING_KEY = "active_strategy"
SOURCE = "strategy"
SQUARE_OFF = time(15, 15)
_CENT = Decimal("0.01")
# (strategy_id, applied_at, symbol) -> end of the latest base bar already evaluated, so a 30-second cycle only
# re-reads a symbol's history when a new bar has completed.
_EVALUATED: dict[tuple[str, str, str], datetime] = {}
_OPEN_ORDER = {OrderStatus.CREATED, OrderStatus.VALIDATED, OrderStatus.RISK_APPROVED, OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


# --- active strategy ------------------------------------------------------------------------------


def active_strategy(repository: CoreRepository) -> tuple[dict, StrategyDefinition] | None:
    stored = repository.get_setting(SETTING_KEY)
    if not stored or not stored["payload"].get("strategy_id"):
        return None
    payload = stored["payload"]
    try:
        return payload, StrategyDefinition.model_validate(payload["definition"])
    except Exception:  # noqa: BLE001 - a stored definition that no longer validates is not applied
        logger.exception("active_strategy_invalid")
        return None


def live_problems(definition: StrategyDefinition) -> list[str]:
    """Why a definition cannot be applied to paper trading (empty = it can)."""
    problems = []
    if definition.direction != "long":
        problems.append("the paper engine trades long only; short strategies are for backtests")
    if definition.stop.kind == "none":
        problems.append("a strategy applied to paper trading needs a stop")
    return problems


def live_warnings(definition: StrategyDefinition, settings, starting_cash: float = 1_000_000) -> list[str]:  # type: ignore[no-untyped-def]
    """Settings that will block or limit this strategy's paper entries (it can still be applied)."""
    out: list[str] = []
    per_trade = definition.sizing.value if definition.sizing.kind == "notional" else definition.sizing.max_notional
    if per_trade > float(settings.max_order_notional):
        out.append(f"each buy is cut to the per-order limit of ₹{float(settings.max_order_notional):,.0f} (the strategy asks for ₹{per_trade:,.0f})")
    if definition.max_open_positions > settings.max_open_positions:
        out.append(f"Settings allow {settings.max_open_positions} open positions in total, shared with the agents; the strategy allows {definition.max_open_positions}")
    if definition.add_on is not None and per_trade + definition.add_on.notional > float(settings.max_per_stock):
        out.append(f"an add-on would take a stock past the ₹{float(settings.max_per_stock):,.0f} per-stock limit, so it will be rejected")
    stop = definition.stop
    if stop.kind == "percent" and definition.sizing.kind == "notional":
        risk_pct = per_trade * stop.value / starting_cash
        if risk_pct > float(settings.max_risk_per_trade_pct):
            out.append(f"a {stop.value:g}% stop on ₹{per_trade:,.0f} risks more than the {settings.max_risk_per_trade_pct}% per-trade limit")
    first = definition.targets[0] if definition.targets else None
    floor = float(settings.min_reward_risk)
    if first is not None and floor > 0:
        if first.kind == "level" or stop.kind in ("level", "atr"):
            out.append(f"the risk engine rejects a buy whose first target is less than {floor:g}× its stop distance; with level or ATR exits that depends on each signal")
        elif first.kind == "percent" and stop.kind == "percent" and first.value / stop.value < floor:
            out.append(f"the first target ({first.value:g}%) is {first.value / stop.value:.2f}× the stop ({stop.value:g}%), below the {floor:g}× reward-to-risk floor: every entry will be rejected")
    mode = getattr(settings, "strategy_mode", "replace")
    out.append({"replace": "mode: the strategy replaces the agents' entries", "alongside": "mode: the strategy and the agents both trade",
                "agents_agree": "mode: the strategy trades only when the agents agree, and the portfolio manager reviews each entry"}.get(mode, f"mode: {mode}"))
    return out


# --- bars from the database -----------------------------------------------------------------------


def _load(repository: CoreRepository, symbol: str, timeframe: str, start: datetime, end: datetime) -> Bars | None:
    return bars_from_rows(repository.ohlcv(symbol, timeframe, start, end))


def strategy_context(repository: CoreRepository, definition: StrategyDefinition, symbol: str, now: datetime) -> Context | None:
    intraday = definition.timeframe in INTRADAY
    start = now - (timedelta(days=20) if intraday else timedelta(days=700))
    base = _load(repository, symbol, "5m" if intraday else "1d", start, now)
    if base is None or len(base) < 2:
        return None
    bars = base if definition.timeframe in ("5m", "1d") else resample(base, TIMEFRAME_MINUTES[definition.timeframe])
    if len(bars) < 2:
        return None

    def higher(timeframe: str) -> Bars | None:
        if timeframe == "1d":
            return _load(repository, symbol, "1d", now - timedelta(days=700), now)
        return resample(base, TIMEFRAME_MINUTES[timeframe])

    def index() -> Bars | None:
        loaded = _load(repository, "NIFTY50", "5m" if intraday else "1d", start, now)
        if loaded is None or definition.timeframe in ("5m", "1d"):
            return loaded
        return resample(loaded, TIMEFRAME_MINUTES[definition.timeframe])

    return context_for(definition, bars, higher, index)


def latest_signal_bars(repository: CoreRepository, definition: StrategyDefinition, symbol: str, now: datetime) -> tuple[Context | None, bool]:
    """(context, entry rule true on the latest completed bar)."""
    context = strategy_context(repository, definition, symbol, now)
    if context is None:
        return None, False
    return context, bool(evaluate(context, definition.entry)[-1])


def last_closed_session(now: datetime) -> date | None:
    """The most recent NSE session that has closed by `now` (IST), from the trading calendar."""
    from core_paper.trading_calendar import session_for

    local = now.astimezone(IST)
    day = local.date()
    if not (session_for(day) is not None and local.time() >= time(15, 30)):
        day -= timedelta(days=1)
    for _ in range(14):
        if session_for(day) is not None:
            return day
        day -= timedelta(days=1)
    return None


def _fresh(definition: StrategyDefinition, bar_end: datetime, now: datetime) -> bool:
    """The latest bar is the one that just completed, not an old one (no entries on stale data). A daily bar is
    fresh when it is the last session that has closed, so Friday's signal is still taken on Monday morning."""
    if definition.timeframe == "1d":
        return bar_end.astimezone(IST).date() == last_closed_session(now)
    return (now - bar_end) <= timedelta(minutes=TIMEFRAME_MINUTES[definition.timeframe]) + timedelta(minutes=3)


# --- entries --------------------------------------------------------------------------------------


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def agents_view(
    repository: CoreRepository, symbol: str, horizon: Horizon, moment: datetime, weights: dict | None, only: tuple[str, ...] | None = None
) -> float | None:
    """The agents' fused signal on this stock now, or None when no agent has a valid opinion.

    With `only`, just those agents vote, each with weight 1 (the live fusion weights are ignored): a strategy
    decides which opinions count as disagreement.
    """
    from core_fusion import fuse

    if only is not None:
        weights = {horizon: {agent.value: (1.0 if agent.value in only else 0.0) for agent in AgentName}}
    aggregate = fuse(repository.signals_for(symbol), horizon=horizon, as_of=moment, weights=weights)
    return None if aggregate is None else aggregate.aggregated_signal


def strategy_entries(repository: CoreRepository, publisher, *, starting_cash: Decimal, moment: datetime, settings, mode: TradingMode, weights: dict | None = None, manager_review: bool = False) -> int:  # type: ignore[no-untyped-def]
    """Propose and queue BUYs for every symbol whose entry rule fired on the bar that just completed.

    In "agents_agree" mode an entry also needs a fused agent view that is not bearish, and it then goes
    through the portfolio manager like an agent BUY (it may wait a few cycles for the verdict).
    """
    from core_paper.cycle import _publish

    found = active_strategy(repository)
    if found is None:
        return 0
    meta, definition = found
    book = repository.active_paper_session()
    if book is None:
        return 0
    agree = getattr(settings, "strategy_mode", "replace") == "agents_agree"
    agree_with = agree_agent_names(settings) if agree else None
    review = agree and manager_review and getattr(settings, "manager_review", False)
    created = 0
    # Entries from earlier cycles still waiting for the portfolio manager.
    for waiting in repository.list_proposals():
        if waiting.metadata.get("source") == SOURCE and waiting.metadata.get("needs_review") and repository.risk_for_proposal(waiting.proposal_id) is None:
            created += _decide(repository, publisher, waiting, starting_cash=starting_cash, moment=moment, settings=settings, mode=mode, review=review)
    members = {item.symbol for item in repository.members_at(moment)}
    symbols = sorted(members) if definition.symbols == ["ALL"] else [s for s in definition.symbols if s in members]
    pending = {order.symbol for order in repository.list_orders() if order.side == Side.BUY and order.status in _OPEN_ORDER}
    base_timeframe = Timeframe.M5 if definition.timeframe in INTRADAY else Timeframe.D1
    # The strategy's own position limit, counting its holdings and its entries still waiting to fill.
    held_by_strategy = {p.symbol for p in repository.list_positions() if p.quantity > 0 and entry_plan(repository, p.symbol) is not None}
    waiting = {o.symbol for o in repository.list_orders() if o.side == Side.BUY and o.status in _OPEN_ORDER and _from_strategy(repository, o.proposal_id)}
    slots = definition.max_open_positions - len(held_by_strategy | waiting)
    for symbol in symbols:
        if symbol in held_by_strategy and symbol not in pending and definition.add_on is not None:
            created += _maybe_add_on(repository, publisher, definition, meta, symbol, starting_cash=starting_cash, moment=moment, settings=settings, mode=mode)
            continue
        if repository.held_quantity(symbol) > 0 or symbol in pending:
            continue
        if slots <= 0:
            continue
        newest = repository.latest_candle(symbol, base_timeframe)
        if newest is None:
            continue
        seen_key = (str(meta["strategy_id"]), str(meta.get("applied_at")), symbol)
        if _EVALUATED.get(seen_key) == newest.end:
            continue  # no new bar since the last evaluation
        _EVALUATED[seen_key] = newest.end
        context, signal = latest_signal_bars(repository, definition, symbol, moment)
        if context is None or not signal:
            continue
        bars = context.bars
        last = len(bars) - 1
        bar_end = bars.end[last]
        if not _fresh(definition, bar_end, moment):
            continue
        proposal_id = f"strategy-{_digest(book.session_id, meta['strategy_id'], symbol, bar_end.isoformat())}"
        if repository.get_proposal(proposal_id) is not None:
            continue  # this bar's signal was already handled
        close = float(bars.close[last])
        limit = None
        if definition.entry_order.type == "limit":
            level = float(operand_values(context, definition.entry_order.price)[last])  # type: ignore[arg-type]
            if math.isnan(level) or level <= 0:
                continue
            limit = level
        entry = limit if limit is not None else close
        stop = stop_price(definition, context, last, entry)
        if stop is None or math.isnan(stop) or stop >= entry:
            continue
        targets = target_prices(definition, context, last, entry, stop)
        if definition.sizing.kind == "risk_percent":
            quantity = int(float(starting_cash) * definition.sizing.value / 100 // (entry - stop))
            quantity = min(quantity, int(definition.sizing.max_notional // entry))
        else:
            quantity = int(definition.sizing.value // entry)
        quantity = min(quantity, int(float(settings.max_order_notional) // entry))
        if quantity < 1:
            continue
        final_target = targets[-1][0] if targets else entry * 10  # no target: exits come from stop/trailing/time/rule
        horizon = Horizon.INTRADAY if definition.timeframe in INTRADAY else Horizon.SWING
        view = agents_view(repository, symbol, horizon, moment, weights, only=agree_with) if agree else None
        if agree and view is not None and view < 0:
            logger.info("strategy_entry_blocked_by_agents symbol=%s fused=%.3f agents=%s", symbol, view, ",".join(agree_with or ()))
            continue
        proposal = TradeProposal(
            proposal_id=proposal_id,
            symbol=symbol,
            timestamp=bar_end.astimezone(timezone.utc),
            horizon=horizon,
            side=Side.BUY,
            quantity=quantity,
            entry_price=Decimal(str(round(entry, 2))),
            stop_loss=Decimal(str(round(stop, 2))),
            take_profit=Decimal(str(round(final_target, 2))),
            strategy_id=f"user:{meta['strategy_id']}",
            strategy_version=str(meta.get("applied_at", "1")),
            aggregated_signal=1,
            aggregated_confidence=1,
            supporting_signal_ids=[proposal_id],
            metadata={
                "source": SOURCE,
                "strategy_name": definition.name,
                "timeframe": definition.timeframe,
                "signal_bar_end": bar_end.isoformat(),
                # Intraday limit entries live at most valid_bars bars, as in the Strategy-lab backtest.
                "entry_valid_until": (
                    (bar_end + timedelta(minutes=TIMEFRAME_MINUTES[definition.timeframe] * definition.entry_order.valid_bars)).isoformat()
                    if definition.entry_order.type == "limit" and definition.timeframe in INTRADAY
                    else None
                ),
                "decided_at": moment.isoformat(),
                "strategy_mode": getattr(settings, "strategy_mode", "replace"),
                "agents_fused_signal": view,
                "agree_agents": list(agree_with) if agree_with else None,
                "needs_review": review,
                "limit_price": None if limit is None else round(limit, 2),
                "stops_monitored": True,
                "same_bar_exit": "stop_first",
                "plan": {
                    # Planned from the signal price; re-based onto the actual fill when the position is managed.
                    "reference": round(entry, 4),
                    "stop": round(stop, 4),
                    "stop_spec": {"kind": definition.stop.kind, "value": definition.stop.value},
                    "stop_percent": definition.stop.value if definition.stop.kind == "percent" else None,
                    "add_on": None if definition.add_on is None else {
                        "notional": definition.add_on.notional,
                        "target": (lambda price: None if price is None else round(price, 4))(add_on_target(definition, context, last, entry, stop)),
                        "target_kind": definition.add_on.target.kind if definition.add_on.target else None,
                        "target_value": definition.add_on.target.value if definition.add_on.target else None,
                        "restop_from_average": definition.add_on.restop_from_average,
                    },
                    "targets": [{**item, "price": round(item["price"], 4)} for item in planned_targets(definition, context, last, entry, stop)],
                    "breakeven_after_first_target": definition.breakeven_after_first_target,
                    "trailing": None if definition.trailing is None else definition.trailing.model_dump(),
                    "max_hold_bars": definition.max_hold_bars,
                    "square_off_intraday": definition.square_off_intraday,
                },
            },
        )
        if repository.insert_proposal(proposal):
            _publish(publisher, EventType.DECISION_CREATED, f"decision.created:{proposal_id}", bar_end, proposal_id, proposal)
        opened = _decide(repository, publisher, proposal, starting_cash=starting_cash, moment=moment, settings=settings, mode=mode, review=review)
        created += opened
        slots -= 1 if (opened or review) else 0
    return created


def _decide(repository: CoreRepository, publisher, proposal: TradeProposal, *, starting_cash: Decimal, moment: datetime, settings, mode: TradingMode, review: bool) -> int:  # type: ignore[no-untyped-def]
    """Portfolio-manager gate (agents_agree mode), risk, then the order. Returns 1 when an order opened."""
    from contracts.schemas.review import ReviewVerdict
    from core_paper.cycle import _order_event, _publish, portfolio_context
    from core_paper.execute import queue_entry
    from core_paper.review_gate import review_gate
    from core_paper.risk_inputs import trade_context
    from core_risk import assess

    gate = review_gate(repository, publisher, proposal, moment) if review else None
    if gate is not None and gate.wait:
        return 0
    assessed = proposal
    if gate is not None and gate.verdict == ReviewVerdict.REDUCE:
        assessed = proposal.model_copy(update={"quantity": max(1, int(proposal.quantity * gate.size_fraction))})
    bar_end = proposal.timestamp
    decision = assess(
        assessed,
        mode=mode,
        in_universe=True,
        cash=repository.available_cash(starting_cash),
        held_quantity=0,
        timestamp=bar_end,
        max_notional=settings.max_order_notional,
        portfolio=portfolio_context(repository, starting_cash, moment, settings),
        manager_ok=None if gate is None or gate.verdict in {None, ReviewVerdict.UNAVAILABLE} else gate.verdict != ReviewVerdict.VETO,
        manager_note="" if gate is None else gate.critique,
        trade=trade_context(repository, assessed, starting_cash=starting_cash, now=moment, settings=settings),
    )
    if repository.insert_risk_decision(decision):
        kind = EventType.RISK_APPROVED if decision.status == RiskStatus.APPROVED else EventType.RISK_REJECTED
        _publish(publisher, kind, f"{kind.value}:{decision.risk_decision_id}", bar_end, proposal.proposal_id, decision)
    if decision.status != RiskStatus.APPROVED:
        return 0
    limit = proposal.metadata.get("limit_price")
    order = queue_entry(
        repository,
        proposal,
        bar_end,
        placed_at=moment,
        cap=settings.max_order_notional,
        daily_limit=settings.daily_entry_limit,
        limit_override=None if limit is None else Decimal(str(limit)),
        quantity_limit=decision.approved_quantity,
    )
    if order is None:
        return 0
    kind = _order_event(order)
    _publish(publisher, kind, f"{kind.value}:{order.order_id}", bar_end, proposal.proposal_id, order)
    return 1 if order.status == OrderStatus.OPEN else 0


# --- exits ----------------------------------------------------------------------------------------


def entry_plan(repository: CoreRepository, symbol: str):  # type: ignore[no-untyped-def]
    """(entry execution, entry proposal) for a holding opened by an applied strategy, else None.
    An add-on fill is part of the position, not its entry: the newest non-add-on entry is the one that counts."""
    orders = {item.order_id: item for item in repository.list_orders() if item.symbol == symbol}
    entries = [item for item in repository.list_executions() if item.symbol == symbol and item.metadata.get("reason") == "entry"]
    for execution in reversed(entries):
        order = orders.get(execution.order_id)
        proposal = repository.get_proposal(order.proposal_id) if order is not None else None
        if proposal is None:
            continue
        if proposal.metadata.get("add_on"):
            continue
        return (execution, proposal) if proposal.metadata.get("source") == SOURCE else None
    return None


def _from_strategy(repository: CoreRepository, proposal_id: str) -> bool:
    proposal = repository.get_proposal(proposal_id)
    return proposal is not None and proposal.metadata.get("source") == SOURCE and not proposal.metadata.get("add_on")


def _add_on_state(repository: CoreRepository, symbol: str, filled_at: datetime) -> tuple[int, int, bool]:
    """(added shares filled, added shares sold at their target, an add-on order exists) for the current position."""
    orders = [item for item in repository.list_orders() if item.symbol == symbol and item.created_at >= filled_at]
    executions = {item.order_id: item for item in repository.list_executions() if item.symbol == symbol}
    added, sold, exists = 0, 0, False
    for order in orders:
        proposal = repository.get_proposal(order.proposal_id)
        if order.side == Side.BUY and proposal is not None and proposal.metadata.get("add_on"):
            if order.status not in (OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED):
                exists = True
            if order.order_id in executions:
                added += executions[order.order_id].quantity
        if order.side == Side.SELL and order.metadata.get("reason") == "strategy_add_on_target" and order.order_id in executions:
            sold += executions[order.order_id].quantity
    return added, sold, exists


def _maybe_add_on(repository: CoreRepository, publisher, definition: StrategyDefinition, meta: dict, symbol: str, *, starting_cash: Decimal, moment: datetime, settings, mode: TradingMode) -> int:  # type: ignore[no-untyped-def]
    """Add to a strategy holding once, when its add-on rule is true on the latest completed bar and no target was hit."""
    from core_paper.cycle import _publish

    found = entry_plan(repository, symbol)
    book = repository.active_paper_session()
    if found is None or book is None or definition.add_on is None:
        return 0
    execution, entry_proposal = found
    if entry_proposal.strategy_id != f"user:{meta['strategy_id']}":
        return 0  # a holding from an earlier strategy keeps its own plan
    filled_at = execution.executed_at
    _, _, exists = _add_on_state(repository, symbol, filled_at)
    targets_hit = any(
        item.side == Side.SELL and item.symbol == symbol and item.created_at >= filled_at and str(item.metadata.get("reason", "")).startswith("strategy_target")
        for item in repository.list_orders()
    )
    if exists or targets_hit:
        return 0
    context = strategy_context(repository, definition, symbol, moment)
    if context is None:
        return 0
    bar_end = context.bars.end[-1]
    if bar_end <= filled_at or not _fresh(definition, bar_end, moment) or not bool(evaluate(context, definition.add_on.when)[-1]):
        return 0
    close = float(context.bars.close[-1])
    quantity = min(int(definition.add_on.notional // close), int(float(settings.max_order_notional) // close))
    if quantity < 1:
        return 0
    proposal_id = f"strategy-addon-{_digest(book.session_id, entry_proposal.proposal_id, bar_end.isoformat())}"
    if repository.get_proposal(proposal_id) is not None:
        return 0
    proposal = entry_proposal.model_copy(
        update={
            "proposal_id": proposal_id,
            "timestamp": bar_end.astimezone(timezone.utc),
            "quantity": quantity,
            "entry_price": Decimal(str(round(close, 2))),
            "stop_loss": min(entry_proposal.stop_loss, Decimal(str(round(close * 0.999, 2)))),
            "take_profit": max(entry_proposal.take_profit, Decimal(str(round(close * 1.001, 2)))),
            "supporting_signal_ids": [proposal_id],
            "metadata": {"source": SOURCE, "add_on": True, "parent_proposal_id": entry_proposal.proposal_id, "strategy_name": definition.name,
                         "decided_at": moment.isoformat(), "stops_monitored": True, "same_bar_exit": "stop_first", "limit_price": None, "needs_review": False},
        }
    )
    if repository.insert_proposal(proposal):
        _publish(publisher, EventType.DECISION_CREATED, f"decision.created:{proposal_id}", bar_end, proposal_id, proposal)
    return _decide(repository, publisher, proposal, starting_cash=starting_cash, moment=moment, settings=settings, mode=mode, review=False)


def is_strategy_position(repository: CoreRepository, symbol: str) -> bool:
    return entry_plan(repository, symbol) is not None


def manage_strategy_positions(repository: CoreRepository, publisher, schedule, starting_cash: Decimal, mode: TradingMode, moment: datetime) -> int:  # type: ignore[no-untyped-def]
    """Queue the exits a strategy position is due on the latest 5-minute bar. Returns exit orders queued."""
    queued = 0
    open_sells = {order.symbol for order in repository.list_orders() if order.side == Side.SELL and order.status in _OPEN_ORDER}
    for position in repository.list_positions():
        if position.quantity <= 0 or position.symbol in open_sells:
            continue
        found = entry_plan(repository, position.symbol)
        if found is None:
            continue
        execution, proposal = found
        plan = proposal.metadata.get("plan") or {}
        bar = repository.latest_candle(position.symbol, Timeframe.M5)
        if bar is None or bar.end <= execution.executed_at:
            continue
        entry = float(execution.price)
        filled_at = execution.executed_at
        # Stops and targets are measured from the price actually paid (planned levels re-based onto the fill).
        rebased_stop, targets, rebased_add_target = rebase_plan(plan, entry)
        stop = float(rebased_stop if rebased_stop is not None else proposal.stop_loss)
        original = execution.quantity
        sold = original - position.quantity
        # Targets already taken = target sells recorded for this entry.
        taken = sum(1 for order in repository.list_orders() if order.side == Side.SELL and order.symbol == position.symbol
                    and str(order.metadata.get("reason", "")).startswith("strategy_target") and order.created_at >= filled_at
                    and order.status not in (OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED))
        added, added_sold, _ = _add_on_state(repository, position.symbol, filled_at)
        added_left = max(0, added - added_sold)
        add_plan = plan.get("add_on") or {}
        add_target = rebased_add_target
        current_stop = stop
        if added and not taken and plan.get("stop_percent") and add_plan.get("restop_from_average"):
            current_stop = float(position.average_price) * (1 - float(plan["stop_percent"]) / 100)  # re-measured from the average cost
        if taken and plan.get("breakeven_after_first_target"):
            current_stop = max(current_stop, entry)
        trailing = plan.get("trailing")
        if trailing:
            history = repository.ohlcv(position.symbol, "5m", filled_at, bar.start)  # bars before the latest one
            best = max([entry] + [row[3] for row in history])
            risk = entry - stop
            if risk > 0 and (best - entry) / risk >= float(trailing.get("activate_after_r") or 0):
                if trailing.get("kind") == "percent":
                    level = best * (1 - float(trailing["value"]) / 100)
                else:
                    atr = _atr_now(repository, position.symbol, int(trailing.get("period") or 14), moment)
                    level = best - float(trailing["value"]) * atr if atr else current_stop
                current_stop = max(current_stop, level)
        low, high, open_ = float(bar.low), float(bar.high), float(bar.open)
        local = bar.end.astimezone(IST)
        exit_quantity, reason, price, fill_at = 0, "", float(bar.close), "next_open"
        # Added shares with their own target are kept out of the initial targets' quantity.
        reserved = added_left if add_target is not None else 0
        initial_left = position.quantity - reserved
        if low <= current_stop:
            label = "strategy_stop" if current_stop == stop or (added and not taken) else ("strategy_breakeven" if math.isclose(current_stop, entry) else "strategy_trailing_stop")
            exit_quantity, reason, price, fill_at = position.quantity, label, min(current_stop, open_), "level"  # a gap down fills at the open
        elif taken < len(targets) and initial_left > 0 and high >= float(targets[taken]["price"]):
            share = int(math.floor(original * float(targets[taken]["fraction"]) + 1e-9))
            last_target = taken == len(targets) - 1
            exit_quantity = initial_left if last_target or share >= initial_left else max(1, share)
            reason, price, fill_at = f"strategy_target_{taken + 1}", max(float(targets[taken]["price"]), open_), "level"  # a gap up fills at the open
        elif reserved > 0 and high >= float(add_target):
            exit_quantity, reason, price, fill_at = reserved, "strategy_add_on_target", max(float(add_target), open_), "level"
        elif plan.get("square_off_intraday") and (local.time() >= SQUARE_OFF or local.date() != filled_at.astimezone(IST).date()):
            exit_quantity, reason = position.quantity, "strategy_square_off"
        elif plan.get("max_hold_bars") and _bars_held(repository, proposal, position.symbol, filled_at, bar.end) >= int(plan["max_hold_bars"]):
            exit_quantity, reason = position.quantity, "strategy_max_hold"
        elif _exit_rule_fired(repository, proposal, position.symbol, moment, filled_at):
            exit_quantity, reason = position.quantity, "strategy_exit_rule"
        if exit_quantity <= 0:
            continue
        if _queue_exit(repository, publisher, position, exit_quantity, Decimal(str(round(price, 2))), bar.end, reason, fill_at, starting_cash, mode):
            queued += 1
    return queued


def _atr_now(repository: CoreRepository, symbol: str, period: int, now: datetime) -> float | None:
    from core_paper.strategy_engine import _atr

    bars = _load(repository, symbol, "5m", now - timedelta(days=10), now)
    if bars is None or len(bars) <= period:
        return None
    value = float(_atr(bars, period)[-1])
    return None if math.isnan(value) else value


def _bars_held(repository: CoreRepository, proposal: TradeProposal, symbol: str, filled_at: datetime, now_end: datetime) -> int:
    """Strategy-timeframe bars since the fill, counting the fill bar: stored sessions for daily strategies."""
    timeframe = str(proposal.metadata.get("timeframe", "1d"))
    if timeframe == "1d":
        return 1 + len(repository.ohlcv(symbol, "1d", filled_at + timedelta(seconds=1), now_end))
    return int((now_end - filled_at).total_seconds() // (TIMEFRAME_MINUTES[timeframe] * 60)) + 1


def _exit_rule_fired(repository: CoreRepository, proposal: TradeProposal, symbol: str, moment: datetime, filled_at: datetime) -> bool:
    found = active_strategy(repository)
    definition = None
    if found is not None and f"user:{found[0]['strategy_id']}" == proposal.strategy_id:
        definition = found[1]
    if definition is None or definition.exit is None:
        return False
    context = strategy_context(repository, definition, symbol, moment)
    if context is None or context.bars.end[-1] <= filled_at:
        return False
    return bool(evaluate(context, definition.exit)[-1])


def _queue_exit(repository, publisher, position, quantity: int, price: Decimal, as_of: datetime, reason: str, fill_at: str, starting_cash: Decimal, mode: TradingMode) -> bool:  # type: ignore[no-untyped-def]
    from core_paper.cycle import _order_event, _publish, _queue
    from core_risk import assess

    book = repository.active_paper_session()
    if book is None:
        return False
    moment = as_of.astimezone(timezone.utc)
    proposal_id = f"exit-{_digest(book.session_id, position.symbol, reason, moment.isoformat())}"
    if repository.order_for_proposal(proposal_id) is not None:
        return False
    proposal = TradeProposal(
        proposal_id=proposal_id,
        symbol=position.symbol,
        timestamp=moment,
        horizon=Horizon.SWING,
        side=Side.SELL,
        quantity=quantity,
        entry_price=price,
        stop_loss=(price * Decimal("1.02")).quantize(_CENT),
        take_profit=(price * Decimal("0.96")).quantize(_CENT),
        strategy_id="strategy-exit",
        strategy_version="1.0.0",
        aggregated_signal=-1,
        aggregated_confidence=1,
        supporting_signal_ids=[proposal_id],
        metadata={"reason": reason, "source": SOURCE, "stops_monitored": True, "same_bar_exit": "stop_first"},
    )
    repository.insert_proposal(proposal)
    decision = assess(proposal, mode=mode, in_universe=True, cash=repository.available_cash(starting_cash), held_quantity=position.quantity, timestamp=moment)
    repository.insert_risk_decision(decision)
    if decision.status != RiskStatus.APPROVED:
        return False
    _queue(repository, proposal, moment, reason=reason, fill_at=fill_at, raw_price=price if fill_at == "level" else None)
    order = repository.order_for_proposal(proposal_id)
    if order is not None:
        kind = _order_event(order)
        _publish(publisher, kind, f"{kind.value}:{order.order_id}", moment, proposal_id, order)
    return order is not None


def expire_strategy_orders(repository: CoreRepository, now: datetime) -> int:
    """Cancel open strategy limit entries past their valid_bars window (entry_valid_until)."""
    from core_paper.operator import OperatorRejected, cancel_order

    book = repository.active_paper_session()
    if book is None:
        return 0
    cancelled = 0
    for order in repository.list_orders():
        if order.side != Side.BUY or order.status != OrderStatus.OPEN:
            continue
        proposal = repository.get_proposal(order.proposal_id)
        if proposal is None or proposal.metadata.get("source") != SOURCE:
            continue
        until = proposal.metadata.get("entry_valid_until")
        if not until or datetime.fromisoformat(str(until)) > now.astimezone(timezone.utc):
            continue
        try:
            cancel_order(repository, session_id=book.session_id, order_id=order.order_id, operator_id="strategy", reason="limit_valid_bars_expired", expected_status="OPEN", now=now)
            cancelled += 1
        except OperatorRejected:
            continue
    return cancelled
