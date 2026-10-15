"""Strategy lab: user-built rule strategies, backtested on stored NSE candles.

A strategy is plain JSON: entry conditions (all must hold), exit conditions (any), optional
stop / target / maximum hold / 15:15 square-off, and position size. Conditions compare two
operands, where each operand is an indicator (EMA, SMA, RSI, MACD, Bollinger, ATR, volume,
return, highest, lowest, price) or a number.

Rules of the simulation:
- no look-ahead: a condition is evaluated on a bar's close and acted on at the next bar's open;
- one position per symbol, fixed rupee size per trade, whole shares;
- Zerodha delivery (CNC) charges on both legs plus slippage on every fill;
- a stop fills at min(open, stop), a target at max(open, target); if one bar touches both, the stop wins;
- portfolio pass: trades are taken in entry order while a position slot and the cash are free.
Results are in-sample: a rule tuned on this data will look better here than it will trade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

IST = ZoneInfo("Asia/Kolkata")
SQUARE_OFF = time(15, 15)
MAX_5M_SYMBOLS = 10
MAX_5M_DAYS = 400
MAX_TRADES_LISTED = 1500

Indicator = Literal[
    "close", "open", "high", "low", "volume",
    "sma", "ema", "rsi", "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "atr", "atr_pct", "volume_sma", "return_pct", "highest", "lowest",
]
NEEDS_PERIOD = {"sma", "ema", "rsi", "bb_upper", "bb_lower", "atr", "atr_pct", "volume_sma", "return_pct", "highest", "lowest"}
LABELS = {
    "close": "Close", "open": "Open", "high": "High", "low": "Low", "volume": "Volume",
    "sma": "SMA", "ema": "EMA", "rsi": "RSI", "macd": "MACD line (12, 26)", "macd_signal": "MACD signal (9)",
    "macd_hist": "MACD histogram", "bb_upper": "Bollinger upper (2σ)", "bb_lower": "Bollinger lower (2σ)",
    "atr": "ATR", "atr_pct": "ATR % of close", "volume_sma": "Average volume", "return_pct": "Return % over N bars",
    "highest": "Highest high of previous N bars", "lowest": "Lowest low of previous N bars",
}


class Operand(BaseModel):
    indicator: Indicator | None = None
    period: int | None = Field(default=None, ge=1, le=400)
    value: float | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> "Operand":
        if (self.indicator is None) == (self.value is None):
            raise ValueError("an operand is either an indicator or a number")
        if self.indicator in NEEDS_PERIOD and self.period is None:
            raise ValueError(f"{self.indicator} needs a period")
        return self

    def label(self) -> str:
        if self.value is not None:
            return f"{self.value:g}"
        name = LABELS[self.indicator or "close"]
        return f"{name}({self.period})" if self.indicator in NEEDS_PERIOD else name


class Condition(BaseModel):
    left: Operand
    op: Literal[">", "<", ">=", "<=", "crosses_above", "crosses_below"]
    right: Operand

    def label(self) -> str:
        words = {"crosses_above": "crosses above", "crosses_below": "crosses below"}
        return f"{self.left.label()} {words.get(self.op, self.op)} {self.right.label()}"


class StrategyDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    timeframe: Literal["1d", "5m"] = "1d"
    symbols: list[str] = Field(default_factory=lambda: ["ALL"], min_length=1, max_length=60)
    entry: list[Condition] = Field(min_length=1, max_length=8)
    exit: list[Condition] = Field(default_factory=list, max_length=8)
    stop_loss_pct: float | None = Field(default=2.0, gt=0, le=50)
    take_profit_pct: float | None = Field(default=4.0, gt=0, le=200)
    max_hold_bars: int | None = Field(default=None, ge=1, le=5000)
    square_off_intraday: bool = False
    position_notional: float = Field(default=20000, ge=1000, le=100000)
    max_open_positions: int = Field(default=10, ge=1, le=50)
    initial_cash: float = Field(default=500000, ge=10000, le=100_000_000)
    slippage_bps: float = Field(default=5, ge=0, le=100)

    @field_validator("symbols")
    @classmethod
    def _upper(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().upper() for item in value if item.strip()})


class BacktestRequest(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _order(self) -> "BacktestRequest":
        if self.end < self.start:
            raise ValueError("end is before start")
        return self


# --- indicators -----------------------------------------------------------------------------------


@dataclass
class Bars:
    end: list[datetime]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    sums = np.cumsum(np.insert(values, 0, 0.0))
    out[period - 1 :] = (sums[period:] - sums[:-period]) / period
    return out


def _rolling(values: np.ndarray, period: int, fn) -> np.ndarray:  # type: ignore[no-untyped-def]
    out = np.full(len(values), np.nan)
    for i in range(period, len(values)):
        out[i] = fn(values[i - period : i])  # previous N bars, excluding the current one
    return out


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) <= period:
        return out
    change = np.diff(close)
    gain, loss = np.clip(change, 0, None), np.clip(-change, 0, None)
    avg_gain, avg_loss = gain[:period].mean(), loss[:period].mean()
    for i in range(period, len(close)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def _atr(bars: Bars, period: int) -> np.ndarray:
    previous = np.concatenate([[bars.close[0]], bars.close[:-1]])
    true_range = np.maximum(bars.high - bars.low, np.maximum(abs(bars.high - previous), abs(bars.low - previous)))
    return _ema(true_range, period)


def indicator(bars: Bars, operand: Operand, cache: dict) -> np.ndarray:
    key = (operand.indicator, operand.period, operand.value)
    if key in cache:
        return cache[key]
    n = len(bars.close)
    kind, period = operand.indicator, operand.period or 0
    if operand.value is not None:
        out = np.full(n, float(operand.value))
    elif kind in ("close", "open", "high", "low", "volume"):
        out = getattr(bars, kind).astype(float)
    elif kind == "sma":
        out = _sma(bars.close, period)
    elif kind == "ema":
        out = _ema(bars.close, period)
    elif kind == "rsi":
        out = _rsi(bars.close, period)
    elif kind in ("macd", "macd_signal", "macd_hist"):
        line = _ema(bars.close, 12) - _ema(bars.close, 26)
        valid = ~np.isnan(line)
        signal = np.full(n, np.nan)
        if valid.sum() >= 9:
            first = int(np.argmax(valid))
            signal[first:] = _ema(line[first:], 9)
        out = {"macd": line, "macd_signal": signal, "macd_hist": line - signal}[kind]
    elif kind in ("bb_upper", "bb_lower"):
        mid = _sma(bars.close, period)
        std = np.full(n, np.nan)
        for i in range(period - 1, n):
            std[i] = bars.close[i - period + 1 : i + 1].std()
        out = mid + 2 * std if kind == "bb_upper" else mid - 2 * std
    elif kind == "atr":
        out = _atr(bars, period)
    elif kind == "atr_pct":
        out = _atr(bars, period) / bars.close * 100
    elif kind == "volume_sma":
        out = _sma(bars.volume.astype(float), period)
    elif kind == "return_pct":
        out = np.full(n, np.nan)
        out[period:] = (bars.close[period:] / bars.close[:-period] - 1) * 100
    elif kind == "highest":
        out = _rolling(bars.high, period, np.max)
    elif kind == "lowest":
        out = _rolling(bars.low, period, np.min)
    else:  # pragma: no cover - guarded by the Literal type
        raise ValueError(kind)
    cache[key] = out
    return out


def evaluate(bars: Bars, conditions: list[Condition], *, mode: str) -> np.ndarray:
    """Boolean per bar: all conditions (mode="all") or any (mode="any"). NaN never passes."""
    n = len(bars.close)
    if not conditions:
        return np.zeros(n, dtype=bool)
    cache: dict = {}
    results = []
    for condition in conditions:
        left, right = indicator(bars, condition.left, cache), indicator(bars, condition.right, cache)
        with np.errstate(invalid="ignore"):
            if condition.op in (">", "<", ">=", "<="):
                passed = {">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[condition.op]
            else:
                prev_left, prev_right = np.roll(left, 1), np.roll(right, 1)
                prev_left[0] = prev_right[0] = np.nan
                if condition.op == "crosses_above":
                    passed = (left > right) & (prev_left <= prev_right)
                else:
                    passed = (left < right) & (prev_left >= prev_right)
        valid = ~(np.isnan(left) | np.isnan(right))
        results.append(passed & valid)
    stack = np.vstack(results)
    return stack.all(axis=0) if mode == "all" else stack.any(axis=0)


# --- simulation -----------------------------------------------------------------------------------


@dataclass
class Trade:
    symbol: str
    entry_at: datetime
    exit_at: datetime
    entry_price: float
    exit_price: float
    quantity: int
    reason: str
    charges: float
    net_pnl: float
    bars_held: int


def _charges(notional: float, *, buy: bool) -> float:
    from core_paper.charges import ZERODHA_EQUITY_RI, delivery_buy, delivery_sell

    value = Decimal(str(round(notional, 2)))
    quote = delivery_buy(value, ZERODHA_EQUITY_RI) if buy else delivery_sell(value, ZERODHA_EQUITY_RI, include_dp=True)
    return float(quote.total)


def simulate_symbol(symbol: str, bars: Bars, strategy: StrategyDefinition, first_index: int) -> list[Trade]:
    entries = evaluate(bars, strategy.entry, mode="all")
    exits = evaluate(bars, strategy.exit, mode="any")
    slip = strategy.slippage_bps / 10_000
    clocks = [moment.astimezone(IST) for moment in bars.end]
    trades: list[Trade] = []
    n = len(bars.close)
    i = max(first_index, 1)
    while i < n:
        if not entries[i - 1] or i - 1 < first_index:
            i += 1
            continue
        if strategy.timeframe == "5m" and strategy.square_off_intraday and clocks[i].time() > SQUARE_OFF:
            i += 1  # no new intraday entry after the square-off time
            continue
        entry_price = float(bars.open[i]) * (1 + slip)
        quantity = int(strategy.position_notional // entry_price)
        if quantity < 1:
            i += 1
            continue
        stop = entry_price * (1 - strategy.stop_loss_pct / 100) if strategy.stop_loss_pct else None
        target = entry_price * (1 + strategy.take_profit_pct / 100) if strategy.take_profit_pct else None
        exit_index, exit_raw, reason = n - 1, float(bars.close[n - 1]), "end_of_data"
        j = i
        while j < n:
            # On the entry bar the fill was the open, so a touch later in that bar fills at the level itself.
            if stop is not None and bars.low[j] <= stop:
                exit_index, exit_raw, reason = j, min(float(bars.open[j]), stop) if j > i else stop, "stop"
                break
            if target is not None and bars.high[j] >= target:
                exit_index, exit_raw, reason = j, max(float(bars.open[j]), target) if j > i else target, "target"
                break
            if strategy.timeframe == "5m" and strategy.square_off_intraday:
                same_day = clocks[j].date() == clocks[i].date()
                if not same_day:
                    exit_index, exit_raw, reason = j - 1, float(bars.close[j - 1]), "square_off"
                    break
                if clocks[j].time() >= SQUARE_OFF:
                    exit_index, exit_raw, reason = j, float(bars.close[j]), "square_off"
                    break
            if strategy.max_hold_bars and j - i + 1 >= strategy.max_hold_bars:
                exit_index, exit_raw, reason = j, float(bars.close[j]), "max_hold"
                break
            if exits[j] and j + 1 < n:
                exit_index, exit_raw, reason = j + 1, float(bars.open[j + 1]), "exit_rule"
                break
            j += 1
        exit_price = exit_raw * (1 - slip)
        bought, sold = entry_price * quantity, exit_price * quantity
        charges = _charges(bought, buy=True) + _charges(sold, buy=False)
        trades.append(
            Trade(symbol, bars.end[i], bars.end[exit_index], entry_price, exit_price, quantity, reason, charges, sold - bought - charges, exit_index - i + 1)
        )
        i = exit_index + 1
    return trades


def portfolio(trades: list[Trade], strategy: StrategyDefinition) -> tuple[list[Trade], list[Trade]]:
    """Take trades in entry order while a slot and the cash are free. Returns (taken, skipped)."""
    taken: list[Trade] = []
    skipped: list[Trade] = []
    open_trades: list[Trade] = []
    cash = strategy.initial_cash
    for trade in sorted(trades, key=lambda item: (item.entry_at, item.symbol)):
        for item in [t for t in open_trades if t.exit_at <= trade.entry_at]:
            open_trades.remove(item)
            cash += item.exit_price * item.quantity - _charges(item.exit_price * item.quantity, buy=False)
        cost = trade.entry_price * trade.quantity
        if len(open_trades) >= strategy.max_open_positions or cost + _charges(cost, buy=True) > cash:
            skipped.append(trade)
            continue
        cash -= cost + _charges(cost, buy=True)
        open_trades.append(trade)
        taken.append(trade)
    return taken, skipped


def equity_curve(taken: list[Trade], closes: dict[str, dict[date, float]], days: list[date], initial: float) -> list[dict[str, object]]:
    """End-of-day equity: initial cash + realized P&L + open positions marked at that day's close."""
    curve = []
    for day in days:
        realized = sum(t.net_pnl for t in taken if t.exit_at.astimezone(IST).date() <= day)
        unrealized = 0.0
        for t in taken:
            if t.entry_at.astimezone(IST).date() <= day < t.exit_at.astimezone(IST).date():
                mark = closes.get(t.symbol, {}).get(day)
                if mark is not None:
                    unrealized += (mark - t.entry_price) * t.quantity
        curve.append({"date": day.isoformat(), "equity": round(initial + realized + unrealized, 2)})
    return curve


def metrics(taken: list[Trade], curve: list[dict[str, object]], initial: float) -> dict[str, object]:
    nets = [t.net_pnl for t in taken]
    wins, losses = [v for v in nets if v > 0], [-v for v in nets if v < 0]
    equity = np.array([float(point["equity"]) for point in curve]) if curve else np.array([initial])
    returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
    peak = np.maximum.accumulate(equity)
    years = max(len(equity) / 250, 1 / 250)
    final = float(equity[-1])
    reasons: dict[str, int] = {}
    for t in taken:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return {
        "trades": len(taken),
        "win_rate": len(wins) / len(nets) if nets else None,
        "net_pnl": round(sum(nets), 2),
        "charges": round(sum(t.charges for t in taken), 2),
        "total_return": final / initial - 1,
        "cagr": (final / initial) ** (1 / years) - 1 if final > 0 else None,
        "sharpe": float(returns.mean() / returns.std(ddof=1) * math.sqrt(250)) if len(returns) > 2 and returns.std(ddof=1) > 0 else None,
        "max_drawdown": float(np.max(1 - equity / peak)) if len(equity) else 0.0,
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
        "average_win": float(np.mean(wins)) if wins else None,
        "average_loss": float(-np.mean(losses)) if losses else None,
        "average_bars_held": float(np.mean([t.bars_held for t in taken])) if taken else None,
        "exit_reasons": reasons,
    }


def run_strategy(
    strategy: StrategyDefinition,
    request: BacktestRequest,
    load_bars,  # (symbol, timeframe, start, end) -> Bars | None
    universe: list[str],
    benchmark: Bars | None = None,
) -> dict[str, object]:
    symbols = universe if strategy.symbols == ["ALL"] else [s for s in strategy.symbols if s in set(universe)]
    if not symbols:
        raise ValueError("no known symbols selected")
    if strategy.timeframe == "5m":
        if len(symbols) > MAX_5M_SYMBOLS:
            raise ValueError(f"5-minute backtests are limited to {MAX_5M_SYMBOLS} symbols on this server")
        if (request.end - request.start).days > MAX_5M_DAYS:
            raise ValueError(f"5-minute backtests are limited to {MAX_5M_DAYS} days on this server")
    start = datetime.combine(request.start, time(0), IST).astimezone(timezone.utc)
    end = datetime.combine(request.end, time(23, 59), IST).astimezone(timezone.utc)
    warmup = timedelta(days=400) if strategy.timeframe == "1d" else timedelta(days=10)
    all_trades: list[Trade] = []
    closes: dict[str, dict[date, float]] = {}
    days: set[date] = set()
    for symbol in symbols:
        bars = load_bars(symbol, strategy.timeframe, start - warmup, end)
        if bars is None or len(bars.close) < 2:
            continue
        first = next((k for k, moment in enumerate(bars.end) if moment >= start), len(bars.end))
        all_trades += simulate_symbol(symbol, bars, strategy, first)
        daily: dict[date, float] = {}
        for moment, close in zip(bars.end, bars.close):
            if moment >= start:
                day = moment.astimezone(IST).date()
                daily[day] = float(close)
                days.add(day)
        closes[symbol] = daily
    taken, skipped = portfolio(all_trades, strategy)
    ordered_days = sorted(days)
    curve = equity_curve(taken, closes, ordered_days, strategy.initial_cash)
    result = metrics(taken, curve, strategy.initial_cash)
    half = ordered_days[len(ordered_days) // 2] if ordered_days else None
    halves = {}
    if half is not None:
        first_half = [t for t in taken if t.entry_at.astimezone(IST).date() < half]
        second_half = [t for t in taken if t.entry_at.astimezone(IST).date() >= half]
        halves = {
            "split_date": half.isoformat(),
            "first_half": {"trades": len(first_half), "net_pnl": round(sum(t.net_pnl for t in first_half), 2)},
            "second_half": {"trades": len(second_half), "net_pnl": round(sum(t.net_pnl for t in second_half), 2)},
        }
    bench = None
    if benchmark is not None and len(benchmark.close):
        points = [(m.astimezone(IST).date(), float(c)) for m, c in zip(benchmark.end, benchmark.close) if start <= m <= end]
        if len(points) > 1:
            base = points[0][1]
            bench = {
                "symbol": "NIFTY50",
                "total_return": points[-1][1] / base - 1,
                "curve": [{"date": d.isoformat(), "equity": round(strategy.initial_cash * c / base, 2)} for d, c in points],
            }
    return {
        "kind": "strategy_lab",
        "strategy": strategy.model_dump(mode="json"),
        "rules": {"entry": [c.label() for c in strategy.entry], "exit": [c.label() for c in strategy.exit]},
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "symbols_tested": len(closes),
        "signals_considered": len(all_trades),
        "trades_skipped_by_portfolio": len(skipped),
        "metrics": result,
        "halves": halves,
        "benchmark": bench,
        "equity_curve": curve,
        "trades": [
            {
                "symbol": t.symbol,
                "entry_at": t.entry_at.isoformat(),
                "exit_at": t.exit_at.isoformat(),
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "quantity": t.quantity,
                "reason": t.reason,
                "charges": round(t.charges, 2),
                "net_pnl": round(t.net_pnl, 2),
                "bars_held": t.bars_held,
            }
            for t in sorted(taken, key=lambda item: item.entry_at)[-MAX_TRADES_LISTED:]
        ],
        "trades_listed_limit": MAX_TRADES_LISTED,
        "live_enabled": False,
        "notes": [
            "In-sample: this is the data the rule was written against. Expect live results to be worse.",
            "Signals use the bar close and fill at the next bar's open, so no future data is used.",
            "Charges are Zerodha delivery (CNC) on both legs, plus slippage on each fill.",
        ],
    }


TEMPLATES: list[dict[str, object]] = [
    {
        "name": "EMA 20/50 crossover",
        "description": "Buy when the 20-day EMA crosses above the 50-day EMA; sell when it crosses back below.",
        "timeframe": "1d",
        "entry": [{"left": {"indicator": "ema", "period": 20}, "op": "crosses_above", "right": {"indicator": "ema", "period": 50}}],
        "exit": [{"left": {"indicator": "ema", "period": 20}, "op": "crosses_below", "right": {"indicator": "ema", "period": 50}}],
        "stop_loss_pct": 5, "take_profit_pct": 15,
    },
    {
        "name": "RSI oversold bounce",
        "description": "Buy when RSI(14) crosses back above 30 while the stock is above its 200-day SMA; exit when RSI passes 60.",
        "timeframe": "1d",
        "entry": [
            {"left": {"indicator": "rsi", "period": 14}, "op": "crosses_above", "right": {"value": 30}},
            {"left": {"indicator": "close"}, "op": ">", "right": {"indicator": "sma", "period": 200}},
        ],
        "exit": [{"left": {"indicator": "rsi", "period": 14}, "op": ">", "right": {"value": 60}}],
        "stop_loss_pct": 4, "take_profit_pct": 8, "max_hold_bars": 15,
    },
    {
        "name": "20-day breakout",
        "description": "Buy when the close breaks above the highest high of the previous 20 days on above-average volume.",
        "timeframe": "1d",
        "entry": [
            {"left": {"indicator": "close"}, "op": ">", "right": {"indicator": "highest", "period": 20}},
            {"left": {"indicator": "volume"}, "op": ">", "right": {"indicator": "volume_sma", "period": 20}},
        ],
        "exit": [{"left": {"indicator": "close"}, "op": "<", "right": {"indicator": "ema", "period": 20}}],
        "stop_loss_pct": 4, "take_profit_pct": 12,
    },
    {
        "name": "MACD trend",
        "description": "Buy when the MACD line crosses above its signal line with price above the 50-day EMA.",
        "timeframe": "1d",
        "entry": [
            {"left": {"indicator": "macd"}, "op": "crosses_above", "right": {"indicator": "macd_signal"}},
            {"left": {"indicator": "close"}, "op": ">", "right": {"indicator": "ema", "period": 50}},
        ],
        "exit": [{"left": {"indicator": "macd"}, "op": "crosses_below", "right": {"indicator": "macd_signal"}}],
        "stop_loss_pct": 4, "take_profit_pct": 10,
    },
    {
        "name": "Intraday EMA 9/21 (5m)",
        "description": "Buy when the 9-bar EMA crosses above the 21-bar EMA on 5-minute bars; squared off at 15:15.",
        "timeframe": "5m",
        "symbols": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
        "entry": [{"left": {"indicator": "ema", "period": 9}, "op": "crosses_above", "right": {"indicator": "ema", "period": 21}}],
        "exit": [{"left": {"indicator": "ema", "period": 9}, "op": "crosses_below", "right": {"indicator": "ema", "period": 21}}],
        "stop_loss_pct": 1, "take_profit_pct": 2, "square_off_intraday": True,
    },
]


def operand_catalog() -> list[dict[str, object]]:
    return [{"indicator": key, "label": label, "needs_period": key in NEEDS_PERIOD} for key, label in LABELS.items()]
