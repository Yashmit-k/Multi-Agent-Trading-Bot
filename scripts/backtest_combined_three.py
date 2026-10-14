"""Backtest the three screenshot rules together on the frozen research snapshots.

Does not open the holdout, does not place orders, and does not change paper execution.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
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
from quant_agents.research.combined_three import ORDER_CAP, SYMBOL_CAP, simulate_symbol, summarize

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "combined_three"


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    chosen = []
    for row in manifest["symbols"]:
        if row["symbol"] == "TATAMOTORS" or int(row["count"]) <= 0:
            continue
        chosen.append(row["symbol"])
    return tuple(chosen)


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _money(value: object) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _write_report(path: Path, meta: dict, summary: dict) -> None:
    lines = [
        "# Combined three-algo backtest",
        "",
        "This is a research result for the three screenshot rules on one shared per-stock book. It is not evidence that the rules are profitable.",
        "",
        "## Rules",
        "",
        f"- Order notional cap ₹{meta['order_cap']}. Symbol open-notional cap ₹{meta['symbol_cap']}. Charges sit on top.",
        "- No stop. A falling price does not sell.",
        "- Dip: 5–12% below the prior 20-day EMA, three completed down days, and a 1% drop, scanned every 30 minutes. Second tranche only at 8–12% below. First tranche exits at +2%. Second tranche exits at the prior EMA plus 3%.",
        "- Narrow day gain: +0.50% to +0.75%, three rising 5-minute candles, volume above the prorated 10-session average, within ±3% of the prior EMA, and at least 2% below the prior 20-session high. Scan 09:30–15:00 IST.",
        "- Wide day gain: +1% to +4% from 10:00–13:00 IST, with the same volume baseline. Half exits at +2%. The rest exits on a 1% pullback after +1.5%.",
        "- Narrow and wide positions recheck at 15:15 and sell only when net P&L after charges is positive.",
        "",
        "## Data",
        "",
        f"- 5-minute snapshot `{meta['snapshot_5m']}` sha `{meta['sha256_5m']}`",
        f"- Daily snapshot `{meta['snapshot_1d']}` sha `{meta['sha256_1d']}`",
        f"- First bar `{meta['first_bar']}`",
        f"- Last bar `{meta['last_bar']}`",
        f"- Symbols {meta['symbol_count']} (TATAMOTORS skipped)",
        f"- Missing 5-minute steps counted and not filled: {meta['missing_5m']}",
        "- Holdout was not opened.",
        "",
        "## Result",
        "",
        f"- Realized slices: {summary['realized_slices']}",
        f"- Realized net after charges: {_money(summary['realized_net'])}",
        f"- Open marks: {summary['open_marks']}",
        f"- Unrealized net of open marks: {_money(summary['unrealized_net'])}",
        "",
        "| Algo | Realized slices | Realized net | Open marks | Unrealized net |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for algo, row in summary["by_algo"].items():
        lines.append(
            f"| {algo} | {row['realized']['count']} | {_money(row['realized']['net'])} | {row['open']['count']} | {_money(row['open']['net'])} |"
        )
    lines.extend(["", summary["note"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(days=80))
    intraday, missing, sha_5m = stream_candles(SNAPSHOT_5M, chosen, START, END, warmup=timedelta(0))
    by_daily: dict[str, list] = defaultdict(list)
    by_intraday: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_daily[bar.symbol].append(bar)
    first = None
    last = None
    for bar in intraday:
        by_intraday[bar.symbol].append(bar)
        first = bar.end if first is None or bar.end < first else first
        last = bar.end if last is None or bar.end > last else last
    closed: list[dict] = []
    marks: list[dict] = []
    for index, symbol in enumerate(chosen, start=1):
        bars = by_intraday.get(symbol, [])
        symbol_closed, symbol_marks = simulate_symbol(symbol, bars, by_daily.get(symbol, []))
        closed.extend(symbol_closed)
        marks.extend(symbol_marks)
        print(f"{index}/{len(chosen)} {symbol} bars={len(bars)} slices={len(symbol_closed)} open={len(symbol_marks)}", flush=True)
    summary = summarize(closed, marks)
    meta = {
        "snapshot_5m": SNAPSHOT_5M,
        "snapshot_1d": SNAPSHOT_1D,
        "sha256_5m": sha_5m,
        "sha256_1d": sha_1d,
        "first_bar": first.isoformat() if first else None,
        "last_bar": last.isoformat() if last else None,
        "symbol_count": len(chosen),
        "missing_5m": missing,
        "order_cap": format(ORDER_CAP, "f"),
        "symbol_cap": format(SYMBOL_CAP, "f"),
        "holdout_opened": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for row in closed:
            handle.write(json.dumps(_plain(row)) + "\n")
    with (OUT / "open_marks.jsonl").open("w", encoding="utf-8") as handle:
        for row in marks:
            handle.write(json.dumps(_plain(row)) + "\n")
    (OUT / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2), encoding="utf-8")
    _write_report(OUT / "report.md", meta, summary)
    print(summary["note"], summary["realized_net"], summary["unrealized_net"], flush=True)


if __name__ == "__main__":
    main()
