"""Intraday breakout study. Signals use completed bars only.

The previous session's close and the prior 20 daily highs never include the
signal day. Volume history is the prior 10 sessions at the same clock time.
Entry is the next same-session 5-minute open.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from contracts.enums import Side
from contracts.schemas.market import Candle
from core_features.engine import _ema
from core_paper.backtest import exit_on_bar

from quant_agents.research.rebound import IST, PER_TRADE_CAP, session_date

WINDOW_OPEN = 9 * 60 + 30
WINDOW_CLOSE = 15 * 60
STEP = timedelta(minutes=5)
STOP_PCT = Decimal("0.0075")
TARGET_PCT = Decimal("0.01")
VARIANTS = (
    "full",
    "ablate_day_gain",
    "ablate_rising",
    "ablate_volume",
    "ablate_ema",
    "ablate_high",
    "diagnostic_higher_close",
    "baseline_day_gain",
    "baseline_volume",
    "baseline_rising",
)


@dataclass(slots=True)
class _Flags:
    day_gain: bool
    rising: bool
    higher_close: bool
    volume: bool
    ema_band: bool
    near_high: bool
    prior_close: Decimal | None
    prior_session: date | None
    gain_pct: Decimal | None
    ema20: Decimal | None
    ema_dist: Decimal | None
    high: Decimal | None
    high_through: date | None
    high_dist: Decimal | None
    expected_volume: Decimal | None
    volume_ratio: Decimal | None
    volume_sessions: int


@dataclass(slots=True)
class _Position:
    signal_time: datetime
    signal_price: Decimal
    entry_time: datetime
    entry_bar_end: datetime
    entry_price: Decimal
    quantity: int
    flags: _Flags
    session_date: date
    stop: Decimal
    target: Decimal


@dataclass(slots=True)
class _Leg:
    pending: tuple[datetime, Decimal, _Flags, date] | None = None
    position: _Position | None = None


def clock_minutes(moment: datetime) -> int:
    local = moment.astimezone(IST)
    return local.hour * 60 + local.minute


def in_window(moment: datetime) -> bool:
    minutes = clock_minutes(moment)
    return WINDOW_OPEN <= minutes <= WINDOW_CLOSE


def _match(variant: str, flags: _Flags) -> bool:
    if variant == "full":
        return flags.day_gain and flags.rising and flags.volume and flags.ema_band and flags.near_high
    if variant == "ablate_day_gain":
        return flags.rising and flags.volume and flags.ema_band and flags.near_high
    if variant == "ablate_rising":
        return flags.day_gain and flags.volume and flags.ema_band and flags.near_high
    if variant == "ablate_volume":
        return flags.day_gain and flags.rising and flags.ema_band and flags.near_high
    if variant == "ablate_ema":
        return flags.day_gain and flags.rising and flags.volume and flags.near_high
    if variant == "ablate_high":
        return flags.day_gain and flags.rising and flags.volume and flags.ema_band
    if variant == "diagnostic_higher_close":
        return flags.day_gain and flags.higher_close and flags.volume and flags.ema_band and flags.near_high
    if variant == "baseline_day_gain":
        return flags.day_gain
    if variant == "baseline_volume":
        return flags.volume
    if variant == "baseline_rising":
        return flags.rising
    raise KeyError(variant)


def _daily(bars: list[Candle]) -> tuple[list[date], list[Decimal], list[Decimal]]:
    sessions: list[date] = []
    closes: list[Decimal] = []
    highs: list[Decimal] = []
    for bar in sorted(bars, key=lambda item: item.end):
        day = session_date(bar.end)
        if sessions and sessions[-1] == day:
            closes[-1] = bar.close
            highs[-1] = max(highs[-1], bar.high)
            continue
        sessions.append(day)
        closes.append(bar.close)
        highs.append(bar.high)
    return sessions, closes, highs


def _profiles(bars: list[Candle]) -> tuple[list[date], dict[date, dict[int, int]]]:
    order: list[date] = []
    profiles: dict[date, dict[int, int]] = {}
    current: date | None = None
    cumulative = 0
    for bar in bars:
        day = session_date(bar.end)
        if day != current:
            current = day
            cumulative = 0
            profiles[day] = {}
            order.append(day)
        cumulative += bar.volume
        profiles[day][clock_minutes(bar.end)] = cumulative
    return order, profiles


def _flags_for(
    bars: list[Candle],
    index: int,
    sessions: list[date],
    closes: list[Decimal],
    highs: list[Decimal],
    order: list[date],
    profiles: dict[date, dict[int, int]],
    ema_series: list[float],
) -> _Flags | None:
    bar = bars[index]
    if not in_window(bar.end) or bar.close <= 0:
        return None
    day = session_date(bar.end)
    prior_index = bisect_left(sessions, day) - 1
    prior_close = closes[prior_index] if prior_index >= 0 else None
    prior_session = sessions[prior_index] if prior_index >= 0 else None
    gain = None
    day_gain = False
    if prior_close not in (None, 0):
        gain = (bar.close - prior_close) / prior_close * Decimal(100)
        day_gain = Decimal("0.50") <= gain <= Decimal("0.75")
    rising = False
    higher_close = False
    if index >= 2:
        trio = bars[index - 2 : index + 1]
        rising = all(trio[cursor].close > trio[cursor].open for cursor in range(3)) and _consecutive(trio)
    if index >= 3:
        four = bars[index - 3 : index + 1]
        higher_close = _consecutive(four) and all(four[cursor].close > four[cursor - 1].close for cursor in range(1, 4))
    clock = clock_minutes(bar.end)
    volume_ok = False
    expected = None
    ratio = None
    volume_sessions = 0
    place = bisect_left(order, day) - 1
    if place >= 9:
        samples = []
        complete = True
        for session in order[place - 9 : place + 1]:
            value = profiles[session].get(clock)
            if value is None:
                complete = False
                break
            samples.append(value)
        if complete and samples:
            volume_sessions = len(samples)
            expected = Decimal(sum(samples)) / Decimal(len(samples))
            today = profiles[day].get(clock)
            if expected > 0 and today is not None:
                ratio = Decimal(today) / expected
                volume_ok = ratio > 1
    ema_value = None
    ema_dist = None
    ema_ok = False
    if index >= 19:
        ema_value = Decimal(str(ema_series[index - 19]))
        if ema_value != 0:
            ema_dist = (bar.close - ema_value) / ema_value * Decimal(100)
            ema_ok = abs(ema_dist) <= 3
    high = None
    high_through = None
    high_dist = None
    near_high = False
    if prior_index >= 19:
        window = highs[prior_index - 19 : prior_index + 1]
        high = max(window)
        high_through = sessions[prior_index]
        if high != 0:
            high_dist = (high - bar.close) / high * Decimal(100)
            near_high = Decimal("0") <= high_dist <= Decimal("2")
    return _Flags(
        day_gain=day_gain,
        rising=rising,
        higher_close=higher_close,
        volume=volume_ok,
        ema_band=ema_ok,
        near_high=near_high,
        prior_close=prior_close,
        prior_session=prior_session,
        gain_pct=gain,
        ema20=ema_value,
        ema_dist=ema_dist,
        high=high,
        high_through=high_through,
        high_dist=high_dist,
        expected_volume=expected,
        volume_ratio=ratio,
        volume_sessions=volume_sessions,
    )


def _consecutive(group: list[Candle]) -> bool:
    for earlier, later in zip(group, group[1:]):
        if session_date(earlier.end) != session_date(later.end) or later.end - earlier.end != STEP:
            return False
    return True


def _close(symbol: str, variant: str, position: _Position, price: Decimal, when: datetime, reason: str) -> dict:
    flags = position.flags
    return {
        "symbol": symbol,
        "variant": variant,
        "mode": "intraday",
        "signal_time": position.signal_time,
        "signal_price": position.signal_price,
        "entry_time": position.entry_time,
        "entry_bar_end": position.entry_bar_end,
        "entry_price": position.entry_price,
        "quantity": position.quantity,
        "previous_close": flags.prior_close,
        "ltp": position.signal_price,
        "ema20": flags.ema20,
        "distance_pct": flags.ema_dist,
        "down_days": 0,
        "today_drop_pct": flags.gain_pct,
        "session_date": position.session_date,
        "ema_through": position.signal_time,
        "prior_session": flags.prior_session,
        "high_through": flags.high_through,
        "high": flags.high,
        "expected_volume": flags.expected_volume,
        "volume_ratio": flags.volume_ratio,
        "volume_sessions": flags.volume_sessions,
        "rising_ok": flags.rising,
        "session_final": False,
        "exit_time": when,
        "exit_price": price,
        "exit_reason": reason,
    }


def _unresolved(symbol: str, variant: str, position: _Position) -> dict:
    trade = _close(symbol, variant, position, Decimal("0"), position.entry_bar_end, "unresolved")
    trade["exit_price"] = None
    trade["exit_time"] = None
    return trade


def _walk(symbol: str, bars: list[Candle], flags: list[_Flags | None], variants: tuple[str, ...], armed: set[int] | None) -> list[dict]:
    final_end: dict[date, datetime] = {}
    for bar in bars:
        day = session_date(bar.end)
        current = final_end.get(day)
        if current is None or bar.end > current:
            final_end[day] = bar.end
    legs = {variant: _Leg() for variant in variants}
    trades: list[dict] = []
    for index, bar in enumerate(bars):
        day = session_date(bar.end)
        state = flags[index]
        session_final = final_end.get(day) == bar.end
        for variant, leg in legs.items():
            if leg.pending is not None:
                signal_time, signal_price, signal_flags, signal_day = leg.pending
                leg.pending = None
                if day == signal_day and bar.open > 0:
                    quantity = int(PER_TRADE_CAP // bar.open)
                    if quantity >= 1:
                        entry = bar.open
                        leg.position = _Position(
                            signal_time=signal_time,
                            signal_price=signal_price,
                            entry_time=bar.start,
                            entry_bar_end=bar.end,
                            entry_price=entry,
                            quantity=quantity,
                            flags=signal_flags,
                            session_date=signal_day,
                            stop=entry * (Decimal(1) - STOP_PCT),
                            target=entry * (Decimal(1) + TARGET_PCT),
                        )
            position = leg.position
            if position is not None and bar.end > position.entry_bar_end:
                reason = exit_on_bar(Side.BUY, position.stop, position.target, bar)
                if reason == "stop":
                    trades.append(_close(symbol, variant, position, position.stop, bar.end, "stop"))
                    leg.position = None
                elif reason == "target":
                    trades.append(_close(symbol, variant, position, position.target, bar.end, "target"))
                    leg.position = None
            if leg.position is not None and session_final and leg.position.session_date == day:
                closed = _close(symbol, variant, leg.position, bar.close, bar.end, "session_flatten")
                closed["session_final"] = True
                trades.append(closed)
                leg.position = None
            should_arm = False
            if leg.position is None and leg.pending is None and state is not None:
                if armed is None:
                    should_arm = _match(variant, state)
                elif index in armed:
                    should_arm = True
            if should_arm and state is not None:
                leg.pending = (bar.end, bar.close, state, day)
    for variant, leg in legs.items():
        if leg.position is not None:
            trades.append(_unresolved(symbol, variant, leg.position))
    return trades


def prepare(symbol: str, bars_5m: list[Candle], bars_1d: list[Candle]) -> tuple[list[Candle], list[_Flags | None], dict[str, int], list[int]]:
    bars = sorted((bar for bar in bars_5m if bar.symbol == symbol), key=lambda bar: bar.end)
    sessions, closes, highs = _daily([bar for bar in bars_1d if bar.symbol == symbol])
    order, profiles = _profiles(bars)
    ema_series = _ema([float(bar.close) for bar in bars], 20)
    flags: list[_Flags | None] = []
    funnel = {"eligible": 0, "day_gain": 0, "rising": 0, "volume": 0, "ema": 0, "near_high": 0}
    eligible: list[int] = []
    for index, bar in enumerate(bars):
        state = _flags_for(bars, index, sessions, closes, highs, order, profiles, ema_series)
        flags.append(state)
        if state is None:
            continue
        if index + 1 < len(bars) and session_date(bars[index + 1].end) == session_date(bar.end):
            eligible.append(index)
        funnel["eligible"] += 1
        if not state.day_gain:
            continue
        funnel["day_gain"] += 1
        if not state.rising:
            continue
        funnel["rising"] += 1
        if not state.volume:
            continue
        funnel["volume"] += 1
        if not state.ema_band:
            continue
        funnel["ema"] += 1
        if not state.near_high:
            continue
        funnel["near_high"] += 1
    return bars, flags, funnel, eligible


def simulate_breakout(
    symbol: str, bars_5m: list[Candle], bars_1d: list[Candle]
) -> tuple[list[dict], dict[str, int], list[Candle], list[int], list[_Flags | None]]:
    bars, flags, funnel, eligible = prepare(symbol, bars_5m, bars_1d)
    trades = _walk(symbol, bars, flags, VARIANTS, None)
    return trades, funnel, bars, eligible, flags


def simulate_indexed(symbol: str, bars: list[Candle], flags: list[_Flags | None], indexes: list[int], variant: str) -> list[dict]:
    return _walk(symbol, bars, flags, (variant,), set(indexes))


def lookahead_audit(raw_trades: list[dict]) -> dict:
    """Check the full-rule book. A single failure blocks classification."""
    full = [trade for trade in raw_trades if trade["variant"] == "full"]
    failures: list[str] = []
    unresolved: list[dict] = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for trade in full:
        symbol = trade["symbol"]
        if trade["prior_session"] is None or trade["prior_session"] >= trade["session_date"]:
            failures.append(f"{symbol} previous close is not from a session before the signal")
        if trade["ema_through"] != trade["signal_time"] or trade["ema_through"] > trade["signal_time"]:
            failures.append(f"{symbol} EMA is not the completed signal bar")
        if not trade["rising_ok"]:
            failures.append(f"{symbol} three rising candles were not complete at the signal")
        if trade["volume_sessions"] != 10 or trade["expected_volume"] is None:
            failures.append(f"{symbol} volume average is not the prior 10 sessions")
        if trade["volume_ratio"] is None or trade["volume_ratio"] <= 1:
            failures.append(f"{symbol} volume ratio does not exclude a non-confirming bar")
        if trade["high_through"] is None or trade["high_through"] >= trade["session_date"]:
            failures.append(f"{symbol} 20-day high includes the signal session")
        if not in_window(trade["signal_time"]):
            failures.append(f"{symbol} signal is outside 09:30-15:00 IST")
        if trade["entry_bar_end"] <= trade["signal_time"] or session_date(trade["entry_time"]) != trade["session_date"]:
            failures.append(f"{symbol} entry is not the next same-session open")
        if trade["exit_time"] is not None and trade["exit_time"] < trade["entry_time"]:
            failures.append(f"{symbol} exit is before the entry")
        if trade["exit_reason"] == "session_flatten":
            if not trade["session_final"]:
                failures.append(f"{symbol} session exit is not the final completed 5-minute close")
        elif trade["exit_reason"] == "unresolved":
            unresolved.append({"symbol": symbol, "session_date": trade["session_date"].isoformat(), "entry_time": trade["entry_time"].isoformat()})
        elif trade["exit_reason"] not in {"stop", "target"}:
            failures.append(f"{symbol} unexpected exit {trade['exit_reason']}")
        grouped[symbol].append(trade)
    for symbol, rows in grouped.items():
        rows.sort(key=lambda trade: trade["entry_time"])
        for earlier, later in zip(rows, rows[1:]):
            if earlier["exit_time"] is None or later["entry_time"] < earlier["exit_time"]:
                failures.append(f"overlapping positions for {symbol}")
                break
    def failed(fragment: str) -> bool:
        return any(fragment in item for item in failures)

    checks = [
        {"item": "Previous daily close is from a session strictly before the signal", "status": "FAIL" if failed("previous close") else "PASS"},
        {"item": "EMA20 uses only completed 5-minute bars through the signal", "status": "FAIL" if failed("EMA") else "PASS"},
        {"item": "Three rising candles are completed, consecutive, and on the signal session", "status": "FAIL" if failed("rising") else "PASS"},
        {"item": "Current cumulative volume is compared with the previous 10 completed sessions", "status": "FAIL" if failed("volume average") else "PASS"},
        {"item": "Today's volume is not part of the historical average", "status": "FAIL" if failed("volume ratio") else "PASS"},
        {"item": "20-day high uses only completed sessions before the signal day", "status": "FAIL" if failed("20-day high") else "PASS"},
        {"item": "Signal is a completed 5-minute bar from 09:30 through 15:00 IST", "status": "FAIL" if failed("outside") else "PASS"},
        {"item": "Entry is the next same-session 5-minute open", "status": "FAIL" if failed("entry") else "PASS"},
        {"item": "Exit uses only information available at the exit bar", "status": "FAIL" if failed("exit is before") or failed("unexpected exit") else "PASS"},
        {"item": "Session exit is the final completed 5-minute close, not the official daily close", "status": "FAIL" if failed("session exit") else "PASS"},
    ]
    status = "FAIL" if failures or any(check["status"] == "FAIL" for check in checks) else "PASS"
    return {
        "status": status,
        "valid": status == "PASS",
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures[:50],
        "unresolved_count": len(unresolved),
        "unresolved": unresolved[:100],
        "full_trades": len(full),
    }
