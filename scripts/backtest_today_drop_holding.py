"""Diagnostic holding-period path for the frozen delivery today-drop entries.

Does not rewrite earlier research outputs, does not open the holdout, and does
not choose a new exit.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
from quant_agents.research.rebound import price_trade, simulate_symbol
from quant_agents.research.today_drop_holding import (
    HORIZONS,
    answer_questions,
    lookahead_audit,
    measure_path,
    stock_table,
    summarize_paths,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "today_drop_holding"
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
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _pct(value) -> str:
    if value is None:
        return ""
    return f"{Decimal(value) * 100:.2f}%"


def _write_report(path: Path, meta: dict, summary: dict, stocks: dict, answers: list[str], audit: dict) -> None:
    lines = [
        "# Today-drop holding period",
        "",
        "These checkpoints describe the path after a Strategy A entry. They are not a new exit and they are not tradable results.",
        "",
        "## Answers",
        "",
    ]
    for index, answer in enumerate(answers, start=1):
        lines.append(f"{index}. {answer}")
    lines.extend(
        [
            "",
            "## Data",
            "",
            f"- Entries {meta['entries']}, of which {meta['frozen_trades']} match the frozen closed book and the rest were still open",
            "- Day 1 is the first daily close after the fill. On an intraday entry that is the entry session's official close. Later days are the following observed sessions. Missing sessions are not invented.",
            f"- Frozen Strategy A trades {meta['frozen_trades']}, net at 2 bp {meta['frozen_net']}",
            f"- Replayed trades {meta['replay_trades']}, net at 2 bp {meta['replay_net']}",
            f"- Identity {'PASS' if meta['identity_match'] else 'FAIL'}",
            f"- Look-ahead {audit['status']}",
            f"- First bar `{meta['first_bar']}`",
            f"- Last bar `{meta['last_bar']}`",
            "",
            "## Forward close, all entries",
            "",
            "| Days | N | Unresolved | Median | Mean | Win rate | P25 | P75 | Median MFE | Median MAE |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for horizon in HORIZONS:
        block = summary["all"][str(horizon)]
        gross = block["gross"]
        lines.append(
            f"| {horizon} | {gross['observations']} | {block['unresolved']} | {_pct(gross['median'])} | {_pct(gross['mean'])} | {_pct(gross['win_rate'])} | {_pct(gross['p25'])} | {_pct(gross['p75'])} | {_pct(block['mfe']['median'])} | {_pct(block['mae']['median'])} |"
        )
    lines.extend(["", "## After costs, median return", "", "| Days | Before costs | 0 bp | 2 bp | 5 bp |", "|---:|---:|---:|---:|---:|"])
    for horizon in HORIZONS:
        block = summary["all"][str(horizon)]
        lines.append(
            f"| {horizon} | {_pct(block['gross']['median'])} | {_pct(block['net_0bp']['median'])} | {_pct(block['net_2bp']['median'])} | {_pct(block['net_5bp']['median'])} |"
        )
    lines.extend(["", "## Original +5% / -3% status at each checkpoint", "", "| Days | Hit +5% | Hit -3% | Neither | Unresolved |", "|---:|---:|---:|---:|---:|"])
    for horizon in HORIZONS:
        exits = summary["all"][str(horizon)]["original_exit"]
        lines.append(f"| {horizon} | {exits['target']} | {exits['stop']} | {exits['neither']} | {exits['unresolved']} |")
    lines.extend(["", "## Median gross return by year", "", "| Days | 2024 | 2025 | 2026 |", "|---:|---:|---:|---:|"])
    for horizon in HORIZONS:
        lines.append(
            "| {horizon} | {y2024} | {y2025} | {y2026} |".format(
                horizon=horizon,
                y2024=_pct(summary["years"]["2024"][str(horizon)]["gross"]["median"]),
                y2025=_pct(summary["years"]["2025"][str(horizon)]["gross"]["median"]),
                y2026=_pct(summary["years"]["2026"][str(horizon)]["gross"]["median"]),
            )
        )
    lines.extend(["", "## Median gross return, original winners and losers", "", "| Days | Winners | Losers |", "|---:|---:|---:|"])
    for horizon in HORIZONS:
        lines.append(
            f"| {horizon} | {_pct(summary['winners'][str(horizon)]['gross']['median'])} | {_pct(summary['losers'][str(horizon)]['gross']['median'])} |"
        )
    lines.extend(
        [
            "",
            "## Stocks",
            "",
            stocks["rule"],
            "",
            f"- Consistently positive ({len(stocks['consistently_positive'])}): {', '.join(stocks['consistently_positive']) or 'none'}",
            f"- Consistently negative ({len(stocks['consistently_negative'])}): {', '.join(stocks['consistently_negative']) or 'none'}",
            f"- Mixed: {len(stocks['mixed'])}",
            f"- Fewer than 5 observations at a checkpoint: {len(stocks['too_thin'])}",
            "",
            "## Files",
            "",
            "- Created `services/quant/src/quant_agents/research/today_drop_holding.py`",
            "- Created `scripts/backtest_today_drop_holding.py`",
            "- Created `tests/test_today_drop_holding.py`",
            "- Created this research folder. Earlier rebound, isolation, regime, and breakout folders were not rewritten.",
            "- Reproduce with `python scripts/backtest_today_drop_holding.py`",
            "",
            "## Git diff",
            "",
            "```",
            meta["git_diff"],
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["results"]["A|2"]["full"]
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(0))
    by_symbol: dict[str, list] = {}
    for bar in daily:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    raw: list[dict] = []
    paths: list[dict] = []
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
        trades = simulate_symbol(symbol, bars, by_symbol.get(symbol, []), variants=("baseline_today_drop",), modes=("delivery",))
        raw.extend(trades)
        paths.extend(measure_path(trade, bars, by_symbol.get(symbol, [])) for trade in trades)
        print(f"{index}/{len(chosen)} {symbol} entries={len(trades)}", flush=True)
    priced = [price_trade(trade, Decimal("2")) for trade in raw]
    closed = [trade for trade in priced if trade["net_pnl"] is not None]
    replay_net = sum((trade["net_pnl"] for trade in closed), Decimal("0")).quantize(Decimal("0.01"))
    identity = (
        len(closed) == frozen["trades"]
        and len(raw) - len(closed) == frozen["unresolved"]
        and format(replay_net, "f") == frozen["net_pnl"]
    )
    audit = lookahead_audit(raw, paths)
    if not identity:
        audit = {
            **audit,
            "status": "FAIL",
            "valid": False,
            "failures": [f"Replay {len(raw)} trades net {replay_net} does not match frozen {frozen['trades']} trades net {frozen['net_pnl']}", *audit["failures"]],
            "failure_count": audit["failure_count"] + 1,
        }
    summary = summarize_paths(paths)
    stocks = stock_table(paths)
    if identity and audit["valid"]:
        answers = answer_questions(summary)
    else:
        answers = ["The replay does not match Strategy A or the look-ahead audit failed, so the seven questions are not answered."]
    diff = subprocess.run(["git", "diff", "--stat"], cwd=ROOT, check=False, capture_output=True, text=True).stdout
    meta = {
        "snapshot_5m": SNAPSHOT_5M,
        "snapshot_1d": SNAPSHOT_1D,
        "sha256_5m": sha_5m,
        "sha256_1d": sha_1d,
        "first_bar": first.isoformat() if first else None,
        "last_bar": last.isoformat() if last else None,
        "symbol_count": len(chosen),
        "missing_5m": missing,
        "entries": len(raw),
        "frozen_trades": frozen["trades"],
        "frozen_net": frozen["net_pnl"],
        "replay_trades": len(raw),
        "replay_net": format(replay_net, "f"),
        "identity_match": identity,
        "holdout_opened": False,
        "git_diff": diff.strip(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps({"meta": meta, "answers": answers, "forward": _plain(summary)}, indent=2), encoding="utf-8")
    (OUT / "forward_returns.json").write_text(json.dumps({"forward": _plain(summary), "stocks": _plain(stocks)}, indent=2), encoding="utf-8")
    with (OUT / "trade_paths.jsonl").open("w", encoding="utf-8") as handle:
        for path in paths:
            public = {key: value for key, value in path.items() if key not in {"detected_exit", "detected_exit_time"}}
            handle.write(json.dumps(_plain(public)) + "\n")
    (OUT / "lookahead.json").write_text(json.dumps(_plain(audit), indent=2), encoding="utf-8")
    _write_report(OUT / "report.md", meta, _plain(summary), stocks, answers, audit)
    print(audit["status"], "identity", identity, flush=True)


if __name__ == "__main__":
    main()
