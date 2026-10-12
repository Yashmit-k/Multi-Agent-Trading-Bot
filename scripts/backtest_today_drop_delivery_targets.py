"""Delivery-only today-drop book with 2% and 5% targets and a daily ledger.

Does not open the holdout, does not place orders, and does not rewrite earlier research.
"""

from __future__ import annotations

import csv
import json
import sys
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

from core_market_data.replay import SnapshotRefused, stream_candles
from quant_agents.research.today_drop_delivery_targets import simulate_portfolio, summarize

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "today_drop_delivery_targets"


def symbols_from_manifest() -> tuple[str, ...]:
    path = ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json"
    daily = ROOT / "snapshots 2" / "nifty50" / "1D" / "manifest.json"
    if not path.is_file() or not daily.is_file():
        raise SystemExit("missing snapshots 2/nifty50 manifest; not substituting another dataset")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("snapshot_id") != SNAPSHOT_5M:
        raise SystemExit(f"5m manifest snapshot_id is {manifest.get('snapshot_id')}")
    chosen = []
    for row in manifest["symbols"]:
        if row["symbol"] == "TATAMOTORS" or int(row["count"]) <= 0:
            continue
        chosen.append(row["symbol"])
    return tuple(chosen)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")


def _day_public(day: dict) -> dict:
    hidden = {"entries", "exits", "rejected", "holdings", "loss_inventory"}
    return {key: value for key, value in day.items() if key not in hidden}


def _write_csv(path: Path, days: list[dict]) -> None:
    rows = []
    for day in days:
        public = _day_public(day)
        if not day["holdings"]:
            rows.append({**public, "symbol": "", "status": "", "unrealized_net_pnl": day["unrealized_net_pnl"]})
            continue
        for holding in day["holdings"]:
            rows.append({**public, **{key: holding[key] for key in holding if key != "date"}})
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _cost_breakdown(result: dict) -> dict:
    same = {"trades": 0, "brokerage": Decimal("0"), "stt": Decimal("0"), "other": Decimal("0")}
    overnight = {"trades": 0, "brokerage": Decimal("0"), "stt": Decimal("0"), "dp": Decimal("0"), "other": Decimal("0")}
    for trade in result["closed"]:
        charges = trade["exit_charges"]
        bucket = same if trade["holding"] == "same_session" else overnight
        bucket["trades"] += 1
        bucket["brokerage"] += Decimal(charges["brokerage"])
        bucket["stt"] += Decimal(charges["stt"])
        if "dp" in bucket:
            bucket["dp"] += Decimal(charges["dp"])
        bucket["other"] += Decimal(charges["transaction"]) + Decimal(charges["sebi"]) + Decimal(charges["gst"]) + Decimal(charges["stamp"])
    def dump(bucket: dict) -> dict:
        return {key: (value if isinstance(value, int) else format(value, "f")) for key, value in bucket.items()}
    return {
        "schedule_id": result["schedule_id"],
        "schedule_note": result["schedule_note"],
        "by_component": result["charges"],
        "same_session_exits": dump(same),
        "overnight_exits": dump(overnight),
        "entry_charges_are_reclassified_when_the_exit_is_the_same_session": True,
    }


def _report(path: Path, summary: dict, meta: dict) -> None:
    final_losses = summary["largest_unrealized_losses"]
    loss_lines = [f"- {row['symbol']}: {row['unrealized_net_pnl']} on cost {row['cost_basis']}" for row in final_losses[:10]] or ["- none"]
    lines = [
        "# Delivery today-drop targets",
        "",
        summary["classification"],
        "",
        summary["classification_note"],
        "",
        "Look-ahead audit: " + summary["audit"],
        "",
        "## Data",
        "",
        f"- 5-minute snapshot `{meta['snapshot_5m']}` sha `{meta['sha256_5m']}`",
        f"- Daily snapshot `{meta['snapshot_1d']}` sha `{meta['sha256_1d']}`",
        f"- Symbols {meta['symbol_count']} (TATAMOTORS skipped when count is 0)",
        f"- Missing 5-minute steps counted and not filled: {meta['missing_5m']}",
        f"- Window {meta['start']} through {meta['end']}",
        f"- Schedule `{summary['schedule_id']}`. {summary['schedule_note']}",
        "- Same-session round trips use the intraday table, including brokerage. Overnight sales use delivery, brokerage 0, plus the DP charge.",
        "- Slippage on the primary run is 0 bps. A 5 bp adverse run and a zero-brokerage run are sensitivities. Statutory charges stay in the zero-brokerage run.",
        "- The entry bar cannot exit. A later bar that opens through the target fills at the open. Otherwise a high at the target fills at the target.",
        "- 2026 is a partial year through 2026-10-05.",
        "",
        "## Answers",
        "",
        f"1. Starting capital: {summary['starting_cash']}",
        f"2. Peak capital deployed, at cost: {summary['peak_capital_deployed']}",
        f"3. Ending cash: {summary['ending_cash']}",
        f"4. Ending market value of open holdings: {summary['ending_market_value']}",
        f"5. Realized net P&L: {summary['realized_net_pnl']}",
        f"6. Unrealized net P&L, after estimated delivery-exit charges: {summary['unrealized_net_pnl']}",
        f"7. Holdings in loss at the end: {summary['ending_loss_count']}",
        "8. Largest unrealized net losses:",
        *loss_lines,
        f"9. Capital tied up in loss-making positions: {summary['ending_capital_in_loss']}",
        f"10. Positions that never reached the target: {summary['unresolved']}",
        f"11. Realized net is {summary['realized_net_pnl']} and unrealized net is {summary['unrealized_net_pnl']}. Realized divided by the sum of those two figures is {summary['realized_share_of_total_pnl']}. A value above 1 means the open book is a net loss and realized profit is larger than the combined result.",
        f"12. Primary result uses `{summary['schedule_id']}` with brokerage {'on' if summary['brokerage'] else 'off'} and slippage {summary['slippage_bps']} bp.",
        "13. Year equity change, from the daily mark-to-market path:",
    ]
    for year, row in summary["years"].items():
        if row["days"] == 0:
            lines.append(f"- {year}: no days")
            continue
        partial = " partial" if row["partial"] else ""
        lines.append(
            f"- {year}{partial}: equity {row['starting_equity']} to {row['ending_equity']} ({row['year_equity_change']}), "
            f"cumulative realized {row['realized_net_pnl']}, unrealized {row['unrealized_net_pnl']}"
        )
    lines.extend(
        [
            f"14. Maximum drawdown on daily portfolio equity, including open marks: {summary['max_drawdown']}",
            "15. The book is not economically robust. There is no stop, so losers stay open and the drawdown includes them. A positive ending equity would still not be a robust edge.",
            "",
            "## Closed trades",
            "",
            f"- Signals {summary['signals']}, entries {summary['entries']}, exits {summary['exits']}, unresolved {summary['unresolved']}, cash rejects and over-cap rejects {summary['rejected']}",
            f"- Win rate on closed trades only: {summary['win_rate_closed']}. Every exit is a profit target, so a closed trade cannot be a loss. Open losers are not in this win rate.",
            f"- Average closed net {summary['average_closed_net']}, median {summary['median_closed_net']}, profit factor {summary['profit_factor'] or 'undefined because no closed trade lost'}",
            f"- Realized gross {summary['realized_gross_pnl']}, realized net {summary['realized_net_pnl']}",
            f"- Average holding sessions {summary['average_holding_sessions']}, max {summary['max_holding_sessions']}",
            f"- Positions that lasted at least 1/5/10/20/60 sessions: {summary['open_after_sessions']}",
            f"- Ending equity {summary['ending_equity']}, total return percent {summary['total_return_pct']}",
            f"- Average capital deployed {summary['average_capital_deployed']}, average cash {summary['average_cash']}",
            f"- Days with a position {summary['days_with_positions_pct']} percent, days with a loser {summary['days_with_losses_pct']} percent",
            f"- Top 5 percent of closed trades as a share of net realized P&L: {summary['top_5pct_closed_share_of_net']}",
            "",
            "## Sensitivities",
            "",
            f"- 5 bp adverse slippage ending equity {meta['slippage_5bp']['ending_equity']}, realized net {meta['slippage_5bp']['realized_net_pnl']}, max drawdown {meta['slippage_5bp']['max_drawdown']}",
            f"- Zero brokerage, statutory charges kept, ending equity {meta['zero_brokerage']['ending_equity']}, realized net {meta['zero_brokerage']['realized_net_pnl']}",
            "",
            "Daily rows are in `daily_portfolio.csv`.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    symbols = symbols_from_manifest()
    try:
        daily, _, sha_1d = stream_candles(SNAPSHOT_1D, symbols, START, END, warmup=timedelta(0))
        bars, missing, sha_5m = stream_candles(SNAPSHOT_5M, symbols, START, END, warmup=timedelta(0))
    except SnapshotRefused as exc:
        raise SystemExit(str(exc)) from exc
    primary = simulate_portfolio(bars, daily)
    summary = summarize(primary)
    if summary["audit"] != "PASS":
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "lookahead.json").write_text(json.dumps(primary["audit"], indent=2), encoding="utf-8")
        (OUT / "report.md").write_text(
            "# Delivery today-drop targets\n\nLook-ahead audit failed. Results are not interpreted.\n\n"
            + "\n".join(f"- {item}" for item in primary["audit"]["failures"][:50])
            + "\n",
            encoding="utf-8",
        )
        raise SystemExit("look-ahead audit failed")
    slip = summarize(simulate_portfolio(bars, daily, slippage_bps=Decimal("5")))
    zero = summarize(simulate_portfolio(bars, daily, brokerage=False))
    meta = {
        "snapshot_5m": SNAPSHOT_5M,
        "snapshot_1d": SNAPSHOT_1D,
        "sha256_5m": sha_5m,
        "sha256_1d": sha_1d,
        "symbol_count": len(symbols),
        "missing_5m": missing,
        "start": START.isoformat(),
        "end": END.isoformat(),
        "slippage_5bp": slip,
        "zero_brokerage": zero,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps({**summary, "data": {key: meta[key] for key in meta if key not in {"slippage_5bp", "zero_brokerage"}}, "slippage_5bp": slip, "zero_brokerage": zero}, indent=2, default=str), encoding="utf-8")
    _write_jsonl(OUT / "daily_portfolio.jsonl", [_day_public(day) for day in primary["days"]])
    _write_jsonl(
        OUT / "daily_cash_ledger.jsonl",
        [
            {
                "date": day["date"],
                "opening_cash": day["opening_cash"],
                "closing_cash": day["closing_cash"],
                "buy_notional": day["buy_notional"],
                "sale_proceeds": day["sale_proceeds"],
                "charges": day["charges"],
                "cash_reconciled": day["cash_reconciled"],
            }
            for day in primary["days"]
        ],
    )
    _write_jsonl(OUT / "daily_holdings.jsonl", [row for day in primary["days"] for row in day["holdings"]])
    _write_jsonl(OUT / "daily_loss_inventory.jsonl", [row for day in primary["days"] for row in day["loss_inventory"]])
    _write_jsonl(OUT / "trades.jsonl", primary["events"])
    (OUT / "cost_breakdown.json").write_text(json.dumps(_cost_breakdown(primary), indent=2), encoding="utf-8")
    (OUT / "yearly_results.json").write_text(json.dumps(summary["years"], indent=2), encoding="utf-8")
    (OUT / "lookahead.json").write_text(json.dumps(primary["audit"], indent=2), encoding="utf-8")
    _write_csv(OUT / "daily_portfolio.csv", primary["days"])
    _report(OUT / "report.md", summary, meta)
    print(f"wrote {OUT}")
    print(summary["classification"], "equity", summary["ending_equity"], "audit", summary["audit"])


if __name__ == "__main__":
    main()
