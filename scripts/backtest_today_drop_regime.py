"""Regime stability of the frozen delivery today-drop book.

Does not rewrite earlier rebound outputs and does not open the holdout.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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

os.chdir(ROOT)

from contracts.enums import Timeframe
from core_features.context import load_index_bars
from core_market_data.replay import stream_candles
from quant_agents.research.rebound import (
    COST_BPS,
    enrich,
    lookahead_audit,
    price_trade,
    summarize,
    trade_record,
    simulate_symbol,
)
from quant_agents.research.today_drop_regime import (
    NIFTY_BUCKETS,
    TREND_BUCKETS,
    VIX_BUCKETS,
    IndexView,
    classify_direction,
    loss_explained_by_regime,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "today_drop_regime"
FROZEN = ROOT / "datasets" / "research" / "rebound_isolation" / "summary.json"
YEARS = ("2024", "2025", "2026")


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    return tuple(row["symbol"] for row in manifest["symbols"] if row["symbol"] != "TATAMOTORS" and int(row["count"]) > 0)


def _net(summary: dict) -> Decimal:
    value = summary.get("net_pnl")
    return Decimal(value) if value else Decimal("0")


def _share(part: Decimal, total: Decimal) -> float | None:
    if total == 0:
        return None
    return float(part / total)


def _year_cell(trades_2: list[dict], trades_5: list[dict]) -> dict:
    left = summarize(trades_2)
    right = summarize(trades_5)
    return {"trades": left.get("trades", 0), "net_2": _net(left), "net_5": _net(right)}


def _regime_table(trades_2: list[dict], trades_5: list[dict], key: str, labels: tuple[str, ...]) -> list[dict]:
    total_trades = sum(1 for trade in trades_2 if trade["net_pnl"] is not None)
    total_2 = sum((_net_trade(trade) for trade in trades_2 if trade["net_pnl"] is not None), Decimal("0"))
    total_5 = sum((_net_trade(trade) for trade in trades_5 if trade["net_pnl"] is not None), Decimal("0"))
    rows = []
    for label in labels:
        group_2 = [trade for trade in trades_2 if trade[key] == label]
        group_5 = [trade for trade in trades_5 if trade[key] == label]
        left = summarize(group_2)
        right = summarize(group_5)
        years = {}
        for year in YEARS:
            years[year] = _year_cell(
                [trade for trade in group_2 if str(trade["session_date"].year) == year],
                [trade for trade in group_5 if str(trade["session_date"].year) == year],
            )
        rows.append(
            {
                "bucket": label,
                "trades": left.get("trades", 0),
                "win_rate": left.get("win_rate"),
                "avg_return_pct": left.get("avg_return_pct"),
                "median_return_pct": left.get("median_return_pct"),
                "expectancy": left.get("expectancy"),
                "gross_pnl": left.get("gross_pnl"),
                "net_pnl_2bp": left.get("net_pnl"),
                "net_pnl_5bp": right.get("net_pnl"),
                "net_2": _net(left),
                "net_5": _net(right),
                "max_drawdown": left.get("max_drawdown"),
                "profit_factor": left.get("profit_factor"),
                "avg_holding_minutes": left.get("avg_holding_minutes"),
                "share_of_trades": None if total_trades == 0 else left.get("trades", 0) / total_trades,
                "share_of_net_2bp": _share(_net(left), total_2),
                "share_of_net_5bp": _share(_net(right), total_5),
                "years": years,
            }
        )
    return rows


def _net_trade(trade: dict) -> Decimal:
    return trade["net_pnl"]


def _distribution(summary: dict, trades: list[dict]) -> dict:
    stocks = summary.get("per_stock", [])
    total = _net(summary)
    winners = sorted((trade for trade in trades if trade["net_pnl"] is not None and trade["net_pnl"] > 0), key=lambda trade: trade["net_pnl"], reverse=True)

    def stock_share(count: int) -> float | None:
        if total == 0:
            return None
        part = sum((Decimal(row["net_pnl"]) for row in stocks[:count]), Decimal("0"))
        return float(part / total)

    def winner_share(count: int) -> float | None:
        if total == 0:
            return None
        part = sum((trade["net_pnl"] for trade in winners[:count]), Decimal("0"))
        return float(part / total)

    months = summary.get("monthly_pnl", {})
    month_values = [Decimal(value) for value in months.values()]
    year_rows = summary.get("years", {})
    return {
        "top10_stocks": stocks[:10],
        "bottom10_stocks": list(reversed(stocks[-10:])),
        "top1_stock_share": stock_share(1),
        "top5_stock_share": stock_share(5),
        "top10_stock_share": stock_share(10),
        "top1_winner_share": winner_share(1),
        "top5_winner_share": winner_share(5),
        "top10_winner_share": winner_share(10),
        "positive_months": sum(1 for value in month_values if value > 0),
        "negative_months": sum(1 for value in month_values if value < 0),
        "positive_years": sum(1 for row in year_rows.values() if Decimal(row.get("net_pnl") or "0") > 0),
        "negative_years": sum(1 for row in year_rows.values() if Decimal(row.get("net_pnl") or "0") < 0),
    }


def _feature_split(trades: list[dict]) -> dict:
    winners = [trade for trade in trades if trade["net_pnl"] is not None and trade["net_pnl"] > 0]
    losers = [trade for trade in trades if trade["net_pnl"] is not None and trade["net_pnl"] < 0]

    def pack(group: list[dict], field: str) -> dict:
        values = [float(trade[field]) for trade in group if trade.get(field) is not None]
        if not values:
            return {"count": 0, "mean": None, "median": None}
        return {"count": len(values), "mean": sum(values) / len(values), "median": float(median(values))}

    fields = ("today_drop_pct", "nifty_return_pct", "vix_level", "holding_minutes")
    return {
        "winners": {field: pack(winners, field) for field in fields},
        "losers": {field: pack(losers, field) for field in fields},
    }


def _public_row(row: dict) -> dict:
    exported = {key: value for key, value in row.items() if key not in {"net_2", "net_5", "years"}}
    exported["years"] = {
        year: {"trades": cell["trades"], "net_pnl_2bp": f"{cell['net_2']:.2f}", "net_pnl_5bp": f"{cell['net_5']:.2f}"}
        for year, cell in row["years"].items()
    }
    return exported


def _fmt(value, kind: str = "num") -> str:
    if value is None:
        return ""
    if kind == "pct":
        return f"{float(value) * 100:.1f}%"
    if kind == "num" and isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _write_report(path: Path, payload: dict) -> None:
    decision = payload["classification"]
    lines = [
        "# Today-drop regime stability",
        "",
        f"{decision['code']}. {decision['decision']}",
        "",
        *[f"- {reason}" for reason in decision["reasons"]],
        "",
        "This is not a robust edge.",
        "",
        "## Answers",
        "",
    ]
    for item in payload["answers"]:
        lines.append(f"- {item['question']} {item['answer']}")
    lines.extend(["", "## Availability", ""])
    for key, value in payload["availability"].items():
        lines.append(f"- {key}: {value}")
    for title, rows in (
        ("NIFTY return", payload["nifty_return"]),
        ("NIFTY trend", payload["trend"]),
        ("India VIX", payload["vix"]),
    ):
        lines.extend(["", f"## {title}", "", "| Bucket | Trades | Win rate | Avg | Median | Expectancy | Gross | Net 2 bp | Net 5 bp | Max DD | PF | Avg hold | Share of trades | Share of net 2 bp |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for row in rows:
            lines.append(
                "| {bucket} | {trades} | {win} | {avg} | {med} | {exp} | {gross} | {net2} | {net5} | {dd} | {pf} | {hold} | {share} | {netshare} |".format(
                    bucket=row["bucket"],
                    trades=row["trades"],
                    win=_fmt(row["win_rate"], "pct"),
                    avg=_fmt(row["avg_return_pct"]),
                    med=_fmt(row["median_return_pct"]),
                    exp=row["expectancy"] or "",
                    gross=row["gross_pnl"] or "",
                    net2=row["net_pnl_2bp"] or "",
                    net5=row["net_pnl_5bp"] or "",
                    dd=row["max_drawdown"] or "",
                    pf=_fmt(row["profit_factor"]),
                    hold=_fmt(row["avg_holding_minutes"]),
                    share=_fmt(row["share_of_trades"], "pct"),
                    netshare=_fmt(row["share_of_net_2bp"], "pct"),
                )
            )
    for title, rows in (
        ("NIFTY return", payload["nifty_return"]),
        ("NIFTY trend", payload["trend"]),
        ("India VIX", payload["vix"]),
    ):
        lines.extend(["", f"## Year by {title} at 2 bp", "", "| Bucket | 2024 trades | 2024 net | 2025 trades | 2025 net | 2026 trades | 2026 net |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for row in rows:
            cells = row["years"]
            lines.append(
                f"| {row['bucket']} | {cells['2024']['trades']} | {cells['2024']['net_pnl_2bp']} | {cells['2025']['trades']} | {cells['2025']['net_pnl_2bp']} | {cells['2026']['trades']} | {cells['2026']['net_pnl_2bp']} |"
            )
    dist = payload["distribution"]
    lines.extend(
        [
            "",
            "## Distribution at 2 bp",
            "",
            f"- Top 1 stock share of net: {_fmt(dist['top1_stock_share'], 'pct')}",
            f"- Top 5 stock share of net: {_fmt(dist['top5_stock_share'], 'pct')}",
            f"- Top 10 stock share of net: {_fmt(dist['top10_stock_share'], 'pct')}",
            f"- Top 1 winning trade share of net: {_fmt(dist['top1_winner_share'], 'pct')}",
            f"- Top 5 winning trades share of net: {_fmt(dist['top5_winner_share'], 'pct')}",
            f"- Top 10 winning trades share of net: {_fmt(dist['top10_winner_share'], 'pct')}",
            f"- Positive months: {dist['positive_months']}",
            f"- Negative months: {dist['negative_months']}",
            f"- Positive years: {dist['positive_years']}",
            f"- Negative years: {dist['negative_years']}",
            "",
            "## Costs",
            "",
            "| bps | Trades | Net | Expectancy | Max DD |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for bps, row in payload["costs"].items():
        lines.append(f"| {bps} | {row['trades']} | {row['net_pnl']} | {row['expectancy']} | {row['max_drawdown']} |")
    audit = payload["audit"]
    lines.extend(["", "## Look-ahead", "", f"Status: {audit['status']}", f"Unresolved exits: {audit['unresolved_count']}", ""])
    for check in audit["checks"]:
        lines.append(f"- {check['status']}: {check['item']}")
    lines.extend(["", "## Reproduce", "", "```", "python scripts/backtest_today_drop_regime.py", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _answers(rows: list[dict], explained: bool, decision: dict) -> list[dict]:
    profitable = [row["bucket"] for row in rows if row["bucket"] != "unavailable" and row["trades"] >= 30 and row["net_2"] > 0 and row["net_5"] > 0]
    poor = [row["bucket"] for row in rows if row["bucket"] != "unavailable" and all((year["trades"] < 20 or (year["net_2"] < 0 and year["net_5"] < 0)) for year in row["years"].values()) and any(year["trades"] >= 20 for year in row["years"].values())]
    return [
        {
            "question": "Does the today-drop signal remain profitable at 2 bp and 5 bp across multiple market regimes?",
            "answer": "Yes." if len(profitable) >= 2 else "No.",
        },
        {
            "question": "Is the 2026 loss explained by a change in market regime?",
            "answer": "Yes." if explained else "No.",
        },
        {
            "question": "Is there a regime in which the strategy consistently performs poorly?",
            "answer": "Yes: " + ", ".join(poor) + "." if poor else "No.",
        },
        {
            "question": "Is the apparent edge broad enough to continue research?",
            "answer": "Yes, without a regime filter." if decision["code"] == "B" else "No.",
        },
        {
            "question": "Is there evidence that the strategy should be restricted to a particular market regime?",
            "answer": "Yes." if decision["code"] == "C" else "No.",
        },
    ]


def main() -> None:
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(0))
    by_symbol: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_symbol[bar.symbol].append(bar)
    raw: list[dict] = []
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
        raw.extend(
            simulate_symbol(
                symbol,
                bars,
                by_symbol.get(symbol, []),
                variants=("baseline_today_drop",),
                modes=("delivery",),
            )
        )
        print(f"{index}/{len(chosen)} {symbol}", flush=True)
    audit = lookahead_audit(raw)
    priced = {int(bps): [price_trade(trade, bps) for trade in raw] for bps in COST_BPS}
    book = {bps: enrich(rows, paths=bps == 2) for bps, rows in priced.items()}
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["results"]["A|2"]["full"]
    replay = book[2]
    mismatch = frozen["trades"] != replay["trades"] or frozen["net_pnl"] != replay["net_pnl"]
    OUT.mkdir(parents=True, exist_ok=True)
    if mismatch or not audit["valid"]:
        reason = "Replay diverged from the frozen today-drop summary." if mismatch else "Look-ahead audit failed."
        (OUT / "lookahead.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
        (OUT / "report.md").write_text(f"# Today-drop regime stability\n\nExperiment stopped. {reason}\n", encoding="utf-8")
        print(reason, flush=True)
        raise SystemExit(1)
    loaded_5m = load_index_bars(Timeframe.M5, END)
    loaded_1d = load_index_bars(Timeframe.D1, END)
    view = IndexView.build(
        loaded_5m.get("NIFTY50", []),
        loaded_1d.get("NIFTY50", []),
        loaded_5m.get("INDIAVIX", []),
        loaded_1d.get("INDIAVIX", []),
    )
    labels = [view.classify(trade["signal_time"]) for trade in raw]
    for rows in priced.values():
        for trade, label in zip(rows, labels):
            trade["nifty_return_pct"] = label["nifty_return_pct"]
            trade["nifty_return_bucket"] = label["nifty_return_bucket"]
            trade["nifty_trend"] = label["nifty_trend"]
            trade["vix_level"] = label["vix_level"]
            trade["vix_bucket"] = label["vix_bucket"]
    closed = [trade for trade in priced[2] if trade["net_pnl"] is not None]
    unavailable = sum(1 for trade in closed if trade["nifty_return_bucket"] == "unavailable")
    availability = {
        "nifty_5m_bars": len(view.nifty_5m),
        "nifty_1d_bars": len(view.nifty_1d),
        "vix_bars": len(view.vix),
        "vix_daily_bars": len(view.vix_daily),
        "unavailable_trades": unavailable,
        "unavailable_share": 0 if not closed else unavailable / len(closed),
    }
    nifty_rows = _regime_table(priced[2], priced[5], "nifty_return_bucket", NIFTY_BUCKETS)
    trend_rows = _regime_table(priced[2], priced[5], "nifty_trend", TREND_BUCKETS)
    vix_rows = _regime_table(priced[2], priced[5], "vix_bucket", VIX_BUCKETS)
    explained = loss_explained_by_regime(nifty_rows)
    decision = classify_direction(
        nifty_rows,
        nifty_5m_count=availability["nifty_5m_bars"],
        nifty_1d_count=availability["nifty_1d_bars"],
        unavailable_share=availability["unavailable_share"],
    )
    answers = _answers(nifty_rows, explained, decision)
    distribution = _distribution(book[2], priced[2])
    features = _feature_split(priced[2])
    costs = {str(bps): {"trades": summary.get("trades"), "net_pnl": summary.get("net_pnl"), "expectancy": summary.get("expectancy"), "max_drawdown": summary.get("max_drawdown")} for bps, summary in book.items()}
    analysis = {
        "availability": availability,
        "nifty_return": [_public_row(row) for row in nifty_rows],
        "trend": [_public_row(row) for row in trend_rows],
        "vix": [_public_row(row) for row in vix_rows],
        "loss_explained_by_regime": explained,
        "winners_losers": features,
        "distribution": distribution,
        "answers": answers,
        "classification": decision,
    }
    payload = {
        "classification": decision,
        "answers": answers,
        "availability": availability,
        "nifty_return": analysis["nifty_return"],
        "trend": analysis["trend"],
        "vix": analysis["vix"],
        "distribution": distribution,
        "costs": costs,
        "audit": audit,
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
        "mode": "delivery",
        "strategy": "A",
        "holdout_opened": False,
        "frozen_summary_checked": True,
    }
    with (OUT / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for trade in priced[2]:
            record = trade_record(trade)
            record["nifty_return_pct"] = float(trade["nifty_return_pct"]) if trade["nifty_return_pct"] is not None else None
            record["nifty_return_bucket"] = trade["nifty_return_bucket"]
            record["nifty_trend"] = trade["nifty_trend"]
            record["vix_level"] = float(trade["vix_level"]) if trade["vix_level"] is not None else None
            record["vix_bucket"] = trade["vix_bucket"]
            handle.write(json.dumps(record) + "\n")
    (OUT / "summary.json").write_text(json.dumps({"meta": meta, "classification": decision, "answers": answers, "costs": costs, "availability": availability}, indent=2), encoding="utf-8")
    (OUT / "regime_analysis.json").write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
    (OUT / "lookahead.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    _write_report(OUT / "report.md", payload)
    print(decision["code"], decision["decision"], audit["status"], flush=True)


if __name__ == "__main__":
    main()
