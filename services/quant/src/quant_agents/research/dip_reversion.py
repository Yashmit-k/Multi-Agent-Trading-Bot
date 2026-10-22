"""EMA dip reversion, refined, per services/quant/docs/dip-reversion-protocol.md.

Daily bars 2015-2026 (Kite, split-adjusted). Signal on a close, fill at the next open.

    python -m quant_agents.research.dip_reversion
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research.mentor_strategies import delivery_charges

DATA = er.ROOT / "datasets/research/dip_history/daily_2015_2026.jsonl"
TRAIN = (date(2015, 3, 1), date(2020, 12, 31))
VALIDATE = (date(2021, 1, 1), date(2023, 12, 31))
SEEN = (date(2024, 4, 1), date(2026, 10, 5))
YEARS = {year: (date(year, 1, 1), date(year, 12, 31)) for year in (2021, 2022, 2023)}
NOTIONAL = 20000.0
SLIP = 0.0005
CAP = 20
EVENT_GAP = 0.20
EVENT_QUIET = 20
FORMER = ("YESBANK", "IDEA", "ZEEL", "VEDL", "IOC", "GAIL", "UPL", "BOSCHLTD", "AUROPHARMA", "LUPIN", "BHEL", "ACC", "AMBUJACEM", "BANKBARODA", "HINDPETRO", "DIVISLAB", "SHREECEM", "INDUSTOWER")


@dataclass(frozen=True)
class Variant:
    exit_level: str  # "ema" | "fixed"
    time_stop: int | None
    price_stop: float | None
    stock_specific: bool
    tranche2: bool

    @property
    def name(self) -> str:
        return f"{self.exit_level}-t{self.time_stop or 0}-s{int((self.price_stop or 0) * 100)}-{'idio' if self.stock_specific else 'all'}-{'2tr' if self.tranche2 else '1tr'}"


BASE = Variant("ema", None, None, False, True)
VARIANTS = [Variant(*combo) for combo in itertools.product(("ema", "fixed"), (None, 15), (None, 0.10), (False, True), (True, False))]


@dataclass
class Series:
    dates: np.ndarray  # ordinals
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    ema_prev: np.ndarray
    event: np.ndarray  # corporate-action gap at this bar
    index: dict[int, int]


def load(path: Path = DATA) -> dict[str, Series]:
    raw: dict[str, list[tuple]] = {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        raw.setdefault(r["symbol"], []).append((date.fromisoformat(r["date"][:10]).toordinal(), r["open"], r["high"], r["low"], r["close"]))
    out = {}
    for symbol, rows in raw.items():
        rows.sort()
        d, o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
        ema = np.full(len(c), np.nan)
        if len(c) >= 20:
            ema[19] = c[:20].mean()
            for k in range(20, len(c)):
                ema[k] = (2 / 21) * c[k] + (19 / 21) * ema[k - 1]
        prev_close = np.concatenate([[np.nan], c[:-1]])
        out[symbol] = Series(d.astype(int), o, h, l, c, np.concatenate([[np.nan], ema[:-1]]), np.abs(o / prev_close - 1) > EVENT_GAP, {int(x): k for k, x in enumerate(d.astype(int))})
    return out


@dataclass
class Lot:
    qty: int
    price: float


@dataclass
class Position:
    symbol: str
    entered: int  # bar index of the first fill
    level: float  # fixed exit level (used when exit_level == "fixed")
    lots: list[Lot] = field(default_factory=list)
    t1_done: bool = False
    t2_done: bool = False
    net: float = 0.0  # realised so far

    @property
    def qty(self) -> int:
        return sum(lot.qty for lot in self.lots)

    @property
    def cost(self) -> float:
        return sum(lot.qty * lot.price for lot in self.lots)


def _sell(pos: Position, qty: int, price: float) -> float:
    remaining, gross, buy_value = qty, 0.0, 0.0
    sell_price = price * (1 - SLIP)
    while remaining and pos.lots:
        lot = pos.lots[0]
        take = min(remaining, lot.qty)
        gross += take * (sell_price - lot.price)
        buy_value += take * lot.price
        lot.qty -= take
        remaining -= take
        if lot.qty == 0:
            pos.lots.pop(0)
    net = gross - delivery_charges(buy_value, buy_value + gross)
    pos.net += net
    return net


def _mark(pos: Position, close: float) -> float:
    value = pos.qty * close * (1 - SLIP)
    return value - pos.cost - (delivery_charges(pos.cost, value) if pos.qty else 0.0)


def simulate(data: dict[str, Series], symbols: list[str], variant: Variant, period: tuple[date, date]) -> dict:
    lo, hi = period[0].toordinal(), period[1].toordinal()
    nifty = data["NIFTY50"]
    days = sorted({int(x) for s in symbols for x in data[s].dates if lo <= x <= hi})
    open_pos: dict[str, Position] = {}
    pending: dict[str, tuple[str, float]] = {}  # symbol -> ("entry"|"t2", fixed level)
    quiet_until: dict[str, int] = {}
    closed: list[float] = []
    realised = 0.0
    long_held = 0
    deployed, equity = [], []
    last_close: dict[str, float] = {}
    entries = 0
    for day in days:
        for symbol in symbols:
            s = data[symbol]
            k = s.index.get(day)
            if k is None or k < 21:
                continue
            o, h, l, c, ema = s.open[k], s.high[k], s.low[k], s.close[k], s.ema_prev[k]
            pos = open_pos.get(symbol)
            # corporate action: close at the previous close, then stay out
            if s.event[k]:
                pending.pop(symbol, None)
                quiet_until[symbol] = k + EVENT_QUIET
                if pos is not None:
                    realised += _sell(pos, pos.qty, s.close[k - 1])
                    closed.append(pos.net)
                    del open_pos[symbol]
                last_close[symbol] = c
                continue
            # fills at the open
            order = pending.pop(symbol, None)
            if order is not None:
                fill = o * (1 + SLIP)
                qty = int(NOTIONAL // fill)
                if qty >= 1:
                    if order[0] == "entry" and pos is None:
                        pos = open_pos[symbol] = Position(symbol, k, order[1], [Lot(qty, fill)])
                        entries += 1
                    elif order[0] == "t2" and pos is not None:
                        pos.lots.append(Lot(qty, fill))
                        pos.t2_done = True
            if pos is not None:
                avg = pos.cost / pos.qty
                level = ema if variant.exit_level == "ema" else pos.level
                done = False
                if variant.price_stop is not None and l <= avg * (1 - variant.price_stop):
                    stop = avg * (1 - variant.price_stop)
                    realised += _sell(pos, pos.qty, o if o <= stop else stop)
                    done = True
                elif not math.isnan(level):
                    if not pos.t1_done and h >= level:
                        first = pos.lots[0].qty if pos.lots else 0
                        realised += _sell(pos, first, max(o, level))
                        pos.t1_done = True
                    if pos.qty and h >= level * 1.03:
                        realised += _sell(pos, pos.qty, max(o, level * 1.03))
                    done = pos.qty == 0
                if not done and variant.time_stop is not None and k - pos.entered >= variant.time_stop:
                    realised += _sell(pos, pos.qty, c)
                    done = True
                if done:
                    if k - pos.entered > 60:
                        long_held += 1
                    closed.append(pos.net)
                    del open_pos[symbol]
                    pos = None
            last_close[symbol] = c
        # signals on today's close, deepest first
        candidates = []
        for symbol in symbols:
            s = data[symbol]
            k = s.index.get(day)
            if k is None or k < 25 or quiet_until.get(symbol, -1) >= k or symbol in pending:
                continue
            ema, c = s.ema_prev[k], s.close[k]
            if math.isnan(ema):
                continue
            below = 1 - c / ema
            pos = open_pos.get(symbol)
            if pos is not None:
                if variant.tranche2 and not pos.t2_done and not pos.t1_done and 0.08 <= below <= 0.12:
                    pending[symbol] = ("t2", pos.level)
                continue
            down = all(s.close[k - j] < s.close[k - j - 1] for j in (1, 2, 3))
            if not (0.05 <= below <= 0.12 and down and c / s.close[k - 1] - 1 <= -0.01):
                continue
            if variant.stock_specific:
                nk = nifty.index.get(day)
                if nk is None or nk < 5:
                    continue
                if (c / s.close[k - 5] - 1) - (nifty.close[nk] / nifty.close[nk - 5] - 1) > -0.04:
                    continue
            candidates.append((below, symbol, ema))
        free = CAP - len(open_pos) - sum(1 for kind, _ in pending.values() if kind == "entry")
        for below, symbol, ema in sorted(candidates, reverse=True)[: max(0, free)]:
            pending[symbol] = ("entry", ema)
        deployed.append(sum(p.cost for p in open_pos.values()))
        equity.append(realised + sum(_mark(p, last_close.get(p.symbol, p.cost / p.qty)) for p in open_pos.values() if p.qty))
    marks = [p.net + _mark(p, last_close.get(p.symbol, p.cost / p.qty)) for p in open_pos.values() if p.qty]
    long_held += sum(1 for p in open_pos.values() if days and data[p.symbol].index.get(days[-1], p.entered) - p.entered > 60)
    positions = np.array(closed + marks)
    total = float(realised + sum(_mark(p, last_close.get(p.symbol, p.cost / p.qty)) for p in open_pos.values() if p.qty))
    years = max((hi - lo) / 365.25, 1e-9)
    avg_deployed = float(np.mean(deployed)) if deployed else 0.0
    eq = np.array(equity) if equity else np.array([0.0])
    n_lo, n_hi = _nifty_span(nifty, lo, hi)
    return {
        "variant": variant.name,
        "entries": entries,
        "closed": len(closed),
        "win_rate": float((np.array(closed) > 0).mean()) if closed else None,
        "realised": float(realised),
        "open_at_end": len(marks),
        "open_mark": float(sum(_mark(p, last_close.get(p.symbol, p.cost / p.qty)) for p in open_pos.values() if p.qty)),
        "total": total,
        "avg_deployed": avg_deployed,
        "peak_deployed": float(max(deployed)) if deployed else 0.0,
        "annual_return_on_deployed_pct": total / avg_deployed / years * 100 if avg_deployed > 0 else None,
        "max_drawdown": float(np.max(np.maximum.accumulate(eq) - eq)),
        "held_over_60_sessions": long_held,
        "position_mean_low": _boot_low(positions),
        "nifty_annual_pct": ((n_hi / n_lo) ** (1 / years) - 1) * 100 if n_lo else None,
    }


def _nifty_span(nifty: Series, lo: int, hi: int) -> tuple[float, float]:
    inside = [k for k, d in enumerate(nifty.dates) if lo <= d <= hi]
    return (float(nifty.close[inside[0]]), float(nifty.close[inside[-1]])) if inside else (0.0, 0.0)


def _boot_low(values: np.ndarray, draws: int = 2000) -> float | None:
    if len(values) < 2:
        return None
    rng = np.random.default_rng(0)
    return float(np.quantile([rng.choice(values, len(values)).mean() for _ in range(draws)], 0.05))


def run() -> dict:
    data = load()
    current = sorted(s for s in data if s not in FORMER and s not in ("NIFTY50", "INDIAVIX"))
    former = [s for s in FORMER if s in data]
    train = {v.name: simulate(data, current, v, TRAIN) for v in VARIANTS}
    eligible = [(name, row) for name, row in train.items() if row["entries"] >= 150 and row["annual_return_on_deployed_pct"] is not None]
    chosen_name = max(eligible, key=lambda item: (item[1]["annual_return_on_deployed_pct"], -item[1]["max_drawdown"]))[0] if eligible else None
    chosen = next(v for v in VARIANTS if v.name == chosen_name) if chosen_name else None
    report: dict[str, object] = {"protocol": "services/quant/docs/dip-reversion-protocol.md", "universe_a": current, "universe_b": former, "train": train, "chosen": chosen_name}
    if chosen is None:
        return report
    validate = simulate(data, current, chosen, VALIDATE)
    yearly = {str(year): simulate(data, current, chosen, period)["total"] for year, period in YEARS.items()}
    hurdle = max(7.0, validate["nifty_annual_pct"] or 0.0)
    checks = {
        "total_positive": validate["total"] > 0,
        "beats_7pct_and_nifty": (validate["annual_return_on_deployed_pct"] or -1) >= hurdle,
        "position_mean_lower_bound_positive": (validate["position_mean_low"] or -1) > 0,
        "every_year_positive": all(value > 0 for value in yearly.values()),
    }
    neighbours = {}
    for field_name in ("exit_level", "time_stop", "price_stop", "stock_specific", "tranche2"):
        other = {"exit_level": "fixed" if chosen.exit_level == "ema" else "ema", "time_stop": None if chosen.time_stop else 15,
                 "price_stop": None if chosen.price_stop else 0.10, "stock_specific": not chosen.stock_specific, "tranche2": not chosen.tranche2}[field_name]
        variant = Variant(**{**chosen.__dict__, field_name: other})
        neighbours[variant.name] = simulate(data, current, variant, VALIDATE)
    report.update({
        "validate": validate,
        "validate_years": yearly,
        "hurdle_pct": hurdle,
        "checks": checks,
        "passes": all(checks.values()),
        "neighbours_validate": neighbours,
        "chosen_universe_b": {label: simulate(data, former, chosen, period) for label, period in (("train", TRAIN), ("validate", VALIDATE), ("seen", SEEN))},
        "chosen_seen": simulate(data, current, chosen, SEEN),
        "base_rule": {label: simulate(data, current, BASE, period) for label, period in (("train", TRAIN), ("validate", VALIDATE), ("seen", SEEN))},
        "base_rule_universe_b": {label: simulate(data, former, BASE, period) for label, period in (("train", TRAIN), ("validate", VALIDATE), ("seen", SEEN))},
    })
    return report


def main() -> None:
    out = er.ROOT / "services/quant/docs/results/dip-reversion-result.json"
    report = run()
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: report.get(k) for k in ("chosen", "checks", "passes", "hurdle_pct", "validate_years")}, indent=2, default=str))


if __name__ == "__main__":
    main()
