"""Test dip exit guards on the frozen combined book.

Wide stays without the pullback. Narrow stays at the ±2% EMA band.
Does not open the holdout, place orders, or change paper execution.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "packages/contracts/src",
    "services/core/db/src",
    "services/core/candle-engine/src",
    "services/core/feature-engine/src",
    "services/core/signal-ingestion/src",
    "services/core/market-data/src",
    "services/core/worker/src",
    "services/core/api/src",
    "services/core/signal-fusion/src",
    "services/core/decision-engine/src",
    "services/core/risk-engine/src",
    "services/core/paper-execution/src",
    "services/quant/src",
):
    sys.path.insert(0, str(ROOT / relative))

from core_market_data.replay import stream_candles
from quant_agents.research.combined_three import BookConfig, _days, measure, passes, simulate_symbol

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
SLIPPAGE = Decimal("5")
OUT = ROOT / "datasets" / "research" / "combined_three"


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    chosen = []
    for row in manifest["symbols"]:
        if row["symbol"] == "TATAMOTORS" or int(row["count"]) <= 0:
            continue
        chosen.append(row["symbol"])
    return tuple(chosen)


def _money(value: object) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _frozen(name: str, **changes: object) -> BookConfig:
    return BookConfig(
        name=name,
        slippage_bps=SLIPPAGE,
        wide_retrace=False,
        ema_band=Decimal("2"),
        **changes,
    )


def run_book(config: BookConfig, symbols: tuple[str, ...], by_intraday: dict, by_daily: dict):
    closed: list[dict] = []
    marks: list[dict] = []
    paths: list[list[dict]] = []
    for symbol in symbols:
        path: list[dict] = []
        symbol_closed, symbol_marks = simulate_symbol(
            symbol,
            by_intraday.get(symbol, []),
            by_daily.get(symbol, []),
            config,
            path=path,
        )
        closed.extend(symbol_closed)
        marks.extend(symbol_marks)
        paths.append(path)
    return measure(closed, marks, paths), _dip_detail(closed, marks)


def _median(values: list[Decimal]) -> str:
    if not values:
        return ""
    ordered = sorted(values)
    mid = len(ordered) // 2
    chosen = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return format(chosen.quantize(Decimal("0.01")), "f")


def _dip_detail(closed: list[dict], marks: list[dict]) -> dict:
    dip_closed = [row for row in closed if row["algo"] == "dip"]
    dip_open = [row for row in marks if row["algo"] == "dip"]
    closed_losses = [row for row in dip_closed if row["net_pnl"] <= 0]
    open_losses = [row for row in dip_open if row["unrealized_net"] < 0]
    reasons: dict[str, dict[str, str]] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in closed_losses:
        grouped[f"tranche_{row['tranche']}:{row['exit_reason']}"].append(row)
    for label, rows in sorted(grouped.items()):
        reasons[label] = {
            "count": str(len(rows)),
            "net": format(sum((row["net_pnl"] for row in rows), Decimal("0")), "f"),
        }
    return {
        "closed_loss_count": len(closed_losses),
        "closed_loss_net": format(sum((row["net_pnl"] for row in closed_losses), Decimal("0")), "f"),
        "closed_loss_reasons": reasons,
        "open_loss_count": len(open_losses),
        "open_loss_net": format(sum((row["unrealized_net"] for row in open_losses), Decimal("0")), "f"),
        "median_closed_hold_days": _median([_days(row["entry_time"], row["exit_time"]) for row in dip_closed]),
        "max_closed_hold_days": "" if not dip_closed else format(max(_days(row["entry_time"], row["exit_time"]) for row in dip_closed).quantize(Decimal("0.01")), "f"),
        "median_open_hold_days": _median([_days(row["entry_time"], row["mark_time"]) for row in dip_open]),
        "max_open_hold_days": "" if not dip_open else format(max(_days(row["entry_time"], row["mark_time"]) for row in dip_open).quantize(Decimal("0.01")), "f"),
    }


def _days_text(value: object) -> str:
    if value in (None, ""):
        return ""
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _row(name: str, metrics: dict, kept: str) -> str:
    return (
        f"| {name} | {_money(metrics['total_net'])} | {_money(metrics['realized_net'])} | "
        f"{_money(metrics['unrealized_net'])} | {_money(metrics['max_drawdown'])} | "
        f"{_money(metrics['average_open_notional'])} | {_money(metrics['ending_open_notional'])} | "
        f"{metrics['open_positions']} | {_days_text(metrics['median_closed_hold_days'])} | {_days_text(metrics['max_closed_hold_days'])} | "
        f"{_days_text(metrics['median_open_hold_days'])} | {_days_text(metrics['max_open_hold_days'])} | {kept} |"
    )


def _dip_row(name: str, detail: dict) -> str:
    return (
        f"| {name} | {detail['closed_loss_count']} | {_money(detail['closed_loss_net'])} | "
        f"{detail['open_loss_count']} | {_money(detail['open_loss_net'])} | "
        f"{detail['median_closed_hold_days']} | {detail['max_closed_hold_days']} | "
        f"{detail['median_open_hold_days']} | {detail['max_open_hold_days']} |"
    )


def _write(path: Path, rows: list[tuple[str, dict, dict, str]]) -> None:
    lines = [
        "# Dip exit guards on the frozen combined book",
        "",
        "Wide stays without the pullback exit. Narrow stays within ±2% of the prior EMA20. Every book uses 5 bps slippage, the Zerodha charge table, ₹20,000 per order, and ₹40,000 open notional per symbol. The window is 2024-01-01 through 2026-10-05 on `nifty50_5m_20261005` and `nifty50_1d_20261005`, excluding TATAMOTORS. The holdout was not opened.",
        "",
        "The tranche-1 guard sells at +2% only when the round trip is strictly profitable after that slippage and the applicable charges, including the delivery DP charge. The tranche-2 guard sells at EMA +3% only on the same test. A sale that does not clear the test stays open.",
        "",
        "A variant is kept only when total net is higher, average open notional is not higher, and maximum drawdown is not worse than the frozen combined book.",
        "",
        "| Book | Total net | Realized | Unrealized | Max drawdown | Average open notional | Ending open notional | Open positions | Median closed hold | Max closed hold | Median open hold | Max open hold | Kept |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, metrics, _detail, kept in rows:
        lines.append(_row(name, metrics, kept))
    lines.extend(
        [
            "",
            "## Dip losses",
            "",
            "Closed losses are dip slices whose net after charges is zero or negative. Open losses are dip lots still open with a negative mark. Hold times in this table are for dip lots only.",
            "",
            "| Book | Closed dip losses | Closed loss net | Open dip losses | Open loss net | Median closed hold | Max closed hold | Median open hold | Max open hold |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, _metrics, detail, _kept in rows:
        lines.append(_dip_row(name, detail))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    chosen = symbols_from_manifest()
    daily, _, _sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(days=80))
    intraday, _missing, _sha_5m = stream_candles(SNAPSHOT_5M, chosen, START, END, warmup=timedelta(0))
    by_daily: dict[str, list] = defaultdict(list)
    by_intraday: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_daily[bar.symbol].append(bar)
    for bar in intraday:
        by_intraday[bar.symbol].append(bar)
    print("loaded", len(chosen), "symbols", flush=True)
    books = [
        _frozen("combined"),
        _frozen("dip_tranche1_guard", dip_tranche1_guard=True),
        _frozen("dip_tranche2_guard", dip_cost_guard=True),
        _frozen("dip_both_guards", dip_tranche1_guard=True, dip_cost_guard=True),
    ]
    measured: list[tuple[BookConfig, dict, dict]] = []
    for config in books:
        metrics, detail = run_book(config, chosen, by_intraday, by_daily)
        measured.append((config, metrics, detail))
        print(config.name, metrics["total_net"], flush=True)
    baseline = measured[0][1]
    rows = []
    payload_rows = []
    for config, metrics, detail in measured:
        if config.name == "combined":
            kept = "baseline"
        else:
            kept = "yes" if passes(metrics, baseline) else "no"
        rows.append((config.name, metrics, detail, kept))
        payload_rows.append({"name": config.name, "kept": kept, "metrics": metrics, "dip": detail})
        print(config.name, kept, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dip_exit_guards.json").write_text(json.dumps({"slippage_bps": "5", "rows": payload_rows}, indent=2), encoding="utf-8")
    _write(OUT / "dip_exit_guards.md", rows)


if __name__ == "__main__":
    main()
