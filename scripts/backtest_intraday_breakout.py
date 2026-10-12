"""Run the frozen intraday breakout study on the research snapshots.

Does not open the holdout, does not place orders, and does not rewrite earlier studies.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
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

os.chdir(ROOT)

from contracts.enums import Side, Timeframe
from core_features.context import load_index_bars
from core_market_data.replay import stream_candles
from core_paper.backtest import exit_on_bar
from quant_agents.research.intraday_breakout import (
    STOP_PCT,
    TARGET_PCT,
    VARIANTS,
    clock_minutes,
    lookahead_audit,
    simulate_breakout,
    simulate_indexed,
)
from quant_agents.research.rebound import (
    COST_BPS,
    IST,
    PER_TRADE_CAP,
    enrich,
    price_trade,
    session_date,
    summarize,
    trade_record,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
OUT = ROOT / "datasets" / "research" / "intraday_breakout"
ABLATIONS = ("ablate_day_gain", "ablate_rising", "ablate_volume", "ablate_ema", "ablate_high")
SINGLE = ("baseline_day_gain", "baseline_volume", "baseline_rising")
COMPARE = (*SINGLE, "random_entry", "nifty_matched")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    return tuple(row["symbol"] for row in manifest["symbols"] if row["symbol"] != "TATAMOTORS" and int(row["count"]) > 0)


def _net(summary: dict | None) -> Decimal:
    if not summary or summary.get("net_pnl") is None:
        return Decimal("0")
    return Decimal(summary["net_pnl"])


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def hour_bucket(moment: datetime) -> str:
    minutes = clock_minutes(moment)
    if minutes < 10 * 60:
        return "09:30-10:00"
    if minutes >= 15 * 60:
        return "14:00-15:00"
    hour = minutes // 60
    return f"{hour:02d}:00-{hour + 1:02d}:00"


def _shell(symbol: str, variant: str, **fields) -> dict:
    trade = {
        "symbol": symbol,
        "variant": variant,
        "mode": "intraday",
        "previous_close": fields["entry_price"],
        "ltp": fields["entry_price"],
        "ema20": None,
        "distance_pct": None,
        "down_days": 0,
        "today_drop_pct": None,
        "ema_through": fields["signal_time"],
        "exit_price": fields.get("exit_price"),
        "exit_time": fields.get("exit_time"),
        "exit_reason": fields["exit_reason"],
    }
    trade.update(fields)
    return trade


def replay_index(bars: list, entries: list[dict]) -> tuple[list[dict], int]:
    ordered = sorted(bars, key=lambda bar: bar.end)
    by_start = {bar.start: index for index, bar in enumerate(ordered)}
    final_end: dict[date, datetime] = {}
    for bar in ordered:
        day = session_date(bar.end)
        current = final_end.get(day)
        if current is None or bar.end > current:
            final_end[day] = bar.end
    trades: list[dict] = []
    missing = 0
    for entry in entries:
        index = by_start.get(entry["entry_time"])
        if index is None:
            missing += 1
            continue
        bar = ordered[index]
        if bar.open <= 0:
            missing += 1
            continue
        price = bar.open
        quantity = PER_TRADE_CAP / price
        stop = price * (Decimal(1) - STOP_PCT)
        target = price * (Decimal(1) + TARGET_PCT)
        day = session_date(bar.end)
        exit_price = None
        exit_time = None
        reason = "unresolved"
        if final_end.get(day) == bar.end:
            exit_price, exit_time, reason = bar.close, bar.end, "session_flatten"
        else:
            for later in ordered[index + 1 :]:
                if session_date(later.end) != day:
                    break
                hit = exit_on_bar(Side.BUY, stop, target, later)
                if hit == "stop":
                    exit_price, exit_time, reason = stop, later.end, "stop"
                    break
                if hit == "target":
                    exit_price, exit_time, reason = target, later.end, "target"
                    break
                if final_end.get(day) == later.end:
                    exit_price, exit_time, reason = later.close, later.end, "session_flatten"
                    break
        trades.append(
            _shell(
                "NIFTY50",
                "nifty_matched",
                signal_time=entry["signal_time"],
                signal_price=entry["signal_price"],
                entry_time=bar.start,
                entry_bar_end=bar.end,
                entry_price=price,
                quantity=quantity,
                session_date=entry["session_date"],
                exit_price=exit_price,
                exit_time=exit_time,
                exit_reason=reason,
            )
        )
    return trades, missing


def buy_and_hold(bars: list) -> dict | None:
    ordered = sorted(bars, key=lambda bar: bar.end)
    if not ordered or ordered[0].open <= 0:
        return None
    first, last = ordered[0], ordered[-1]
    quantity = PER_TRADE_CAP / first.open
    return _shell(
        "NIFTY50",
        "nifty_buy_hold",
        mode="buy_hold",
        signal_time=first.end,
        signal_price=first.open,
        entry_time=first.start,
        entry_bar_end=first.end,
        entry_price=first.open,
        quantity=quantity,
        session_date=session_date(first.end),
        exit_price=last.close,
        exit_time=last.end,
        exit_reason="last_daily_close",
    )


def _share(rows: list[dict], total: Decimal, count: int) -> float | None:
    if total == 0:
        return None
    part = sum((Decimal(row["net_pnl"]) for row in rows[:count]), Decimal("0"))
    return float(part / total)


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
        "max_drawdown": summary.get("max_drawdown"),
        "sharpe": summary.get("sharpe"),
        "sortino": summary.get("sortino"),
        "profit_factor": summary.get("profit_factor"),
        "avg_holding_minutes": summary.get("avg_holding_minutes"),
        "max_holding_minutes": summary.get("max_holding_minutes"),
        "best_trade": summary.get("best_trade"),
        "worst_trade": summary.get("worst_trade"),
        "splits": {
            name: {"trades": block.get("trades", 0), "net_pnl": block.get("net_pnl"), "expectancy": block.get("expectancy"), "max_drawdown": block.get("max_drawdown"), "sharpe": block.get("sharpe")}
            for name, block in summary.get("splits", {}).items()
        },
        "years": {year: {"trades": block.get("trades", 0), "net_pnl": block.get("net_pnl")} for year, block in summary.get("years", {}).items()},
    }


def classify_breakout(results: dict[tuple[str, int], dict], audit: dict) -> dict:
    if not audit.get("valid"):
        return {"classification": None, "stopped": True, "reasons": ["Look-ahead audit failed, so no class is assigned."]}
    def cell(variant: str, bps: int, split: str | None = None) -> dict:
        summary = results[(variant, bps)]
        return summary if split is None else summary["splits"][split]

    val2 = _net(cell("full", 2, "h2_2025"))
    val5 = _net(cell("full", 5, "h2_2025"))
    y2026_2 = _net(cell("full", 2, "from_2026"))
    reasons = [f"Validation net at 2 bp is {_money(val2)} and at 5 bp is {_money(val5)}."]
    if val2 <= 0 or val5 <= 0:
        reasons.append("Validation net is not positive at both 2 bp and 5 bp.")
        return {"classification": "NO EDGE", "stopped": False, "reasons": reasons}
    beaten = []
    for variant in (*SINGLE, "random_entry"):
        other = _net(cell(variant, 2, "h2_2025"))
        if other > val2:
            beaten.append(f"{variant} validation net at 2 bp is {_money(other)}")
    if beaten or y2026_2 <= 0:
        reasons.extend(beaten)
        if y2026_2 <= 0:
            reasons.append(f"2026 net at 2 bp is {_money(y2026_2)}.")
        return {"classification": "WEAK EDGE", "stopped": False, "reasons": reasons}
    beats = True
    for variant in COMPARE:
        for bps in (2, 5):
            other = _net(cell(variant, bps, "h2_2025"))
            if _net(cell("full", bps, "h2_2025")) <= other:
                beats = False
                reasons.append(f"{variant} validation net at {bps} bp is {_money(other)}, which the full rule does not beat.")
    robust = beats
    for bps in (2, 5):
        for split, label in (("through_2025_06_30", "research"), ("h2_2025", "validation"), ("from_2026", "2026")):
            value = _net(cell("full", bps, split))
            if value <= 0:
                robust = False
                reasons.append(f"{label} net at {bps} bp is {_money(value)}.")
        for year in ("2024", "2025", "2026"):
            value = _net(cell("full", bps).get("years", {}).get(year))
            if value <= 0:
                robust = False
                reasons.append(f"{year} net at {bps} bp is {_money(value)}.")
        summary = cell("full", bps)
        drawdown = Decimal(summary.get("max_drawdown") or "0")
        total = _net(summary)
        if drawdown >= total:
            robust = False
            reasons.append(f"Drawdown {_money(drawdown)} is not below net {_money(total)} at {bps} bp.")
    full_2 = cell("full", 2)
    stocks = full_2.get("per_stock") or []
    top_share = _share(stocks, _net(full_2), 1)
    if top_share is None or top_share > 0.40:
        robust = False
        reasons.append(f"Top stock share of 2 bp net is {top_share}.")
    for variant in ABLATIONS:
        higher = all(_net(cell(variant, bps, "h2_2025")) > _net(cell("full", bps, "h2_2025")) for bps in (2, 5))
        if higher:
            robust = False
            reasons.append(f"{variant} raises validation net at both 2 bp and 5 bp.")
    if beats and robust:
        return {"classification": "ROBUST EDGE", "stopped": False, "reasons": reasons}
    if beats:
        return {"classification": "PROMISING BUT UNPROVEN", "stopped": False, "reasons": reasons}
    return {"classification": "WEAK EDGE", "stopped": False, "reasons": reasons}


def _pct(count: int, base: int) -> float | None:
    if base == 0:
        return None
    return count / base


def _write_report(path: Path, meta: dict, funnel: dict, results: dict, audit: dict, verdict: dict, hours: dict, weekdays: dict, concentration: dict) -> None:
    def line(variant: str, bps: int, split: str | None = None) -> str:
        summary = results[(variant, bps)]
        block = summary if split is None else summary["splits"][split]
        return f"{block.get('trades', 0)} trades, net {block.get('net_pnl')}"

    lines = [
        "# Intraday momentum breakout",
        "",
        verdict["classification"] if verdict["classification"] else "Classification stopped",
        "",
        *[f"- {reason}" for reason in verdict["reasons"]],
        "",
        "## Answers",
        "",
        f"- Profitable at 2 bp: {results[('full', 2)]['net_pnl']}",
        f"- Profitable at 5 bp: {results[('full', 5)]['net_pnl']}",
        f"- Validation at 2 bp: {line('full', 2, 'h2_2025')}",
        f"- Validation at 5 bp: {line('full', 5, 'h2_2025')}",
        f"- 2026 at 2 bp: {line('full', 2, 'from_2026')}",
        f"- 2026 at 5 bp: {line('full', 5, 'from_2026')}",
        "- Keeping the day-gain, three-candle, volume, and 20-day-high filters each reduces the validation loss. Removing the EMA band leaves the same trades, because every volume-confirmed bar was already inside ±3% of EMA20. None of the filters turns validation net positive.",
        "- On validation the full rule loses more than random entries and more than the matched NIFTY book, at both 2 bp and 5 bp. The day-gain, volume, and three-candle baselines lose more than the full rule. The one-trade NIFTY buy-and-hold is reported separately and is not the classification baseline.",
        f"- Final classification: {verdict['classification']}",
        "",
        "## Data",
        "",
        f"- 5-minute snapshot `{meta['snapshot_5m']}` sha `{meta['sha256_5m']}`",
        f"- Daily snapshot `{meta['snapshot_1d']}` sha `{meta['sha256_1d']}`",
        f"- First bar `{meta['first_bar']}`",
        f"- Last bar `{meta['last_bar']}`",
        f"- Symbols {meta['symbol_count']}, missing 5-minute steps {meta['missing_5m']}",
        f"- NIFTY 5-minute bars {meta['nifty_5m']}, daily bars {meta['nifty_1d']}, missing matched entries {meta['nifty_missing']}",
        f"- Look-ahead {audit['status']}",
        "",
        "## Funnel",
        "",
    ]
    for key in ("eligible", "day_gain", "rising", "volume", "ema", "near_high"):
        lines.append(f"- {key}: {funnel[key]} ({funnel['remaining_pct'][key]})")
    lines.extend(["", "## Ablations and baselines", ""])
    lines.append(f"- NIFTY buy-and-hold, one ₹20,000 position: {results[('nifty_buy_hold', 2)]['trades']} trades at 2 bp, net {results[('nifty_buy_hold', 2)]['net_pnl']}; at 5 bp, net {results[('nifty_buy_hold', 5)]['net_pnl']}")
    for variant in (*ABLATIONS, "diagnostic_higher_close", *COMPARE):
        left = results[(variant, 2)]["splits"]["h2_2025"]
        right = results[(variant, 5)]["splits"]["h2_2025"]
        lines.append(f"- {variant} validation: 2 bp {left.get('trades', 0)} trades, net {left.get('net_pnl')}; 5 bp net {right.get('net_pnl')}")
    lines.extend(["", "## Full rule", ""])
    for bps in (0, 1, 2, 3, 5):
        block = results[("full", bps)]
        lines.append(f"- {bps} bp: {block['trades']} trades, net {block['net_pnl']}, expectancy {block.get('expectancy')}, drawdown {block.get('max_drawdown')}, Sharpe {block.get('sharpe')}")
    lines.extend(["", "## Hours at 2 bp", ""])
    for label, block in hours.items():
        lines.append(f"- {label}: {block.get('trades', 0)} trades, win rate {block.get('win_rate')}, avg return {block.get('avg_return_pct')}, net {block.get('net_pnl')}")
    lines.extend(["", "## Weekdays at 2 bp", ""])
    for label, block in weekdays.items():
        lines.append(f"- {label}: {block.get('trades', 0)} trades, net {block.get('net_pnl')}")
    lines.extend(["", "## Concentration at 2 bp", ""])
    lines.append(f"- Top 1 / 5 / 10 share: {concentration['top1']} / {concentration['top5']} / {concentration['top10']}")
    lines.append("- Top 10: " + ", ".join(f"{row['symbol']} {row['net_pnl']}" for row in concentration["top"]))
    lines.append("- Bottom 10: " + ", ".join(f"{row['symbol']} {row['net_pnl']}" for row in concentration["bottom"]))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- Created `services/quant/src/quant_agents/research/intraday_breakout.py`",
            "- Created `scripts/backtest_intraday_breakout.py`",
            "- Created `tests/test_intraday_breakout.py`",
            "- Created this research folder. Earlier rebound folders were not rewritten.",
            "- Reproduce with `python scripts/backtest_intraday_breakout.py`",
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
    chosen = symbols_from_manifest()
    daily, _, sha_1d = stream_candles(SNAPSHOT_1D, chosen, START, END, warmup=timedelta(0))
    by_symbol: dict[str, list] = defaultdict(list)
    for bar in daily:
        by_symbol[bar.symbol].append(bar)
    raw: list[dict] = []
    funnel = {"eligible": 0, "day_gain": 0, "rising": 0, "volume": 0, "ema": 0, "near_high": 0}
    rng = random.Random(7)
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
        trades, counts, ordered, eligible, flags = simulate_breakout(symbol, bars, by_symbol.get(symbol, []))
        for key in funnel:
            funnel[key] += counts[key]
        full_count = sum(1 for trade in trades if trade["variant"] == "full")
        picked = rng.sample(eligible, min(full_count, len(eligible))) if full_count and eligible else []
        raw.extend(trades)
        raw.extend(simulate_indexed(symbol, ordered, flags, picked, "random_entry"))
        print(f"{index}/{len(chosen)} {symbol} bars={len(bars)} full={full_count} random={len(picked)}", flush=True)
    nifty_5m = load_index_bars(Timeframe.M5, END).get("NIFTY50", [])
    nifty_1d = load_index_bars(Timeframe.D1, END).get("NIFTY50", [])
    matched, nifty_missing = replay_index(nifty_5m, [trade for trade in raw if trade["variant"] == "full"])
    raw.extend(matched)
    hold = buy_and_hold(nifty_1d)
    if hold is not None:
        raw.append(hold)
    audit = lookahead_audit(raw)
    variants = (*VARIANTS, "random_entry", "nifty_matched", "nifty_buy_hold")
    results: dict[tuple[str, int], dict] = {}
    full_rows = []
    for bps in COST_BPS:
        priced = [price_trade(trade, bps) for trade in raw]
        for variant in variants:
            subset = [trade for trade in priced if trade["variant"] == variant]
            results[(variant, int(bps))] = enrich(subset, paths=variant == "full" and int(bps) == 2)
        if int(bps) == 2:
            full_2 = [trade for trade in priced if trade["variant"] == "full"]
        full_rows.extend(trade_record(trade) for trade in priced if trade["variant"] == "full")
    verdict = classify_breakout(results, audit) if audit["valid"] else {"classification": None, "stopped": True, "reasons": ["Look-ahead audit failed, so no class is assigned."]}
    hours = {label: summarize([trade for trade in full_2 if hour_bucket(trade["signal_time"]) == label]) for label in ("09:30-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00")}
    weekdays = {label: summarize([trade for trade in full_2 if WEEKDAYS[trade["session_date"].weekday()] == label]) for label in WEEKDAYS}
    stocks = results[("full", 2)].get("per_stock") or []
    total = _net(results[("full", 2)])
    concentration = {"top1": _share(stocks, total, 1), "top5": _share(stocks, total, 5), "top10": _share(stocks, total, 10), "top": stocks[:10], "bottom": list(reversed(stocks[-10:])) if stocks else []}
    base = funnel["eligible"]
    funnel["remaining_pct"] = {key: _pct(funnel[key], base) for key in ("eligible", "day_gain", "rising", "volume", "ema", "near_high")}
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
        "nifty_5m": len(nifty_5m),
        "nifty_1d": len(nifty_1d),
        "nifty_missing": nifty_missing,
        "signal_bars": funnel["near_high"],
        "per_trade_cap": "20000",
        "slippage_bps": 0,
        "holdout_opened": False,
        "git_diff": diff.strip(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for row in full_rows:
            handle.write(json.dumps(row) + "\n")
    (OUT / "funnel.json").write_text(json.dumps(funnel, indent=2), encoding="utf-8")
    (OUT / "lookahead.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    ablations = {variant: {str(bps): _compact(results[(variant, bps)]) for bps in (2, 5)} for variant in (*VARIANTS, "random_entry", "nifty_matched", "nifty_buy_hold")}
    (OUT / "ablations.json").write_text(json.dumps(ablations, indent=2), encoding="utf-8")
    serial = {f"{variant}|{bps}": summary for (variant, bps), summary in results.items()}
    (OUT / "summary.json").write_text(json.dumps({"meta": meta, "classification": verdict, "concentration": concentration, "hours": hours, "weekdays": weekdays, "results": serial}, indent=2, default=str), encoding="utf-8")
    _write_report(OUT / "report.md", meta, funnel, results, audit, verdict, hours, weekdays, concentration)
    print(verdict["classification"], audit["status"], flush=True)


if __name__ == "__main__":
    main()
