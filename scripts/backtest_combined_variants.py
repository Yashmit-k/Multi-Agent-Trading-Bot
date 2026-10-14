"""Compare one-change books, then run the kept rules together.

Does not open the holdout, does not place orders, and does not change paper execution.
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
from quant_agents.research.combined_three import BookConfig, choose, measure, merge_books, passes, simulate_symbol

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "combined_three" / "variants"

WIDE = [
    BookConfig(name="wide_cap_3", wide_gain_max=Decimal("3")),
    BookConfig(name="wide_cap_2", wide_gain_max=Decimal("2")),
    BookConfig(name="wide_no_retrace", wide_retrace=False),
]
NARROW = [
    BookConfig(name="narrow_gain", narrow_gain_min=Decimal("0.60")),
    BookConfig(name="narrow_volume", narrow_volume_multiple=Decimal("1.5")),
    BookConfig(name="narrow_ema", ema_band=Decimal("2")),
    BookConfig(name="narrow_high", high_distance=Decimal("3")),
]
DIP = [
    BookConfig(name="dip_cost_guard", dip_cost_guard=True),
    BookConfig(name="dip_four_down", dip_down_days=4),
    BookConfig(
        name="dip_tight_band",
        dip_band_low=Decimal("-10"),
        dip_band_high=Decimal("-6"),
        dip_deeper_low=Decimal("-10"),
        dip_deeper_high=Decimal("-8"),
    ),
    BookConfig(name="dip_no_second", dip_second=False),
]


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


def run_book(config: BookConfig, symbols: tuple[str, ...], by_intraday: dict, by_daily: dict) -> tuple[dict, list[dict]]:
    closed: list[dict] = []
    marks: list[dict] = []
    rejected: list[dict] = []
    paths: list[list[dict]] = []
    for symbol in symbols:
        path: list[dict] = []
        symbol_closed, symbol_marks = simulate_symbol(
            symbol,
            by_intraday.get(symbol, []),
            by_daily.get(symbol, []),
            config,
            rejected,
            path,
        )
        closed.extend(symbol_closed)
        marks.extend(symbol_marks)
        paths.append(path)
    return measure(closed, marks, paths), rejected


def _row(name: str, metrics: dict, kept: str) -> str:
    return (
        f"| {name} | {_money(metrics['total_net'])} | {_money(metrics['realized_net'])} | "
        f"{_money(metrics['unrealized_net'])} | {_money(metrics['max_drawdown'])} | "
        f"{_money(metrics['average_open_notional'])} | {_money(metrics['ending_open_notional'])} | "
        f"{metrics['open_positions']} | {kept} |"
    )


def _write(path: Path, baseline: dict, groups: dict, kept: dict, combined: dict, slipped: dict, gate: bool) -> None:
    lines = [
        "# Algo variant comparison",
        "",
        "Each row changes one rule. A variant is kept only when total net is higher, average open notional is not higher, and maximum drawdown is not worse. Ending open notional and the open-position count are shown and do not decide the keep.",
        "",
        "Return figures are rupees after charges. They are not a portfolio growth rate, and they are not evidence that a rule is profitable.",
        "",
        "| Book | Total net | Realized | Unrealized | Max drawdown | Average open notional | Ending open notional | Open positions | Kept |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        _row("baseline", baseline, "baseline"),
    ]
    for algo, rows in groups.items():
        for name, metrics, keep in rows:
            lines.append(_row(name, metrics, "yes" if keep else "no"))
    lines.extend(
        [
            "",
            "## Kept for the combined book",
            "",
            f"- Wide: {kept['wide']}",
            f"- Narrow: {kept['narrow']}",
            f"- Dip: {kept['dip']}",
            "",
            "## Combined book",
            "",
            _row("combined", combined, "shared cap"),
            _row("combined with 5 bps slippage", slipped, "slippage"),
            "",
            f"Paper-trading gate, total net after charges and 5 bps slippage: {'positive' if gate else 'not positive'}.",
            "",
            "Signals that do not fit under ₹40,000 are filled Wide, then Narrow, then Dip tranche 1, then Dip tranche 2. The rest are rejected and not carried forward.",
            "",
        ]
    )
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
    baseline_config = BookConfig()
    baseline, _rejected = run_book(baseline_config, chosen, by_intraday, by_daily)
    print("baseline", baseline["total_net"], flush=True)
    groups: dict[str, list] = {}
    chosen_books = []
    for algo, variants in (("wide", WIDE), ("narrow", NARROW), ("dip", DIP)):
        measured = []
        rows = []
        for config in variants:
            metrics, _rejected = run_book(config, chosen, by_intraday, by_daily)
            keep = passes(metrics, baseline)
            measured.append((config, metrics))
            rows.append((config.name, metrics, keep))
            print(algo, config.name, "keep" if keep else "drop", metrics["total_net"], flush=True)
        winner = choose(baseline, measured)
        chosen_books.append(winner)
        groups[algo] = rows
        print("kept", algo, winner.name, flush=True)
    combined_config = merge_books(chosen_books, "combined")
    combined, rejected = run_book(combined_config, chosen, by_intraday, by_daily)
    slipped_config = merge_books(chosen_books, "combined_slippage", Decimal("5"))
    slipped, _slipped_rejected = run_book(slipped_config, chosen, by_intraday, by_daily)
    gate = Decimal(str(slipped["total_net"])) > 0
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline": baseline,
        "groups": {algo: [{"name": name, "kept": keep, "metrics": metrics} for name, metrics, keep in rows] for algo, rows in groups.items()},
        "kept": {"wide": chosen_books[0].name, "narrow": chosen_books[1].name, "dip": chosen_books[2].name},
        "combined": combined,
        "combined_slippage": slipped,
        "paper_gate_positive": gate,
        "rejected_signals": len(rejected),
    }
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (OUT / "rejected_signals.jsonl").open("w", encoding="utf-8") as handle:
        for row in rejected:
            handle.write(json.dumps(row, default=str) + "\n")
    _write(
        OUT / "report.md",
        baseline,
        groups,
        payload["kept"],
        combined,
        slipped,
        gate,
    )
    print("gate", "positive" if gate else "not positive", slipped["total_net"], flush=True)


if __name__ == "__main__":
    main()
