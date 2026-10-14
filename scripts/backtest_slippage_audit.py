"""Compare the baseline and the frozen combined book at 5 bps slippage.

Uses the same snapshots, window, charges, caps, and slipped_price path as the
variant study. Does not open the holdout, place orders, or change paper execution.
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

from contracts.enums import Side
from core_market_data.replay import stream_candles
from core_paper.costs import slipped_price
from quant_agents.research.combined_three import (
    FILL_RANK,
    ORDER_CAP,
    SYMBOL_CAP,
    BookConfig,
    _round_trip,
    measure,
    merge_books,
    simulate_symbol,
)
from quant_agents.research.rebound import session_date

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


def run_book(config: BookConfig, symbols: tuple[str, ...], by_intraday: dict, by_daily: dict):
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
    return measure(closed, marks, paths), closed, marks, rejected


def _lot_key(row: dict) -> tuple:
    return (row["symbol"], row["algo"], row["tranche"], str(row["entry_time"]))


def _signal_counts(closed: list[dict], marks: list[dict], rejected: list[dict]) -> dict:
    accepted: dict[tuple, int] = defaultdict(int)
    seen: set[tuple] = set()
    for row in closed + marks:
        key = _lot_key(row)
        if key in seen:
            continue
        seen.add(key)
        accepted[(row["algo"], row["tranche"])] += 1
    rejected_counts: dict[tuple, int] = defaultdict(int)
    reasons: set[str] = set()
    for row in rejected:
        rejected_counts[(row["algo"], row["tranche"])] += 1
        reasons.add(row["reason"])
    return {
        "accepted": {f"{algo}:{tranche}": count for (algo, tranche), count in sorted(accepted.items())},
        "rejected": {f"{algo}:{tranche}": count for (algo, tranche), count in sorted(rejected_counts.items())},
        "accepted_total": sum(accepted.values()),
        "rejected_total": sum(rejected_counts.values()),
        "rejection_reasons": sorted(reasons),
        "fill_rank": FILL_RANK,
    }


def _dip_audit(closed: list[dict], marks: list[dict]) -> dict:
    charge_mismatches = 0
    net_mismatches = 0
    tranche1_exact = 0
    tranche1_gap = 0
    tranche1_below = 0
    closed_losers: dict[str, int] = defaultdict(int)
    closed_loser_net = Decimal("0")
    reasons: dict[str, int] = defaultdict(int)
    dip_closed = [row for row in closed if row["algo"] == "dip"]
    for row in dip_closed:
        reasons[f"{row['tranche']}:{row['exit_reason']}"] += 1
        expected_net, expected_charges = _round_trip(
            row["entry_price"],
            row["exit_price"],
            row["quantity"],
            row["same_session"],
        )
        if expected_charges != row["charges"] or expected_charges <= 0:
            charge_mismatches += 1
        if expected_net != row["net_pnl"]:
            net_mismatches += 1
        if row["net_pnl"] <= 0:
            label = f"tranche_{row['tranche']}:{row['exit_reason']}"
            closed_losers[label] += 1
            closed_loser_net += row["net_pnl"]
        if row["tranche"] == 1 and row["exit_reason"] == "target_2pct":
            target = row["entry_price"] * Decimal("1.02")
            slipped_target = slipped_price(Side.SELL, target, SLIPPAGE)
            if row["exit_price"] == slipped_target:
                tranche1_exact += 1
            elif row["exit_price"] > slipped_target:
                tranche1_gap += 1
            else:
                tranche1_below += 1
    open_mismatches = 0
    open_losers = 0
    open_loser_net = Decimal("0")
    dip_open = [row for row in marks if row["algo"] == "dip"]
    for row in dip_open:
        sold = slipped_price(Side.SELL, row["mark_price"], SLIPPAGE)
        same_session = session_date(row["mark_time"]) == session_date(row["entry_time"])
        expected_net, expected_charges = _round_trip(row["entry_price"], sold, row["quantity"], same_session)
        if expected_net != row["unrealized_net"] or expected_charges != row["charges"]:
            open_mismatches += 1
        if row["unrealized_net"] < 0:
            open_losers += 1
            open_loser_net += row["unrealized_net"]
    return {
        "closed_slices": len(dip_closed),
        "exit_reasons": dict(sorted(reasons.items())),
        "charge_or_net_mismatches": charge_mismatches + net_mismatches,
        "tranche1_sold_at_slipped_target": tranche1_exact,
        "tranche1_gapped_through_target": tranche1_gap,
        "tranche1_below_slipped_target": tranche1_below,
        "closed_losers": dict(sorted(closed_losers.items())),
        "closed_loser_net": format(closed_loser_net, "f"),
        "open_positions": len(dip_open),
        "open_mark_mismatches": open_mismatches,
        "open_losers": open_losers,
        "open_loser_net": format(open_loser_net, "f"),
        "cost_guard": False,
    }


def _outperforms(combined: dict, baseline: dict) -> dict:
    total = Decimal(str(combined["total_net"])) > Decimal(str(baseline["total_net"]))
    capital = Decimal(str(combined["average_open_notional"])) <= Decimal(str(baseline["average_open_notional"]))
    drawdown = Decimal(str(combined["max_drawdown"])) <= Decimal(str(baseline["max_drawdown"]))
    return {
        "higher_total_net": total,
        "average_open_notional_not_higher": capital,
        "drawdown_not_worse": drawdown,
        "passes_keep_rule": total and capital and drawdown,
    }


def _row(name: str, metrics: dict) -> str:
    return (
        f"| {name} | {_money(metrics['total_net'])} | {_money(metrics['realized_net'])} | "
        f"{_money(metrics['unrealized_net'])} | {_money(metrics['max_drawdown'])} | "
        f"{_money(metrics['average_open_notional'])} | {_money(metrics['ending_open_notional'])} | "
        f"{metrics['open_positions']} |"
    )


def _delta(combined: dict, baseline: dict, key: str) -> str:
    value = Decimal(str(combined[key])) - Decimal(str(baseline[key]))
    return format(value.quantize(Decimal("0.01")), "f")


def _write(path: Path, baseline: dict, combined: dict, verdict: dict, baseline_signals: dict, combined_signals: dict, baseline_dip: dict, combined_dip: dict) -> None:
    lines = [
        "# Slippage baseline and combined book",
        "",
        "Both books use 5 bps slippage on every fill through `slipped_price`, the Zerodha charge table, ₹20,000 per order, and ₹40,000 open notional per symbol. The window is 2024-01-01 through 2026-10-05 on `nifty50_5m_20261005` and `nifty50_1d_20261005`, excluding TATAMOTORS. The holdout was not opened.",
        "",
        "The combined book keeps the frozen rules: Wide without the pullback exit, Narrow with the EMA band at ±2%, and baseline Dip. Baseline Dip does not use the cost guard, so tranche 2 still sells at EMA +3% when that sale loses money after charges.",
        "",
        "| Book | Total net | Realized | Unrealized | Max drawdown | Average open notional | Ending open notional | Open positions |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        _row("baseline, 5 bps", baseline),
        _row("combined, 5 bps", combined),
        (
            f"| combined minus baseline | {_delta(combined, baseline, 'total_net')} | {_delta(combined, baseline, 'realized_net')} | "
            f"{_delta(combined, baseline, 'unrealized_net')} | {_delta(combined, baseline, 'max_drawdown')} | "
            f"{_delta(combined, baseline, 'average_open_notional')} | {_delta(combined, baseline, 'ending_open_notional')} | "
            f"{int(combined['open_positions']) - int(baseline['open_positions'])} |"
        ),
        "",
        "## Verdict",
        "",
        f"Combined total net is {'higher' if verdict['higher_total_net'] else 'not higher'} than the baseline under the same 5 bps slippage.",
        f"Average open notional is {'not higher' if verdict['average_open_notional_not_higher'] else 'higher'}. Maximum drawdown is {'not worse' if verdict['drawdown_not_worse'] else 'worse'}.",
        f"The three-part keep rule is {'met' if verdict['passes_keep_rule'] else 'not met'}.",
        "",
        "## Dip exit audit",
        "",
        "Every dip sale and every open dip mark was recomputed from the stored prices. A closed net equals the slipped exit minus the slipped entry, times quantity, minus the delivery or intraday charges. An open mark uses the same charges on a sell of the snapshot close after 5 bps. Tranche 1 sells its remaining quantity when price reaches 2% above the slipped entry. There is no stop. A dip lot that has not reached its target stays open, including when the mark is a loss.",
        "",
        "| Check | Baseline | Combined |",
        "| --- | ---: | ---: |",
        f"| Closed dip slices | {baseline_dip['closed_slices']} | {combined_dip['closed_slices']} |",
        f"| Charge or net mismatches | {baseline_dip['charge_or_net_mismatches']} | {combined_dip['charge_or_net_mismatches']} |",
        f"| Tranche 1 sold at the slipped +2% target | {baseline_dip['tranche1_sold_at_slipped_target']} | {combined_dip['tranche1_sold_at_slipped_target']} |",
        f"| Tranche 1 gapped through that target | {baseline_dip['tranche1_gapped_through_target']} | {combined_dip['tranche1_gapped_through_target']} |",
        f"| Tranche 1 filled below the slipped target | {baseline_dip['tranche1_below_slipped_target']} | {combined_dip['tranche1_below_slipped_target']} |",
        f"| Open dip marks | {baseline_dip['open_positions']} | {combined_dip['open_positions']} |",
        f"| Open-mark mismatches | {baseline_dip['open_mark_mismatches']} | {combined_dip['open_mark_mismatches']} |",
        f"| Open dip lots with a negative mark | {baseline_dip['open_losers']} | {combined_dip['open_losers']} |",
        f"| Net of those open losses | {_money(baseline_dip['open_loser_net'])} | {_money(combined_dip['open_loser_net'])} |",
        f"| Closed dip slices with net at or below zero | {sum(baseline_dip['closed_losers'].values())} | {sum(combined_dip['closed_losers'].values())} |",
        f"| Net of those closed losses | {_money(baseline_dip['closed_loser_net'])} | {_money(combined_dip['closed_loser_net'])} |",
        "",
        f"Baseline closed-loss reasons: {baseline_dip['closed_losers'] or 'none'}.",
        f"Combined closed-loss reasons: {combined_dip['closed_losers'] or 'none'}.",
        "",
        "## Shared-stock priority",
        "",
        "Ready signals on one symbol are attempted Wide, then Narrow, then Dip tranche 1, then Dip tranche 2. A signal that cannot buy one share is logged as `symbol_cap` and is not carried to a later bar.",
        "",
        "| Book | Accepted wide | Accepted narrow | Accepted dip 1 | Accepted dip 2 | Rejected wide | Rejected narrow | Rejected dip 1 | Rejected dip 2 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, signals in (("baseline, 5 bps", baseline_signals), ("combined, 5 bps", combined_signals)):
        accepted = signals["accepted"]
        rejected = signals["rejected"]
        lines.append(
            f"| {name} | {accepted.get('wide:1', 0)} | {accepted.get('narrow:1', 0)} | {accepted.get('dip:1', 0)} | {accepted.get('dip:2', 0)} | "
            f"{rejected.get('wide:1', 0)} | {rejected.get('narrow:1', 0)} | {rejected.get('dip:1', 0)} | {rejected.get('dip:2', 0)} |"
        )
    lines.extend(
        [
            "",
            f"Order cap {ORDER_CAP}, symbol cap {SYMBOL_CAP}. Rejection reasons on the baseline: {baseline_signals['rejection_reasons'] or 'none'}. Rejection reasons on the combined book: {combined_signals['rejection_reasons'] or 'none'}.",
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
    baseline_config = BookConfig(name="baseline_slippage", slippage_bps=SLIPPAGE)
    baseline, baseline_closed, baseline_marks, baseline_rejected = run_book(baseline_config, chosen, by_intraday, by_daily)
    print("baseline", baseline["total_net"], flush=True)
    frozen = [
        BookConfig(name="wide_no_retrace", wide_retrace=False),
        BookConfig(name="narrow_ema", ema_band=Decimal("2")),
        BookConfig(name="baseline"),
    ]
    combined_config = merge_books(frozen, "combined_slippage", SLIPPAGE)
    combined, combined_closed, combined_marks, combined_rejected = run_book(combined_config, chosen, by_intraday, by_daily)
    print("combined", combined["total_net"], flush=True)
    verdict = _outperforms(combined, baseline)
    baseline_signals = _signal_counts(baseline_closed, baseline_marks, baseline_rejected)
    combined_signals = _signal_counts(combined_closed, combined_marks, combined_rejected)
    baseline_dip = _dip_audit(baseline_closed, baseline_marks)
    combined_dip = _dip_audit(combined_closed, combined_marks)
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "slippage_bps": "5",
        "snapshots": {"5m": SNAPSHOT_5M, "1d": SNAPSHOT_1D},
        "window": {"start": START.isoformat(), "end": END.isoformat()},
        "excluded": ["TATAMOTORS"],
        "frozen_rules": {"wide": "wide_no_retrace", "narrow": "narrow_ema", "dip": "baseline"},
        "baseline": baseline,
        "combined": combined,
        "verdict": verdict,
        "signals": {"baseline": baseline_signals, "combined": combined_signals},
        "dip_audit": {"baseline": baseline_dip, "combined": combined_dip},
    }
    (OUT / "slippage_audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write(OUT / "slippage_audit.md", baseline, combined, verdict, baseline_signals, combined_signals, baseline_dip, combined_dip)
    print("verdict", verdict, flush=True)


if __name__ == "__main__":
    main()
