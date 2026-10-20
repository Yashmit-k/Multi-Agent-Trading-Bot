"""Rule-strategy engine shared by the Strategy lab backtester and live paper trading.

A strategy is JSON. Rules are nested groups (all / any / not) of conditions; a condition compares
two operands. An operand is a number or an indicator, optionally:
  - from a higher timeframe (`timeframe`), aligned to the last *completed* higher-timeframe bar;
  - N bars ago (`offset`);
  - transformed (`scale` x value + `shift`).
A condition can also be required to hold for N consecutive bars (`for_bars`) or at least once in the
last N bars (`within_bars`). Every array is computed from bars up to and including the bar it
belongs to, so a rule evaluated at a bar's close never sees a later bar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Literal, Union
from zoneinfo import ZoneInfo

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "1d": 24 * 60}
INTRADAY = ("5m", "15m", "1h")

# indicator -> (label, group, needs period, default period, uses period2, uses param)
CATALOG: dict[str, tuple[str, str, bool, int | None, bool, bool]] = {
    # price
    "close": ("Close", "Price", False, None, False, False),
    "open": ("Open", "Price", False, None, False, False),
    "high": ("High", "Price", False, None, False, False),
    "low": ("Low", "Price", False, None, False, False),
    "hl2": ("(High + Low) / 2", "Price", False, None, False, False),
    "typical": ("Typical price (H+L+C)/3", "Price", False, None, False, False),
    "volume": ("Volume", "Volume", False, None, False, False),
    # moving averages and trend
    "sma": ("SMA", "Trend", True, 20, False, False),
    "ema": ("EMA", "Trend", True, 20, False, False),
    "wma": ("WMA", "Trend", True, 20, False, False),
    "vwap": ("VWAP (session)", "Trend", False, None, False, False),
    "supertrend": ("SuperTrend line", "Trend", True, 10, False, True),
    "supertrend_dir": ("SuperTrend direction (+1 up / -1 down)", "Trend", True, 10, False, True),
    "adx": ("ADX", "Trend", True, 14, False, False),
    "plus_di": ("+DI", "Trend", True, 14, False, False),
    "minus_di": ("-DI", "Trend", True, 14, False, False),
    "macd": ("MACD line", "Momentum", False, 12, True, False),
    "macd_signal": ("MACD signal", "Momentum", False, 12, True, False),
    "macd_hist": ("MACD histogram", "Momentum", False, 12, True, False),
    # momentum and oscillators
    "rsi": ("RSI", "Momentum", True, 14, False, False),
    "stoch_k": ("Stochastic %K", "Momentum", True, 14, True, False),
    "stoch_d": ("Stochastic %D", "Momentum", True, 14, True, False),
    "williams_r": ("Williams %R", "Momentum", True, 14, False, False),
    "cci": ("CCI", "Momentum", True, 20, False, False),
    "return_pct": ("Return % over N bars", "Momentum", True, 10, False, False),
    "roc": ("Rate of change % (same as return)", "Momentum", True, 10, False, False),
    # volatility and channels
    "atr": ("ATR", "Volatility", True, 14, False, False),
    "atr_pct": ("ATR % of close", "Volatility", True, 14, False, False),
    "bb_upper": ("Bollinger upper", "Volatility", True, 20, False, True),
    "bb_mid": ("Bollinger middle", "Volatility", True, 20, False, True),
    "bb_lower": ("Bollinger lower", "Volatility", True, 20, False, True),
    "bb_width_pct": ("Bollinger width % of middle", "Volatility", True, 20, False, True),
    "keltner_upper": ("Keltner upper (EMA + k x ATR)", "Volatility", True, 20, False, True),
    "keltner_lower": ("Keltner lower (EMA - k x ATR)", "Volatility", True, 20, False, True),
    "highest": ("Highest high of the previous N bars", "Volatility", True, 20, False, False),
    "lowest": ("Lowest low of the previous N bars", "Volatility", True, 20, False, False),
    "donchian_upper": ("Donchian upper (last N bars incl. this)", "Volatility", True, 20, False, False),
    "donchian_lower": ("Donchian lower (last N bars incl. this)", "Volatility", True, 20, False, False),
    "stdev_pct": ("Std-dev of returns % over N", "Volatility", True, 20, False, False),
    # volume
    "volume_sma": ("Average volume", "Volume", True, 20, False, False),
    "volume_ratio": ("Volume / average volume", "Volume", True, 20, False, False),
    "obv": ("On-balance volume", "Volume", False, None, False, False),
    "mfi": ("Money flow index", "Volume", True, 14, False, False),
    # session / calendar
    "prev_day_high": ("Previous day high", "Session", False, None, False, False),
    "prev_day_low": ("Previous day low", "Session", False, None, False, False),
    "prev_day_close": ("Previous day close", "Session", False, None, False, False),
    "day_open": ("Today's open", "Session", False, None, False, False),
    "day_high": ("Today's high so far", "Session", False, None, False, False),
    "day_low": ("Today's low so far", "Session", False, None, False, False),
    "gap_pct": ("Gap % (today's open vs previous close)", "Session", False, None, False, False),
    "opening_range_high": ("Opening-range high (first N minutes)", "Session", True, 15, False, False),
    "opening_range_low": ("Opening-range low (first N minutes)", "Session", True, 15, False, False),
    "time_hhmm": ("Bar end time as HHMM (e.g. 1015)", "Session", False, None, False, False),
    "day_of_week": ("Day of week (1 = Monday)", "Session", False, None, False, False),
    "bars_since_open": ("Bars since session open", "Session", False, None, False, False),
    # candles (flags are 1 or 0)
    "body_pct": ("Candle body % of open", "Candle", False, None, False, False),
    "range_pct": ("Candle range % of open", "Candle", False, None, False, False),
    "upper_wick_pct": ("Upper wick % of open", "Candle", False, None, False, False),
    "lower_wick_pct": ("Lower wick % of open", "Candle", False, None, False, False),
    "green": ("Green candle (1/0)", "Candle", False, None, False, False),
    "red": ("Red candle (1/0)", "Candle", False, None, False, False),
    "doji": ("Doji (1/0)", "Candle", False, None, False, False),
    "hammer": ("Hammer (1/0)", "Candle", False, None, False, False),
    "shooting_star": ("Shooting star (1/0)", "Candle", False, None, False, False),
    "bullish_engulfing": ("Bullish engulfing (1/0)", "Candle", False, None, False, False),
    "bearish_engulfing": ("Bearish engulfing (1/0)", "Candle", False, None, False, False),
    "inside_bar": ("Inside bar (1/0)", "Candle", False, None, False, False),
    "outside_bar": ("Outside bar (1/0)", "Candle", False, None, False, False),
    # market structure (pivots use N bars each side; a pivot counts only after N bars confirm it)
    "swing_high": ("Last confirmed swing high", "Structure", True, 2, False, False),
    "swing_low": ("Last confirmed swing low", "Structure", True, 2, False, False),
    "bos_up": ("Break of structure up (1/0)", "Structure", True, 2, False, False),
    "bos_down": ("Break of structure down (1/0)", "Structure", True, 2, False, False),
    "higher_high": ("Last swing high above the previous one (1/0)", "Structure", True, 2, False, False),
    "higher_low": ("Last swing low above the previous one (1/0)", "Structure", True, 2, False, False),
}
INDICATORS = tuple(CATALOG)


class Operand(BaseModel):
    indicator: str | None = None
    value: float | None = None
    period: int | None = Field(default=None, ge=1, le=500)
    period2: int | None = Field(default=None, ge=1, le=500)
    param: float | None = Field(default=None, gt=0, le=20)
    offset: int = Field(default=0, ge=0, le=500)
    timeframe: Literal["5m", "15m", "1h", "1d"] | None = None
    scale: float = 1.0
    shift: float = 0.0

    @model_validator(mode="after")
    def _check(self) -> "Operand":
        if (self.indicator is None) == (self.value is None):
            raise ValueError("an operand is either an indicator or a number")
        if self.indicator is not None:
            if self.indicator not in CATALOG:
                raise ValueError(f"unknown indicator {self.indicator!r}")
            if CATALOG[self.indicator][2] and self.period is None:
                self.period = CATALOG[self.indicator][3]
        return self

    def label(self) -> str:
        if self.value is not None:
            return f"{self.value:g}"
        name = CATALOG[self.indicator or "close"][0]
        args = [str(item) for item in (self.period, self.period2, self.param) if item is not None]
        text = f"{name}({', '.join(args)})" if args else name
        if self.timeframe:
            text = f"{self.timeframe} {text}"
        if self.offset:
            text += f" {self.offset} bars ago"
        if self.scale != 1.0:
            text = f"{self.scale:g} x {text}"
        if self.shift:
            text += f" {'+' if self.shift > 0 else '-'} {abs(self.shift):g}"
        return text


Op = Literal[">", "<", ">=", "<=", "==", "crosses_above", "crosses_below"]


class Condition(BaseModel):
    left: Operand
    op: Op
    right: Operand
    for_bars: int = Field(default=1, ge=1, le=200)
    within_bars: int = Field(default=1, ge=1, le=200)

    def label(self) -> str:
        words = {"crosses_above": "crosses above", "crosses_below": "crosses below", "==": "="}
        text = f"{self.left.label()} {words.get(self.op, self.op)} {self.right.label()}"
        if self.for_bars > 1:
            text += f" for {self.for_bars} bars"
        if self.within_bars > 1:
            text += f" within the last {self.within_bars} bars"
        return text


class Group(BaseModel):
    logic: Literal["all", "any"] = "all"
    negate: bool = False
    items: list[Union["Group", Condition]] = Field(min_length=1, max_length=20)

    def label(self) -> str:
        joined = f" {'AND' if self.logic == 'all' else 'OR'} ".join(
            f"({item.label()})" if isinstance(item, Group) else item.label() for item in self.items
        )
        return f"NOT ({joined})" if self.negate else joined

    def depth(self) -> int:
        return 1 + max((item.depth() for item in self.items if isinstance(item, Group)), default=0)


Group.model_rebuild()


class StopSpec(BaseModel):
    kind: Literal["none", "percent", "atr", "level"] = "percent"
    value: float = Field(default=2.0, gt=0, le=50)  # percent, or ATR multiple
    period: int = Field(default=14, ge=1, le=200)  # ATR period
    level: Operand | None = None  # e.g. swing_low or lowest(10), read at the signal bar
    buffer_pct: float = Field(default=0.0, ge=0, le=10)

    @model_validator(mode="after")
    def _level(self) -> "StopSpec":
        if self.kind == "level" and self.level is None:
            raise ValueError("a level stop needs an operand, e.g. swing_low")
        return self


class TargetSpec(BaseModel):
    kind: Literal["percent", "atr", "r_multiple"] = "percent"
    value: float = Field(gt=0, le=200)
    period: int = Field(default=14, ge=1, le=200)
    fraction: float = Field(default=1.0, gt=0, le=1)


class TrailingSpec(BaseModel):
    kind: Literal["percent", "atr"] = "percent"
    value: float = Field(gt=0, le=50)
    period: int = Field(default=14, ge=1, le=200)
    activate_after_r: float = Field(default=0.0, ge=0, le=20)  # start trailing once price is this many R in profit


class EntryOrder(BaseModel):
    type: Literal["market", "limit"] = "market"
    price: Operand | None = None  # limit price, read at the signal bar (e.g. swing_high for a retest)
    valid_bars: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def _price(self) -> "EntryOrder":
        if self.type == "limit" and self.price is None:
            raise ValueError("a limit entry needs a price operand")
        return self


class Sizing(BaseModel):
    kind: Literal["notional", "risk_percent"] = "notional"
    value: float = Field(default=20000, gt=0)  # rupees, or % of starting cash risked per trade
    max_notional: float = Field(default=100000, ge=1000, le=100000)


class StrategyDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    timeframe: Literal["5m", "15m", "1h", "1d"] = "1d"
    direction: Literal["long", "short"] = "long"
    symbols: list[str] = Field(default_factory=lambda: ["ALL"], min_length=1, max_length=60)
    entry: Group
    exit: Group | None = None
    entry_order: EntryOrder = Field(default_factory=EntryOrder)
    stop: StopSpec = Field(default_factory=StopSpec)
    targets: list[TargetSpec] = Field(default_factory=lambda: [TargetSpec(kind="percent", value=4.0)], max_length=3)
    breakeven_after_first_target: bool = False
    trailing: TrailingSpec | None = None
    max_hold_bars: int | None = Field(default=None, ge=1, le=5000)
    square_off_intraday: bool = False
    last_entry_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    sizing: Sizing = Field(default_factory=Sizing)
    max_open_positions: int = Field(default=10, ge=1, le=50)
    initial_cash: float = Field(default=500000, ge=10000, le=100_000_000)
    slippage_bps: float = Field(default=5, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data: Any) -> Any:
        """Strategies saved before groups existed: entry/exit lists, stop_loss_pct, take_profit_pct, position_notional."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if isinstance(data.get("entry"), list):
            data["entry"] = {"logic": "all", "items": data["entry"]}
        if isinstance(data.get("exit"), list):
            data["exit"] = {"logic": "any", "items": data["exit"]} if data["exit"] else None
        if "stop_loss_pct" in data:
            pct = data.pop("stop_loss_pct")
            data.setdefault("stop", {"kind": "percent", "value": pct} if pct else {"kind": "none"})
        if "take_profit_pct" in data:
            pct = data.pop("take_profit_pct")
            data.setdefault("targets", [{"kind": "percent", "value": pct, "fraction": 1.0}] if pct else [])
        if "position_notional" in data:
            data.setdefault("sizing", {"kind": "notional", "value": data.pop("position_notional")})
        return data

    @field_validator("symbols")
    @classmethod
    def _upper(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().upper() for item in value if item.strip()})

    @model_validator(mode="after")
    def _consistent(self) -> "StrategyDefinition":
        if self.entry.depth() > 4 or (self.exit is not None and self.exit.depth() > 4):
            raise ValueError("rules can nest at most 4 groups deep")
        if sum(target.fraction for target in self.targets) > 1.0 + 1e-9:
            raise ValueError("target fractions add up to more than 100% of the position")
        if any(target.kind == "r_multiple" for target in self.targets) and self.stop.kind == "none":
            raise ValueError("R-multiple targets need a stop (R = entry minus stop)")
        if self.trailing is not None and self.trailing.activate_after_r > 0 and self.stop.kind == "none":
            raise ValueError("a trailing stop that activates after N R needs a stop")
        if self.sizing.kind == "risk_percent":
            if self.stop.kind == "none":
                raise ValueError("risk-percent sizing needs a stop")
            if self.sizing.value > 5:
                raise ValueError("risk per trade is capped at 5% of starting cash")
        elif not 1000 <= self.sizing.value <= 100000:
            raise ValueError("money per trade must be between Rs 1,000 and Rs 1,00,000")
        if self.direction == "short" and not (self.timeframe in INTRADAY and self.square_off_intraday):
            raise ValueError("short selling is intraday only in Indian cash equities: use an intraday timeframe with square-off")
        if self.square_off_intraday and self.timeframe not in INTRADAY:
            raise ValueError("square-off applies to intraday timeframes only")
        for operand in operands(self):
            if operand.timeframe and TIMEFRAME_MINUTES[operand.timeframe] <= TIMEFRAME_MINUTES[self.timeframe]:
                raise ValueError(f"{operand.label()}: a higher-timeframe operand must be above the strategy's {self.timeframe}")
        return self

    @property
    def product(self) -> Literal["CNC", "MIS"]:
        return "MIS" if self.square_off_intraday else "CNC"


def operands(strategy: StrategyDefinition) -> list[Operand]:
    found: list[Operand] = []

    def walk(group: Group | None) -> None:
        if group is None:
            return
        for item in group.items:
            if isinstance(item, Group):
                walk(item)
            else:
                found.extend((item.left, item.right))

    walk(strategy.entry)
    walk(strategy.exit)
    if strategy.entry_order.price is not None:
        found.append(strategy.entry_order.price)
    if strategy.stop.level is not None:
        found.append(strategy.stop.level)
    return found


# --- bars -----------------------------------------------------------------------------------------


@dataclass
class Bars:
    start: list[datetime]
    end: list[datetime]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return len(self.end)

    def sessions(self) -> np.ndarray:
        return np.array([moment.astimezone(IST).date().toordinal() for moment in self.end])


def bars_from_rows(rows: list[tuple]) -> Bars | None:
    """rows: (start, end, open, high, low, close, volume)."""
    if not rows:
        return None
    cols = list(zip(*rows))
    return Bars(list(cols[0]), list(cols[1]), *(np.array(col, dtype=float) for col in cols[2:]))


def resample(bars: Bars, minutes: int) -> Bars:
    """Session-anchored bars from 09:15 IST. A bar is kept only if every 5-minute bar inside it exists."""
    groups: dict[tuple[date, int], list[int]] = {}
    for i, moment in enumerate(bars.start):
        local = moment.astimezone(IST)
        offset = (local.hour * 60 + local.minute) - (9 * 60 + 15)
        if offset < 0 or local.time() >= SESSION_CLOSE:
            continue
        groups.setdefault((local.date(), offset // minutes), []).append(i)
    starts, ends, o, h, l, c, v = [], [], [], [], [], [], []
    for (day, slot), idx in sorted(groups.items()):
        slot_start = datetime.combine(day, SESSION_OPEN, IST) + timedelta(minutes=slot * minutes)
        slot_end = min(slot_start + timedelta(minutes=minutes), datetime.combine(day, SESSION_CLOSE, IST))
        if len(idx) != int((slot_end - slot_start).total_seconds() // 300):
            continue
        starts.append(slot_start.astimezone(timezone.utc))
        ends.append(slot_end.astimezone(timezone.utc))
        o.append(bars.open[idx[0]])
        h.append(bars.high[idx].max())
        l.append(bars.low[idx].min())
        c.append(bars.close[idx[-1]])
        v.append(bars.volume[idx].sum())
    return Bars(starts, ends, *(np.array(col, dtype=float) for col in (o, h, l, c, v)))


# --- indicator library ----------------------------------------------------------------------------


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    valid = np.where(~np.isnan(values))[0]
    if len(valid) < period:
        return out
    first = valid[0]
    if first + period > len(values):
        return out
    alpha = 2.0 / (period + 1)
    out[first + period - 1] = np.nanmean(values[first : first + period])
    for i in range(first + period, len(values)):
        value = values[i]
        out[i] = out[i - 1] if math.isnan(value) else alpha * value + (1 - alpha) * out[i - 1]
    return out


def _wilder(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    sums = np.cumsum(np.insert(values, 0, 0.0))
    out[period - 1 :] = (sums[period:] - sums[:-period]) / period
    return out


def _wma(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    weights = np.arange(1, period + 1, dtype=float)
    for i in range(period - 1, len(values)):
        out[i] = float(np.dot(values[i - period + 1 : i + 1], weights) / weights.sum())
    return out


def _window(values: np.ndarray, period: int, fn, *, include_current: bool) -> np.ndarray:  # type: ignore[no-untyped-def]
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        lo, hi = (i - period + 1, i + 1) if include_current else (i - period, i)
        if lo >= 0:
            out[i] = fn(values[lo:hi])
    return out


def _true_range(bars: Bars) -> np.ndarray:
    previous = np.concatenate([[bars.close[0]], bars.close[:-1]])
    return np.maximum(bars.high - bars.low, np.maximum(abs(bars.high - previous), abs(bars.low - previous)))


def _atr(bars: Bars, period: int) -> np.ndarray:
    return _wilder(_true_range(bars), period)


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


def _dmi(bars: Bars, period: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    up = np.diff(bars.high, prepend=bars.high[0])
    down = -np.diff(bars.low, prepend=bars.low[0])
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = _wilder(_true_range(bars), period)
    with np.errstate(invalid="ignore", divide="ignore"):
        plus = 100 * _wilder(plus_dm, period) / tr
        minus = 100 * _wilder(minus_dm, period) / tr
        dx = 100 * abs(plus - minus) / (plus + minus)
    adx = np.full(len(bars), np.nan)
    valid = np.where(~np.isnan(dx))[0]
    if len(valid) >= period:
        first = valid[0]
        adx[first:] = _wilder(np.nan_to_num(dx[first:]), period)
    return plus, minus, adx


def _supertrend(bars: Bars, period: int, multiplier: float) -> tuple[np.ndarray, np.ndarray]:
    atr = _atr(bars, period)
    mid = (bars.high + bars.low) / 2
    upper, lower = mid + multiplier * atr, mid - multiplier * atr
    line = np.full(len(bars), np.nan)
    direction = np.full(len(bars), np.nan)
    final_upper, final_lower = upper.copy(), lower.copy()
    for i in range(len(bars)):
        if math.isnan(atr[i]):
            continue
        if i > 0 and not math.isnan(final_upper[i - 1]):
            final_upper[i] = upper[i] if upper[i] < final_upper[i - 1] or bars.close[i - 1] > final_upper[i - 1] else final_upper[i - 1]
            final_lower[i] = lower[i] if lower[i] > final_lower[i - 1] or bars.close[i - 1] < final_lower[i - 1] else final_lower[i - 1]
        previous = direction[i - 1] if i > 0 and not math.isnan(direction[i - 1]) else 1.0
        if previous == 1.0:
            direction[i] = -1.0 if bars.close[i] < final_lower[i] else 1.0
        else:
            direction[i] = 1.0 if bars.close[i] > final_upper[i] else -1.0
        line[i] = final_lower[i] if direction[i] == 1.0 else final_upper[i]
    return line, direction


def _pivots(bars: Bars, width: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Confirmed swing levels and flags. A pivot at i is known at the close of i + width."""
    n = len(bars)
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    bos_up = np.zeros(n)
    bos_down = np.zeros(n)
    higher_high = np.zeros(n)
    higher_low = np.zeros(n)
    last_high = last_low = math.nan
    prev_high = prev_low = math.nan
    high_broken = low_broken = True
    for b in range(n):
        candidate = b - width
        if candidate - width >= 0:
            window = bars.high[candidate - width : candidate + width + 1]
            if bars.high[candidate] == window.max() and (window == bars.high[candidate]).sum() == 1:
                prev_high, last_high, high_broken = last_high, float(bars.high[candidate]), False
            window = bars.low[candidate - width : candidate + width + 1]
            if bars.low[candidate] == window.min() and (window == bars.low[candidate]).sum() == 1:
                prev_low, last_low, low_broken = last_low, float(bars.low[candidate]), False
        swing_high[b], swing_low[b] = last_high, last_low
        if not high_broken and bars.close[b] > last_high:
            bos_up[b], high_broken = 1.0, True
        if not low_broken and bars.close[b] < last_low:
            bos_down[b], low_broken = 1.0, True
        higher_high[b] = 1.0 if not math.isnan(prev_high) and last_high > prev_high else 0.0
        higher_low[b] = 1.0 if not math.isnan(prev_low) and last_low > prev_low else 0.0
    return swing_high, swing_low, bos_up, bos_down, higher_high, higher_low


def _session_values(bars: Bars, intraday: bool) -> dict[str, np.ndarray]:
    """Previous-session high/low/close, today's open/high/low so far, gap %, bars since open, VWAP."""
    n = len(bars)
    out = {name: np.full(n, np.nan) for name in ("prev_day_high", "prev_day_low", "prev_day_close", "day_open", "day_high", "day_low", "gap_pct", "bars_since_open", "vwap")}
    if not intraday:  # daily bars: the previous bar is the previous day
        out["prev_day_high"][1:], out["prev_day_low"][1:], out["prev_day_close"][1:] = bars.high[:-1], bars.low[:-1], bars.close[:-1]
        out["day_open"], out["day_high"], out["day_low"] = bars.open.copy(), bars.high.copy(), bars.low.copy()
        out["gap_pct"][1:] = (bars.open[1:] / bars.close[:-1] - 1) * 100
        out["bars_since_open"][:] = 0
        out["vwap"] = (bars.high + bars.low + bars.close) / 3
        return out
    days = bars.sessions()
    prev = None  # (high, low, close) of the previous session
    current_day, day_open, day_high, day_low, count, pv, vol = None, math.nan, -math.inf, math.inf, 0, 0.0, 0.0
    for i in range(n):
        if days[i] != current_day:
            if current_day is not None:
                prev = (day_high, day_low, float(bars.close[i - 1]))
            current_day, day_open, day_high, day_low, count, pv, vol = days[i], float(bars.open[i]), -math.inf, math.inf, 0, 0.0, 0.0
        day_high, day_low = max(day_high, float(bars.high[i])), min(day_low, float(bars.low[i]))
        typical = (bars.high[i] + bars.low[i] + bars.close[i]) / 3
        pv, vol = pv + typical * bars.volume[i], vol + bars.volume[i]
        out["day_open"][i], out["day_high"][i], out["day_low"][i] = day_open, day_high, day_low
        out["bars_since_open"][i] = count
        out["vwap"][i] = pv / vol if vol > 0 else typical
        if prev is not None:
            out["prev_day_high"][i], out["prev_day_low"][i], out["prev_day_close"][i] = prev
            out["gap_pct"][i] = (day_open / prev[2] - 1) * 100
        count += 1
    return out


def _opening_range(bars: Bars, minutes: int) -> tuple[np.ndarray, np.ndarray]:
    """High/low of the first `minutes` of each session, available only once that range has closed."""
    high, low = np.full(len(bars), np.nan), np.full(len(bars), np.nan)
    days = bars.sessions()
    current, range_high, range_low = None, -math.inf, math.inf
    for i, moment in enumerate(bars.end):
        local = moment.astimezone(IST)
        if days[i] != current:
            current, range_high, range_low = days[i], -math.inf, math.inf
        elapsed = (local.hour * 60 + local.minute) - (9 * 60 + 15)
        if elapsed <= minutes:
            range_high, range_low = max(range_high, float(bars.high[i])), min(range_low, float(bars.low[i]))
        if elapsed >= minutes and range_high > -math.inf:
            high[i], low[i] = range_high, range_low
    return high, low


def raw_indicator(bars: Bars, name: str, period: int | None, period2: int | None, param: float | None, intraday: bool, cache: dict) -> np.ndarray:
    key = (name, period, period2, param)
    if key in cache:
        return cache[key]
    n = len(bars)
    p = period or CATALOG[name][3] or 14
    o, h, l, c, v = bars.open, bars.high, bars.low, bars.close, bars.volume
    rng = h - l
    body = abs(c - o)
    with np.errstate(invalid="ignore", divide="ignore"):
        if name in ("close", "open", "high", "low", "volume"):
            out = getattr(bars, name).astype(float)
        elif name == "hl2":
            out = (h + l) / 2
        elif name == "typical":
            out = (h + l + c) / 3
        elif name == "sma":
            out = _sma(c, p)
        elif name == "ema":
            out = _ema(c, p)
        elif name == "wma":
            out = _wma(c, p)
        elif name in ("macd", "macd_signal", "macd_hist"):
            fast, slow, signal_period = period or 12, period2 or 26, int(param or 9)
            line = _ema(c, fast) - _ema(c, slow)
            signal = _ema(line, signal_period)
            out = {"macd": line, "macd_signal": signal, "macd_hist": line - signal}[name]
        elif name == "rsi":
            out = _rsi(c, p)
        elif name in ("stoch_k", "stoch_d"):
            low_n = _window(l, p, np.min, include_current=True)
            high_n = _window(h, p, np.max, include_current=True)
            raw_k = 100 * (c - low_n) / (high_n - low_n)
            k = _window(raw_k, period2 or 3, np.mean, include_current=True)  # NaN until the window is defined
            out = k if name == "stoch_k" else _window(k, 3, np.mean, include_current=True)
        elif name == "williams_r":
            high_n = _window(h, p, np.max, include_current=True)
            low_n = _window(l, p, np.min, include_current=True)
            out = -100 * (high_n - c) / (high_n - low_n)
        elif name == "cci":
            tp = (h + l + c) / 3
            mean = _sma(tp, p)
            dev = _window(tp, p, lambda w: np.mean(np.abs(w - w.mean())), include_current=True)
            out = (tp - mean) / (0.015 * dev)
        elif name in ("return_pct", "roc"):
            out = np.full(n, np.nan)
            out[p:] = (c[p:] / c[:-p] - 1) * 100
        elif name == "atr":
            out = _atr(bars, p)
        elif name == "atr_pct":
            out = _atr(bars, p) / c * 100
        elif name in ("bb_upper", "bb_mid", "bb_lower", "bb_width_pct"):
            k = param or 2.0
            mid = _sma(c, p)
            std = _window(c, p, np.std, include_current=True)
            out = {"bb_upper": mid + k * std, "bb_mid": mid, "bb_lower": mid - k * std, "bb_width_pct": 2 * k * std / mid * 100}[name]
        elif name in ("keltner_upper", "keltner_lower"):
            k = param or 2.0
            mid, atr = _ema(c, p), _atr(bars, p)
            out = mid + k * atr if name == "keltner_upper" else mid - k * atr
        elif name == "highest":
            out = _window(h, p, np.max, include_current=False)
        elif name == "lowest":
            out = _window(l, p, np.min, include_current=False)
        elif name == "donchian_upper":
            out = _window(h, p, np.max, include_current=True)
        elif name == "donchian_lower":
            out = _window(l, p, np.min, include_current=True)
        elif name == "stdev_pct":
            returns = np.concatenate([[np.nan], c[1:] / c[:-1] - 1])
            out = _window(returns, p, np.std, include_current=True) * 100
        elif name == "volume_sma":
            out = _sma(v, p)
        elif name == "volume_ratio":
            out = v / _sma(v, p)
        elif name == "obv":
            out = np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)
        elif name == "mfi":
            tp = (h + l + c) / 3
            flow = tp * v
            direction = np.sign(np.diff(tp, prepend=tp[0]))
            pos = _window(np.where(direction > 0, flow, 0.0), p, np.sum, include_current=True)
            neg = _window(np.where(direction < 0, flow, 0.0), p, np.sum, include_current=True)
            out = 100 - 100 / (1 + pos / neg)
        elif name in ("supertrend", "supertrend_dir"):
            line, direction = _supertrend(bars, p, param or 3.0)
            out = line if name == "supertrend" else direction
        elif name in ("adx", "plus_di", "minus_di"):
            plus, minus, adx = _dmi(bars, p)
            out = {"adx": adx, "plus_di": plus, "minus_di": minus}[name]
        elif name in ("prev_day_high", "prev_day_low", "prev_day_close", "day_open", "day_high", "day_low", "gap_pct", "bars_since_open", "vwap"):
            out = _session_values(bars, intraday)[name]
        elif name in ("opening_range_high", "opening_range_low"):
            if not intraday:
                out = np.full(n, np.nan)
            else:
                high_r, low_r = _opening_range(bars, p)
                out = high_r if name == "opening_range_high" else low_r
        elif name == "time_hhmm":
            out = np.array([float(m.astimezone(IST).hour * 100 + m.astimezone(IST).minute) for m in bars.end])
        elif name == "day_of_week":
            out = np.array([float(m.astimezone(IST).isoweekday()) for m in bars.end])
        elif name == "body_pct":
            out = body / o * 100
        elif name == "range_pct":
            out = rng / o * 100
        elif name == "upper_wick_pct":
            out = (h - np.maximum(o, c)) / o * 100
        elif name == "lower_wick_pct":
            out = (np.minimum(o, c) - l) / o * 100
        elif name == "green":
            out = (c > o).astype(float)
        elif name == "red":
            out = (c < o).astype(float)
        elif name == "doji":
            out = ((rng > 0) & (body <= 0.1 * rng)).astype(float)
        elif name == "hammer":
            lower = np.minimum(o, c) - l
            upper = h - np.maximum(o, c)
            out = ((rng > 0) & (lower >= 2 * body) & (upper <= body) & (body > 0)).astype(float)
        elif name == "shooting_star":
            lower = np.minimum(o, c) - l
            upper = h - np.maximum(o, c)
            out = ((rng > 0) & (upper >= 2 * body) & (lower <= body) & (body > 0)).astype(float)
        elif name in ("bullish_engulfing", "bearish_engulfing", "inside_bar", "outside_bar"):
            out = np.zeros(n)
            po, pc, ph, pl = np.roll(o, 1), np.roll(c, 1), np.roll(h, 1), np.roll(l, 1)
            if name == "bullish_engulfing":
                flag = (pc < po) & (c > o) & (c >= po) & (o <= pc)
            elif name == "bearish_engulfing":
                flag = (pc > po) & (c < o) & (c <= po) & (o >= pc)
            elif name == "inside_bar":
                flag = (h < ph) & (l > pl)
            else:
                flag = (h > ph) & (l < pl)
            out[1:] = flag[1:].astype(float)
        elif name in ("swing_high", "swing_low", "bos_up", "bos_down", "higher_high", "higher_low"):
            values = dict(zip(("swing_high", "swing_low", "bos_up", "bos_down", "higher_high", "higher_low"), _pivots(bars, period or 2)))
            out = values[name]
        else:  # pragma: no cover - guarded by the catalog check
            raise ValueError(name)
    out = np.asarray(out, dtype=float)
    cache[key] = out
    return out


# --- evaluation -----------------------------------------------------------------------------------


@dataclass
class Context:
    """Bars for the strategy timeframe plus any higher timeframes its operands use."""

    bars: Bars
    timeframe: str
    higher: dict[str, Bars]
    cache: dict

    def aligned(self, timeframe: str) -> np.ndarray:
        """For each bar, the index of the last *completed* higher-timeframe bar (-1 if none)."""
        key = ("__align__", timeframe)
        if key not in self.cache:
            htf = self.higher[timeframe]
            ends = np.array([moment.timestamp() for moment in htf.end])
            mine = np.array([moment.timestamp() for moment in self.bars.end])
            self.cache[key] = np.searchsorted(ends, mine, side="right") - 1
        return self.cache[key]


def operand_values(context: Context, operand: Operand) -> np.ndarray:
    n = len(context.bars)
    if operand.value is not None:
        return np.full(n, float(operand.value))
    name = operand.indicator or "close"
    if operand.timeframe:
        htf = context.higher.get(operand.timeframe)
        if htf is None or len(htf) == 0:
            return np.full(n, np.nan)
        sub_cache = context.cache.setdefault(("__htf__", operand.timeframe), {})
        series = raw_indicator(htf, name, operand.period, operand.period2, operand.param, operand.timeframe in INTRADAY, sub_cache)
        if operand.offset:
            series = np.concatenate([np.full(operand.offset, np.nan), series[: -operand.offset]]) if operand.offset < len(series) else np.full(len(series), np.nan)
        index = context.aligned(operand.timeframe)
        values = np.where(index >= 0, series[np.clip(index, 0, None)], np.nan)
    else:
        values = raw_indicator(context.bars, name, operand.period, operand.period2, operand.param, context.timeframe in INTRADAY, context.cache)
        if operand.offset:
            values = np.concatenate([np.full(operand.offset, np.nan), values[: -operand.offset]]) if operand.offset < n else np.full(n, np.nan)
    return values * operand.scale + operand.shift


def _condition(context: Context, condition: Condition) -> np.ndarray:
    left, right = operand_values(context, condition.left), operand_values(context, condition.right)
    with np.errstate(invalid="ignore"):
        if condition.op in (">", "<", ">=", "<=", "=="):
            passed = {">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right, "==": np.isclose(left, right)}[condition.op]
        else:
            prev_left, prev_right = np.roll(left, 1), np.roll(right, 1)
            prev_left[0] = prev_right[0] = np.nan
            passed = (left > right) & (prev_left <= prev_right) if condition.op == "crosses_above" else (left < right) & (prev_left >= prev_right)
    passed = passed & ~(np.isnan(left) | np.isnan(right))
    if condition.for_bars > 1:
        run = np.zeros(len(passed))
        count = 0
        for i, flag in enumerate(passed):
            count = count + 1 if flag else 0
            run[i] = count
        passed = run >= condition.for_bars
    if condition.within_bars > 1:
        cumulative = np.cumsum(np.insert(passed.astype(int), 0, 0))
        window = condition.within_bars
        lagged = np.concatenate([np.zeros(window, dtype=int), cumulative[:-window]])[: len(passed) + 1]
        passed = (cumulative[1:] - lagged[1:]) > 0
    return passed


def evaluate(context: Context, group: Group | None) -> np.ndarray:
    """Boolean per bar. An empty/absent group is never true. NaN operands never pass."""
    n = len(context.bars)
    if group is None:
        return np.zeros(n, dtype=bool)
    parts = [evaluate(context, item) if isinstance(item, Group) else _condition(context, item) for item in group.items]
    stack = np.vstack(parts)
    result = stack.all(axis=0) if group.logic == "all" else stack.any(axis=0)
    return ~result if group.negate else result


def context_for(strategy: StrategyDefinition, bars: Bars, higher_loader: Callable[[str], Bars | None]) -> Context:
    needed = sorted({operand.timeframe for operand in operands(strategy) if operand.timeframe})
    higher = {}
    for timeframe in needed:
        loaded = higher_loader(timeframe)
        if loaded is not None:
            higher[timeframe] = loaded
    return Context(bars=bars, timeframe=strategy.timeframe, higher=higher, cache={})


# --- order levels (shared by backtest and live) ---------------------------------------------------


def stop_price(strategy: StrategyDefinition, context: Context, signal_index: int, entry: float) -> float | None:
    """Stop for an entry at `entry`, using only values known at the signal bar. None = no stop."""
    spec = strategy.stop
    long = strategy.direction == "long"
    if spec.kind == "none":
        return None
    if spec.kind == "percent":
        level = entry * (1 - spec.value / 100) if long else entry * (1 + spec.value / 100)
    elif spec.kind == "atr":
        atr = raw_indicator(context.bars, "atr", spec.period, None, None, context.timeframe in INTRADAY, context.cache)[signal_index]
        if math.isnan(atr):
            return math.nan
        level = entry - spec.value * atr if long else entry + spec.value * atr
    else:
        level = float(operand_values(context, spec.level)[signal_index])  # type: ignore[arg-type]
        if math.isnan(level):
            return math.nan
    buffer = spec.buffer_pct / 100
    return level * (1 - buffer) if long else level * (1 + buffer)


def target_prices(strategy: StrategyDefinition, context: Context, signal_index: int, entry: float, stop: float | None) -> list[tuple[float, float]]:
    """(price, fraction) for each target, nearest first."""
    long = strategy.direction == "long"
    sign = 1 if long else -1
    out = []
    for spec in strategy.targets:
        if spec.kind == "percent":
            distance = entry * spec.value / 100
        elif spec.kind == "atr":
            atr = raw_indicator(context.bars, "atr", spec.period, None, None, context.timeframe in INTRADAY, context.cache)[signal_index]
            if math.isnan(atr):
                continue
            distance = spec.value * atr
        else:
            if stop is None:
                continue
            distance = spec.value * abs(entry - stop)
        out.append((entry + sign * distance, spec.fraction))
    out.sort(key=lambda item: item[0] * sign)
    return out


def catalog() -> list[dict[str, object]]:
    return [
        {"indicator": key, "label": label, "group": group, "needs_period": needs, "default_period": default, "uses_period2": p2, "uses_param": prm}
        for key, (label, group, needs, default, p2, prm) in CATALOG.items()
    ]
