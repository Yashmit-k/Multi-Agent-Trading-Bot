"""Historical replay through the same fusion, proposal, and risk functions as paper.

Fills use the next stored bar. A signal on the last bar does not fill at that bar's close.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Horizon, OrderType, Side, Timeframe, TradingMode
from contracts.fakes import FakeSignalSink
from contracts.schemas.market import Candle
from contracts.schemas.position import Position
from core_decision.propose import build_proposal
from core_features.engine import FEATURE_VERSION, build_feature_set
from core_fusion import fuse
from core_paper.costs import CostSchedule, fee_on, slipped_price
from core_paper.cycle import next_position
from core_risk import assess

MAX_NOTIONAL = Decimal("100000")
_CENT = Decimal("0.01")
FIVE_MINUTE_PERIODS = 75 * 252
DAILY_PERIODS = 252


@dataclass
class _Working:
    proposal: object
    order_type: OrderType
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    reason: str = "entry"


@dataclass
class _Book:
    cash: Decimal
    positions: dict[str, Position] = field(default_factory=dict)
    pending: dict[str, _Working] = field(default_factory=dict)
    trades: list[dict[str, object]] = field(default_factory=list)
    equity: list[dict[str, object]] = field(default_factory=list)
    signals: int = 0
    orders: int = 0
    fills: int = 0
    fees: Decimal = Decimal("0")
    slippage_pnl: Decimal = Decimal("0")
    gross_pnl: Decimal = Decimal("0")
    kill: bool = False
    opened_at: dict[str, datetime] = field(default_factory=dict)


def periods_per_year(timeframe: str) -> int:
    if timeframe == "5m":
        return FIVE_MINUTE_PERIODS
    return DAILY_PERIODS


def exit_on_bar(side: Side, stop: Decimal, target: Decimal, bar: Candle) -> str | None:
    """If one bar contains both exits, the stop wins."""
    if side == Side.BUY:
        stopped = bar.low <= stop
        targeted = bar.high >= target
    else:
        stopped = bar.high >= stop
        targeted = bar.low <= target
    if stopped:
        return "stop"
    if targeted:
        return "target"
    return None


def run_backtest(
    candles: list[Candle],
    *,
    symbols: tuple[str, ...],
    timeframe: str,
    start: datetime,
    end: datetime,
    snapshot_id: str,
    candle_sha256: str,
    initial_cash: Decimal,
    schedule: CostSchedule,
    missing_candles: int = 0,
    max_position_notional: Decimal = MAX_NOTIONAL,
    kill_after: datetime | None = None,
    seed: int = 0,
    index_bars: dict[str, list[Candle]] | None = None,
) -> dict[str, object]:
    frame = Timeframe(timeframe)
    horizon = Horizon.INTRADAY if frame == Timeframe.M5 else Horizon.SWING
    window_start = start.astimezone(timezone.utc)
    window_end = end.astimezone(timezone.utc)
    by_symbol: dict[str, list[Candle]] = defaultdict(list)
    for bar in candles:
        if bar.timeframe == frame and bar.symbol in symbols:
            by_symbol[bar.symbol].append(bar)
    for bars in by_symbol.values():
        bars.sort(key=lambda item: item.end)
    book = _Book(cash=initial_cash)
    stamps = sorted({bar.end.astimezone(timezone.utc) for bars in by_symbol.values() for bar in bars if bar.end.astimezone(timezone.utc) <= window_end})
    for stamp in stamps:
        if kill_after is not None and stamp >= kill_after.astimezone(timezone.utc):
            book.kill = True
        for symbol in symbols:
            bars = by_symbol.get(symbol, [])
            index = next((cursor for cursor, bar in enumerate(bars) if bar.end.astimezone(timezone.utc) == stamp), None)
            if index is None:
                continue
            bar = bars[index]
            _fill_pending(book, symbol, bar, schedule)
            if book.kill and symbol in book.positions:
                _flatten(book, symbol, bar.open, stamp, schedule, reason="kill_switch")
            elif symbol in book.positions and index > 0:
                _guard_exit(book, symbol, bar, schedule)
            _mark(book, symbol, bar.close, stamp)
            if window_start <= stamp <= window_end:
                _decide(
                    book,
                    symbol,
                    bars[: index + 1],
                    stamp,
                    horizon,
                    frame,
                    schedule,
                    max_position_notional,
                    index_bars or {},
                )
        book.equity.append({"timestamp": stamp.isoformat(), "equity": str(_equity(book))})
    metrics = summarize(book, initial_cash, timeframe, missing_candles)
    return {
        "snapshot_id": snapshot_id,
        "candle_sha256": candle_sha256,
        "strategy_id": "paper-fusion",
        "strategy_version": "1.0.0",
        "feature_version": FEATURE_VERSION,
        "timeframe": timeframe,
        "start": window_start.isoformat(),
        "end": window_end.isoformat(),
        "symbols": list(symbols),
        "initial_cash": str(initial_cash),
        "transaction_cost_bps": None if schedule.flat_bps is None else str(schedule.flat_bps),
        "slippage_bps": str(schedule.slippage_bps),
        "cost_schedule": {
            "brokerage_rate": str(schedule.brokerage_rate),
            "exchange_rate": str(schedule.exchange_rate),
            "stt_rate": str(schedule.stt_rate),
            "gst_rate": str(schedule.gst_rate),
            "stamp_rate": str(schedule.stamp_rate),
            "sebi_rate": str(schedule.sebi_rate),
            "flat_bps": None if schedule.flat_bps is None else str(schedule.flat_bps),
            "slippage_bps": str(schedule.slippage_bps),
        },
        "seed": seed,
        "live_enabled": False,
        "candles_processed": sum(1 for bars in by_symbol.values() for bar in bars if window_start <= bar.end.astimezone(timezone.utc) <= window_end),
        "signals_generated": book.signals,
        "orders_generated": book.orders,
        "orders_filled": book.fills,
        "positions": {symbol: position.quantity for symbol, position in book.positions.items()},
        "portfolio_value": str(_equity(book)),
        "trades": book.trades,
        "equity_curve": book.equity,
        "missing_candles": missing_candles,
        "performance": metrics,
    }


def summarize(book: _Book, initial_cash: Decimal, timeframe: str, missing_candles: int) -> dict[str, object]:
    equities = [Decimal(point["equity"]) for point in book.equity]
    returns = [float((equities[index] / equities[index - 1]) - 1) for index in range(1, len(equities)) if equities[index - 1] > 0]
    periods = periods_per_year(timeframe)
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    duration = 0
    longest = 0
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0 and equity < peak:
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)
            duration += 1
            longest = max(longest, duration)
        else:
            duration = 0
    closed = [trade for trade in book.trades if trade["reason"] != "entry"]
    wins = [Decimal(str(trade["pnl"])) for trade in closed if Decimal(str(trade["pnl"])) > 0]
    losses = [Decimal(str(trade["pnl"])) for trade in closed if Decimal(str(trade["pnl"])) < 0]
    pnls = [Decimal(str(trade["pnl"])) for trade in closed]
    gross = book.gross_pnl
    net = _equity(book) - initial_cash
    total_return = float(net / initial_cash) if initial_cash else 0.0
    annualized = (sum(returns) / len(returns) * periods) if returns else 0.0
    calmar = annualized / float(max_drawdown) if max_drawdown else None
    return {
        "total_return": total_return,
        "cumulative_pnl": str(net),
        "gross_pnl": str(gross),
        "transaction_costs": str(book.fees),
        "slippage": str(book.slippage_pnl),
        "net_pnl": str(net),
        "max_drawdown": str(max_drawdown),
        "drawdown_duration_bars": longest,
        "volatility": _scale(_stdev(returns), periods),
        "downside_volatility": _scale(_downside(returns), periods),
        "sharpe": _ratio(returns, _stdev(returns), periods),
        "sortino": _ratio(returns, _downside(returns), periods),
        "calmar": calmar,
        "periods_per_year": periods,
        "trades": len(closed),
        "win_rate": float(len(wins) / len(closed)) if closed else 0.0,
        "average_win": str(sum(wins, Decimal("0")) / len(wins)) if wins else "0",
        "average_loss": str(sum(losses, Decimal("0")) / len(losses)) if losses else "0",
        "profit_factor": str(sum(wins, Decimal("0")) / abs(sum(losses, Decimal("0")))) if losses else None,
        "average_trade_pnl": str(sum(pnls, Decimal("0")) / len(pnls)) if pnls else "0",
        "median_trade_pnl": str(sorted(pnls)[len(pnls) // 2]) if pnls else "0",
        "turnover": str(sum((Decimal(str(trade["notional"])) for trade in book.trades), Decimal("0"))),
        "gross_exposure": str(sum((abs(position.market_value) for position in book.positions.values()), Decimal("0"))),
        "net_exposure": str(sum((position.market_value for position in book.positions.values()), Decimal("0"))),
        "average_holding_seconds": _average_hold(closed),
        "daily_pnl": _daily_pnl(book.equity),
        "missing_candles": missing_candles,
    }


def _decide(book, symbol, visible, stamp, horizon, frame, schedule, max_notional, index_bars) -> None:
    if symbol in book.pending or symbol in book.positions or book.kill:
        return
    nifty_return = _index_return(index_bars.get("NIFTY50", []), stamp)
    feature_set = build_feature_set(symbol, frame, visible, stamp, nifty_return=nifty_return)
    if feature_set is None:
        return
    index_sets = tuple(
        item
        for item in (
            build_feature_set(name, frame, _recent(bars, stamp), stamp)
            for name, bars in index_bars.items()
        )
        if item is not None and item.timestamp <= stamp
    )
    signals = _agent_signals(symbol, feature_set, stamp, horizon, frame, index_sets)
    book.signals += len(signals)
    aggregate = fuse(signals, horizon=horizon, as_of=stamp)
    if aggregate is None:
        return
    proposal = build_proposal(aggregate, visible[-1], stamp)
    if proposal is None or proposal.side != Side.BUY:
        return
    quantity = _shares(book.cash, proposal.entry_price, max_notional, schedule)
    if quantity < 1:
        return
    proposal = proposal.model_copy(update={"quantity": quantity})
    decision = assess(
        proposal,
        mode=TradingMode.PAPER,
        in_universe=True,
        cash=book.cash,
        held_quantity=book.positions[symbol].quantity if symbol in book.positions else 0,
        timestamp=stamp,
    )
    if decision.status.value != "APPROVED":
        return
    book.orders += 1
    book.pending[symbol] = _Working(proposal=proposal, order_type=OrderType.MARKET)


def limit_touched(limit: Decimal, bar: Candle) -> bool:
    return bar.low <= limit <= bar.high


def _stop_breached(stop: Decimal, bar: Candle) -> bool:
    return bar.low <= stop <= bar.high


def _fill_pending(book: _Book, symbol: str, bar: Candle, schedule: CostSchedule) -> None:
    working = book.pending.get(symbol)
    if working is None:
        return
    if working.order_type == OrderType.MARKET:
        filled = _apply(
            book,
            symbol,
            working.proposal,
            bar.open,
            bar.end,
            schedule,
            reason=working.reason,
            reference=bar.open,
        )
        if filled:
            book.pending.pop(symbol, None)
            book.opened_at[symbol] = bar.end
        return
    if working.order_type == OrderType.LIMIT and working.limit_price is not None and limit_touched(working.limit_price, bar):
        filled = _apply(book, symbol, working.proposal, working.limit_price, bar.end, schedule, reason=working.reason, reference=working.limit_price)
        if filled:
            book.pending.pop(symbol, None)
            book.opened_at[symbol] = bar.end
        return
    if working.order_type == OrderType.STOP_LOSS_MARKET and working.stop_price is not None and _stop_breached(working.stop_price, bar):
        working.order_type = OrderType.MARKET
        return
    if (
        working.order_type == OrderType.STOP_LOSS
        and working.stop_price is not None
        and working.limit_price is not None
        and _stop_breached(working.stop_price, bar)
        and limit_touched(working.limit_price, bar)
    ):
        filled = _apply(book, symbol, working.proposal, working.limit_price, bar.end, schedule, reason=working.reason, reference=working.limit_price)
        if filled:
            book.pending.pop(symbol, None)


def _guard_exit(book: _Book, symbol: str, bar: Candle, schedule: CostSchedule) -> None:
    position = book.positions.get(symbol)
    if position is None:
        return
    # The entry proposal's brackets are stored on the last entry trade.
    entry = next(trade for trade in reversed(book.trades) if trade["symbol"] == symbol and trade["reason"] == "entry")
    stop = Decimal(str(entry["stop_loss"]))
    target = Decimal(str(entry["take_profit"]))
    reason = exit_on_bar(Side.BUY, stop, target, bar)
    if reason == "stop":
        _flatten(book, symbol, stop, bar.end, schedule, reason="stop")
    elif reason == "target":
        _flatten(book, symbol, target, bar.end, schedule, reason="target")


def _flatten(book, symbol, price, stamp, schedule, reason: str) -> None:
    position = book.positions.get(symbol)
    if position is None or position.quantity <= 0:
        return
    _apply(book, symbol, None, price, stamp, schedule, reason=reason, reference=price)


def _apply(book, symbol, proposal, raw_price, stamp, schedule, reason: str, reference: Decimal) -> bool:
    side = proposal.side if reason == "entry" else Side.SELL
    quantity = proposal.quantity if reason == "entry" else book.positions[symbol].quantity
    fill = slipped_price(side, raw_price, schedule.slippage_bps).quantize(_CENT)
    notional = fill * quantity
    fees = fee_on(notional, schedule).quantize(_CENT)
    slip = (abs(fill - reference) * quantity).quantize(_CENT)
    if side == Side.BUY:
        if notional + fees > book.cash:
            return False
        book.cash -= notional + fees
    else:
        book.cash += notional - fees
    current = book.positions.get(symbol)
    updated = next_position(current, symbol, side, quantity, fill, stamp)
    if updated.quantity == 0:
        book.positions.pop(symbol, None)
    else:
        book.positions[symbol] = updated
    entry_price = current.average_price if current is not None and side == Side.SELL else fill
    pnl = ((fill - entry_price) * quantity - fees) if side == Side.SELL and current is not None else Decimal("0")
    if side == Side.SELL and current is not None:
        entry_reference = current.average_price
        for item in reversed(book.trades):
            if item["symbol"] == symbol and item["reason"] == "entry":
                entry_reference = Decimal(str(item["reference_price"]))
                break
        book.gross_pnl += (reference - entry_reference) * quantity
    book.fees += fees
    book.slippage_pnl += slip
    book.fills += 1
    opened = book.opened_at.get(symbol, stamp)
    book.trades.append(
        {
            "symbol": symbol,
            "side": side.value,
            "quantity": quantity,
            "price": str(fill),
            "reference_price": str(reference),
            "fees": str(fees),
            "slippage": str(slip),
            "notional": str(abs(notional)),
            "pnl": str(pnl.quantize(_CENT)),
            "reason": reason,
            "timestamp": stamp.isoformat(),
            "stop_loss": str(proposal.stop_loss) if reason == "entry" else None,
            "take_profit": str(proposal.take_profit) if reason == "entry" else None,
            "holding_seconds": None if reason == "entry" else (stamp - opened).total_seconds(),
        }
    )
    return True


def _mark(book: _Book, symbol: str, price: Decimal, stamp: datetime) -> None:
    position = book.positions.get(symbol)
    if position is None:
        return
    unrealized = (price - position.average_price) * position.quantity
    book.positions[symbol] = position.model_copy(
        update={"market_price": price, "market_value": price * position.quantity, "unrealized_pnl": unrealized, "updated_at": stamp}
    )


def _shares(cash: Decimal, price: Decimal, max_notional: Decimal, schedule: CostSchedule) -> int:
    if price <= 0:
        return 0
    quantity = int(min(cash, max_notional) / price)
    while quantity > 0:
        fill = slipped_price(Side.BUY, price, schedule.slippage_bps)
        notional = fill * quantity
        if notional <= max_notional and notional + fee_on(notional, schedule) <= cash:
            return quantity
        quantity -= 1
    return 0


def _equity(book: _Book) -> Decimal:
    return book.cash + sum((item.market_value for item in book.positions.values()), Decimal("0"))


def _agent_signals(symbol, feature_set, stamp, horizon, frame, index_sets=()):
    from quant_agents.paper import publish_symbol_signals

    symbols = tuple(item.symbol for item in index_sets) or ()
    sink = FakeSignalSink()
    publish_symbol_signals(
        symbol,
        feature_set,
        sink,
        configuration={"horizon": horizon, "timeframe": frame, "regime_index_symbols": symbols},
        index_sets=index_sets,
    )
    return sink.submitted


def _recent(bars: list[Candle], stamp: datetime, limit: int = 80) -> list[Candle]:
    visible = [bar for bar in bars if bar.end.astimezone(timezone.utc) <= stamp.astimezone(timezone.utc)]
    return visible[-limit:]


def _index_return(bars: list[Candle], stamp: datetime) -> float | None:
    visible = [bar for bar in bars if bar.end.astimezone(timezone.utc) <= stamp.astimezone(timezone.utc)]
    if len(visible) < 2 or visible[-2].close == 0:
        return None
    return float(visible[-1].close / visible[-2].close - 1)


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((item - mean) ** 2 for item in values) / (len(values) - 1))


def _downside(values: list[float]) -> float:
    losses = [item for item in values if item < 0]
    if len(losses) < 2:
        return 0.0
    return math.sqrt(sum(item**2 for item in losses) / (len(losses) - 1))


def _scale(deviation: float, periods: int) -> float | None:
    if deviation == 0:
        return None
    return deviation * math.sqrt(periods)


def _ratio(values: list[float], deviation: float, periods: int) -> float | None:
    if len(values) < 2 or deviation == 0:
        return None
    return (sum(values) / len(values)) / deviation * math.sqrt(periods)


def _average_hold(trades: list[dict[str, object]]) -> float | None:
    holds = [float(trade["holding_seconds"]) for trade in trades if trade.get("holding_seconds") is not None]
    if not holds:
        return None
    return sum(holds) / len(holds)


def _daily_pnl(equity: list[dict[str, object]]) -> list[dict[str, str]]:
    by_day: dict[str, Decimal] = {}
    for point in equity:
        by_day[str(point["timestamp"])[:10]] = Decimal(str(point["equity"]))
    days = sorted(by_day)
    rows: list[dict[str, str]] = []
    previous = by_day[days[0]] if days else Decimal("0")
    for day in days:
        rows.append({"date": day, "pnl": str(by_day[day] - previous)})
        previous = by_day[day]
    return rows
