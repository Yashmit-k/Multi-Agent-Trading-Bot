"""Exit-rules study, scored per services/quant/docs/exit-rules-protocol.md.

Stage 1 replays the live quant agents + fusion + proposal rule over the snapshot and records every
BUY/SELL proposal (cached per symbol). Stage 2 replays each exit rule on those same entries using
5-minute bars. Run with the root virtualenv and the pytest.ini source paths on PYTHONPATH:

    python -m quant_agents.research.exit_rules --workers 9
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import pickle
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from quant_agents.calendar.static_nse import StaticNseCalendar
from quant_agents.research import ml_ensemble as me
from quant_agents.research.timesfm3.scores import EXCLUDED_SYMBOL

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[5]
STOCK_5M = ROOT / "snapshots/nifty50/5m/candles.jsonl"
STOCK_1D = ROOT / "snapshots/nifty50/1D/candles.jsonl"
INDEX_5M = ROOT / "snapshots/context_through_20261005/5m/candles.jsonl"
INDEX_1D = ROOT / "snapshots/context_through_20261005/1D/candles.jsonl"
CACHE = ROOT / "datasets/research/exit_rules"
INDEX_NAMES = {"NIFTY 50": "NIFTY50", "INDIA VIX": "INDIAVIX"}
ENTRY_FIRST_END = time(9, 20)
ENTRY_LAST_END = time(15, 15)
LIMIT_MARKUP = 1.0025
INTRADAY_SESSIONS = 250
SWING_START = date(2024, 7, 1)
FEATURE_BARS = 400
INDEX_BARS = 400
MAX_HOLD_SESSIONS = 5
ATR_STOP, ATR_TARGET = 1.0, 2.0
RULES = {"INTRADAY": ("E0", "E1", "E2", "E3", "E4"), "SWING": ("E0", "E1", "E2", "E4")}
COMPARISONS = 7
CALENDAR = StaticNseCalendar()


# --- data -----------------------------------------------------------------------------------------


def split_snapshots() -> None:
    """One pickle of raw bar dicts per symbol and timeframe, so workers read only their own rows."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if (CACHE / "split.done").exists():
        return
    for path, frame, rename in ((STOCK_5M, "5m", {}), (STOCK_1D, "1d", {}), (INDEX_5M, "5m", INDEX_NAMES), (INDEX_1D, "1d", INDEX_NAMES)):
        rows: dict[str, list[dict]] = defaultdict(list)
        with path.open() as handle:
            for line in handle:
                bar = json.loads(line)
                symbol = rename.get(bar["symbol"], bar["symbol"]) if rename else bar["symbol"]
                if rename and symbol not in INDEX_NAMES.values():
                    continue
                if bar.get("timeframe") != frame:
                    continue
                bar["symbol"] = symbol
                rows[symbol].append(bar)
        for symbol, bars in rows.items():
            bars.sort(key=lambda item: item["end"])
            with (CACHE / f"bars-{symbol}-{frame}.pkl").open("wb") as out:
                pickle.dump(bars, out)
    (CACHE / "split.done").write_text("ok")


def _bars(symbol: str, frame: str) -> list[dict]:
    with (CACHE / f"bars-{symbol}-{frame}.pkl").open("rb") as handle:
        return pickle.load(handle)


def stock_symbols() -> list[str]:
    manifest = json.loads((STOCK_5M.parent / "manifest.json").read_text())
    return sorted(item["symbol"] for item in manifest["symbols"] if item["symbol"] != EXCLUDED_SYMBOL)


def _ist(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp).astimezone(IST)


def regular(day: date) -> bool:
    return CALENDAR.covers(day) and CALENDAR.is_trading_day(day)


# --- stage 1: proposals from the live pipeline ---------------------------------------------------


def _candles(rows: list[dict]):
    from contracts.schemas.market import Candle

    return [Candle.model_validate(row) for row in rows]


def scored_sessions(book: str) -> list[date]:
    days = sorted({_ist(row["end"]).date() for row in _bars("NIFTY50", "1d")} | {_ist(row["end"]).date() for row in _bars(stock_symbols()[0], "1d")})
    days = [day for day in days if regular(day)]
    if book == "INTRADAY":
        return days[-INTRADAY_SESSIONS:]
    return [day for day in days if day >= SWING_START]


def index_feature_sets(frame: str, stamps: list[datetime]) -> dict[datetime, tuple]:
    """Regime context per decision stamp, built once and shared by every symbol."""
    from contracts.enums import Timeframe
    from core_features.engine import build_feature_set

    timeframe = Timeframe.M5 if frame == "5m" else Timeframe.D1
    series = {name: _candles(_bars(name, frame)) for name in INDEX_NAMES.values()}
    ends = {name: [bar.end for bar in bars] for name, bars in series.items()}
    out: dict[datetime, tuple] = {}
    for stamp in stamps:
        sets = []
        for name, bars in series.items():
            cut = bisect.bisect_right(ends[name], stamp)
            window = bars[max(0, cut - INDEX_BARS) : cut] if frame == "5m" else bars[:cut]
            built = build_feature_set(name, timeframe, window, stamp)
            if built is not None and built.timestamp <= stamp:
                sets.append(built)
        out[stamp] = tuple(sets)
    return out


def _proposals_for(args: tuple[str, str]) -> tuple[str, str, list[tuple[str, str, float]]]:
    symbol, book = args
    target = CACHE / f"proposals-{book}-{symbol}.json"
    if target.exists():
        return symbol, book, json.loads(target.read_text())
    import logging

    logging.disable(logging.WARNING)
    from contracts.enums import Horizon, Timeframe
    from core_decision.propose import build_proposal
    from core_features.engine import build_feature_set
    from core_fusion import fuse
    from core_paper.backtest import _agent_signals

    frame = "5m" if book == "INTRADAY" else "1d"
    timeframe = Timeframe.M5 if frame == "5m" else Timeframe.D1
    horizon = Horizon.INTRADAY if book == "INTRADAY" else Horizon.SWING
    with (CACHE / f"index-sets-{book}.pkl").open("rb") as handle:
        index_sets = pickle.load(handle)
    sessions = set(scored_sessions(book))
    bars = _candles(_bars(symbol, frame))
    out: list[tuple[str, str, float]] = []
    for cursor, bar in enumerate(bars):
        local = bar.end.astimezone(IST)
        if local.date() not in sessions:
            continue
        window = bars[max(0, cursor - FEATURE_BARS + 1) : cursor + 1] if frame == "5m" else bars[: cursor + 1]
        built = build_feature_set(symbol, timeframe, window, bar.end)
        if built is None:
            continue
        signals = _agent_signals(symbol, built, bar.end, horizon, timeframe, index_sets.get(bar.end, ()))
        aggregate = fuse(signals, horizon=horizon, as_of=bar.end)
        if aggregate is None:
            continue
        proposal = build_proposal(aggregate, bar, bar.end)
        if proposal is not None:
            out.append((bar.end.isoformat(), proposal.side.value, float(bar.close)))
    target.write_text(json.dumps(out))
    return symbol, book, out


def stage_one(workers: int) -> dict[str, dict[str, list[tuple[str, str, float]]]]:
    split_snapshots()
    for book, frame in (("INTRADAY", "5m"), ("SWING", "1d")):
        path = CACHE / f"index-sets-{book}.pkl"
        if path.exists():
            continue
        sessions = set(scored_sessions(book))
        stamps = sorted({datetime.fromisoformat(row["end"]) for row in _bars("NIFTY50", frame) if _ist(row["end"]).date() in sessions})
        with path.open("wb") as handle:
            pickle.dump(index_feature_sets(frame, stamps), handle)
    jobs = [(symbol, book) for book in ("SWING", "INTRADAY") for symbol in stock_symbols()]
    result: dict[str, dict[str, list]] = {"INTRADAY": {}, "SWING": {}}
    with Pool(workers) as pool:
        for symbol, book, proposals in pool.imap_unordered(_proposals_for, jobs):
            result[book][symbol] = proposals
            print(f"stage1 {book} {symbol}: {len(proposals)} proposals", flush=True)
    return result


# --- stage 2: exit rules --------------------------------------------------------------------------


@dataclass
class Path5m:
    ends: list[datetime]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    session: list[date]
    clock: list[time]
    last_of_session: dict[date, int]
    sessions: list[date]
    atr: dict[date, float]


def load_path(symbol: str) -> Path5m:
    rows = [row for row in _bars(symbol, "5m") if regular(_ist(row["end"]).date())]
    ends = [datetime.fromisoformat(row["end"]) for row in rows]
    local = [end.astimezone(IST) for end in ends]
    last: dict[date, int] = {}
    for index, moment in enumerate(local):
        last[moment.date()] = index
    daily = [row for row in _bars(symbol, "1d") if regular(_ist(row["end"]).date())]
    atr: dict[date, float] = {}
    ranges: list[float] = []
    previous_close: float | None = None
    for row in daily:
        day = _ist(row["end"]).date()
        if len(ranges) >= 14:
            atr[day] = float(np.mean(ranges[-14:]))  # the 14 sessions before `day`
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        true_range = high - low if previous_close is None else max(high - low, abs(high - previous_close), abs(low - previous_close))
        ranges.append(true_range)
        previous_close = close
    return Path5m(
        ends=ends,
        open=np.array([float(row["open"]) for row in rows]),
        high=np.array([float(row["high"]) for row in rows]),
        low=np.array([float(row["low"]) for row in rows]),
        close=np.array([float(row["close"]) for row in rows]),
        session=[moment.date() for moment in local],
        clock=[moment.timetz().replace(tzinfo=None) for moment in local],
        last_of_session=last,
        sessions=sorted(last),
        atr=atr,
    )


@dataclass
class Trade:
    symbol: str
    entry_at: datetime
    exit_at: datetime
    exit_session: date
    entry: float
    exit: float
    reason: str
    hold_sessions: int
    net: float
    invested: float


def simulate(symbol: str, path: Path5m, proposals: list[tuple[str, str, float]], book: str, rule: str) -> list[Trade]:
    """One position at a time; every event is acted on from the bar after it."""
    atr_rule = rule in ("E1", "E4")
    max_hold = rule in ("E2", "E4")
    square_off = book == "INTRADAY" and rule in ("E3", "E4")
    events: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for stamp, side, reference in proposals:
        moment = datetime.fromisoformat(stamp)
        if book == "INTRADAY":
            index = bisect.bisect_left(path.ends, moment)
            if index >= len(path.ends) or path.ends[index] != moment:
                continue
        else:  # a daily close: act from the next session, so anchor on this session's last 5m bar
            day = moment.astimezone(IST).date()
            if day not in path.last_of_session:
                continue
            index = path.last_of_session[day]
        events[index].append((side, reference))
    trades: list[Trade] = []
    state = "flat"
    limit = reference_price = stop = target = entry_price = 0.0
    order_last = time_exit = fill_index = 0
    entry_day: date | None = None
    exit_next = False
    n = len(path.ends)
    first = min(events) if events else n

    def close_out(index: int, price: float, reason: str) -> None:
        nonlocal state, exit_next
        result = me.trade_net(entry_price, price)
        if result is not None:
            session = path.session[index]
            hold = bisect.bisect_left(path.sessions, session) - bisect.bisect_left(path.sessions, entry_day)
            trades.append(Trade(symbol, path.ends[fill_index], path.ends[index], session, entry_price, price, reason, hold, result[0], result[1]))
        state, exit_next = "flat", False

    for i in range(first, n):
        if state == "holding" and i > fill_index:
            if exit_next:
                close_out(i, float(path.open[i]), "signal")
            elif path.low[i] <= stop:
                close_out(i, min(float(path.open[i]), stop), "stop")
            elif path.high[i] >= target:
                close_out(i, target, "target")
            elif time_exit and i >= time_exit:
                close_out(i, float(path.close[i]), "time")
        elif state == "working":
            if i > order_last:
                state = "flat"
            elif path.clock[i] >= ENTRY_FIRST_END and path.low[i] <= limit:
                entry_price, fill_index, entry_day = min(float(path.open[i]), limit), i, path.session[i]
                state = "holding"
                width = path.atr.get(entry_day) if atr_rule else None
                if atr_rule and width:
                    stop, target = reference_price - ATR_STOP * width, reference_price + ATR_TARGET * width
                else:
                    stop, target = reference_price * 0.98, reference_price * 1.04
                exits = []
                if max_hold:
                    position = bisect.bisect_left(path.sessions, entry_day) + MAX_HOLD_SESSIONS
                    if position < len(path.sessions):
                        exits.append(path.last_of_session[path.sessions[position]])
                if square_off:
                    candidates = [k for k in range(i, path.last_of_session[entry_day] + 1) if path.clock[k] == ENTRY_LAST_END]
                    if candidates:
                        exits.append(candidates[0])
                time_exit = min(exits) if exits else 0
                if time_exit and time_exit == i:
                    close_out(i, float(path.close[i]), "time")
        for side, reference in events.get(i, ()):
            if side == "SELL" and state == "holding" and i >= fill_index:
                exit_next = True
            elif side == "BUY" and state == "flat":
                if book == "INTRADAY":
                    if not (ENTRY_FIRST_END <= path.clock[i] <= ENTRY_LAST_END):
                        continue
                    day = path.session[i]
                else:
                    position = bisect.bisect_right(path.sessions, path.session[i])
                    if position >= len(path.sessions):
                        continue
                    day = path.sessions[position]
                window = [k for k in range(i + 1, path.last_of_session[day] + 1) if path.clock[k] <= ENTRY_LAST_END]
                if not window:
                    continue
                state, limit, reference_price, order_last = "working", reference * LIMIT_MARKUP, reference, window[-1]
    if state == "holding":
        close_out(n - 1, float(path.close[n - 1]), "end_of_data")
    return trades


# --- scoring --------------------------------------------------------------------------------------


def session_pnl(trades: list[Trade], sessions: list[date]) -> np.ndarray:
    index = {day: k for k, day in enumerate(sessions)}
    out = np.zeros(len(sessions))
    for trade in trades:
        k = index.get(trade.exit_session)
        if k is None:  # exits after the last scored session land on the last one
            k = len(sessions) - 1 if trade.exit_session > sessions[-1] else None
        if k is not None:
            out[k] += trade.net
    return out


def lower_bound(series: np.ndarray, *, resamples: int = 2000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for k in range(resamples):
        means[k] = series[me.stationary_bootstrap_indices(len(series), 5.0, rng)].mean()
    return float(np.quantile(means, 0.10 / COMPARISONS))


def describe(trades: list[Trade], pnl: np.ndarray) -> dict[str, object]:
    nets = [trade.net for trade in trades]
    wins = [value for value in nets if value > 0]
    losses = [-value for value in nets if value < 0]
    curve = np.cumsum(pnl)
    reasons: dict[str, int] = defaultdict(int)
    for trade in trades:
        reasons[trade.reason] += 1
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(nets) if nets else None,
        "mean_net_return_per_trade": float(np.mean([t.net / t.invested for t in trades])) if trades else None,
        "total_net_pnl": float(sum(nets)),
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
        "average_hold_sessions": float(np.mean([t.hold_sessions for t in trades])) if trades else None,
        "max_drawdown_rupees": float(np.max(np.maximum.accumulate(np.concatenate([[0.0], curve])) - np.concatenate([[0.0], curve]))),
        "exit_reasons": dict(reasons),
        "mean_session_pnl_lower_bound": lower_bound(pnl),
    }


def score(proposals: dict[str, dict[str, list]]) -> dict[str, object]:
    paths = {symbol: load_path(symbol) for symbol in stock_symbols()}
    report: dict[str, object] = {"protocol": "services/quant/docs/exit-rules-protocol.md", "books": {}}
    for book, rules in RULES.items():
        sessions = scored_sessions(book)
        results: dict[str, dict[str, object]] = {}
        series: dict[str, np.ndarray] = {}
        for rule in rules:
            trades = [trade for symbol, path in paths.items() for trade in simulate(symbol, path, proposals[book].get(symbol, []), book, rule)]
            series[rule] = session_pnl(trades, sessions)
            results[rule] = describe(trades, series[rule])
            results[rule]["profitable"] = bool(results[rule]["total_net_pnl"] > 0 and results[rule]["mean_session_pnl_lower_bound"] > 0)
        half = len(sessions) // 2
        for rule in rules[1:]:
            diff = series[rule] - series["E0"]
            first, second = float(diff[:half].sum()), float(diff[half:].sum())
            bound = lower_bound(diff)
            results[rule]["vs_live"] = {
                "total_difference": float(diff.sum()),
                "difference_lower_bound": bound,
                "first_half": first,
                "second_half": second,
                "beats_live": bool(diff.sum() > 0 and bound > 0 and first > 0 and second > 0),
            }
        report["books"][book] = {  # type: ignore[index]
            "sessions": {"first": sessions[0].isoformat(), "last": sessions[-1].isoformat(), "count": len(sessions)},
            "buy_proposals": sum(1 for items in proposals[book].values() for item in items if item[1] == "BUY"),
            "sell_proposals": sum(1 for items in proposals[book].values() for item in items if item[1] == "SELL"),
            "rules": results,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "services/quant/docs/results/exit-rules-result.json")
    args = parser.parse_args()
    proposals = stage_one(args.workers)
    report = score(proposals)
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
