"""Options-market signals for choosing shares (batch 2 of trend-volume-options-protocol.md). No option is traded.

O1 vol_skew (Xing, Zhang & Zhao 2010): IV of the ~0.95-moneyness traded put minus IV of the ~ATM traded call (lowest best).
O2 call_put_spread (Cremers & Weinbaum 2010): OI-weighted mean of call IV - put IV over strikes where both traded
(highest best). Each is the mean of its daily values over the last 5 sessions of the month (at least 2 valid).
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import defaultdict
from datetime import date, datetime

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_compound as mc
from quant_agents.research import momentum_variants as mv
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

RAW = er.ROOT / "datasets/research/fo/raw"
RATE = 0.065
PERIODS = {"train": (date(2016, 2, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 27))}
K = 5


def _ncdf(x):
    from scipy.special import ndtr

    return ndtr(x)


def bs_price(spot, strike, years, vol, call):
    d1 = (np.log(spot / strike) + (RATE + 0.5 * vol ** 2) * years) / (vol * np.sqrt(years))
    d2 = d1 - vol * np.sqrt(years)
    disc = strike * np.exp(-RATE * years)
    return np.where(call, spot * _ncdf(d1) - disc * _ncdf(d2), disc * _ncdf(-d2) - spot * _ncdf(-d1))


def implied_vol(price, spot, strike, years, call):
    """Bisection on [1%, 300%]; NaN when the price is below intrinsic value or above the upper bound."""
    price, spot, strike, years, call = map(np.asarray, (price, spot, strike, years, call))
    lo, hi = np.full(price.shape, 0.01), np.full(price.shape, 3.0)
    p_lo, p_hi = bs_price(spot, strike, years, lo, call), bs_price(spot, strike, years, hi, call)
    ok = (price > p_lo) & (price < p_hi)
    for _ in range(60):
        mid = (lo + hi) / 2
        above = bs_price(spot, strike, years, mid, call) > price
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return np.where(ok, (lo + hi) / 2, np.nan)


def rows(day: date):
    """Traded stock-option rows of one day: (symbol, expiry, strike, is_call, settle, oi)."""
    path = RAW / f"{day.isoformat()}.zip"
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(text))
    out = []
    new = "TckrSymb" in (reader.fieldnames or [])
    for r in reader:
        try:
            if new:
                if r["FinInstrmTp"] != "STO" or float(r["TtlTradgVol"] or 0) <= 0:
                    continue
                expiry = date.fromisoformat(r["XpryDt"])
                out.append((r["TckrSymb"].strip(), expiry, float(r["StrkPric"]), r["OptnTp"] == "CE", float(r["SttlmPric"] or r["ClsPric"]), float(r["OpnIntrst"] or 0)))
            else:
                if r["INSTRUMENT"].strip() != "OPTSTK" or float(r["CONTRACTS"] or 0) <= 0:
                    continue
                expiry = datetime.strptime(r["EXPIRY_DT"].strip(), "%d-%b-%Y").date()
                out.append((r["SYMBOL"].strip(), expiry, float(r["STRIKE_PR"]), r["OPTION_TYP"].strip() == "CE", float(r["SETTLE_PR"] or r["CLOSE"]), float(r["OPEN_INT"] or 0)))
        except (KeyError, ValueError):
            continue
    return out


def daily_signals(day: date, spot_of) -> dict[str, tuple[float, float]]:
    """symbol -> (skew, call-put spread) for one day; NaN where it cannot be computed. All IVs solved in one batch."""
    by_symbol = defaultdict(list)
    for row in rows(day):
        by_symbol[row[0]].append(row)
    chosen, spots, owners = [], [], []
    for symbol, items in by_symbol.items():
        spot = spot_of(symbol)
        if spot is None or not spot > 0:
            continue
        expiries = sorted({e for _, e, *_ in items if (e - day).days >= 7})
        if not expiries:
            continue
        for it in items:
            if it[1] == expiries[0] and it[4] > 0:
                chosen.append(it)
                spots.append(spot)
                owners.append(symbol)
    if not chosen:
        return {}
    strikes = np.array([it[2] for it in chosen])
    calls = np.array([it[3] for it in chosen])
    prices = np.array([it[4] for it in chosen])
    oi = np.array([it[5] for it in chosen])
    years = np.array([max((it[1] - day).days, 1) / 365.0 for it in chosen])
    spots_a = np.array(spots)
    iv = implied_vol(prices, spots_a, strikes, years, calls)
    mny = strikes / spots_a
    owners_a = np.array(owners)
    out = {}
    for symbol in np.unique(owners_a):
        idx = np.where(owners_a == symbol)[0]
        k_, c_, v_, m_, o_ = strikes[idx], calls[idx], iv[idx], mny[idx], oi[idx]
        skew = math.nan
        puts = np.where(~c_ & (m_ >= 0.80) & (m_ <= 0.95) & np.isfinite(v_))[0]
        atm = np.where(c_ & (m_ >= 0.95) & (m_ <= 1.05) & np.isfinite(v_))[0]
        if len(puts) and len(atm):
            skew = float(v_[puts[np.argmin(np.abs(m_[puts] - 0.95))]] - v_[atm[np.argmin(np.abs(m_[atm] - 1.00))]])
        pairs, weights = [], []
        for k in np.unique(k_):
            ci = np.where(c_ & (k_ == k) & np.isfinite(v_))[0]
            pi = np.where(~c_ & (k_ == k) & np.isfinite(v_))[0]
            if len(ci) and len(pi):
                pairs.append(v_[ci[0]] - v_[pi[0]])
                weights.append(o_[ci[0]] + o_[pi[0]])
        spread = float(np.average(pairs, weights=weights)) if pairs and sum(weights) > 0 else math.nan
        out[str(symbol)] = (skew, spread)
    return out


def monthly_signals(m) -> dict[int, dict[int, tuple[float, float]]]:
    """month-end index -> {chain: (skew, spread)} from the last 5 sessions of that month."""
    by_symbol: dict[str, list[int]] = defaultdict(list)
    for j, s in enumerate(m.p.symbols):
        by_symbol[str(s)].append(j)
    result = {}
    for t in sorted(m.members):
        if m.d[t] < date(2016, 1, 1):
            continue
        daily = defaultdict(list)
        for k in range(t - 4, t + 1):

            def spot_of(symbol, k=k):
                for j in by_symbol.get(symbol, []):
                    if m.p.series[k, j] == 1 and not math.isnan(m.p.close[k, j]):
                        return float(m.p.close[k, j])
                return None

            for symbol, vals in daily_signals(m.d[k], spot_of).items():
                for j in by_symbol.get(symbol, []):
                    if m.p.series[k, j] == 1:
                        daily[j].append(vals)
                        break
        month = {}
        for j, vals in daily.items():
            sk = [v[0] for v in vals if np.isfinite(v[0])]
            sp = [v[1] for v in vals if np.isfinite(v[1])]
            month[j] = (float(np.mean(sk)) if len(sk) >= 2 else math.nan, float(np.mean(sp)) if len(sp) >= 2 else math.nan)
        result[t] = month
        print(m.d[t], "F&O stocks with signals:", len(month), flush=True)
    return result


def scorer_for(signals, which: int, sign: float):
    def scorer(m, rule, t, cols):
        month = signals.get(t, {})
        return np.array([sign * month[j][which] if j in month and np.isfinite(month[j][which]) else -np.inf for j in cols])
    return scorer


def fo_benchmark(m, signals, ends, lo):
    out, start = [], lo - 1
    for t in ends:
        anchor = max(k for k in signals if k <= start) if any(k <= start for k in signals) else None
        members = [j for j in (signals.get(anchor, {}) if anchor is not None else {}) if j in set(m.members.get(anchor, []).tolist())]
        out.append(float(np.nanmean(m.index[t, members] / m.index[start, members] - 1)) if members else 0.0)
        start = t
    return out


def book(m, signals, start, end, scorer):
    wm.scores = scorer
    try:
        sim = mc.simulate(m, start=start, end=end, fill_leftover=True)
    finally:
        wm.scores = mv.ORIGINAL
    lo, hi, marks = sim["lo"], sim["hi"], sim["marks"]
    ends = [t for t in m.month_ends if lo <= t <= hi] + ([hi] if hi not in m.month_ends else [])
    values = [mc.CAPITAL] + [marks[t] for t in ends]
    years = (m.p.days[hi] - m.p.days[lo - 1]) / 365.25
    fo = fo_benchmark(m, signals, ends, lo)
    nifty = wm.asset_months(m, wm.chain_of(m, "NIFTYBEES"), [(t, 0.0) for t in ends], lo)
    eq = np.array(values)
    grow = lambda xs: float(np.prod([1 + x for x in xs]) ** (1 / years) - 1)  # noqa: E731
    return {"monthly": [values[k + 1] / values[k] - 1 for k in range(len(ends))], "fo_monthly": fo, "final": float(values[-1]),
            "cagr": float((values[-1] / mc.CAPITAL) ** (1 / years) - 1), "fo_benchmark_cagr": grow(fo), "niftybees_cagr": grow(nifty),
            "max_drawdown": float(np.max(1 - eq / np.maximum.accumulate(eq))), "charges": float(sim["charges"]), "trades": len(sim["trades"])}


def batch2() -> dict[str, object]:
    m = wm.Market(load())
    signals = monthly_signals(m)
    out: dict[str, object] = {}
    for name, which, sign in (("vol_skew", 0, -1.0), ("call_put_spread", 1, 1.0)):
        per = {k: book(m, signals, a, b, scorer_for(signals, which, sign)) for k, (a, b) in PERIODS.items()}
        beats_fo = {k: bool(v["cagr"] > v["fo_benchmark_cagr"]) for k, v in per.items()}
        beats_nifty = {k: bool(v["cagr"] > v["niftybees_cagr"]) for k, v in per.items()}
        diff = np.array([a - b for v in per.values() for a, b in zip(v["monthly"], v["fo_monthly"])])
        rng = np.random.default_rng(0)
        low = float(np.quantile(diff[rng.integers(0, len(diff), size=(2000, len(diff)))].mean(axis=1), 0.10 / K))
        gate = {"beats_fo_benchmark": beats_fo, "beats_niftybees": beats_nifty, "mean_monthly_vs_fo": float(diff.mean()),
                "t_stat": float(diff.mean() / (diff.std(ddof=1) / math.sqrt(len(diff)))), "bonferroni_low": low,
                "passes": bool(all(beats_fo.values()) and all(beats_nifty.values()) and low > 0)}
        out[name] = {"periods": {k: {a: b for a, b in v.items() if a not in ("monthly", "fo_monthly")} for k, v in per.items()}, "gate": gate}
        cells = "  ".join(f"{k} {v['cagr']:+.1%} (F&O eq-wt {v['fo_benchmark_cagr']:+.1%}, NIFTYBEES {v['niftybees_cagr']:+.1%}, dd {v['max_drawdown']:.0%})" for k, v in per.items())
        print(f"{name:16} {cells}")
        print(f"{'':16} gate {beats_fo} {beats_nifty} diff {gate['mean_monthly_vs_fo']*100:+.2f}%/m t {gate['t_stat']:.2f} low {low*100:+.2f}% -> {'PASSES' if gate['passes'] else 'no'}")
    out["momentum_for_reference"] = {k: {a: b for a, b in mv.book(m, a2, b2).items() if a != "monthly"} for k, (a2, b2) in PERIODS.items()}
    out["coverage"] = {m.d[t].isoformat(): len(v) for t, v in signals.items()}
    return out
