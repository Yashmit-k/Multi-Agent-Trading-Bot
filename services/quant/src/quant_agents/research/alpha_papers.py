"""Published alpha papers on NIFTY 50, per services/quant/docs/alpha-papers-protocol.md. Scored once.

    python -m quant_agents.research.alpha_papers
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import slow_rotation as sl
from quant_agents.research.dip_reversion import DATA
from quant_agents.research.mentor_strategies import GST, SEBI, TXN, delivery_charges
from quant_agents.research.risk_off_nifty import etf_costs

PERIODS = sl.PERIODS
I5_PERIODS = {"2024": (date(2024, 1, 1), date(2024, 12, 31)), "2025": (date(2025, 1, 1), date(2025, 12, 31)), "2026": (date(2026, 1, 1), date(2026, 10, 5))}
K = 13
Q = 0.10 / K
LOOK = 252
SKIP = 21
HOLD = 10
INDEX_NOTIONAL = 100_000.0
ETF_SLIP = 0.0002
CASH_YIELD = 0.06
IST = ZoneInfo("Asia/Kolkata")
MONTHLY = SimpleNamespace(rebalance="month")


# --- data -------------------------------------------------------------------------------------------


def load() -> tuple[sl.Grid, np.ndarray, list[str], list[str], np.ndarray]:
    """The slow-rotation grid, a matching high grid, the universes and NIFTY's daily opens."""
    grid, current, former = sl.load_grid()
    index = {d: k for k, d in enumerate(grid.days.tolist())}
    col = {s: j for j, s in enumerate(grid.symbols)}
    high = np.full_like(grid.close, np.nan)
    nifty_open = np.full(len(grid.days), np.nan)
    for line in DATA.read_text().splitlines():
        r = json.loads(line)
        k = index.get(date.fromisoformat(r["date"][:10]).toordinal())
        if k is None:
            continue
        if r["symbol"] == "NIFTY50":
            nifty_open[k] = float(r["open"])
        elif r["symbol"] in col:
            high[k, col[r["symbol"]]] = float(r["high"])
    return grid, high, current, former, nifty_open


# --- stock-selection scores (higher = better; only information up to the close of t) ---------------


class Scores:
    def __init__(self, grid: sl.Grid, high: np.ndarray) -> None:
        self.grid, self.high = grid, high
        c = grid.close
        self.ret = np.vstack([np.full((1, c.shape[1]), np.nan), c[1:] / c[:-1] - 1])
        n = grid.nifty
        self.nret = np.concatenate([[np.nan], n[1:] / n[:-1] - 1])
        self.month_end = self._month_ends()

    def _month_ends(self) -> list[int]:
        days = [date.fromordinal(int(d)) for d in self.grid.days]
        return [t for t in range(len(days) - 1) if days[t].month != days[t + 1].month]

    def eligible(self, t: int, cols: list[int]) -> list[int]:
        g = self.grid
        out = []
        for j in cols:
            if t + 1 >= len(g.days) or math.isnan(g.open[t + 1, j]):
                continue
            window = self.ret[t - LOOK + 1: t + 1, j]
            if np.isnan(window).any() or g.event[t - LOOK + 1: t + 2, j].any():
                continue
            out.append(j)
        return out

    def momentum(self, t: int, j: int) -> float:
        c = self.grid.close
        return c[t - SKIP, j] / c[t - LOOK, j] - 1

    def score(self, rule: str, t: int, j: int) -> float:
        r = self.ret[t - LOOK + 1: t + 1, j]
        if rule == "low_vol":
            return -float(np.std(r))
        if rule == "low_beta":
            m = self.nret[t - LOOK + 1: t + 1]
            return -float(np.cov(r, m)[0, 1] / np.var(m, ddof=1))
        if rule == "low_max":
            return -float(np.mean(np.sort(r[-21:])[-5:]))
        if rule == "high_52w":
            return float(self.grid.close[t, j] / np.nanmax(self.high[t - LOOK + 1: t + 1, j]))
        if rule == "resid_mom":
            m = self.nret[t - LOOK + 1: t + 1]
            beta = np.cov(r, m)[0, 1] / np.var(m, ddof=1)
            alpha = r.mean() - beta * m.mean()
            resid = r - alpha - beta * m
            part = resid[: LOOK - SKIP]
            sd = np.std(part)
            return float(part.sum() / sd) if sd > 0 else 0.0
        raise ValueError(rule)

    def info_discreteness(self, t: int, j: int) -> float:
        r = self.ret[t - LOOK + 1: t - SKIP + 1, j]
        return float(np.sign(self.momentum(t, j)) * ((r < 0).mean() - (r > 0).mean()))

    def seasonal(self, t: int, j: int) -> float | None:
        """Mean return of stock j in the next calendar month, over all earlier years (at least 3)."""
        days = self.grid.days
        target = date.fromordinal(int(days[t + 1])).month
        values = []
        ends = [k for k in self.month_end if k <= t]
        for a, b in zip(ends, ends[1:]):
            if date.fromordinal(int(days[b])).month != target:
                continue
            ca, cb = self.grid.close[a, j], self.grid.close[b, j]
            if math.isnan(ca) or math.isnan(cb) or self.grid.event[a + 1: b + 1, j].any():
                continue
            values.append(cb / ca - 1)
        return float(np.mean(values)) if len(values) >= 3 else None

    def select(self, rule: str, t: int, cols: list[int]) -> list[int]:
        pool = self.eligible(t, cols)
        if rule == "frog_pan":
            moms = sorted(((self.momentum(t, j), j) for j in pool), reverse=True)
            top = [j for _, j in moms[: len(moms) // 2]]
            return [j for _, j in sorted((self.info_discreteness(t, j), j) for j in top)][:HOLD]
        if rule == "seasonal":
            scored = [(s, j) for j in pool if (s := self.seasonal(t, j)) is not None]
            return [j for _, j in sorted(scored, reverse=True)][:HOLD]
        if rule == "conservative":
            vol = {j: k for k, (_, j) in enumerate(sorted(((-self.score("low_vol", t, j), j) for j in pool)))}
            mom = {j: k for k, (_, j) in enumerate(sorted(((self.momentum(t, j), j) for j in pool), reverse=True))}
            return [j for _, j in sorted(((vol[j] + mom[j]) / 2, j) for j in pool)][:HOLD]
        return [j for _, j in sorted(((self.score(rule, t, j), j) for j in pool), reverse=True)][:HOLD]


STOCK_RULES = ("low_vol", "low_beta", "low_max", "high_52w", "resid_mom", "frog_pan", "seasonal", "conservative")


def simulate(grid: sl.Grid, scores: Scores, rule: str, cols: list[int], period: tuple[date, date]) -> dict[str, object]:
    """slow_rotation.simulate with the ranking replaced by `rule` (same fills, charges, slippage and event exits)."""
    lo = int(np.searchsorted(grid.days, period[0].toordinal()))
    hi = int(np.searchsorted(grid.days, period[1].toordinal(), side="right")) - 1
    rebal = sl._rebalance_days(grid, MONTHLY, lo, hi)  # type: ignore[arg-type]
    capital = sl.NOTIONAL * HOLD
    held: dict[int, tuple[int, float]] = {}
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
            sell(j, sl._last_close(grid, t - 1, j))
        for j in pending_sell:
            if j in held:
                o = grid.open[t, j]
                sell(j, (sl._last_close(grid, t - 1, j) if math.isnan(o) else float(o)) * (1 - sl.SLIP))
        for j in pending_buy:
            o = grid.open[t, j]
            if j in held or math.isnan(o):
                continue
            price = float(o) * (1 + sl.SLIP)
            qty = int(sl.NOTIONAL // price)
            if qty < 1:
                continue
            fee = delivery_charges(qty * price, 0.0)
            realised -= fee
            charges += fee
            held[j] = (qty, price)
            buys += 1
        pending_sell, pending_buy = [], []
        marked = realised + sum(q * (sl._last_close(grid, t, j) - e) for j, (q, e) in held.items())
        equity.append((t, marked))
        if t in rebal:
            target = set(scores.select(rule, t, cols))
            pending_sell = [j for j in held if j not in target]
            pending_buy = sorted(target - set(held))
    final = realised + sum(q * (sl._last_close(grid, hi, j) - e) - delivery_charges(0.0, q * sl._last_close(grid, hi, j)) for j, (q, e) in held.items())
    equity[-1] = (hi, final)
    return sl._measures(grid, equity, capital, final, charges, buys, lo, hi)


def _boot_quantile(values: list[float], q: float) -> float:
    arr = np.array(values)
    rng = np.random.default_rng(0)
    return float(np.quantile(arr[rng.integers(0, len(arr), size=(2000, len(arr)))].mean(axis=1), q))


def _period_for(rule: str, label: str) -> tuple[date, date]:
    lo, hi = PERIODS[label]
    if rule == "seasonal" and label == "train":
        return date(2018, 1, 1), hi  # needs 3 earlier years of the same month
    return lo, hi


def stock_study(grid: sl.Grid, high: np.ndarray, current: list[str], former: list[str]) -> dict[str, object]:
    scores = Scores(grid, high)
    universes = {"A": [grid.symbols.index(s) for s in current], "A+B": [grid.symbols.index(s) for s in current + former]}
    out: dict[str, object] = {}
    for uni, cols in universes.items():
        part: dict[str, object] = {}
        for rule in STOCK_RULES:
            per = {}
            for label in PERIODS:
                period = _period_for(rule, label)
                m = simulate(grid, scores, rule, cols, period)
                ew = sl.equal_weight(grid, cols, period)
                m["equal_weight_annual"] = ew["annual_return"]
                m["excess_vs_ew_annual"] = m["annual_return"] - ew["annual_return"]
                m["monthly_excess_vs_ew"] = [a - b for a, b in zip(m["monthly_excess"], ew["monthly_excess"])]  # both vs NIFTY: the NIFTY leg cancels
                per[label] = m
            part[rule] = per
        out[uni] = part
    gate = {}
    for rule in STOCK_RULES:
        ab = out["A+B"][rule]  # type: ignore[index]
        pooled = [x for label in PERIODS for x in ab[label]["monthly_excess_vs_ew"]]
        beats_ew = {label: bool(ab[label]["excess_vs_ew_annual"] > 0) for label in PERIODS}
        beats_nifty = {label: bool(ab[label]["excess_annual"] > 0) for label in PERIODS}
        low = _boot_quantile(pooled, Q)
        mean = float(np.mean(pooled))
        t_stat = mean / (np.std(pooled, ddof=1) / math.sqrt(len(pooled)))
        gate[rule] = {"beats_ew": beats_ew, "beats_nifty": beats_nifty, "pooled_mean_monthly_vs_ew": mean, "t_stat": float(t_stat), "bonferroni_low": low,
                      "works": bool(all(beats_ew.values()) and all(beats_nifty.values()) and low > 0)}
    out["gate"] = gate
    return out


# --- NIFTY index rules --------------------------------------------------------------------------------


def _span(days: np.ndarray, period: tuple[date, date]) -> tuple[int, int]:
    return int(np.searchsorted(days, period[0].toordinal())), int(np.searchsorted(days, period[1].toordinal(), side="right")) - 1


def _month_end_flags(days: np.ndarray) -> np.ndarray:
    d = [date.fromordinal(int(x)) for x in days]
    return np.array([k + 1 < len(d) and d[k].month != d[k + 1].month for k in range(len(d))])


def _allocation(days: np.ndarray, close: np.ndarray, period: tuple[date, date], signal) -> dict[str, object]:
    """Daily equity of a month-end switch between NIFTY (ETF) and cash at CASH_YIELD. signal(t) -> True/False/None."""
    lo, hi = _span(days, period)
    ends = _month_end_flags(days)
    cash, units, switches = INDEX_NOTIONAL, 0.0, 0
    first = signal(lo - 1)
    if first is None or first:
        price = close[lo - 1] * (1 + ETF_SLIP)
        fee = etf_costs(cash, 0.0)
        units, cash = (cash - fee) / price, 0.0
    equity = []
    for t in range(lo, hi + 1):
        cash *= 1 + CASH_YIELD / 252
        if ends[t] and t < hi:
            want = signal(t)
            want = True if want is None else want
            if want and units == 0:
                fee = etf_costs(cash, 0.0)
                units, cash = (cash - fee) / (close[t] * (1 + ETF_SLIP)), 0.0
                switches += 1
            elif not want and units > 0:
                value = units * close[t] * (1 - ETF_SLIP)
                cash, units = value - etf_costs(0.0, value), 0.0
                switches += 1
        equity.append(cash + units * close[t])
    if units > 0:
        value = units * close[hi] * (1 - ETF_SLIP)
        equity[-1] = value - etf_costs(0.0, value)
    return _allocation_measures(days, lo, hi, equity, switches)


def _allocation_measures(days: np.ndarray, lo: int, hi: int, equity: list[float], switches: int) -> dict[str, object]:
    ends = _month_end_flags(days)
    series = np.array([INDEX_NOTIONAL] + equity)
    marks = [0] + [k + 1 for k, t in enumerate(range(lo, hi + 1)) if ends[t] or t == hi]
    monthly = series[marks[1:]] / series[marks[:-1]] - 1
    years = (days[hi] - days[lo - 1]) / 365.25
    peak = np.maximum.accumulate(series)
    return {
        "cagr": float((series[-1] / INDEX_NOTIONAL) ** (1 / years) - 1),
        "sharpe": float(monthly.mean() / monthly.std(ddof=1) * math.sqrt(12)),
        "max_drawdown_pct": float(np.max(1 - series / peak)),
        "switches": switches,
    }


def index_allocation_study(grid: sl.Grid) -> dict[str, object]:
    days, close = grid.days, grid.nifty
    ends = [t for t, flag in enumerate(_month_end_flags(days)) if flag]

    def sma10(t: int) -> bool | None:
        past = [k for k in ends if k <= t][-10:]
        return None if len(past) < 10 else bool(close[t] > np.mean(close[past]))

    def tsmom12(t: int) -> bool | None:
        past = [k for k in ends if k <= t]
        return None if len(past) < 13 else bool(close[t] > close[past[-13]])

    rules = {"buy_hold": lambda t: True, "sma10m": sma10, "tsmom12": tsmom12}
    out: dict[str, object] = {name: {label: _allocation(days, close, p, fn) for label, p in PERIODS.items()} for name, fn in rules.items()}
    gate = {}
    for name in ("sma10m", "tsmom12"):
        sharpe = {label: bool(out[name][label]["sharpe"] > out["buy_hold"][label]["sharpe"]) for label in PERIODS}  # type: ignore[index]
        ret = {label: bool(out[name][label]["cagr"] >= out["buy_hold"][label]["cagr"] - 0.02) for label in PERIODS}  # type: ignore[index]
        gate[name] = {"better_sharpe": sharpe, "return_within_2pp": ret, "works": bool(all(sharpe.values()) and all(ret.values()))}
    out["gate"] = gate
    return out


def _trade(buy_price: float, sell_price: float, *, intraday: bool = False) -> float:
    """Net return of one ₹1 lakh ETF trade."""
    b = buy_price * (1 + ETF_SLIP)
    s = sell_price * (1 - ETF_SLIP)
    qty = INDEX_NOTIONAL / b
    fee = etf_intraday_costs(qty * b, qty * s) if intraday else etf_costs(qty * b, 0.0) + etf_costs(0.0, qty * s)
    return (qty * (s - b) - fee) / INDEX_NOTIONAL


def etf_intraday_costs(buy: float, sell: float) -> float:
    brokerage = min(buy * 0.0003, 20.0) + min(sell * 0.0003, 20.0)
    exchange = (buy + sell) * TXN
    sebi = (buy + sell) * SEBI
    return brokerage + sell * 0.00001 + buy * 0.00003 + exchange + sebi + GST * (brokerage + exchange + sebi)


def _trade_summary(trades: dict[str, list[float]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for label, values in trades.items():
        arr = np.array(values)
        out[label] = {"trades": len(arr), "mean_net_bp": float(arr.mean() * 1e4), "win_rate": float((arr > 0).mean()), "total_pct": float(arr.sum() * 100)}
    pooled = [x for v in trades.values() for x in v]
    positive = all(out[label]["mean_net_bp"] > 0 for label in trades)  # type: ignore[index]
    low = _boot_quantile(pooled, Q)
    out["gate"] = {"positive_each_period": bool(positive), "bonferroni_low_bp": low * 1e4, "works": bool(positive and low > 0)}
    return out


def index_trade_study(grid: sl.Grid, nifty_open: np.ndarray) -> dict[str, object]:
    days, close = grid.days, grid.nifty
    d = [date.fromordinal(int(x)) for x in days]
    tom: dict[str, list[float]] = {label: [] for label in PERIODS}
    overnight: dict[str, list[float]] = {label: [] for label in PERIODS}
    gross_overnight: dict[str, list[float]] = {label: [] for label in PERIODS}
    for label, period in PERIODS.items():
        lo, hi = _span(days, period)
        for t in range(lo, hi):
            if not math.isnan(nifty_open[t + 1]):
                overnight[label].append(_trade(close[t], nifty_open[t + 1]))
                gross_overnight[label].append(nifty_open[t + 1] / close[t] - 1)
            # turn of month: t = second-last session of a month
            if t + 4 <= hi and d[t].month == d[t + 1].month and d[t + 1].month != d[t + 2].month:
                tom[label].append(_trade(close[t], close[t + 4]))
    intraday = intraday_momentum()
    return {
        "turn_of_month": _trade_summary(tom),
        "overnight": {**_trade_summary(overnight), "gross_mean_bp": {k: float(np.mean(v) * 1e4) for k, v in gross_overnight.items()}},
        "intraday_mom": intraday,
    }


def intraday_momentum() -> dict[str, object]:
    z = np.load(er.ROOT / "datasets/research/agent_tuning/features-NIFTY50-5m.npz", allow_pickle=True)
    ends, close = z["ends"], z["close"].astype(float)
    sessions: dict[date, dict[str, float]] = {}
    for stamp, c in zip(ends, close):
        moment = datetime.fromtimestamp(float(stamp), IST)
        row = sessions.setdefault(moment.date(), {})
        hm = moment.strftime("%H:%M")
        if hm in ("09:45", "15:00", "15:30"):
            row[hm] = float(c)
        row["last"] = float(c)
    trades: dict[str, list[float]] = {label: [] for label in I5_PERIODS}
    last_half: dict[str, list[float]] = {label: [] for label in I5_PERIODS}
    signals: dict[str, list[tuple[float, float]]] = {label: [] for label in I5_PERIODS}
    prev_close = None
    for day in sorted(sessions):
        row = sessions[day]
        if prev_close is not None and all(k in row for k in ("09:45", "15:00", "15:30")):
            label = next((k for k, (a, b) in I5_PERIODS.items() if a <= day <= b), None)
            if label:
                first = row["09:45"] / prev_close - 1
                last = row["15:30"] / row["15:00"] - 1
                signals[label].append((first, last))
                last_half[label].append(last)
                if first > 0:
                    trades[label].append(_trade(row["15:00"], row["15:30"], intraday=True))
        prev_close = row["last"]
    out = _trade_summary(trades)
    out["correlation_first_vs_last"] = {k: float(np.corrcoef(np.array(v).T)[0, 1]) for k, v in signals.items()}
    out["gross_last_half_after_up_bp"] = {k: float(np.mean([l for f, l in v if f > 0]) * 1e4) for k, v in signals.items()}
    return out


def run() -> dict[str, object]:
    grid, high, current, former, nifty_open = load()
    return {
        "protocol": "services/quant/docs/alpha-papers-protocol.md",
        "stocks": stock_study(grid, high, current, former),
        "index_allocation": index_allocation_study(grid),
        "index_trades": index_trade_study(grid, nifty_open),
    }


def main() -> None:
    report = run()
    (er.ROOT / "services/quant/docs/results/alpha-papers-result.json").write_text(json.dumps(report, indent=1, default=str))
    stocks = report["stocks"]
    for uni in ("A+B", "A"):
        for rule in STOCK_RULES:
            per = stocks[uni][rule]  # type: ignore[index]
            cells = "  ".join(f"{label} {m['annual_return']:+.1%} (ew {m['equal_weight_annual']:+.1%}, nifty {m['nifty_annual']:+.1%}) buys {m['buys']}" for label, m in per.items())
            print(f"{uni:4} {rule:13} {cells}")
    print(json.dumps(stocks["gate"], indent=1))
    alloc = report["index_allocation"]
    for name in ("buy_hold", "sma10m", "tsmom12"):
        print(name, {label: {k: round(v, 3) for k, v in m.items()} for label, m in alloc[name].items()})  # type: ignore[union-attr]
    print(json.dumps(alloc["gate"], indent=1))
    print(json.dumps(report["index_trades"], indent=1))


if __name__ == "__main__":
    main()
