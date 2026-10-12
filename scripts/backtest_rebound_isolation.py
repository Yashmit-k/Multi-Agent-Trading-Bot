"""Attribute delivery P&L to each frozen oversold-rebound entry condition.

Does not rewrite datasets/research/rebound and does not open the holdout.
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
from quant_agents.research.rebound import (
    COST_BPS,
    count_funnel,
    enrich,
    lookahead_audit,
    price_trade,
    summarize,
    trade_record,
    simulate_symbol,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "rebound_isolation"
FROZEN = ROOT / "datasets" / "research" / "rebound" / "summary.json"
STRATEGIES = (
    ("A", "baseline_today_drop", "today drop <= -1%"),
    ("B", "drop_and_ema5", "today drop <= -1% and distance <= -5%"),
    ("C", "drop_and_down_days", "today drop <= -1% and down days >= 3"),
    ("D", "ablate_down_days", "today drop <= -1% and -12% <= distance <= -5%"),
    ("E", "full", "today drop <= -1%, down days >= 3, and -12% <= distance <= -5%"),
    ("F", "baseline_down_days", "down days >= 3"),
    ("G", "baseline_below_ema5", "distance <= -5%"),
)
VARIANTS = tuple(variant for _, variant, _ in STRATEGIES)
FROZEN_KEYS = {
    "A": "baseline_today_drop",
    "D": "ablate_down_days",
    "E": "full",
    "F": "baseline_down_days",
    "G": "baseline_below_ema5",
}
FUNNEL_STAGES = (
    ("eligible", "All eligible 5-minute observations", None),
    ("today_drop", "Today's drop <= -1%", "A"),
    ("drop_and_below_ema5", "And distance <= -5%", "B"),
    ("drop_and_ema_band", "And distance >= -12%", "D"),
    ("full_rule", "And down days >= 3", "E"),
)
DROP_LABELS = ("1-2", "2-3", "3-4", "4+")
EMA_LABELS = ("5-6", "6-7", "7-8", "8-9", "9-10", "10-11", "11-12", ">12")


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    return tuple(row["symbol"] for row in manifest["symbols"] if row["symbol"] != "TATAMOTORS" and int(row["count"]) > 0)


def _net(summary: dict) -> Decimal:
    value = summary.get("net_pnl")
    return Decimal(value) if value else Decimal("0")


def _expectancy(summary: dict) -> Decimal:
    value = summary.get("expectancy")
    return Decimal(value) if value else Decimal("0")


def _slice(book: dict, strategy: str, bps: int, split: str | None = None) -> dict:
    summary = book[(strategy, bps)]
    if split is None:
        return summary
    return summary["splits"][split]


def _label(left: Decimal, right: Decimal) -> str:
    if left > 0 and right > 0:
        return "HELPFUL"
    if left < 0 and right < 0:
        return "HARMFUL"
    return "NEUTRAL"


def _drop_bucket(trade: dict) -> str | None:
    drop = trade["today_drop_pct"]
    if drop is None:
        return None
    magnitude = -drop
    if 1 <= magnitude < 2:
        return "1-2"
    if 2 <= magnitude < 3:
        return "2-3"
    if 3 <= magnitude < 4:
        return "3-4"
    if magnitude >= 4:
        return "4+"
    return None


def _ema_bucket(trade: dict) -> str | None:
    distance = trade["distance_pct"]
    if distance is None:
        return None
    magnitude = -distance
    edges = (5, 6, 7, 8, 9, 10, 11, 12)
    for lower, upper in zip(edges, edges[1:]):
        if upper == 12 and lower <= magnitude <= upper:
            return f"{lower}-{upper}"
        if lower <= magnitude < upper:
            return f"{lower}-{upper}"
    if magnitude > 12:
        return ">12"
    return None


def _depth(trades_2: list[dict], trades_5: list[dict], bucket_of, labels: tuple[str, ...]) -> list[dict]:
    rows = []
    for label in labels:
        at_2 = [trade for trade in trades_2 if bucket_of(trade) == label]
        at_5 = [trade for trade in trades_5 if bucket_of(trade) == label]
        left = summarize(at_2)
        right = summarize(at_5)
        rows.append(
            {
                "bucket": label,
                "trades": left.get("trades", 0),
                "win_rate": left.get("win_rate"),
                "avg_return_pct": left.get("avg_return_pct"),
                "median_return_pct": left.get("median_return_pct"),
                "net_pnl_2bp": left.get("net_pnl"),
                "net_pnl_5bp": right.get("net_pnl"),
            }
        )
    return rows


def _share(stocks: list[dict], total: Decimal, count: int) -> float | None:
    if total == 0 or not stocks:
        return None
    part = sum((Decimal(row["net_pnl"]) for row in stocks[:count]), Decimal("0"))
    return float(part / total)


def _concentration(summary: dict) -> dict:
    stocks = summary.get("per_stock", [])
    total = _net(summary)
    worst = list(reversed(stocks[-10:]))
    return {
        "top10": stocks[:10],
        "bottom10": worst,
        "top1_share_of_net": _share(stocks, total, 1),
        "top5_share_of_net": _share(stocks, total, 5),
        "top10_share_of_net": _share(stocks, total, 10),
    }


def _month_span(monthly: dict[str, str]) -> list[tuple[str, Decimal]]:
    if not monthly:
        return []
    keys = sorted(monthly)
    cursor = date.fromisoformat(keys[0] + "-01")
    last = date.fromisoformat(keys[-1] + "-01")
    series = []
    while cursor <= last:
        key = f"{cursor.year:04d}-{cursor.month:02d}"
        series.append((key, Decimal(monthly.get(key, "0"))))
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
    return series


def _streaks(monthly: dict[str, str]) -> dict:
    series = _month_span(monthly)
    positive = sum(1 for _, value in series if value > 0)
    negative = sum(1 for _, value in series if value < 0)
    longest_win = longest_loss = current_win = current_loss = 0
    for _, value in series:
        if value > 0:
            current_win += 1
            current_loss = 0
        elif value < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        longest_win = max(longest_win, current_win)
        longest_loss = max(longest_loss, current_loss)
    return {
        "positive_months": positive,
        "negative_months": negative,
        "longest_winning_streak": longest_win,
        "longest_losing_streak": longest_loss,
        "monthly_pnl": {key: f"{value:.2f}" for key, value in series},
    }


def _compact(summary: dict) -> dict:
    return {
        "trades": summary.get("trades", 0),
        "unresolved": summary.get("unresolved", 0),
        "win_rate": summary.get("win_rate"),
        "avg_return_pct": summary.get("avg_return_pct"),
        "median_return_pct": summary.get("median_return_pct"),
        "gross_pnl": summary.get("gross_pnl"),
        "transaction_cost": summary.get("transaction_cost"),
        "net_pnl": summary.get("net_pnl"),
        "expectancy": summary.get("expectancy"),
        "profit_factor": summary.get("profit_factor"),
        "max_drawdown": summary.get("max_drawdown"),
        "sharpe": summary.get("sharpe"),
        "sortino": summary.get("sortino"),
        "avg_holding_minutes": summary.get("avg_holding_minutes"),
    }


def _conditions() -> dict[str, str]:
    return {name: text for name, _, text in STRATEGIES}


def _recommend(book: dict, labels: dict[str, str]) -> dict:
    def cell(name: str, bps: int) -> dict:
        return _slice(book, name, bps, "h2_2025")

    def beats(left: str, right: str) -> bool:
        return all(_net(cell(left, bps)) > _net(cell(right, bps)) for bps in (2, 5))

    e_beats = beats("E", "A") and all(_expectancy(cell("E", bps)) > _expectancy(cell("A", bps)) for bps in (2, 5))
    filters_harmful = any(labels[name] == "HARMFUL" for name in ("ema_distance", "down_days", "upper_bound"))
    filters_helpful = any(labels[name] == "HELPFUL" for name in ("ema_distance", "down_days", "upper_bound"))
    a_positive = all(_net(cell("A", bps)) > 0 for bps in (2, 5))
    reasons = []
    if e_beats and not filters_harmful:
        reasons.append("Validation net and expectancy for the full rule beat today-drop at 2 bp and 5 bp, and none of the added filters is harmful.")
        return {"code": "E", "decision": "CONTINUE RESEARCH ON COMBINED STRATEGY", "reasons": reasons}
    if a_positive and not filters_helpful:
        reasons.append("Today-drop is positive on validation at 2 bp and 5 bp, and none of the EMA, down-day, or -12% increments is helpful.")
        return {"code": "B", "decision": "CONTINUE RESEARCH ON TODAY-DROP SIGNAL", "reasons": reasons}
    if beats("G", "A") and labels["ema_distance"] == "HELPFUL":
        reasons.append("EMA distance alone beats today-drop on validation at both costs, and adding the EMA filter to today-drop increases validation P&L.")
        return {"code": "C", "decision": "CONTINUE RESEARCH ON EMA MEAN-REVERSION", "reasons": reasons}
    if beats("F", "A") and labels["down_days"] == "HELPFUL":
        reasons.append("Down days alone beat today-drop on validation at both costs, and adding down days to today-drop increases validation P&L.")
        return {"code": "D", "decision": "CONTINUE RESEARCH ON DOWN-DAY REVERSAL", "reasons": reasons}
    if not a_positive:
        reasons.append("Today-drop is not positive on validation at both 2 bp and 5 bp, and no continue rule fired.")
        return {"code": "A", "decision": "ABANDON", "reasons": reasons}
    reasons.append("Today-drop stays positive, but no pre-registered continue rule fired.")
    return {"code": "UNRESOLVED", "decision": "NO PRE-REGISTERED RULE", "reasons": reasons}


def _fmt(value, kind: str = "num") -> str:
    if value is None:
        return ""
    if kind == "pct":
        return f"{float(value) * 100:.1f}%"
    if kind == "share":
        return f"{float(value) * 100:.1f}%"
    if kind == "num" and isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _table(book: dict, split: str | None, bps: int) -> list[str]:
    lines = [
        "| Strategy | Conditions | Trades | Win rate | Avg return | Median return | Gross | Cost | Net | Expectancy | PF | Max DD | Sharpe | Sortino | Avg hold min |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    descriptions = _conditions()
    for name, _, _ in STRATEGIES:
        row = _compact(_slice(book, name, bps, split))
        lines.append(
            "| {name} | {conditions} | {trades} | {win} | {avg} | {med} | {gross} | {cost} | {net} | {exp} | {pf} | {dd} | {sharpe} | {sortino} | {hold} |".format(
                name=name,
                conditions=descriptions[name],
                trades=row["trades"],
                win=_fmt(row["win_rate"], "pct"),
                avg=_fmt(row["avg_return_pct"]),
                med=_fmt(row["median_return_pct"]),
                gross=row["gross_pnl"],
                cost=row["transaction_cost"],
                net=row["net_pnl"],
                exp=row["expectancy"],
                pf=_fmt(row["profit_factor"]),
                dd=row["max_drawdown"],
                sharpe=_fmt(row["sharpe"]),
                sortino=_fmt(row["sortino"]),
                hold=_fmt(row["avg_holding_minutes"]),
            )
        )
    return lines


def _write_report(path: Path, payload: dict) -> None:
    book = payload["book"]
    lines = [
        "# Delivery condition isolation",
        "",
        f"{payload['recommendation']['code']}. {payload['recommendation']['decision']}",
        "",
        *[f"- {reason}" for reason in payload["recommendation"]["reasons"]],
        "",
        "## Condition classification",
        "",
        payload["question"],
        "",
    ]
    for name, label in payload["labels"].items():
        lines.append(f"- {name}: {label}")
    lines.extend(["", "## Full period at 2 bp", ""])
    lines.extend(_table(book, None, 2))
    lines.extend(["", "## Full period at 5 bp", ""])
    lines.extend(_table(book, None, 5))
    lines.extend(["", "## Validation at 2 bp", ""])
    lines.extend(_table(book, "h2_2025", 2))
    lines.extend(["", "## Validation at 5 bp", ""])
    lines.extend(_table(book, "h2_2025", 5))
    lines.extend(["", "## 2026 at 2 bp", ""])
    lines.extend(_table(book, "from_2026", 2))
    lines.extend(["", "## 2026 at 5 bp", ""])
    lines.extend(_table(book, "from_2026", 5))
    lines.extend(["", "## Incremental value on validation", ""])
    for row in payload["increments"]:
        lines.append(f"- {row['name']}: 2 bp {row['pnl_2bp']}, 5 bp {row['pnl_5bp']} ({row['label']})")
    lines.extend(["", "## Candidate funnel", "", "| Stage | Candidates | Remaining | Trades |", "| --- | ---: | ---: | ---: |"])
    for stage in payload["funnel"]:
        lines.append(f"| {stage['label']} | {stage['candidates']} | {stage['percent_remaining']} | {stage['trades'] if stage['trades'] is not None else ''} |")
    lines.extend(["", "## Entry depth", ""])
    for block in payload["depth"]:
        lines.append(f"### {block['strategy']} {block['kind']}")
        lines.append("")
        lines.append("| Bucket | Trades | Win rate | Avg return | Median return | Net 2 bp | Net 5 bp |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in block["rows"]:
            lines.append(
                f"| {row['bucket']} | {row['trades']} | {_fmt(row['win_rate'], 'pct')} | {_fmt(row['avg_return_pct'])} | {_fmt(row['median_return_pct'])} | {row['net_pnl_2bp']} | {row['net_pnl_5bp']} |"
            )
        lines.append("")
    lines.extend(["## Stock concentration at 2 bp", ""])
    for name, block in payload["concentration"].items():
        leaders = ", ".join(f"{row['symbol']} {row['net_pnl']}" for row in block["top10"][:10])
        laggards = ", ".join(f"{row['symbol']} {row['net_pnl']}" for row in block["bottom10"])
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- Top 1 share of net: {_fmt(block['top1_share_of_net'], 'share')}")
        lines.append(f"- Top 5 share of net: {_fmt(block['top5_share_of_net'], 'share')}")
        lines.append(f"- Top 10 share of net: {_fmt(block['top10_share_of_net'], 'share')}")
        lines.append(f"- Top 10: {leaders}")
        lines.append(f"- Bottom 10: {laggards}")
        lines.append("")
    lines.extend(["## Yearly stability", "", "| Strategy | Year | Trades | Net 2 bp | Net 5 bp | Win rate | Expectancy |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in payload["years"]:
        lines.append(
            f"| {row['strategy']} | {row['year']} | {row['trades']} | {row['net_2bp']} | {row['net_5bp']} | {_fmt(row['win_rate'], 'pct')} | {row['expectancy']} |"
        )
    lines.extend(["", "## Monthly stability at 2 bp", ""])
    for name, block in payload["monthly"].items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- Positive months: {block['positive_months']}")
        lines.append(f"- Negative months: {block['negative_months']}")
        lines.append(f"- Longest winning streak: {block['longest_winning_streak']}")
        lines.append(f"- Longest losing streak: {block['longest_losing_streak']}")
        lines.append("")
    audit = payload["audit"]
    lines.extend(["## Look-ahead", "", f"Status: {audit['status']}", f"Unresolved exits: {audit['unresolved_count']}", ""])
    for check in audit["checks"]:
        lines.append(f"- {check['status']}: {check['item']}")
    lines.extend(["", "## Reproduce", "", "```", "python scripts/backtest_rebound_isolation.py", "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _public_book(book: dict) -> dict:
    exported = {}
    for (strategy, bps), summary in book.items():
        exported[f"{strategy}|{bps}"] = {
            "full": _compact(summary),
            "splits": {name: _compact(split) for name, split in summary["splits"].items()},
            "years": {year: _compact(row) for year, row in summary["years"].items()},
        }
    return exported


def main() -> None:
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(0))
    by_symbol: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_symbol[bar.symbol].append(bar)
    raw: list[dict] = []
    funnel = {stage: 0 for stage, _, _ in FUNNEL_STAGES}
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
        raw.extend(simulate_symbol(symbol, bars, symbol_daily, variants=VARIANTS, modes=("delivery",)))
        for stage, count in count_funnel(symbol, bars, symbol_daily).items():
            funnel[stage] += count
        print(f"{index}/{len(chosen)} {symbol}", flush=True)
    audit = lookahead_audit(raw)
    priced: dict[int, list[dict]] = {}
    book: dict[tuple[str, int], dict] = {}
    id_by_variant = {variant: name for name, variant, _ in STRATEGIES}
    for bps in COST_BPS:
        rows = [price_trade(trade, bps) for trade in raw]
        priced[int(bps)] = rows
        for name, variant, _ in STRATEGIES:
            subset = [trade for trade in rows if trade["variant"] == variant]
            book[(name, int(bps))] = enrich(subset, paths=int(bps) == 2)
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    mismatches = []
    for name, variant in FROZEN_KEYS.items():
        old = frozen["results"][f"delivery|{variant}|2"]
        new = book[(name, 2)]
        if old["trades"] != new["trades"] or old["net_pnl"] != new["net_pnl"]:
            mismatches.append(
                {
                    "strategy": name,
                    "variant": variant,
                    "frozen_trades": old["trades"],
                    "replay_trades": new["trades"],
                    "frozen_net": old["net_pnl"],
                    "replay_net": new["net_pnl"],
                }
            )
    OUT.mkdir(parents=True, exist_ok=True)
    if mismatches or not audit["valid"]:
        (OUT / "lookahead.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
        (OUT / "divergence.json").write_text(json.dumps({"mismatches": mismatches, "audit": audit["status"]}, indent=2), encoding="utf-8")
        reason = "Replay diverged from the frozen delivery summary." if mismatches else "Look-ahead audit failed."
        (OUT / "report.md").write_text(f"# Delivery condition isolation\n\nExperiment stopped. {reason}\n", encoding="utf-8")
        print(reason, flush=True)
        raise SystemExit(1)
    validation_2 = {name: _net(_slice(book, name, 2, "h2_2025")) for name, _, _ in STRATEGIES}
    others = [name for name, _, _ in STRATEGIES if name not in {"A", "E"}]
    strongest = max(others, key=validation_2.get)
    increments = []
    pairs = (
        ("EMA distance, B - A", "B", "A", "ema_distance"),
        ("Down days, C - A", "C", "A", "down_days"),
        ("-12% boundary, D - B", "D", "B", "upper_bound"),
        ("Combined filters, E - A", "E", "A", "combined"),
    )
    labels = {
        "today_drop": _label(_net(_slice(book, "A", 2, "h2_2025")), _net(_slice(book, "A", 5, "h2_2025"))),
    }
    for title, left, right, key in pairs:
        pnl_2 = _net(_slice(book, left, 2, "h2_2025")) - _net(_slice(book, right, 2, "h2_2025"))
        pnl_5 = _net(_slice(book, left, 5, "h2_2025")) - _net(_slice(book, right, 5, "h2_2025"))
        label = _label(pnl_2, pnl_5)
        if key != "combined":
            labels[key] = label
        increments.append({"name": title, "pnl_2bp": f"{pnl_2:.2f}", "pnl_5bp": f"{pnl_5:.2f}", "label": label})
    eligible = funnel["eligible"] or 1
    trade_counts = {name: book[(name, 2)]["trades"] for name, _, _ in STRATEGIES}
    funnel_rows = []
    for stage, label, strategy in FUNNEL_STAGES:
        count = funnel[stage]
        funnel_rows.append(
            {
                "stage": stage,
                "label": label,
                "candidates": count,
                "percent_remaining": round(count / eligible * 100, 2),
                "trades": None if strategy is None else trade_counts[strategy],
            }
        )
    depth_names = ["A", "E", strongest]
    depth = []
    for name in dict.fromkeys(depth_names):
        variant = next(variant for strategy, variant, _ in STRATEGIES if strategy == name)
        trades_2 = [trade for trade in priced[2] if trade["variant"] == variant]
        trades_5 = [trade for trade in priced[5] if trade["variant"] == variant]
        depth.append({"strategy": name, "kind": "today drop", "rows": _depth(trades_2, trades_5, _drop_bucket, DROP_LABELS)})
        depth.append({"strategy": name, "kind": "EMA distance", "rows": _depth(trades_2, trades_5, _ema_bucket, EMA_LABELS)})
    concentration = {name: _concentration(book[(name, 2)]) for name, _, _ in STRATEGIES}
    years = []
    for name, _, _ in STRATEGIES:
        for year in ("2024", "2025", "2026"):
            at_2 = book[(name, 2)]["years"].get(year, {})
            at_5 = book[(name, 5)]["years"].get(year, {})
            years.append(
                {
                    "strategy": name,
                    "year": year,
                    "trades": at_2.get("trades", 0),
                    "net_2bp": at_2.get("net_pnl"),
                    "net_5bp": at_5.get("net_pnl"),
                    "win_rate": at_2.get("win_rate"),
                    "expectancy": at_2.get("expectancy"),
                }
            )
    monthly = {name: _streaks(book[(name, 2)].get("monthly_pnl", {})) for name in dict.fromkeys(["A", "E", strongest])}
    recommendation = _recommend(book, labels)
    question = (
        "What condition actually contributes to the observed delivery performance? "
        f"Today's drop is {labels['today_drop']}. "
        f"Being at least 5% below the EMA is {labels['ema_distance']}. "
        f"The -12% cap is {labels['upper_bound']}. "
        f"Three completed down days are {labels['down_days']}."
    )
    payload = {
        "book": book,
        "recommendation": recommendation,
        "question": question,
        "labels": {
            "Today's >=1% drop": labels["today_drop"],
            ">=5% below EMA": labels["ema_distance"],
            "<=12% below EMA": labels["upper_bound"],
            ">=3 consecutive down days": labels["down_days"],
        },
        "increments": increments,
        "funnel": funnel_rows,
        "depth": depth,
        "concentration": concentration,
        "years": years,
        "monthly": monthly,
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
        "holdout_opened": False,
        "frozen_summary_checked": True,
        "strongest_other_strategy": strongest,
    }
    with (OUT / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for bps, rows in priced.items():
            for trade in rows:
                record = trade_record(trade)
                record["strategy"] = id_by_variant[trade["variant"]]
                handle.write(json.dumps(record) + "\n")
    (OUT / "summary.json").write_text(
        json.dumps(
            {
                "meta": meta,
                "recommendation": recommendation,
                "labels": payload["labels"],
                "increments": increments,
                "question": question,
                "results": _public_book(book),
                "concentration": concentration,
                "years": years,
                "monthly": monthly,
                "depth": depth,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "funnel.json").write_text(json.dumps(funnel_rows, indent=2), encoding="utf-8")
    (OUT / "lookahead.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    _write_report(OUT / "report.md", payload)
    print(recommendation["code"], recommendation["decision"], audit["status"], flush=True)


if __name__ == "__main__":
    main()
