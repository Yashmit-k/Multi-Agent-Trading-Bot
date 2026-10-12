"""Run the pre-registered oversold rebound study on the frozen research snapshots.

Does not open the holdout, does not place orders, and does not change paper-fusion.
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
from quant_agents.research.rebound import (
    COST_BPS,
    MODES,
    VARIANTS,
    classify,
    enrich,
    lookahead_audit,
    price_trade,
    simulate_symbol,
    trade_record,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "rebound"


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    chosen = []
    for row in manifest["symbols"]:
        if row["symbol"] == "TATAMOTORS" or int(row["count"]) <= 0:
            continue
        chosen.append(row["symbol"])
    return tuple(chosen)


def _cell(results: dict, mode: str, variant: str, bps: int) -> dict:
    return results[(mode, variant, bps)]


def _write_report(path: Path, meta: dict, results: dict, audit: dict, verdict: dict) -> None:
    lines = [
        "# Oversold rebound",
        "",
        verdict["verdict"],
        "",
        *[f"- {reason}" for reason in verdict["reasons"]],
        "",
        "## Data",
        "",
        f"- 5-minute snapshot `{meta['snapshot_5m']}` sha `{meta['sha256_5m']}`",
        f"- Daily snapshot `{meta['snapshot_1d']}` sha `{meta['sha256_1d']}`",
        f"- First bar `{meta['first_bar']}`",
        f"- Last bar `{meta['last_bar']}`",
        f"- Symbols {meta['symbol_count']} (TATAMOTORS skipped, count 0)",
        f"- Missing 5-minute steps counted and not filled: {meta['missing_5m']}",
        "",
        "## Full strategy",
        "",
        "| Mode | bps | Trades | Win rate | Expectancy | Gross | Cost | Net | Max DD | Sharpe | Sortino | PF |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in MODES:
        for bps in COST_BPS:
            row = _cell(results, mode, "full", int(bps))
            lines.append(
                "| {mode} | {bps} | {trades} | {win} | {exp} | {gross} | {cost} | {net} | {dd} | {sharpe} | {sortino} | {pf} |".format(
                    mode=mode,
                    bps=int(bps),
                    trades=row.get("trades", 0),
                    win=_pct(row.get("win_rate")),
                    exp=row.get("expectancy"),
                    gross=row.get("gross_pnl"),
                    cost=row.get("transaction_cost"),
                    net=row.get("net_pnl"),
                    dd=row.get("max_drawdown"),
                    sharpe=_num(row.get("sharpe")),
                    sortino=_num(row.get("sortino")),
                    pf=_num(row.get("profit_factor")),
                )
            )
    lines.extend(["", "## Validation window at 2 bp", "", "| Mode | Variant | Trades | Net | Expectancy |", "| --- | --- | ---: | ---: | ---: |"])
    for mode in MODES:
        for variant in VARIANTS:
            split = _cell(results, mode, variant, 2)["splits"]["h2_2025"]
            lines.append(f"| {mode} | {variant} | {split.get('trades', 0)} | {split.get('net_pnl')} | {split.get('expectancy')} |")
    lines.extend(["", "## Splits of the full rule at 2 bp", "", "| Mode | Split | Trades | Net |", "| --- | --- | ---: | ---: |"])
    for mode in MODES:
        for name, split in _cell(results, mode, "full", 2)["splits"].items():
            lines.append(f"| {mode} | {name} | {split.get('trades', 0)} | {split.get('net_pnl')} |")
    lines.extend(["", "Sharpe and Sortino use weekday daily net P&L, with empty weekdays inside the span counted as zero, scaled by sqrt(252).", ""])
    lines.extend(["## Full rule at 5 bp by split", "", "| Mode | Split | Trades | Net |", "| --- | --- | ---: | ---: |"])
    for mode in MODES:
        for name, split in _cell(results, mode, "full", 5)["splits"].items():
            lines.append(f"| {mode} | {name} | {split.get('trades', 0)} | {split.get('net_pnl')} |")
    lines.extend(["", "## Buckets of the full rule at 2 bp", ""])
    for mode in MODES:
        lines.append(f"### {mode}")
        lines.append("")
        buckets = _cell(results, mode, "full", 2).get("buckets", {})
        for kind, groups in buckets.items():
            lines.append(f"{kind}:")
            lines.append("")
            for label, row in groups.items():
                lines.append(f"- {label}: trades {row.get('trades', 0)}, net {row.get('net_pnl')}, expectancy {row.get('expectancy')}")
            lines.append("")
    lines.extend(["## Stocks at 2 bp", ""])
    for mode in MODES:
        stocks = _cell(results, mode, "full", 2).get("per_stock", [])
        leaders = ", ".join(f"{row['symbol']} {row['net_pnl']}" for row in stocks[:3])
        laggards = ", ".join(f"{row['symbol']} {row['net_pnl']}" for row in stocks[-3:])
        lines.append(f"- {mode} leaders: {leaders}")
        lines.append(f"- {mode} laggards: {laggards}")
    lines.extend(["", "## Look-ahead", "", f"Status: {audit['status']}", f"Unresolved exits: {audit['unresolved_count']}", ""])
    for check in audit["checks"]:
        lines.append(f"- {check['status']}: {check['item']}")
    lines.extend(["", "## Reproduce", "", "```", "python scripts/backtest_rebound.py", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def main() -> None:
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(0))
    by_symbol: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_symbol[bar.symbol].append(bar)
    raw: list[dict] = []
    first = None
    last = None
    missing = 0
    sha_5m = ""
    for index, symbol in enumerate(chosen, start=1):
        bars, gaps, digest = stream_candles(SNAPSHOT_5M, (symbol,), START, END, warmup=timedelta(0))
        sha_5m = digest
        missing += gaps
        if bars:
            first = bars[0].end if first is None or bars[0].end < first else first
            last = bars[-1].end if last is None or bars[-1].end > last else last
        raw.extend(simulate_symbol(symbol, bars, by_symbol.get(symbol, [])))
        print(f"{index}/{len(chosen)} {symbol} bars={len(bars)} trades={sum(1 for trade in raw if trade['symbol'] == symbol)}", flush=True)
    audit = lookahead_audit(raw)
    results = {}
    full_rows = []
    variant_rows = []
    for bps in COST_BPS:
        priced = [price_trade(trade, bps) for trade in raw]
        for mode in MODES:
            for variant in VARIANTS:
                subset = [trade for trade in priced if trade["mode"] == mode and trade["variant"] == variant]
                results[(mode, variant, int(bps))] = enrich(
                    subset,
                    paths=variant == "full" and int(bps) in {0, 2, 5},
                    buckets=variant == "full",
                )
        if int(bps) == 2:
            variant_rows = [trade_record(trade) for trade in priced if trade["variant"] != "full"]
        full_rows.extend(trade_record(trade) for trade in priced if trade["variant"] == "full")
    verdict = classify(results, audit)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for row in full_rows:
            handle.write(json.dumps(row) + "\n")
    with (OUT / "trades_variants_2bp.jsonl").open("w", encoding="utf-8") as handle:
        for row in variant_rows:
            handle.write(json.dumps(row) + "\n")
    serial = {
        f"{mode}|{variant}|{bps}": summary
        for (mode, variant, bps), summary in results.items()
    }
    meta = {
        "snapshot_5m": SNAPSHOT_5M,
        "snapshot_1d": SNAPSHOT_1D,
        "sha256_5m": sha_5m,
        "sha256_1d": sha_1d,
        "first_bar": first.isoformat() if first else None,
        "last_bar": last.isoformat() if last else None,
        "symbol_count": len(chosen),
        "missing_5m": missing,
        "per_trade_cap": "20000",
        "slippage_bps": 0,
        "holdout_opened": False,
    }
    (OUT / "summary.json").write_text(json.dumps({"meta": meta, "verdict": verdict, "results": serial}, indent=2), encoding="utf-8")
    (OUT / "lookahead.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    _write_report(OUT / "report.md", meta, results, audit, verdict)
    print(verdict["verdict"], audit["status"], flush=True)


if __name__ == "__main__":
    main()
