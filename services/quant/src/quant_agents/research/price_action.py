"""Price-action models without lagging indicators, per services/quant/docs/price-action-protocol.md.

Inputs are raw bars, levels, gaps, fixed-window returns, same-time-of-day volume baselines and the move
relative to NIFTY since the open. No moving average, RSI, MACD, Bollinger, ADX, ATR or VWAP is read.

    python -m quant_agents.research.price_action
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date

import numpy as np

from quant_agents.research import agent_tuning as at
from quant_agents.research import exit_rules as er

TRAIN, VALIDATE, TEST = at.TRAIN, at.VALIDATE, at.TEST
PERIODS = {"train": TRAIN, "validate": VALIDATE, "test": TEST}
SLIP = 0.0005
NOTIONAL = 20000.0
MAX_PER_DAY = 2
BARS = 75  # 5-minute bars ending 09:20 .. 15:30
LOOKBACK = 20
MIN_BASELINE = 10


def bar_index(clock: int) -> int:
    """Index of the 5-minute bar ending at HHMM (09:20 -> 0, 15:15 -> 71)."""
    minutes = (clock // 100) * 60 + clock % 100
    return (minutes - (9 * 60 + 20)) // 5


SQUARE_OFF = bar_index(1515)
OR_END = {15: bar_index(930), 30: bar_index(945)}
LAST_ORB_SIGNAL = bar_index(1100)
RECLAIM_BAR = bar_index(945)
RS_BAR = bar_index(1400)


@dataclass
class Grid:
    """One symbol's (or NIFTY's) 5-minute bars as sessions x bar-of-day arrays."""

    sessions: np.ndarray  # session ordinals, shared by every grid
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def prev_close(self) -> np.ndarray:
        last = np.full(len(self.sessions), np.nan)
        for s in range(len(self.sessions)):
            row = self.close[s][~np.isnan(self.close[s])]
            if len(row):
                last[s] = row[-1]
        return np.concatenate([[np.nan], last[:-1]])

    def cumulative_volume_ratio(self) -> np.ndarray:
        """Cumulative session volume at each bar over its median at the same bar on the previous 20 sessions.
        Only earlier sessions form the baseline; at least 10 of them must have that bar."""
        cum = np.nancumsum(np.nan_to_num(self.volume, nan=0.0), axis=1)
        cum[np.isnan(self.close)] = np.nan
        ratio = np.full(cum.shape, np.nan)
        for s in range(MIN_BASELINE, len(self.sessions)):
            past = cum[max(0, s - LOOKBACK): s]
            enough = np.sum(~np.isnan(past), axis=0) >= MIN_BASELINE
            if not enough.any():
                continue
            with np.errstate(all="ignore"):
                median = np.nanmedian(past[:, enough], axis=0)
            ratio[s, enough] = cum[s, enough] / median
        return ratio


def build_grid(raw: dict[str, np.ndarray], sessions: np.ndarray) -> Grid:
    pos = {int(value): k for k, value in enumerate(sessions)}
    shape = (len(sessions), BARS)
    o, h, l, c, v = (np.full(shape, np.nan) for _ in range(5))
    for k in range(len(raw["ends"])):
        s = pos.get(int(raw["sessions"][k]))
        b = bar_index(int(raw["clock"][k]))
        if s is None or not 0 <= b < BARS:
            continue
        o[s, b], h[s, b], l[s, b], c[s, b] = raw["open"][k], raw["high"][k], raw["low"][k], raw["close"][k]
        v[s, b] = raw["last_volume"][k]
    return Grid(sessions, o, h, l, c, v)


@dataclass(frozen=True)
class Candidate:
    symbol: str
    session: int  # row index
    bar: int  # signal bar (decision on its close)
    rank: float
    stop: float
    target: float | None


def mis_charges(buy: float, sell: float) -> float:
    from core_api.strategy_lab import leg_charges

    return leg_charges(buy, sell, "MIS")


def cnc_charges(buy: float, sell: float) -> float:
    from core_api.strategy_lab import leg_charges

    return leg_charges(buy, sell, "CNC")


def simulate_intraday(grid: Grid, cand: Candidate, charges=mis_charges) -> dict | None:  # type: ignore[no-untyped-def]
    s, fill_bar = cand.session, cand.bar + 1
    if fill_bar > SQUARE_OFF or math.isnan(grid.open[s, fill_bar]):
        return None
    entry = grid.open[s, fill_bar] * (1 + SLIP)
    if entry <= cand.stop or (cand.target is not None and entry >= cand.target):
        return None  # opened at or below the stop, or already past the target: no trade
    qty = int(NOTIONAL // entry)
    if qty < 1:
        return None
    exit_price, reason = None, "square_off"
    for b in range(fill_bar, SQUARE_OFF + 1):
        o, hi, lo = grid.open[s, b], grid.high[s, b], grid.low[s, b]
        if math.isnan(lo):
            continue
        if b > fill_bar and o <= cand.stop:
            exit_price, reason = o, "stop_gap"
            break
        if lo <= cand.stop:
            exit_price, reason = cand.stop, "stop"
            break
        if cand.target is not None and hi >= cand.target:
            exit_price, reason = (o if b > fill_bar and o >= cand.target else cand.target), "target"
            break
    if exit_price is None:
        closes = grid.close[s, fill_bar: SQUARE_OFF + 1]
        valid = closes[~np.isnan(closes)]
        if not len(valid):
            return None
        exit_price = valid[-1]
    sell = exit_price * (1 - SLIP)
    gross = qty * (sell - entry)
    net = gross - charges(qty * entry, qty * sell)
    return {"symbol": cand.symbol, "session": int(grid.sessions[s]), "gross": gross, "net": net, "notional": qty * entry, "reason": reason}


def take_in_time_order(candidates: list[Candidate], cap: int = MAX_PER_DAY) -> list[Candidate]:
    """Per session: earliest bar first, then highest rank; at most `cap`, one per symbol."""
    chosen: list[Candidate] = []
    by_session: dict[int, list[Candidate]] = {}
    for cand in candidates:
        by_session.setdefault(cand.session, []).append(cand)
    for session in sorted(by_session):
        taken: set[str] = set()
        for cand in sorted(by_session[session], key=lambda c: (c.bar, -c.rank, c.symbol)):
            if len(taken) >= cap:
                break
            if cand.symbol in taken:
                continue
            taken.add(cand.symbol)
            chosen.append(cand)
    return chosen


# --- intraday rules (each returns every candidate; the daily cap is applied afterwards) ---------------


def orb_candidates(symbol: str, grid: Grid, nifty: Grid, vol_ratio: np.ndarray, *, minutes: int, target_r: float | None) -> list[Candidate]:
    out = []
    end = OR_END[minutes]
    for s in range(len(grid.sessions)):
        opening = grid.open[s, 0]
        if math.isnan(opening) or math.isnan(nifty.open[s, 0]) or np.isnan(grid.high[s, : end + 1]).any():
            continue
        or_high, or_low = np.max(grid.high[s, : end + 1]), np.min(grid.low[s, : end + 1])
        for b in range(end + 1, LAST_ORB_SIGNAL + 1):
            close = grid.close[s, b]
            if math.isnan(close) or close <= or_high:
                continue
            rel = close / opening - nifty.close[s, b] / nifty.open[s, 0] if not math.isnan(nifty.close[s, b]) else math.nan
            if not (vol_ratio[s, b] >= 1.5) or not (rel > 0):
                break  # the first breakout close decides; a failed condition means no trade today
            risk = close - or_low
            target = close + target_r * risk if target_r else None
            out.append(Candidate(symbol, s, b, float(vol_ratio[s, b]), float(or_low), target))
            break
    return out


def gap_reclaim_candidates(symbol: str, grid: Grid, prev_close: np.ndarray, *, gap: float) -> list[Candidate]:
    out = []
    b = RECLAIM_BAR
    for s in range(len(grid.sessions)):
        opening, close, previous = grid.open[s, 0], grid.close[s, b], prev_close[s]
        if any(math.isnan(x) for x in (opening, close, previous)):
            continue
        move = opening / previous - 1
        if move <= -gap and close > opening:
            low = np.nanmin(grid.low[s, : b + 1])
            out.append(Candidate(symbol, s, b, float(-move), float(low), float(previous)))
    return out


def relative_strength_candidates(symbol: str, grid: Grid, nifty: Grid, *, nifty_up_only: bool) -> list[Candidate]:
    out = []
    b = RS_BAR
    for s in range(len(grid.sessions)):
        opening, close, n_open, n_close = grid.open[s, 0], grid.close[s, b], nifty.open[s, 0], nifty.close[s, b]
        if any(math.isnan(x) for x in (opening, close, n_open, n_close)):
            continue
        nifty_move = n_close / n_open - 1
        rel = close / opening - 1 - nifty_move
        if rel > 0.01 and (nifty_move > 0 or not nifty_up_only):
            out.append(Candidate(symbol, s, b, float(rel), float(np.nanmin(grid.low[s, : b + 1])), None))
    return out


# --- swing rules (daily bars) --------------------------------------------------------------------------


@dataclass
class Daily:
    sessions: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray


def daily_of(raw: dict[str, np.ndarray]) -> Daily:
    return Daily(raw["sessions"].astype(int), raw["open"], raw["high"], raw["low"], raw["close"], raw["last_volume"])


def _vol_ratio(d: Daily, k: int) -> float:
    past = d.volume[max(0, k - LOOKBACK): k]
    past = past[~np.isnan(past)]
    if len(past) < MIN_BASELINE or np.median(past) <= 0:
        return math.nan
    return float(d.volume[k] / np.median(past))


def breakout_signals(symbol: str, d: Daily) -> list[tuple[int, str, int, float, float]]:
    out = []
    for k in range(LOOKBACK, len(d.close)):
        prior_high = np.nanmax(d.high[k - LOOKBACK: k])
        span = d.high[k] - d.low[k]
        ratio = _vol_ratio(d, k)
        if span > 0 and d.close[k] > prior_high and ratio >= 2 and (d.close[k] - d.low[k]) / span >= 0.75:
            out.append((int(d.sessions[k]), symbol, k, ratio, float(d.low[k])))
    return out


def capitulation_signals(symbol: str, d: Daily) -> list[tuple[int, str, int, float, float]]:
    out = []
    for k in range(LOOKBACK, len(d.close)):
        span = d.high[k] - d.low[k]
        ratio = _vol_ratio(d, k)
        move = d.close[k] / d.close[k - 1] - 1
        if span > 0 and move <= -0.04 and ratio >= 2 and (d.close[k] - d.low[k]) / span >= 0.5:
            out.append((int(d.sessions[k]), symbol, k, ratio, float(d.low[k])))
    return out


def simulate_swing(d: Daily, k: int, stop: float, hold: int, charges=cnc_charges) -> dict | None:  # type: ignore[no-untyped-def]
    """Signal on day k's close; fill at day k+1's open; exit at the close of day k+hold, or at the stop."""
    if k + hold >= len(d.close) or math.isnan(d.open[k + 1]):
        return None
    entry = d.open[k + 1] * (1 + SLIP)
    if entry <= stop:
        return None
    qty = int(NOTIONAL // entry)
    if qty < 1:
        return None
    exit_price, reason, last = d.close[k + hold], "time", k + hold
    for j in range(k + 1, k + hold + 1):
        if j > k + 1 and d.open[j] <= stop:
            exit_price, reason, last = d.open[j], "stop_gap", j
            break
        if d.low[j] <= stop:
            exit_price, reason, last = stop, "stop", j
            break
    sell = exit_price * (1 - SLIP)
    gross = qty * (sell - entry)
    net = gross - charges(qty * entry, qty * sell)
    return {"session": int(d.sessions[k]), "exit_session": int(d.sessions[last]), "gross": gross, "net": net, "notional": qty * entry, "reason": reason}


def run_swing(dailies: dict[str, Daily], rule, hold: int) -> list[dict]:  # type: ignore[no-untyped-def]
    signals = sorted((sig for symbol, d in dailies.items() for sig in rule(symbol, d)), key=lambda x: (x[0], -x[3], x[1]))
    trades, held_until, per_day = [], {}, {}
    for session, symbol, k, ratio, stop in signals:
        if per_day.get(session, 0) >= MAX_PER_DAY or held_until.get(symbol, -1) >= session:
            continue
        result = simulate_swing(dailies[symbol], k, stop, hold)
        if result is None:
            continue
        per_day[session] = per_day.get(session, 0) + 1
        held_until[symbol] = result["exit_session"]
        trades.append({**result, "symbol": symbol})
    return trades


# --- scoring -------------------------------------------------------------------------------------------


def summary(trades: list[dict], period: tuple[date, date], all_sessions: np.ndarray) -> dict[str, object]:
    lo, hi = period[0].toordinal(), period[1].toordinal()
    inside = [t for t in trades if lo <= t["session"] <= hi]
    days = all_sessions[(all_sessions >= lo) & (all_sessions <= hi)]
    if not inside:
        return {"trades": 0, "sessions": int(len(days))}
    net = np.array([t["net"] for t in inside])
    gross = np.array([t["gross"] for t in inside])
    ret = net / np.array([t["notional"] for t in inside])
    per_day = {int(day): 0.0 for day in days}
    for t in inside:
        per_day[t["session"]] = per_day.get(t["session"], 0.0) + t["net"]
    series = np.array([per_day[day] for day in sorted(per_day)])
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()
    half = len(series) // 2
    active = len({t["session"] for t in inside})
    return {
        "trades": int(len(inside)),
        "sessions": int(len(days)),
        "active_day_share": active / len(days) if len(days) else 0.0,
        "trades_per_active_day": len(inside) / active,
        "win_rate": float((net > 0).mean()),
        "mean_gross_pct": float((gross / np.array([t["notional"] for t in inside])).mean() * 100),
        "mean_net_pct": float(ret.mean() * 100),
        "total_net": float(net.sum()),
        "profit_factor": float(wins / losses) if losses > 0 else math.inf,
        "first_half_net": float(series[:half].sum()),
        "second_half_net": float(series[half:].sum()),
        "session_pnl_low": bootstrap_low(series),
    }


def bootstrap_low(series: np.ndarray, quantile: float = 0.025, draws: int = 2000) -> float:
    if len(series) == 0:
        return math.nan
    rng = np.random.default_rng(0)
    means = [rng.choice(series, len(series), replace=True).mean() for _ in range(draws)]
    return float(np.quantile(means, quantile))


def choose(variants: dict[str, dict[str, dict]]) -> str | None:
    eligible = [(name, rows["train"]) for name, rows in variants.items() if rows["train"].get("trades", 0) >= 60]
    if not eligible:
        return None
    return max(eligible, key=lambda item: (item[1]["mean_net_pct"], -item[1]["trades"]))[0]


def verdict(rows: dict[str, dict]) -> dict[str, object]:
    validate, test = rows["validate"], rows["test"]
    validated = validate.get("trades", 0) > 0 and validate.get("mean_net_pct", -1) > 0
    checks = {
        "validated": validated,
        "at_least_40_trades": test.get("trades", 0) >= 40,
        "mean_net_positive": test.get("mean_net_pct", -1) > 0,
        "session_pnl_lower_bound_positive": test.get("session_pnl_low", -1) > 0,
        "both_halves_profitable": test.get("first_half_net", -1) > 0 and test.get("second_half_net", -1) > 0,
    }
    return {"checks": checks, "works": all(checks.values())}


def run() -> dict[str, object]:
    symbols = er.stock_symbols()
    nifty_raw = at.load("NIFTY50", "5m")
    sessions = np.unique(nifty_raw["sessions"]).astype(int)
    nifty = build_grid(nifty_raw, sessions)
    intraday: dict[str, list[Candidate]] = {name: [] for name in ("I1_or15_none", "I1_or15_2R", "I1_or30_none", "I1_or30_2R", "I2_gap1", "I2_gap2", "I3_always", "I3_nifty_up")}
    grids: dict[str, Grid] = {}
    for symbol in symbols:
        grid = build_grid(at.load(symbol, "5m"), sessions)
        grids[symbol] = grid
        ratio, prev = grid.cumulative_volume_ratio(), grid.prev_close()
        for minutes in (15, 30):
            intraday[f"I1_or{minutes}_none"] += orb_candidates(symbol, grid, nifty, ratio, minutes=minutes, target_r=None)
            intraday[f"I1_or{minutes}_2R"] += orb_candidates(symbol, grid, nifty, ratio, minutes=minutes, target_r=2.0)
        intraday["I2_gap1"] += gap_reclaim_candidates(symbol, grid, prev, gap=0.01)
        intraday["I2_gap2"] += gap_reclaim_candidates(symbol, grid, prev, gap=0.02)
        intraday["I3_always"] += relative_strength_candidates(symbol, grid, nifty, nifty_up_only=False)
        intraday["I3_nifty_up"] += relative_strength_candidates(symbol, grid, nifty, nifty_up_only=True)
    session_days = sessions
    families: dict[str, dict] = {"intraday": {}, "swing": {}}
    for name, cands in intraday.items():
        trades = [t for t in (simulate_intraday(grids[c.symbol], c) for c in take_in_time_order(cands)) if t is not None]
        families["intraday"][name] = {label: summary(trades, period, session_days) for label, period in PERIODS.items()}
    dailies = {symbol: daily_of(at.load(symbol, "1d")) for symbol in symbols}
    daily_sessions = np.unique(np.concatenate([d.sessions for d in dailies.values()]))
    for name, rule, hold in (("S1_hold5", breakout_signals, 5), ("S1_hold10", breakout_signals, 10), ("S2_hold3", capitulation_signals, 3), ("S2_hold5", capitulation_signals, 5)):
        trades = run_swing(dailies, rule, hold)
        families["swing"][name] = {label: summary(trades, period, daily_sessions) for label, period in PERIODS.items()}
    report: dict[str, object] = {"protocol": "services/quant/docs/price-action-protocol.md", "families": {}}
    for family, variants in families.items():
        chosen = choose(variants)
        report["families"][family] = {  # type: ignore[index]
            "variants": variants,
            "chosen": chosen,
            "verdict": verdict(variants[chosen]) if chosen else {"checks": {}, "works": False, "reason": "no variant had 60 train trades"},
        }
    return report


def main() -> None:
    out = er.ROOT / "services/quant/docs/results/price-action-result.json"
    report = run()
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({family: {"chosen": body["chosen"], "verdict": body["verdict"]} for family, body in report["families"].items()}, indent=2, default=str))


if __name__ == "__main__":
    main()
