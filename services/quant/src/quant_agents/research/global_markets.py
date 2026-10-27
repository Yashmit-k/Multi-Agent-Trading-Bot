"""Global markets before 09:15 IST vs NIFTY 50 after the open, per services/quant/docs/global-markets-protocol.md.

    python -m quant_agents.research.global_markets [--fetch]
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import spearmanr

from quant_agents.research import exit_rules as er
from quant_agents.research.dip_reversion import DATA

FOLDER = er.ROOT / "datasets/research/global_markets"
PERIODS = {"train": (date(2015, 3, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 5))}
# name -> (Yahoo symbol, kind, sign): "close" = latest close before D vs the one before; "asia_gap" = open of D vs previous close
INPUTS = {
    "sp500": ("^GSPC", "close", 1),
    "nasdaq": ("^IXIC", "close", 1),
    "vix": ("^VIX", "close", -1),
    "nikkei": ("^N225", "asia_gap", 1),
    "kospi": ("^KS11", "asia_gap", 1),
    "hang_seng": ("^HSI", "asia_gap", 1),
    "ftse": ("^FTSE", "close", 1),
    "dax": ("^GDAXI", "close", 1),
    "brent": ("BZ=F", "close", -1),
    "usdinr": ("INR=X", "close", -1),
    "dollar": ("DX-Y.NYB", "close", -1),
    "us10y": ("^TNX", "close", -1),
}
COMPOSITE = ("sp500", "nasdaq", "asia", "vix", "brent", "usdinr", "dollar", "us10y")
WINDOW = 250


def fetch() -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    start = int(datetime(2014, 6, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 10, 28, tzinfo=timezone.utc).timestamp())
    for name, (symbol, _, _) in INPUTS.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?period1={start}&period2={end}&interval=1d"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            (FOLDER / f"{name}.json").write_bytes(response.read())
        print("fetched", name, flush=True)
        time.sleep(1)


def bars(name: str) -> list[tuple[date, float, float]]:
    """(exchange-local date, open, close), sorted, rows with gaps dropped."""
    result = json.loads((FOLDER / f"{name}.json").read_text())["chart"]["result"][0]
    zone = ZoneInfo(result["meta"]["exchangeTimezoneName"])
    quote = result["indicators"]["quote"][0]
    out = {}
    for stamp, o, c in zip(result["timestamp"], quote["open"], quote["close"]):
        if o is None or c is None or not (o > 0 and c > 0):
            continue
        out[datetime.fromtimestamp(stamp, zone).date()] = (float(o), float(c))
    return [(d, o, c) for d, (o, c) in sorted(out.items())]


def nifty() -> tuple[list[date], np.ndarray, np.ndarray]:
    rows = {}
    for line in DATA.read_text().splitlines():
        r = json.loads(line)
        if r["symbol"] == "NIFTY50":
            rows[date.fromisoformat(r["date"][:10])] = (float(r["open"]), float(r["close"]))
    days = sorted(rows)
    return days, np.array([rows[d][0] for d in days]), np.array([rows[d][1] for d in days])


def input_series(name: str, days: list[date]) -> np.ndarray:
    _, kind, sign = INPUTS[name]
    series = bars(name)
    dates = [d for d, _, _ in series]
    out = np.zeros(len(days))
    if kind == "close":
        last = [int(np.searchsorted(np.array(dates, dtype="datetime64[D]"), np.datetime64(d), side="left")) - 1 for d in days]
        for i in range(1, len(days)):
            k, k_prev = last[i], last[i - 1]
            if k > k_prev >= 0:
                out[i] = series[k][2] / series[k_prev][2] - 1
    else:
        index = {d: k for k, d in enumerate(dates)}
        for i, d in enumerate(days):
            k = index.get(d)
            if k is not None and k > 0:
                out[i] = series[k][1] / series[k - 1][2] - 1
    return sign * out


def scaled(x: np.ndarray) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(WINDOW, len(x)):
        sd = np.std(x[i - WINDOW: i])
        out[i] = x[i] / sd if sd > 0 else 0.0
    return out


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    ok = ~np.isnan(a) & ~np.isnan(b)
    return float(spearmanr(a[ok], b[ok])[0]) if ok.sum() > 20 else math.nan


def _month_boot(a: np.ndarray, b: np.ndarray, months: np.ndarray) -> list[float]:
    ok = ~np.isnan(a) & ~np.isnan(b)
    a, b, months = a[ok], b[ok], months[ok]
    keys = np.unique(months)
    groups = [np.where(months == k)[0] for k in keys]
    rng = np.random.default_rng(0)
    draws = []
    for _ in range(2000):
        pick = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        draws.append(spearmanr(a[pick], b[pick])[0])
    return [float(np.quantile(draws, 0.05)), float(np.quantile(draws, 0.95))]


def run() -> dict[str, object]:
    days, o, c = nifty()
    n = len(days)
    targets = {"gap": np.full(n, np.nan), "open_to_close": c / o - 1, "open_to_5d": np.full(n, np.nan)}
    targets["gap"][1:] = o[1:] / c[:-1] - 1
    targets["open_to_5d"][: n - 4] = c[4:] / o[: n - 4] - 1
    raw = {name: input_series(name, days) for name in INPUTS}
    raw["asia"] = (raw["nikkei"] + raw["kospi"] + raw["hang_seng"]) / 3
    z = {name: scaled(values) for name, values in raw.items()}
    composite = np.nanmean(np.vstack([z[name] for name in COMPOSITE]), axis=0)
    composite[: WINDOW] = np.nan
    risk_off = np.zeros(n, dtype=bool)
    for i in range(2 * WINDOW, n):
        risk_off[i] = composite[i] <= np.nanquantile(composite[i - WINDOW: i], 0.2)
    day_arr = np.array([d.toordinal() for d in days])
    months = np.array([d.year * 12 + d.month for d in days])
    report: dict[str, object] = {"protocol": "services/quant/docs/global-markets-protocol.md", "sessions": n, "first": days[0], "last": days[-1]}
    per: dict[str, object] = {}
    pooled = np.zeros(n, dtype=bool)
    for label, (lo, hi) in PERIODS.items():
        mask = (day_arr >= lo.toordinal()) & (day_arr <= hi.toordinal())
        pooled |= mask
        part: dict[str, object] = {"sessions": int(mask.sum()), "risk_off_days": int((mask & risk_off).sum())}
        for target, y in targets.items():
            part[target] = {
                "composite": _corr(composite[mask], y[mask]),
                "inputs": {name: _corr(z[name][mask], y[mask]) for name in list(INPUTS) + ["asia"]},
                "risk_off_bp": float(np.nanmean(y[mask & risk_off]) * 1e4),
                "other_bp": float(np.nanmean(y[mask & ~risk_off & ~np.isnan(composite)]) * 1e4),
            }
        per[label] = part
    report["periods"] = per
    gate = {}
    for target in ("open_to_close", "open_to_5d", "gap"):
        signs = {label: per[label][target]["composite"] for label in PERIODS}  # type: ignore[index]
        same = all(v > 0 for v in signs.values()) or all(v < 0 for v in signs.values())
        interval = _month_boot(composite[pooled], targets[target][pooled], months[pooled])
        excludes = interval[0] > 0 or interval[1] < 0
        gate[target] = {"by_period": signs, "pooled": _corr(composite[pooled], targets[target][pooled]), "pooled_90": interval, "useful": bool(same and excludes and target != "gap"), "counts_for_gate": target != "gap"}
    report["gate"] = gate
    return report


def main() -> None:
    if "--fetch" in sys.argv:
        fetch()
    report = run()
    (er.ROOT / "services/quant/docs/results/global-markets-result.json").write_text(json.dumps(report, indent=1, default=str))
    for label, part in report["periods"].items():  # type: ignore[union-attr]
        print(label, "sessions", part["sessions"], "risk-off", part["risk_off_days"])
        for target in ("gap", "open_to_close", "open_to_5d"):
            t = part[target]
            top = ", ".join(f"{k} {v:+.2f}" for k, v in t["inputs"].items())
            print(f"  {target:14} composite {t['composite']:+.3f}  risk-off {t['risk_off_bp']:+.1f}bp vs {t['other_bp']:+.1f}bp | {top}")
    print(json.dumps(report["gate"], indent=1))


if __name__ == "__main__":
    main()
