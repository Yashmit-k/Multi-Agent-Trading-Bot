"""Post-announcement drift on NIFTY 50 quarterly results, per services/quant/docs/earnings-drift-protocol.md.

    python -m quant_agents.research.earnings_drift
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, time, timedelta

from pathlib import Path

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research.mentor_strategies import delivery_charges
from quant_agents.research.slow_rotation import Grid, load_grid

RESULTS = er.ROOT / "datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/financial-results"
PERIODS = {"train": (date(2015, 3, 1), date(2019, 12, 31)), "validate": (date(2020, 1, 1), date(2022, 12, 31)), "test": (date(2023, 1, 1), date(2025, 2, 28))}
ANNOUNCEMENTS_2024 = er.ROOT / "datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/corporate-announcements"
ANNOUNCEMENTS_NEW = er.ROOT / "datasets/research/earnings_drift/nse-ann-20261027"
CLEAN = (date(2025, 3, 1), date(2026, 10, 5))
RESULT_CATEGORIES = {"Outcome of Board Meeting", "Financial Result Updates", "Integrated Filing- Financial"}
RULES = {"pos2_h20": (0.02, 20), "pos4_h20": (0.04, 20), "pos2_h40": (0.02, 40), "pos4_h40": (0.04, 40)}
CLOSE = time(15, 30)
SLIP = 0.0005
NOTIONAL = 20000.0


def _quarter_ends(start: date, end: date) -> list[date]:
    out = []
    for year in range(start.year - 1, end.year + 1):
        out += [date(year, 3, 31), date(year, 6, 30), date(year, 9, 30), date(year, 12, 31)]
    return out


def announcement_results(folder: Path, since: date, until: date) -> list[tuple[str, datetime]]:
    """Amendment A: per symbol and quarter end Q, the result announcement dated 7-75 days after Q."""
    out = []
    for path in sorted(folder.glob("*.json")):
        rows = [r for r in json.loads(path.read_text() or "[]") if r.get("desc") in RESULT_CATEGORIES and r.get("exchdisstime")]
        parsed = [(datetime.strptime(r["exchdisstime"], "%d-%b-%Y %H:%M:%S"), r) for r in rows]
        symbol = path.stem
        for q in _quarter_ends(since, until):
            window = sorted(((t, r) for t, r in parsed if q + timedelta(days=7) <= t.date() <= q + timedelta(days=75)), key=lambda item: item[0])
            if not window:
                continue
            named = [t for t, r in window if "result" in (r.get("attchmntText") or "").lower()]
            board = [t for t, r in window if r["desc"] == "Outcome of Board Meeting"]
            moment = named[0] if named else (board[0] if board else None)
            if moment is not None and since <= moment.date() <= until:
                out.append((symbol, moment))
    return sorted(set(out))


def extraction_check(grid: Grid) -> dict[str, object]:
    """Amendment A: the announcement rule against the results endpoint, on 2024 day 0 sessions."""
    truth = [(s, m) for s, m in announcements() if m.year == 2024]
    symbols = {s for s, _ in truth}
    found = [(s, m) for s, m in announcement_results(ANNOUNCEMENTS_2024, date(2024, 1, 1), date(2024, 12, 31)) if s in symbols]
    same_session = len({(s, day_zero(grid, m)) for s, m in truth} & {(s, day_zero(grid, m)) for s, m in found})
    # Amendment A.1: the same result event, found between 3 days before and 6 hours after the endpoint's time.
    matched = sum(1 for s, m in truth if any(fs == s and m - timedelta(days=3) <= g <= m + timedelta(hours=6) for fs, g in found))
    later = sum(1 for s, m in truth if any(fs == s and m + timedelta(hours=6) < g <= m + timedelta(days=5) for fs, g in found))
    return {"endpoint_events": len(truth), "rule_events": len(found), "same_session": same_session, "match_rate": matched / max(1, len(truth)), "rule_later_than_endpoint": later}


def announcements() -> list[tuple[str, datetime]]:
    """(symbol, earliest dissemination time, IST) per symbol and quarter."""
    first: dict[tuple[str, str], datetime] = {}
    for path in sorted(RESULTS.glob("*.raw")):
        for row in json.loads(path.read_text() or "[]"):
            if row.get("period") != "Quarterly" or not row.get("exchdisstime"):
                continue
            moment = datetime.strptime(row["exchdisstime"], "%d-%b-%Y %H:%M:%S")
            key = (row["symbol"], row["toDate"])
            first[key] = min(first.get(key, moment), moment)
    return sorted((symbol, moment) for (symbol, _), moment in first.items())


def day_zero(grid: Grid, moment: datetime) -> int | None:
    k = int(np.searchsorted(grid.days, moment.date().toordinal()))
    if k >= len(grid.days):
        return None
    if grid.days[k] == moment.date().toordinal() and moment.time() >= CLOSE:
        k += 1
    return k if k < len(grid.days) else None


def _universe_return(grid: Grid, cols: list[int], skip: int, a: int, b: int, start_open: bool) -> float:
    base = grid.open[a, cols] if start_open else grid.close[a, cols]
    end = grid.close[b, cols]
    ok = ~np.isnan(base) & ~np.isnan(end) & (np.array(cols) != skip)
    return float(np.mean(end[ok] / base[ok] - 1))


def events(grid: Grid, cols: list[int], source: list[tuple[str, datetime]] | None = None) -> list[dict[str, object]]:
    out = []
    index = {s: j for j, s in enumerate(grid.symbols)}
    for symbol, moment in announcements() if source is None else source:
        j = index.get(symbol)
        k0 = day_zero(grid, moment) if j is not None and j in cols else None
        if k0 is None or k0 < 1:
            continue
        row: dict[str, object] = {"symbol": symbol, "announced": moment.isoformat(), "day0": date.fromordinal(int(grid.days[k0])).isoformat()}
        before, after = grid.close[k0 - 1, j], grid.close[min(k0 + 1, len(grid.days) - 1), j]
        if k0 + 2 >= len(grid.days) or math.isnan(before) or math.isnan(after):
            continue
        row["reaction"] = float(after / before - 1) - _universe_return(grid, cols, j, k0 - 1, k0 + 1, False)
        for hold in (20, 40):
            e, x = k0 + 2, k0 + 1 + hold
            if x >= len(grid.days) or math.isnan(grid.open[e, j]) or math.isnan(grid.close[x, j]) or grid.event[k0 - 1: x + 1, j].any():
                continue
            raw = float(grid.close[x, j] / grid.open[e, j] - 1)
            cost = delivery_charges(NOTIONAL, NOTIONAL * (1 + raw)) / NOTIONAL + 2 * SLIP
            row[f"h{hold}"] = {"raw": raw, "excess": raw - _universe_return(grid, cols, j, e, x, True), "cost": cost}
        out.append(row)
    return out


def _quarter(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _block_low(trades: list[tuple[str, float]], q: float) -> float:
    groups: dict[str, list[float]] = {}
    for quarter, value in trades:
        groups.setdefault(quarter, []).append(value)
    keys = list(groups)
    if len(keys) < 4:
        return math.nan
    rng = np.random.default_rng(0)
    means = []
    for _ in range(2000):
        pick = rng.integers(0, len(keys), len(keys))
        values = [v for i in pick for v in groups[keys[i]]]
        means.append(np.mean(values))
    return float(np.quantile(means, q))


def _in(period: tuple[date, date], day: str) -> bool:
    return period[0] <= date.fromisoformat(day) <= period[1]


def run() -> dict[str, object]:
    grid, current, _ = load_grid()
    cols = [grid.symbols.index(s) for s in current]
    rows = events(grid, cols)
    report: dict[str, object] = {"protocol": "services/quant/docs/earnings-drift-protocol.md", "events_with_reaction": len(rows), "periods": PERIODS}
    rules: dict[str, object] = {}
    for name, (threshold, hold) in RULES.items():
        key = f"h{hold}"
        per: dict[str, object] = {}
        pooled: list[tuple[str, float]] = []
        for label, period in PERIODS.items():
            picked = [r for r in rows if _in(period, str(r["day0"])) and key in r and float(r["reaction"]) >= threshold]  # type: ignore[arg-type]
            net = [(_quarter(str(r["day0"])), r[key]["excess"] - r[key]["cost"]) for r in picked]  # type: ignore[index]
            raw_net = [r[key]["raw"] - r[key]["cost"] for r in picked]  # type: ignore[index]
            pooled += net
            values = [v for _, v in net]
            per[label] = {
                "trades": len(values),
                "mean_net_excess": float(np.mean(values)) if values else math.nan,
                "median_net_excess": float(np.median(values)) if values else math.nan,
                "win_rate_vs_universe": float(np.mean([v > 0 for v in values])) if values else math.nan,
                "mean_net_raw": float(np.mean(raw_net)) if raw_net else math.nan,
                "net_excess_low10": _block_low(net, 0.10),
            }
        low10, low025 = _block_low(pooled, 0.10), _block_low(pooled, 0.025)
        every = all(per[label]["mean_net_excess"] > 0 for label in PERIODS)  # type: ignore[index]
        rules[name] = {"periods": per, "pooled_trades": len(pooled), "pooled_mean": float(np.mean([v for _, v in pooled])), "pooled_low10": low10, "pooled_low025": low025, "works": bool(every and low10 > 0), "survives_bonferroni": bool(every and low025 > 0)}
    report["rules"] = rules
    curve = {}
    usable = [r for r in rows if "h20" in r and _in((PERIODS["train"][0], PERIODS["test"][1]), str(r["day0"]))]
    edges = np.quantile([float(r["reaction"]) for r in usable], [0.2, 0.4, 0.6, 0.8])  # type: ignore[arg-type]
    for q in range(5):
        lo = -math.inf if q == 0 else edges[q - 1]
        hi = math.inf if q == 4 else edges[q]
        group = [r for r in usable if lo <= float(r["reaction"]) < hi]  # type: ignore[arg-type]
        curve[f"Q{q + 1}"] = {
            "reaction_range": [None if q == 0 else float(lo), None if q == 4 else float(hi)],
            "events": len(group),
            "mean_reaction": float(np.mean([float(r["reaction"]) for r in group])),  # type: ignore[arg-type]
            "mean_excess_20": float(np.mean([r["h20"]["excess"] for r in group])),  # type: ignore[index]
        }
    report["drift_by_reaction_quintile"] = curve
    return report


def clean_test() -> dict[str, object]:
    grid, current, _ = load_grid()
    cols = [grid.symbols.index(s) for s in current]
    check = extraction_check(grid)
    report: dict[str, object] = {"protocol": "services/quant/docs/earnings-drift-protocol.md#amendment-a", "extraction_check": check}
    print("extraction check", check, flush=True)
    if check["match_rate"] < 0.90:
        report["stopped"] = "announcement rule matches fewer than 90% of 2024 events"
        return report
    rows = events(grid, cols, announcement_results(ANNOUNCEMENTS_NEW, CLEAN[0], date(2026, 10, 27)))
    rows = [r for r in rows if _in(CLEAN, str(r["day0"]))]
    report["events"] = len(rows)
    report["seasons"] = sorted({_quarter(str(r["day0"])) for r in rows})
    out = {}
    for name, (threshold, hold) in RULES.items():
        key = f"h{hold}"
        picked = [r for r in rows if key in r and float(r["reaction"]) >= threshold]  # type: ignore[arg-type]
        net = [(_quarter(str(r["day0"])), r[key]["excess"] - r[key]["cost"]) for r in picked]  # type: ignore[index]
        values = [v for _, v in net]
        out[name] = {
            "scored": name == "pos4_h40",
            "trades": len(values),
            "mean_net_excess": float(np.mean(values)) if values else math.nan,
            "median_net_excess": float(np.median(values)) if values else math.nan,
            "win_rate_vs_universe": float(np.mean([v > 0 for v in values])) if values else math.nan,
            "mean_net_raw": float(np.mean([r[key]["raw"] - r[key]["cost"] for r in picked])) if picked else math.nan,  # type: ignore[index]
            "net_excess_low10": _block_low(net, 0.10),
            "trades_list": [{"symbol": r["symbol"], "day0": r["day0"], "reaction": r["reaction"], "net_excess": r[key]["excess"] - r[key]["cost"], "net_raw": r[key]["raw"] - r[key]["cost"]} for r in picked],  # type: ignore[index]
        }
    report["rules"] = out
    main_rule = out["pos4_h40"]
    report["passes"] = bool(main_rule["trades"] and main_rule["mean_net_excess"] > 0 and main_rule["net_excess_low10"] > 0)
    return report


def main() -> None:
    if "--clean" in sys.argv:
        report = clean_test()
        (er.ROOT / "services/quant/docs/results/earnings-drift-clean-result.json").write_text(json.dumps(report, indent=1, default=str))
        print(json.dumps({k: v for k, v in report.items() if k != "rules"}, indent=1, default=str))
        for name, r in report.get("rules", {}).items():  # type: ignore[union-attr]
            print(name, {k: v for k, v in r.items() if k != "trades_list"})
        return
    report = run()
    out = er.ROOT / "services/quant/docs/results/earnings-drift-result.json"
    out.write_text(json.dumps(report, indent=1, default=str))
    print("events", report["events_with_reaction"])
    for name, r in report["rules"].items():  # type: ignore[union-attr]
        cells = " | ".join(f"{p}: n={v['trades']} net {v['mean_net_excess']:+.2%} med {v['median_net_excess']:+.2%} win {v['win_rate_vs_universe']:.0%} raw {v['mean_net_raw']:+.2%}" for p, v in r["periods"].items())
        print(f"{name}: {cells} | pooled {r['pooled_mean']:+.2%} low10 {r['pooled_low10']:+.2%} low2.5 {r['pooled_low025']:+.2%} works {r['works']}")
    for q, v in report["drift_by_reaction_quintile"].items():  # type: ignore[union-attr]
        print(q, v)


if __name__ == "__main__":
    main()
