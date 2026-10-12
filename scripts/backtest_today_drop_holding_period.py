"""Pre-registered fixed holding periods for the frozen today-drop entry.

Does not rewrite earlier research folders and does not choose a horizon.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

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
from quant_agents.research.rebound import enrich, price_trade, simulate_symbol
from quant_agents.research.today_drop_holding_period import (
    COST_BPS,
    HORIZONS,
    classify_holding,
    contribution,
    lookahead_audit,
    month_runs,
    return_distribution,
    session_date,
    simulate_fixed_hold,
    subsequent_sessions,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "today_drop_holding_period"
FROZEN = ROOT / "datasets" / "research" / "rebound_isolation" / "summary.json"


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    return tuple(row["symbol"] for row in manifest["symbols"] if row["symbol"] != "TATAMOTORS" and int(row["count"]) > 0)


def _plain(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _pct(value) -> str:
    if value is None:
        return ""
    return f"{Decimal(str(value)):.2f}%"


def _money(value) -> str:
    if value is None:
        return ""
    return f"{Decimal(str(value)):.2f}"


def _duration(trades: list[dict]) -> dict:
    closed = [trade for trade in trades if trade.get("exit_time") is not None and trade.get("entry_time") is not None and trade.get("net_pnl") is not None]
    if not closed:
        return {"average_calendar_days": None, "median_calendar_days": None}
    days = [Decimal(str((trade["exit_time"] - trade["entry_time"]).total_seconds() / 86400)) for trade in closed]
    return {"average_calendar_days": sum(days, Decimal("0")) / len(days), "median_calendar_days": Decimal(str(median(days)))}


def _answers(books: dict, verdict: dict) -> list[str]:
    positive_2 = [horizon for horizon in HORIZONS if Decimal(str(books[horizon][2]["net_pnl"])) > 0]
    positive_5 = [horizon for horizon in HORIZONS if Decimal(str(books[horizon][5]["net_pnl"])) > 0]
    survives = [horizon for horizon in positive_2 if horizon in positive_5]
    if survives:
        first = f"Yes for {survives} trading days: full-sample net P&L is positive at both 2 bp and 5 bp. A positive median alone is not treated as a tradable edge."
    else:
        first = "No pre-registered horizon has positive full-sample net P&L at both 2 bp and 5 bp."
    second = f"Positive full-sample net at 2 bp: {positive_2 or 'none'}."
    third = f"Positive full-sample net at 5 bp: {positive_5 or 'none'}."
    year_bits = []
    all_years = True
    for horizon in HORIZONS:
        signs = []
        for year in ("2024", "2025", "2026"):
            net = Decimal(str(books[horizon][2]["years"].get(year, {}).get("net_pnl", "0")))
            count = books[horizon][2]["years"].get(year, {}).get("trades", 0)
            signs.append(f"{year} {count} trades {_money(net)}")
            if net <= 0:
                all_years = False
        year_bits.append(f"{horizon}D: " + "; ".join(signs))
    fourth = ("Every horizon is positive in 2024, 2025, and partial 2026 at 2 bp. " if all_years else "No. At least one horizon is not positive in every year at 2 bp. ") + "2026 is a partial year, so its rupee total is not compared with a full year. " + " | ".join(year_bits)
    shares = []
    broad = True
    for horizon in HORIZONS:
        top1 = books[horizon][2].get("top1_share")
        shares.append(f"{horizon}D top1 {top1}")
        if top1 is None or Decimal(str(top1)) > Decimal("0.40"):
            broad = False
    fifth = ("The 2 bp result is not dominated by one stock. " if broad else "At least one horizon has a top stock above 40% of 2 bp net. ") + ", ".join(shares)
    tails = []
    tail_heavy = False
    for horizon in HORIZONS:
        share = books[horizon][2].get("top5pct_share")
        tails.append(f"{horizon}D {share}")
        if share is not None and Decimal(str(share)) > Decimal("0.50"):
            tail_heavy = True
    sixth = ("Yes. The best 5% of trades are more than half of 2 bp net on at least one horizon. " if tail_heavy else "No horizon has more than half of its 2 bp net in the best 5% of trades. ") + ", ".join(tails)
    seventh = "The bracket and the fixed holds are the same entry rule with different occupancy, so full-sample rupee P&L is not a verdict. Compare expectancy, drawdown, and the year rows rather than crowning the largest total."
    if verdict["id"] == "D":
        eighth = f"The pre-registered robustness bar is met for {verdict['robust_horizons']}. This experiment still does not install one of them as the live exit."
    else:
        eighth = "No. No holding period is promoted to a trading rule. The largest full-sample P&L is not a selection."
    return [first, second, third, fourth, fifth, sixth, seventh, eighth]


def _write_report(path: Path, meta: dict, books: dict, verdict: dict, answers: list[str], audit: dict) -> None:
    lines = [
        "# Today-drop fixed holding periods",
        "",
        f"{verdict['id']} — {verdict['label']}",
        "",
        "Day N is the close of the Nth completed session strictly after the entry session. The entry day's own close is not day 1. Gaps are not filled. These checkpoints were fixed before the run.",
        "",
        "## Answers",
        "",
    ]
    for index, answer in enumerate(answers, start=1):
        lines.append(f"{index}. {answer}")
    lines.extend(["", "## Data", "", f"- Look-ahead {audit['status']}", f"- Bracket identity {'PASS' if meta['identity_match'] else 'FAIL'}", f"- Frozen bracket closed trades {meta['frozen_trades']}, 2 bp net {meta['frozen_net_2']}, 5 bp net {meta['frozen_net_5']}", f"- First bar `{meta['first_bar']}`", f"- Last bar `{meta['last_bar']}`", f"- Snapshots `{meta['snapshot_5m']}` `{meta['sha256_5m']}` and `{meta['snapshot_1d']}` `{meta['sha256_1d']}`", "", "## Comparison at the fixed horizons", "", "| | " + " | ".join(f"{horizon}D" for horizon in HORIZONS) + " |", "|---|" + "---:|" * len(HORIZONS)])
    rows = [
        ("Trades", lambda block: str(block["resolved"])),
        ("Unresolved", lambda block: str(block["unresolved"])),
        ("Median return", lambda block: _pct(block.get("median_return_pct"))),
        ("Mean return", lambda block: _pct(block.get("avg_return_pct"))),
        ("Net @ 2 bp", lambda block: _money(block["net_pnl"])),
        ("Expectancy @ 2 bp", lambda block: _money(block.get("expectancy"))),
        ("Max DD @ 2 bp", lambda block: _money(block.get("max_drawdown"))),
        ("Profit factor @ 2 bp", lambda block: "" if block.get("profit_factor") is None else f"{block['profit_factor']:.2f}"),
    ]
    for label, getter in rows:
        if "5 bp" in label:
            continue
        cells = [getter(books[horizon][2] if "2 bp" in label or label in {"Trades", "Unresolved", "Median return", "Mean return"} else books[horizon][2]) for horizon in HORIZONS]
        lines.append("| " + label + " | " + " | ".join(cells) + " |")
    lines.append("| Net @ 5 bp | " + " | ".join(_money(books[horizon][5]["net_pnl"]) for horizon in HORIZONS) + " |")
    lines.extend(["", "Existing bracket, same entry, +5% / -3%, from the frozen isolation replay:", f"- 2 bp: {meta['frozen_trades']} closed trades, net {meta['frozen_net_2']}, expectancy {meta['frozen_expectancy_2']}, drawdown {meta['frozen_drawdown_2']}", f"- 5 bp: net {meta['frozen_net_5']}", "", "## Median return and trades by year at 2 bp", "", "| Year | " + " | ".join(f"{horizon}D" for horizon in HORIZONS) + " |", "|---|" + "---:|" * len(HORIZONS)])
    for year in ("2024", "2025", "2026"):
        cells = []
        for horizon in HORIZONS:
            block = books[horizon][2]["years"].get(year, {})
            cells.append(f"{_pct(block.get('median_return_pct'))} ({block.get('trades', 0)})")
        lines.append(f"| {year} | " + " | ".join(cells) + " |")
    lines.extend(["", "## Cost at which full-sample net stops being positive", ""])
    for horizon in HORIZONS:
        broken = [int(bps) for bps in COST_BPS if Decimal(str(books[horizon][int(bps)]["net_pnl"])) <= 0]
        if not broken:
            lines.append(f"- {horizon}D remains positive from 0 bp through 5 bp.")
        else:
            lines.append(f"- {horizon}D is not positive at {broken[0]} bp.")
    lines.extend(["", "## Tests", "", f"- `{meta['test_command']}`", f"- {meta['test_result']}", "", "## Git status", "", "```", meta["git_status"], "```", "", "Reproduce:", "`python scripts/backtest_today_drop_holding_period.py`", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["results"]
    frozen_2 = frozen["A|2"]["full"]
    frozen_5 = frozen["A|5"]["full"]
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(0))
    by_symbol: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_symbol[bar.symbol].append(bar)
    raw: dict[int, list] = {horizon: [] for horizon in HORIZONS}
    bracket_raw: list[dict] = []
    sessions: dict[str, list] = {}
    first = last = None
    missing = 0
    sha_5m = ""
    for index, symbol in enumerate(chosen, start=1):
        bars, gaps, digest = stream_candles(SNAPSHOT_5M, (symbol,), START, END, warmup=timedelta(0))
        sha_5m = digest
        missing += gaps
        if bars:
            first = bars[0].end if first is None or bars[0].end < first else first
            last = bars[-1].end if last is None or bars[-1].end > last else last
        symbol_daily = by_symbol.get(symbol, [])
        sessions[symbol] = [session_date(bar.end) for bar in subsequent_sessions(symbol_daily, symbol)]
        bracket_raw.extend(simulate_symbol(symbol, bars, symbol_daily, variants=("baseline_today_drop",), modes=("delivery",)))
        for horizon in HORIZONS:
            raw[horizon].extend(simulate_fixed_hold(symbol, bars, symbol_daily, horizon))
        print(f"{index}/{len(chosen)} {symbol} 1d={len(raw[1])} 20d={len(raw[20])}", flush=True)
    priced_bracket = [price_trade(trade, Decimal("2")) for trade in bracket_raw if trade["exit_price"] is not None]
    replay_net = sum((trade["net_pnl"] for trade in priced_bracket), Decimal("0")).quantize(Decimal("0.01"))
    identity = len(priced_bracket) == frozen_2["trades"] and format(replay_net, "f") == frozen_2["net_pnl"]
    audit = lookahead_audit([trade for rows in raw.values() for trade in rows], sessions)
    if not identity:
        audit = {**audit, "status": "FAIL", "valid": False, "failure_count": audit["failure_count"] + 1, "failures": [f"Bracket replay net {replay_net} on {len(priced_bracket)} trades does not match the frozen book", *audit["failures"]]}
    books: dict[int, dict[int, dict]] = {}
    trade_rows = []
    for horizon in HORIZONS:
        books[horizon] = {}
        priced_by_cost = {int(bps): [price_trade(trade, bps) for trade in raw[horizon]] for bps in COST_BPS}
        for bps, priced in priced_by_cost.items():
            summary = enrich(priced)
            closed = [trade for trade in priced if trade["net_pnl"] is not None]
            summary["resolved"] = len(closed)
            summary["unresolved"] = len(priced) - len(closed)
            summary["censor_ratio"] = (len(priced) - len(closed)) / len(priced) if priced else None
            summary["distribution"] = return_distribution([trade["return_pct"] for trade in closed])
            summary["holding"] = _duration(priced)
            summary["sharpe_meaningful"] = len(closed) >= 30
            if bps == 2:
                summary.update(month_runs(priced))
                summary.update(contribution(priced))
            books[horizon][bps] = summary
        for index, trade in enumerate(raw[horizon]):
            row = {"symbol": trade["symbol"], "horizon": horizon, "session_date": trade["session_date"], "entry_time": trade["entry_time"], "entry_price": trade["entry_price"], "exit_time": trade["exit_time"], "exit_price": trade["exit_price"], "exit_reason": trade["exit_reason"], "quantity": trade["quantity"]}
            for bps, priced in priced_by_cost.items():
                row[f"net_{bps}bp"] = priced[index]["net_pnl"]
            trade_rows.append(row)
    verdict = classify_holding(books) if audit["valid"] else {"id": None, "label": "CLASSIFICATION STOPPED", "drift_horizons": [], "robust_horizons": [], "supportive_horizons": []}
    answers = _answers(books, verdict) if audit["valid"] else ["Look-ahead or bracket identity failed, so the questions are not answered."]
    test = subprocess.run([sys.executable, "-m", "pytest", "tests/test_today_drop_holding_period.py", "-q", "--tb=line"], cwd=ROOT, check=False, capture_output=True, text=True)
    meta = {
        "snapshot_5m": SNAPSHOT_5M,
        "snapshot_1d": SNAPSHOT_1D,
        "sha256_5m": sha_5m,
        "sha256_1d": sha_1d,
        "first_bar": first.isoformat() if first else None,
        "last_bar": last.isoformat() if last else None,
        "symbol_count": len(chosen),
        "missing_5m": missing,
        "identity_match": identity,
        "frozen_trades": frozen_2["trades"],
        "frozen_net_2": frozen_2["net_pnl"],
        "frozen_net_5": frozen_5["net_pnl"],
        "frozen_expectancy_2": frozen_2.get("expectancy"),
        "frozen_drawdown_2": frozen_2.get("max_drawdown"),
        "holdout_opened": False,
        "test_command": "python -m pytest tests/test_today_drop_holding_period.py -q --tb=line",
        "test_result": (test.stdout or test.stderr).strip(),
        "git_status": subprocess.run(["git", "status", "--short"], cwd=ROOT, check=False, capture_output=True, text=True).stdout.strip(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps({"meta": _plain(meta), "classification": verdict, "answers": answers}, indent=2), encoding="utf-8")
    (OUT / "holding_period_results.json").write_text(json.dumps(_plain(books), indent=2), encoding="utf-8")
    yearly = {str(horizon): {year: books[horizon][2]["years"].get(year) for year in ("2024", "2025", "2026")} for horizon in HORIZONS}
    (OUT / "yearly_results.json").write_text(json.dumps(_plain(yearly), indent=2), encoding="utf-8")
    costs = {str(horizon): {str(bps): {"net_pnl": books[horizon][bps]["net_pnl"], "expectancy": books[horizon][bps].get("expectancy"), "resolved": books[horizon][bps]["resolved"]} for bps in books[horizon]} for horizon in HORIZONS}
    (OUT / "cost_sensitivity.json").write_text(json.dumps(_plain(costs), indent=2), encoding="utf-8")
    (OUT / "lookahead.json").write_text(json.dumps(_plain(audit), indent=2), encoding="utf-8")
    with (OUT / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for row in trade_rows:
            handle.write(json.dumps(_plain(row)) + "\n")
    _write_report(OUT / "report.md", meta, books, verdict, answers, audit)
    print(verdict["id"], audit["status"], "identity", identity, flush=True)


if __name__ == "__main__":
    main()
