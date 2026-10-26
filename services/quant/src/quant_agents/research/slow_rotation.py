"""Slow rotation: monthly momentum and monthly / weekly reversal, per services/quant/docs/slow-rotation-protocol.md.

    python -m quant_agents.research.slow_rotation
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research.dip_reversion import DATA, EVENT_GAP, FORMER
from quant_agents.research.mentor_strategies import delivery_charges

PERIODS = {"train": (date(2016, 1, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 5))}
NOTIONAL = 20000.0
SLIP = 0.0005


@dataclass(frozen=True)
class Rule:
    name: str
    rebalance: str  # "month" | "quarter" | "every5"
    long: int  # look-back start, sessions ago
    short: int  # look-back end, sessions ago (0 = today)
    highest: bool  # True: buy the strongest; False: buy the weakest
    hold: int


RULES = (
    Rule("mom_12_1", "month", 252, 21, True, 10),
    Rule("mom_6_1", "month", 126, 21, True, 10),
    Rule("mom_12_1_q", "quarter", 252, 21, True, 10),
    Rule("rev_21", "month", 21, 0, False, 10),
    Rule("rev_5", "every5", 5, 0, False, 5),
)


@dataclass
class Grid:
    days: np.ndarray  # NIFTY session ordinals
    symbols: list[str]
    open: np.ndarray  # days x symbols
    close: np.ndarray
    event: np.ndarray  # open more than 20% from the previous close
    nifty: np.ndarray


def load_grid() -> tuple[Grid, list[str], list[str]]:
    raw: dict[str, dict[int, tuple[float, float]]] = {}
    groups: dict[str, str] = {}
    for line in DATA.read_text().splitlines():
        r = json.loads(line)
        raw.setdefault(r["symbol"], {})[date.fromisoformat(r["date"][:10]).toordinal()] = (float(r["open"]), float(r["close"]))
        groups[r["symbol"]] = r["group"]
    days = np.array(sorted(raw["NIFTY50"]))
    symbols = sorted(s for s, g in groups.items() if g != "index")
    o = np.full((len(days), len(symbols)), np.nan)
    c = np.full_like(o, np.nan)
    for j, s in enumerate(symbols):
        for k, d in enumerate(days):
            bar = raw[s].get(int(d))
            if bar:
                o[k, j], c[k, j] = bar
    prev = np.vstack([np.full((1, len(symbols)), np.nan), c[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        event = np.abs(o / prev - 1) > EVENT_GAP
    nifty = np.array([raw["NIFTY50"][int(d)][1] for d in days])
    current = [s for s in symbols if groups[s] == "current"]
    former = [s for s in symbols if s in FORMER]
    return Grid(days, symbols, o, c, event, nifty), current, former


def _rebalance_days(grid: Grid, rule: Rule, lo: int, hi: int) -> set[int]:
    out = set()
    for t in range(lo, hi):  # hi is the last session; a rebalance needs a next open
        a, b = date.fromordinal(int(grid.days[t])), date.fromordinal(int(grid.days[t + 1]))
        if rule.rebalance == "every5":
            if (t - lo) % 5 == 4:
                out.add(t)
        elif a.month != b.month and (rule.rebalance == "month" or a.month in (3, 6, 9, 12)):
            out.add(t)
    return out


def _ranked(grid: Grid, rule: Rule, t: int, cols: list[int]) -> list[int]:
    scored = []
    for j in cols:
        c_now, c_end, c_start = grid.close[t, j], grid.close[t - rule.short, j], grid.close[t - rule.long, j]
        if any(math.isnan(x) for x in (c_now, c_end, c_start, grid.open[t + 1, j])):
            continue
        if grid.event[t - rule.long + 1: t + 2, j].any():
            continue
        scored.append((c_end / c_start - 1, j))
    scored.sort(reverse=rule.highest)
    return [j for _, j in scored[: rule.hold]]


def _last_close(grid: Grid, t: int, j: int) -> float:
    while math.isnan(grid.close[t, j]):
        t -= 1
    return float(grid.close[t, j])


def simulate(grid: Grid, rule: Rule, cols: list[int], period: tuple[date, date]) -> dict[str, object]:
    lo = int(np.searchsorted(grid.days, period[0].toordinal()))
    hi = int(np.searchsorted(grid.days, period[1].toordinal(), side="right")) - 1
    rebal = _rebalance_days(grid, rule, lo, hi)
    capital = NOTIONAL * rule.hold
    held: dict[int, tuple[int, float]] = {}  # column -> (qty, entry price)
    realised = charges = 0.0
    buys = 0
    pending_sell: list[int] = []
    pending_buy: list[int] = []
    equity: list[tuple[int, float]] = []

    def sell(j: int, price: float) -> None:
        nonlocal realised, charges
        qty, entry = held.pop(j)
        fee = delivery_charges(0.0, qty * price)
        realised += (price - entry) * qty - fee
        charges += fee

    for t in range(lo, hi + 1):
        for j in [j for j in held if grid.event[t, j]]:
            sell(j, _last_close(grid, t - 1, j))
        for j in pending_sell:
            if j in held:
                o = grid.open[t, j]
                sell(j, (_last_close(grid, t - 1, j) if math.isnan(o) else float(o)) * (1 - SLIP))
        for j in pending_buy:
            o = grid.open[t, j]
            if j in held or math.isnan(o):
                continue
            price = float(o) * (1 + SLIP)
            qty = int(NOTIONAL // price)
            if qty < 1:
                continue
            fee = delivery_charges(qty * price, 0.0)
            realised -= fee
            charges += fee
            held[j] = (qty, price)
            buys += 1
        pending_sell, pending_buy = [], []
        marked = realised + sum(q * (_last_close(grid, t, j) - e) for j, (q, e) in held.items())
        equity.append((t, marked))
        if t in rebal:
            target = set(_ranked(grid, rule, t, cols))
            pending_sell = [j for j in held if j not in target]
            pending_buy = sorted(target - set(held))
    final = realised + sum(q * (_last_close(grid, hi, j) - e) - delivery_charges(0.0, q * _last_close(grid, hi, j)) for j, (q, e) in held.items())
    equity[-1] = (hi, final)
    return _measures(grid, equity, capital, final, charges, buys, lo, hi)


def _months(grid: Grid, equity: list[tuple[int, float]], capital: float, lo: int) -> list[tuple[float, float]]:
    """(strategy return, NIFTY return) per calendar month, on fixed capital."""
    out = []
    prev_eq, prev_n = 0.0, float(grid.nifty[lo - 1]) if lo > 0 else float(grid.nifty[lo])
    for k, (t, eq) in enumerate(equity):
        last = k == len(equity) - 1
        if last or date.fromordinal(int(grid.days[t])).month != date.fromordinal(int(grid.days[equity[k + 1][0]])).month:
            out.append(((eq - prev_eq) / capital, float(grid.nifty[t]) / prev_n - 1))
            prev_eq, prev_n = eq, float(grid.nifty[t])
    return out


def _measures(grid: Grid, equity: list[tuple[int, float]], capital: float, final: float, charges: float, buys: int, lo: int, hi: int) -> dict[str, object]:
    years = (grid.days[hi] - grid.days[lo]) / 365.25
    series = np.array([e for _, e in equity])
    drawdown = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], series]))[1:] - series))
    start_n = float(grid.nifty[lo - 1]) if lo > 0 else float(grid.nifty[lo])
    nifty_simple = (float(grid.nifty[hi]) / start_n - 1) / years
    months = _months(grid, equity, capital, lo)
    excess = [s - n for s, n in months]
    return {
        "annual_return": final / capital / years,
        "nifty_annual": nifty_simple,
        "nifty_cagr": (float(grid.nifty[hi]) / start_n) ** (1 / years) - 1,
        "excess_annual": final / capital / years - nifty_simple,
        "total_net": final,
        "charges": charges,
        "buys": buys,
        "max_drawdown": drawdown,
        "max_drawdown_pct": drawdown / capital,
        "monthly_excess": excess,
        "mean_monthly_excess": float(np.mean(excess)),
    }


def equal_weight(grid: Grid, cols: list[int], period: tuple[date, date]) -> dict[str, object]:
    lo = int(np.searchsorted(grid.days, period[0].toordinal()))
    hi = int(np.searchsorted(grid.days, period[1].toordinal(), side="right")) - 1
    pos = {}
    for j in cols:
        if not math.isnan(grid.open[lo, j]):
            price = float(grid.open[lo, j]) * (1 + SLIP)
            if int(NOTIONAL // price):
                pos[j] = (int(NOTIONAL // price), price)
    capital = NOTIONAL * len(pos)
    buy_fees = sum(delivery_charges(q * p, 0.0) for q, p in pos.values())
    equity = [(t, sum(q * (_last_close(grid, t, j) - p) for j, (q, p) in pos.items()) - buy_fees) for t in range(lo, hi + 1)]
    final = equity[-1][1] - sum(delivery_charges(0.0, q * _last_close(grid, hi, j)) for j, (q, _) in pos.items())
    equity[-1] = (hi, final)
    return _measures(grid, equity, capital, final, buy_fees, len(pos), lo, hi)


def _boot_low(values: list[float], q: float = 0.10) -> float:
    arr = np.array(values)
    rng = np.random.default_rng(0)
    return float(np.quantile(arr[rng.integers(0, len(arr), size=(2000, len(arr)))].mean(axis=1), q))


def run() -> dict[str, object]:
    grid, current, former = load_grid()
    universes = {"A": [grid.symbols.index(s) for s in current], "A+B": [grid.symbols.index(s) for s in current + former]}
    report: dict[str, object] = {"protocol": "services/quant/docs/slow-rotation-protocol.md", "periods": PERIODS, "universe_sizes": {k: len(v) for k, v in universes.items()}}
    for uni, cols in universes.items():
        part: dict[str, object] = {"equal_weight": {label: equal_weight(grid, cols, p) for label, p in PERIODS.items()}}
        for rule in RULES:
            part[rule.name] = {label: simulate(grid, rule, cols, p) for label, p in PERIODS.items()}
        report[uni] = part
    gate = {}
    for rule in RULES:
        a, ab = report["A"][rule.name], report["A+B"][rule.name]  # type: ignore[index]
        pooled = [x for label in PERIODS for x in a[label]["monthly_excess"]]
        beats = {label: bool(a[label]["excess_annual"] > 0) for label in PERIODS}
        survivorship = bool(all(ab[label]["excess_annual"] > 0 for label in ("validate", "test")))
        low = _boot_low(pooled)
        gate[rule.name] = {"beats_nifty": beats, "pooled_monthly_excess_low10": low, "survivorship_ok": survivorship, "works": bool(all(beats.values()) and low > 0 and survivorship)}
    report["gate"] = gate
    return report


def main() -> None:
    report = run()
    out = er.ROOT / "services/quant/docs/results/slow-rotation-result.json"
    out.write_text(json.dumps(report, indent=1, default=str))
    for uni in ("A", "A+B"):
        for name, per in report[uni].items():  # type: ignore[union-attr]
            for label, m in per.items():
                print(f"{uni:4} {name:12} {label:8} ann {m['annual_return']:+.1%} nifty {m['nifty_annual']:+.1%} excess {m['excess_annual']:+.1%} net {m['total_net']:>10,.0f} charges {m['charges']:>8,.0f} buys {m['buys']:4d} dd {m['max_drawdown_pct']:.1%}")
    print(json.dumps(report["gate"], indent=1))


if __name__ == "__main__":
    main()
