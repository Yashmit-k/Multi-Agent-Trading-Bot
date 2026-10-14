"""One change on the frozen combined book: Narrow minimum day gain +0.60%.

Stops if the frozen book does not reproduce. Does not open the holdout, place
orders, or change paper execution.
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
from quant_agents.research.combined_three import BookConfig, measure, passes, simulate_symbol

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
SLIPPAGE = Decimal("5")
EXPECTED_TOTAL = Decimal("126128.22")
OUT = ROOT / "datasets" / "research" / "combined_three"
CENT = Decimal("0.01")
SLOTS = (("wide", 1), ("narrow", 1), ("dip", 1), ("dip", 2))


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    return tuple(row["symbol"] for row in manifest["symbols"] if row["symbol"] != "TATAMOTORS" and int(row["count"]) > 0)


def _money(value: object) -> str:
    return format(Decimal(str(value)).quantize(CENT), "f")


def _frozen(name: str, **changes: object) -> BookConfig:
    return BookConfig(name=name, slippage_bps=SLIPPAGE, wide_retrace=False, ema_band=Decimal("2"), **changes)


def run_book(config: BookConfig, symbols, by_intraday, by_daily) -> dict:
    closed: list[dict] = []
    marks: list[dict] = []
    rejected: list[dict] = []
    paths: list[list[dict]] = []
    for symbol in symbols:
        path: list[dict] = []
        symbol_closed, symbol_marks = simulate_symbol(
            symbol, by_intraday.get(symbol, []), by_daily.get(symbol, []), config, rejected, path
        )
        closed.extend(symbol_closed)
        marks.extend(symbol_marks)
        paths.append(path)
    accepted: dict[tuple[str, int], int] = defaultdict(int)
    seen: set[tuple] = set()
    for row in closed + marks:
        key = (row["symbol"], row["algo"], row["tranche"], str(row["entry_time"]))
        if key not in seen:
            seen.add(key)
            accepted[(row["algo"], row["tranche"])] += 1
    refused: dict[tuple[str, int], int] = defaultdict(int)
    for row in rejected:
        refused[(row["algo"], row["tranche"])] += 1
    return {"metrics": measure(closed, marks, paths), "accepted": accepted, "rejected": refused}


def _row(name: str, metrics: dict, kept: str) -> str:
    return (
        f"| {name} | {_money(metrics['total_net'])} | {_money(metrics['realized_net'])} | {_money(metrics['unrealized_net'])} | "
        f"{_money(metrics['max_drawdown'])} | {_money(metrics['average_open_notional'])} | {_money(metrics['ending_open_notional'])} | "
        f"{metrics['open_positions']} | {kept} |"
    )


def _signals(name: str, run: dict) -> str:
    accepted = " | ".join(str(run["accepted"].get(slot, 0)) for slot in SLOTS)
    rejected = " | ".join(str(run["rejected"].get(slot, 0)) for slot in SLOTS)
    return f"| {name} | {accepted} | {rejected} |"


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
    OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / "narrow_gain_060.md"

    base = run_book(_frozen("combined"), chosen, by_intraday, by_daily)
    reproduced = Decimal(base["metrics"]["total_net"]).quantize(CENT)
    print("baseline", reproduced, flush=True)
    if reproduced != EXPECTED_TOTAL:
        report.write_text(
            f"# Narrow minimum day gain stopped\n\nThe frozen book returned {reproduced}, not {EXPECTED_TOTAL}. The variant was not run.\n",
            encoding="utf-8",
        )
        raise SystemExit(f"baseline drifted: {reproduced}")

    variant = run_book(_frozen("narrow_gain_060", narrow_gain_min=Decimal("0.60")), chosen, by_intraday, by_daily)
    keep = passes(variant["metrics"], base["metrics"])
    print("narrow_gain_060", variant["metrics"]["total_net"], "keep" if keep else "drop", flush=True)

    b, v = base["metrics"], variant["metrics"]
    checks = [
        ("Total net higher", Decimal(v["total_net"]) > Decimal(b["total_net"])),
        ("Average open notional not higher", Decimal(v["average_open_notional"]) <= Decimal(b["average_open_notional"])),
        ("Maximum drawdown not worse", Decimal(v["max_drawdown"]) <= Decimal(b["max_drawdown"])),
    ]
    lines = [
        "# Narrow minimum day gain +0.60%",
        "",
        "One change on the frozen combined book: Narrow enters only at a day gain of +0.60% to +0.75%, still within ±2% of the prior EMA20. Wide stays without the pullback exit and Dip stays at baseline. Both runs use 5 bps slippage, the Zerodha charge table, ₹20,000 per order, ₹40,000 open notional per symbol, and fill priority Wide, Narrow, Dip tranche 1, Dip tranche 2. Window 2024-01-01 through 2026-10-05 on `nifty50_5m_20261005` and `nifty50_1d_20261005`, TATAMOTORS excluded. The holdout was not opened.",
        "",
        f"Baseline reproduction: {reproduced}, expected {EXPECTED_TOTAL}. Reproduced.",
        "",
        "This change was suggested by the earlier variant study and the loss review on this same sample. A pass here is not out-of-sample evidence.",
        "",
        "| Book | Total net | Realized | Unrealized | Max drawdown | Average open notional | Ending open notional | Open positions | Kept |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        _row("frozen combined", b, "baseline"),
        _row("narrow +0.60% minimum", v, "yes" if keep else "no"),
        "",
        "| Check | Result |",
        "| --- | --- |",
        *[f"| {label} | {'yes' if ok else 'no'} |" for label, ok in checks],
        "",
        "## Signals",
        "",
        "Accepted counts are lots bought. Rejected counts are signals refused by the ₹40,000 symbol cap and not carried forward.",
        "",
        "| Book | Accepted wide | Accepted narrow | Accepted dip 1 | Accepted dip 2 | Rejected wide | Rejected narrow | Rejected dip 1 | Rejected dip 2 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        _signals("frozen combined", base),
        _signals("narrow +0.60% minimum", variant),
        "",
        "## Result",
        "",
        "The variant passes the keep rule." if keep else "The variant fails the keep rule. The frozen combined book stays the configuration.",
        "",
        "Research only. Nothing here changes paper execution or places an order.",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    payload = {
        "reproduced": str(reproduced),
        "baseline": b,
        "variant": v,
        "kept": keep,
        "signals": {
            name: {kind: {f"{a}:{t}": run[kind].get((a, t), 0) for a, t in SLOTS} for kind in ("accepted", "rejected")}
            for name, run in (("baseline", base), ("variant", variant))
        },
    }
    (OUT / "narrow_gain_060.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
