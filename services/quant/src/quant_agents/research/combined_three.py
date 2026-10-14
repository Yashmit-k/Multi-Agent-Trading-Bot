"""Combined book for the three screenshot rules.

Each buy is at most ₹20,000. Open entry notional for one symbol stays at or
below ₹40,000. A variant changes one setting. Nothing in this module sells
because price fell, places orders, or reads the holdout.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from contracts.enums import Side
from contracts.schemas.market import Candle
from core_paper.costs import slipped_price
from quant_agents.research.delivery_costs import delivery_buy, delivery_sell, intraday_buy, intraday_sell
from quant_agents.research.intraday_breakout import clock_minutes
from quant_agents.research.rebound import daily_context, session_date

ORDER_CAP = Decimal("20000")
SYMBOL_CAP = Decimal("40000")
STEP = timedelta(minutes=5)
FILL_RANK = {"wide": 0, "narrow": 1, "dip": 2}

DIP_SCAN_OPEN = 9 * 60 + 15
DIP_SCAN_CLOSE = 15 * 60 + 15
NARROW_OPEN = 9 * 60 + 30
NARROW_CLOSE = 15 * 60
WIDE_OPEN = 10 * 60
WIDE_CLOSE = 13 * 60
EOD_CHECK = 15 * 60 + 15


@dataclass(frozen=True, slots=True)
class BookConfig:
    """One book. Unset fields keep the baseline screenshot rules."""

    name: str = "baseline"
    slippage_bps: Decimal = Decimal("0")
    wide_gain_min: Decimal = Decimal("1")
    wide_gain_max: Decimal = Decimal("4")
    wide_retrace: bool = True
    narrow_gain_min: Decimal = Decimal("0.50")
    narrow_gain_max: Decimal = Decimal("0.75")
    narrow_volume_multiple: Decimal = Decimal("1")
    wide_volume_multiple: Decimal = Decimal("1")
    ema_band: Decimal = Decimal("3")
    high_distance: Decimal = Decimal("2")
    dip_down_days: int = 3
    dip_band_low: Decimal = Decimal("-12")
    dip_band_high: Decimal = Decimal("-5")
    dip_deeper_low: Decimal = Decimal("-12")
    dip_deeper_high: Decimal = Decimal("-8")
    dip_second: bool = True
    dip_cost_guard: bool = False
    dip_tranche1_guard: bool = False
    time_exit_days: int | None = None
    wide_enabled: bool = True
    narrow_enabled: bool = True
    dip_enabled: bool = True
    news_block: bool = False


@dataclass(slots=True)
class _Intent:
    algo: str
    tranche: int
    signal_time: datetime
    signal_price: Decimal
    session: date
    gain: Decimal | None = None
    distance: Decimal | None = None
    down_days: int | None = None


@dataclass(slots=True)
class _Gate:
    """Same-session announcements seen at or before the bar block new entries."""

    symbol: str
    blocked_now: bool = False
    rows: list[dict] = field(default_factory=list)
    seen: set[tuple[str, int, date]] = field(default_factory=set)


@dataclass(slots=True)
class _Lot:
    algo: str
    tranche: int
    signal_time: datetime
    signal_price: Decimal
    entry_time: datetime
    entry_bar_end: datetime
    entry_session: date
    entry_price: Decimal
    quantity: int
    remaining: int
    half_qty: int
    half_sold: bool = False
    armed: bool = False
    peak: Decimal | None = None
    slices: list[dict] = field(default_factory=list)
    gain: Decimal | None = None
    distance: Decimal | None = None
    down_days: int | None = None
    exit_due: date | None = None


def _open_notional(lots: list[_Lot]) -> Decimal:
    return sum((lot.entry_price * lot.remaining for lot in lots), Decimal("0"))


def _pay(side: Side, price: Decimal, slippage_bps: Decimal) -> Decimal:
    if slippage_bps == 0:
        return price
    return slipped_price(side, price, slippage_bps)


def _shares(price: Decimal, room: Decimal) -> int:
    budget = ORDER_CAP if room > ORDER_CAP else room
    if price <= 0 or budget < price:
        return 0
    return int(budget / price)


def _round_trip(entry: Decimal, exit_price: Decimal, quantity: int, same_session: bool) -> tuple[Decimal, Decimal]:
    bought = entry * quantity
    sold = exit_price * quantity
    if same_session:
        charges = intraday_buy(bought).total + intraday_sell(sold).total
    else:
        charges = delivery_buy(bought).total + delivery_sell(sold).total
    return (exit_price - entry) * quantity - charges, charges


def _slice(lot: _Lot, quantity: int, price: Decimal, when: datetime, reason: str) -> dict:
    same_session = session_date(when) == lot.entry_session
    net, charges = _round_trip(lot.entry_price, price, quantity, same_session)
    lot.remaining -= quantity
    return {
        "symbol": "",
        "algo": lot.algo,
        "tranche": lot.tranche,
        "signal_time": lot.signal_time,
        "signal_price": lot.signal_price,
        "entry_time": lot.entry_time,
        "entry_bar_end": lot.entry_bar_end,
        "entry_session": lot.entry_session,
        "entry_price": lot.entry_price,
        "exit_time": when,
        "exit_price": price,
        "quantity": quantity,
        "entry_notional": lot.entry_price * quantity,
        "exit_reason": reason,
        "same_session": same_session,
        "charges": charges,
        "net_pnl": net,
        "entry_gain": lot.gain,
        "entry_ema_distance": lot.distance,
        "entry_down_days": lot.down_days,
    }


def _touch(bar: Candle, target: Decimal) -> Decimal | None:
    if bar.open >= target:
        return bar.open
    if bar.high >= target:
        return target
    return None


def _dip_exit(lot: _Lot, bar: Candle, ema: Decimal | None, config: BookConfig) -> list[dict]:
    if lot.tranche == 1:
        target = lot.entry_price * Decimal("1.02")
    elif ema is None or ema <= 0:
        return []
    else:
        target = ema * Decimal("1.03")
    raw = _touch(bar, target)
    if raw is None or lot.remaining <= 0:
        return []
    price = _pay(Side.SELL, raw, config.slippage_bps)
    reason = "target_2pct" if lot.tranche == 1 else "ema_plus_3"
    guarded = (lot.tranche == 1 and config.dip_tranche1_guard) or (lot.tranche == 2 and config.dip_cost_guard)
    if guarded:
        net, _charges = _round_trip(lot.entry_price, price, lot.remaining, session_date(bar.end) == lot.entry_session)
        if net <= 0:
            return []
    return [_slice(lot, lot.remaining, price, bar.end, reason)]


def _gain_exit(lot: _Lot, bar: Candle, config: BookConfig) -> list[dict]:
    closed: list[dict] = []
    plus_15 = lot.entry_price * Decimal("1.015")
    plus_2 = lot.entry_price * Decimal("1.02")
    retraced = False
    if lot.algo == "wide":
        if not lot.half_sold and lot.remaining > 0:
            raw = _touch(bar, plus_2)
            if raw is not None:
                quantity = min(lot.half_qty, lot.remaining) if lot.half_qty > 0 else lot.remaining
                closed.append(_slice(lot, quantity, _pay(Side.SELL, raw, config.slippage_bps), bar.end, "half_2pct"))
                lot.half_sold = True
        if config.wide_retrace and lot.armed and lot.peak is not None and lot.remaining > 0:
            trigger = lot.peak * Decimal("0.99")
            raw = None
            if bar.open <= trigger:
                raw = bar.open
            elif bar.low <= trigger:
                raw = trigger
            if raw is not None:
                closed.append(_slice(lot, lot.remaining, _pay(Side.SELL, raw, config.slippage_bps), bar.end, "retrace_1pct"))
                retraced = True
        if config.wide_retrace and not lot.armed and bar.high >= plus_15:
            lot.armed = True
            lot.peak = bar.high
        elif config.wide_retrace and lot.armed and lot.remaining > 0 and lot.peak is not None and not retraced:
            lot.peak = max(lot.peak, bar.high)
    if lot.remaining > 0 and clock_minutes(bar.end) == EOD_CHECK and lot.algo in {"narrow", "wide"}:
        price = _pay(Side.SELL, bar.close, config.slippage_bps)
        net, _charges = _round_trip(lot.entry_price, price, lot.remaining, session_date(bar.end) == lot.entry_session)
        if net > 0:
            closed.append(_slice(lot, lot.remaining, price, bar.end, "eod_positive"))
    return closed


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


def _volume_above(
    day: date,
    clock: int,
    order: list[date],
    profiles: dict[date, dict[int, int]],
    multiple: Decimal,
) -> bool:
    place = order.index(day) if day in profiles else -1
    if place < 10:
        return False
    samples: list[int] = []
    for session in order[place - 10 : place]:
        value = profiles[session].get(clock)
        if value is None:
            return False
        samples.append(value)
    expected = Decimal(sum(samples)) / Decimal(len(samples))
    today = profiles[day].get(clock)
    return expected > 0 and today is not None and Decimal(today) > expected * multiple


def _prior_high(day: date, sessions: list[date], highs: list[Decimal]) -> Decimal | None:
    index = 0
    while index < len(sessions) and sessions[index] < day:
        index += 1
    index -= 1
    if index < 19:
        return None
    return max(highs[index - 19 : index + 1])


def _rising(bars: list[Candle], index: int) -> bool:
    if index < 2:
        return False
    trio = bars[index - 2 : index + 1]
    for earlier, later in zip(trio, trio[1:]):
        if session_date(earlier.end) != session_date(later.end) or later.end - earlier.end != STEP:
            return False
    return all(bar.close > bar.open for bar in trio)


def _has(lots: list[_Lot], pending: list[_Intent], algo: str, tranche: int | None = None) -> bool:
    for lot in lots:
        if lot.remaining > 0 and lot.algo == algo and (tranche is None or lot.tranche == tranche):
            return True
    return any(item.algo == algo and (tranche is None or item.tranche == tranche) for item in pending)


def _fill(intent: _Intent, bar: Candle, lots: list[_Lot], symbol: str, config: BookConfig) -> _Lot | None:
    entry = _pay(Side.BUY, bar.open, config.slippage_bps)
    room = SYMBOL_CAP - _open_notional(lots)
    quantity = _shares(entry, room)
    if quantity <= 0:
        return None
    notional = entry * quantity
    if notional > ORDER_CAP or _open_notional(lots) + notional > SYMBOL_CAP:
        return None
    lot = _Lot(
        algo=intent.algo,
        tranche=intent.tranche,
        signal_time=intent.signal_time,
        signal_price=intent.signal_price,
        entry_time=bar.start,
        entry_bar_end=bar.end,
        entry_session=session_date(bar.end),
        entry_price=entry,
        quantity=quantity,
        remaining=quantity,
        half_qty=quantity // 2,
        gain=intent.gain,
        distance=intent.distance,
        down_days=intent.down_days,
    )
    lots.append(lot)
    if _open_notional(lots) > SYMBOL_CAP:
        raise RuntimeError(f"{symbol} open notional exceeded {SYMBOL_CAP}")
    return lot


def _reject(intent: _Intent, symbol: str, lots: list[_Lot], rejected: list[dict]) -> None:
    rejected.append(
        {
            "symbol": symbol,
            "algo": intent.algo,
            "tranche": intent.tranche,
            "signal_time": intent.signal_time,
            "requested_notional": format(ORDER_CAP, "f"),
            "open_notional": format(_open_notional(lots), "f"),
            "reason": "symbol_cap",
        }
    )


def attempt_fills(
    pending: list[_Intent],
    bar: Candle,
    lots: list[_Lot],
    symbol: str,
    config: BookConfig,
    rejected: list[dict],
) -> list[_Intent]:
    """Fill ready signals Wide, Narrow, Dip tranche 1, then Dip tranche 2."""
    still: list[_Intent] = []
    ready: list[_Intent] = []
    for intent in pending:
        if session_date(bar.end) == intent.session and bar.end <= intent.signal_time:
            still.append(intent)
            continue
        if session_date(bar.end) != intent.session:
            continue
        ready.append(intent)
    ready.sort(key=lambda item: (FILL_RANK[item.algo], item.tranche, item.signal_time))
    for intent in ready:
        if _fill(intent, bar, lots, symbol, config) is None:
            _reject(intent, symbol, lots, rejected)
    return still


def _scan(
    bars: list[Candle],
    index: int,
    ema: Decimal | None,
    previous_close: Decimal | None,
    down_days: int,
    prior_high: Decimal | None,
    order: list[date],
    profiles: dict[date, dict[int, int]],
    lots: list[_Lot],
    pending: list[_Intent],
    config: BookConfig,
    gate: _Gate | None = None,
) -> None:
    bar = bars[index]
    clock = clock_minutes(bar.end)
    day = session_date(bar.end)
    if previous_close in (None, 0):
        return
    gain = (bar.close - previous_close) / previous_close * Decimal(100)
    distance = None
    if ema not in (None, 0):
        distance = (bar.close - ema) / ema * Decimal(100)

    def signal(algo: str, tranche: int) -> None:
        if gate is not None and gate.blocked_now:
            key = (algo, tranche, day)
            if key not in gate.seen:
                gate.seen.add(key)
                gate.rows.append(
                    {"symbol": gate.symbol, "algo": algo, "tranche": tranche, "signal_time": bar.end, "session": day}
                )
            return
        pending.append(_Intent(algo, tranche, bar.end, bar.close, day, gain, distance, down_days))

    dip_window = DIP_SCAN_OPEN <= clock <= DIP_SCAN_CLOSE and clock % 30 == 15
    if config.dip_enabled and dip_window and distance is not None:
        drop = gain <= Decimal("-1")
        band = config.dip_band_low <= distance <= config.dip_band_high
        deeper = config.dip_deeper_low <= distance <= config.dip_deeper_high
        if down_days >= config.dip_down_days and drop and band and not _has(lots, pending, "dip", 1):
            signal("dip", 1)
        if config.dip_second and down_days >= config.dip_down_days and drop and deeper and not _has(lots, pending, "dip", 2):
            signal("dip", 2)
    if config.narrow_enabled and NARROW_OPEN <= clock <= NARROW_CLOSE and not _has(lots, pending, "narrow"):
        volume_ok = _volume_above(day, clock, order, profiles, config.narrow_volume_multiple)
        ema_ok = distance is not None and abs(distance) <= config.ema_band
        below_high = False
        if prior_high not in (None, 0):
            below_high = (prior_high - bar.close) / prior_high * Decimal(100) >= config.high_distance
        gain_ok = config.narrow_gain_min <= gain <= config.narrow_gain_max
        if gain_ok and _rising(bars, index) and volume_ok and ema_ok and below_high:
            signal("narrow", 1)
    if config.wide_enabled and WIDE_OPEN <= clock <= WIDE_CLOSE and not _has(lots, pending, "wide"):
        volume_ok = _volume_above(day, clock, order, profiles, config.wide_volume_multiple)
        if volume_ok and config.wide_gain_min <= gain <= config.wide_gain_max:
            signal("wide", 1)


def _time_exit(lot: _Lot, bar: Candle, config: BookConfig) -> list[dict]:
    """Sell a lot marked at an earlier 15:15 on the first bar of a later session, at its open."""
    if lot.exit_due is None or lot.remaining <= 0 or session_date(bar.end) <= lot.exit_due:
        return []
    price = _pay(Side.SELL, bar.open, config.slippage_bps)
    return [_slice(lot, lot.remaining, price, bar.end, "time_exit")]


def _announcement_days(announcements: list[datetime] | None) -> dict[date, datetime]:
    earliest: dict[date, datetime] = {}
    for moment in announcements or []:
        day = session_date(moment)
        if day not in earliest or moment < earliest[day]:
            earliest[day] = moment
    return earliest


def _mark(lot: _Lot, price: Decimal, when: datetime, config: BookConfig) -> tuple[Decimal, Decimal]:
    sold = _pay(Side.SELL, price, config.slippage_bps)
    return _round_trip(lot.entry_price, sold, lot.remaining, session_date(when) == lot.entry_session)


def simulate_symbol(
    symbol: str,
    bars_5m: list[Candle],
    bars_1d: list[Candle],
    config: BookConfig | None = None,
    rejected: list[dict] | None = None,
    path: list[dict] | None = None,
    announcements: list[datetime] | None = None,
    blocked: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Walk one symbol. Closed slices and open marks use the same book."""
    book = config or BookConfig()
    rejected_rows = rejected if rejected is not None else []
    gate = _Gate(symbol) if book.news_block else None
    first_announcement = _announcement_days(announcements) if book.news_block else {}
    bars = sorted((bar for bar in bars_5m if bar.symbol == symbol), key=lambda item: item.end)
    daily = [bar for bar in bars_1d if bar.symbol == symbol]
    dates, closes, ema_at, streaks = daily_context(daily)
    sessions: list[date] = []
    highs: list[Decimal] = []
    for bar in sorted(daily, key=lambda item: item.end):
        day = session_date(bar.end)
        if sessions and sessions[-1] == day:
            highs[-1] = max(highs[-1], bar.high)
            continue
        sessions.append(day)
        highs.append(bar.high)
    order, profiles = _profiles(bars)
    lots: list[_Lot] = []
    pending: list[_Intent] = []
    closed: list[dict] = []
    realized = Decimal("0")
    for index, bar in enumerate(bars):
        day = session_date(bar.end)
        prior = next((cursor for cursor in range(len(dates) - 1, -1, -1) if dates[cursor] < day), None)
        ema = None if prior is None else ema_at[prior]
        for lot in lots:
            if lot.remaining <= 0 or bar.end <= lot.entry_bar_end:
                continue
            sold = _time_exit(lot, bar, book)
            if not sold:
                if lot.algo == "dip":
                    sold = _dip_exit(lot, bar, ema, book)
                else:
                    sold = _gain_exit(lot, bar, book)
            closed.extend(sold)
            realized += sum((row["net_pnl"] for row in sold), Decimal("0"))
        if book.time_exit_days is not None and clock_minutes(bar.end) == EOD_CHECK:
            for lot in lots:
                if lot.remaining > 0 and lot.exit_due is None and (day - lot.entry_session).days >= book.time_exit_days:
                    lot.exit_due = day
        pending = attempt_fills(pending, bar, lots, symbol, book, rejected_rows)
        if gate is not None:
            seen_at = first_announcement.get(day)
            gate.blocked_now = seen_at is not None and seen_at <= bar.end
        if prior is not None:
            _scan(
                bars,
                index,
                ema,
                closes[prior],
                streaks[prior],
                _prior_high(day, sessions, highs),
                order,
                profiles,
                lots,
                pending,
                book,
                gate,
            )
        if path is not None and clock_minutes(bar.end) == EOD_CHECK:
            unrealized = Decimal("0")
            open_notional = Decimal("0")
            open_count = 0
            for lot in lots:
                if lot.remaining <= 0:
                    continue
                net, _charges = _mark(lot, bar.close, bar.end, book)
                unrealized += net
                open_notional += lot.entry_price * lot.remaining
                open_count += 1
            path.append(
                {
                    "time": bar.end,
                    "realized": realized,
                    "unrealized": unrealized,
                    "open_notional": open_notional,
                    "open_count": open_count,
                }
            )
    marks: list[dict] = []
    if bars:
        last = bars[-1]
        for lot in lots:
            if lot.remaining <= 0:
                continue
            net, charges = _mark(lot, last.close, last.end, book)
            marks.append(
                {
                    "symbol": symbol,
                    "algo": lot.algo,
                    "tranche": lot.tranche,
                    "entry_time": lot.entry_time,
                    "entry_price": lot.entry_price,
                    "quantity": lot.remaining,
                    "entry_notional": lot.entry_price * lot.remaining,
                    "mark_time": last.end,
                    "mark_price": last.close,
                    "charges": charges,
                    "unrealized_net": net,
                    "entry_gain": lot.gain,
                    "entry_ema_distance": lot.distance,
                    "entry_down_days": lot.down_days,
                    "exit_due": lot.exit_due,
                }
            )
    for row in closed:
        row["symbol"] = symbol
    if gate is not None and blocked is not None:
        blocked.extend(gate.rows)
    return closed, marks


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _days(start: datetime, end: datetime) -> Decimal:
    return Decimal(str((end - start).total_seconds())) / Decimal("86400")


def combine_paths(paths: list[list[dict]]) -> list[dict]:
    """Carry each symbol forward so a missing 15:15 does not drop its open book."""
    times = sorted({point["time"] for path in paths for point in path})
    cursors = [0 for _path in paths]
    last: list[dict | None] = [None for _path in paths]
    combined: list[dict] = []
    for moment in times:
        realized = Decimal("0")
        unrealized = Decimal("0")
        open_notional = Decimal("0")
        open_count = 0
        for index, path in enumerate(paths):
            while cursors[index] < len(path) and path[cursors[index]]["time"] <= moment:
                last[index] = path[cursors[index]]
                cursors[index] += 1
            point = last[index]
            if point is None:
                continue
            realized += point["realized"]
            unrealized += point["unrealized"]
            open_notional += point["open_notional"]
            open_count += point["open_count"]
        combined.append(
            {
                "time": moment,
                "realized": realized,
                "unrealized": unrealized,
                "open_notional": open_notional,
                "open_count": open_count,
            }
        )
    return combined


def measure(closed: list[dict], marks: list[dict], paths: list[list[dict]]) -> dict[str, object]:
    """Realized and unrealized results, drawdown, hold time, and capital in use."""
    realized_net = sum((row["net_pnl"] for row in closed), Decimal("0"))
    unrealized_net = sum((row["unrealized_net"] for row in marks), Decimal("0"))
    series = combine_paths(paths)
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    open_values: list[Decimal] = []
    for point in series:
        equity = point["realized"] + point["unrealized"]
        peak = equity if equity > peak else peak
        decline = peak - equity
        if decline > max_drawdown:
            max_drawdown = decline
        open_values.append(point["open_notional"])
    average_open = sum(open_values, Decimal("0")) / Decimal(len(open_values)) if open_values else Decimal("0")
    peak_open = max(open_values) if open_values else Decimal("0")
    closed_holds = [_days(row["entry_time"], row["exit_time"]) for row in closed]
    open_holds = [_days(row["entry_time"], row["mark_time"]) for row in marks]
    ending_open = sum((row["entry_notional"] for row in marks), Decimal("0"))

    def _block(rows: list[dict], field_name: str) -> dict[str, object]:
        net = sum((row[field_name] for row in rows), Decimal("0"))
        return {"count": len(rows), "net": format(net, "f")}

    by_algo: dict[str, dict[str, object]] = {}
    for algo in ("dip", "narrow", "wide"):
        by_algo[algo] = {
            "realized": _block([row for row in closed if row["algo"] == algo], "net_pnl"),
            "open": _block([row for row in marks if row["algo"] == algo], "unrealized_net"),
        }
    dip_tranches = {}
    for tranche in (1, 2):
        dip_tranches[str(tranche)] = {
            "realized": _block([row for row in closed if row["algo"] == "dip" and row["tranche"] == tranche], "net_pnl"),
            "open": _block([row for row in marks if row["algo"] == "dip" and row["tranche"] == tranche], "unrealized_net"),
        }
    return {
        "realized_slices": len(closed),
        "realized_net": format(realized_net, "f"),
        "open_marks": len(marks),
        "unrealized_net": format(unrealized_net, "f"),
        "total_net": format(realized_net + unrealized_net, "f"),
        "max_drawdown": format(max_drawdown, "f"),
        "average_open_notional": format(average_open, "f"),
        "peak_open_notional": format(peak_open, "f"),
        "ending_open_notional": format(ending_open, "f"),
        "open_positions": len(marks),
        "median_closed_hold_days": None if _median(closed_holds) is None else format(_median(closed_holds), "f"),
        "max_closed_hold_days": None if not closed_holds else format(max(closed_holds), "f"),
        "median_open_hold_days": None if _median(open_holds) is None else format(_median(open_holds), "f"),
        "max_open_hold_days": None if not open_holds else format(max(open_holds), "f"),
        "by_algo": by_algo,
        "dip_tranches": dip_tranches,
        "note": "Backtest result only. Open marks are not forced flat, and there is no stop.",
    }


def passes(variant: dict[str, object], baseline: dict[str, object]) -> bool:
    """Keep a variant when total net rises, capital lock-up does not, and drawdown does not."""
    return (
        Decimal(str(variant["total_net"])) > Decimal(str(baseline["total_net"]))
        and Decimal(str(variant["average_open_notional"])) <= Decimal(str(baseline["average_open_notional"]))
        and Decimal(str(variant["max_drawdown"])) <= Decimal(str(baseline["max_drawdown"]))
    )


def choose(baseline: dict[str, object], variants: list[tuple[BookConfig, dict[str, object]]]) -> BookConfig:
    """Highest total net among variants that pass. Otherwise the baseline config."""
    winner: tuple[BookConfig, dict[str, object]] | None = None
    for config, metrics in variants:
        if not passes(metrics, baseline):
            continue
        if winner is None or Decimal(str(metrics["total_net"])) > Decimal(str(winner[1]["total_net"])):
            winner = (config, metrics)
    if winner is None:
        return BookConfig(name="baseline")
    return winner[0]


def merge_books(parts: list[BookConfig], name: str, slippage_bps: Decimal = Decimal("0")) -> BookConfig:
    """Overlay the non-baseline fields of each kept book."""
    merged = BookConfig()
    for part in parts:
        for field_name in (
            "wide_gain_min",
            "wide_gain_max",
            "wide_retrace",
            "narrow_gain_min",
            "narrow_gain_max",
            "narrow_volume_multiple",
            "wide_volume_multiple",
            "ema_band",
            "high_distance",
            "dip_down_days",
            "dip_band_low",
            "dip_band_high",
            "dip_deeper_low",
            "dip_deeper_high",
            "dip_second",
            "dip_cost_guard",
            "dip_tranche1_guard",
        ):
            current = getattr(part, field_name)
            if current != getattr(BookConfig(), field_name):
                merged = replace(merged, **{field_name: current})
    return replace(merged, name=name, slippage_bps=slippage_bps)


def summarize(closed: list[dict], marks: list[dict]) -> dict[str, object]:
    """Realized slices and open marks. A positive net is not a claim of an edge."""
    return measure(closed, marks, [])
