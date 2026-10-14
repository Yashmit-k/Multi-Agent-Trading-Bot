"""Loss attribution, time exits, leave-one-out, and an announcement entry block.

Every run starts from the frozen combined book at 5 bps. The script stops if
that book does not reproduce. Does not open the holdout, place orders, or
change paper execution.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

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
from quant_agents.research.combined_three import BookConfig, _days, measure, passes, simulate_symbol
from quant_agents.research.rebound import session_date

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
SNAPSHOT_5M = "nifty50_5m_20261005"
SNAPSHOT_1D = "nifty50_1d_20261005"
SLIPPAGE = Decimal("5")
EXPECTED_TOTAL = Decimal("126128.22")
IST = ZoneInfo("Asia/Kolkata")
TAPE = ROOT / "datasets" / "h001-pit-events-nse-ann-2024-2025-v1.parquet"
TAPE_MANIFEST = ROOT / "datasets" / "h001-pit-events-nse-ann-2024-2025-v1.manifest.json"
TAPE_LAST_DAY = date(2025, 12, 31)
OUT = ROOT / "datasets" / "research" / "combined_three"
CENT = Decimal("0.01")
HOLD_BUCKETS = ((0, 30, "under 30 days"), (30, 90, "30–89 days"), (90, 180, "90–179 days"), (180, 365, "180–364 days"), (365, 100000, "365 days or more"))


def symbols_from_manifest() -> tuple[str, ...]:
    manifest = json.loads((ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json").read_text(encoding="utf-8"))
    return tuple(row["symbol"] for row in manifest["symbols"] if row["symbol"] != "TATAMOTORS" and int(row["count"]) > 0)


def _money(value: object) -> str:
    return format(Decimal(str(value)).quantize(CENT), "f")


def _frozen(name: str, **changes: object) -> BookConfig:
    return BookConfig(name=name, slippage_bps=SLIPPAGE, wide_retrace=False, ema_band=Decimal("2"), **changes)


def run_book(config: BookConfig, symbols, by_intraday, by_daily, announcements=None) -> dict:
    closed: list[dict] = []
    marks: list[dict] = []
    paths: list[list[dict]] = []
    blocked: list[dict] = []
    for symbol in symbols:
        path: list[dict] = []
        symbol_closed, symbol_marks = simulate_symbol(
            symbol,
            by_intraday.get(symbol, []),
            by_daily.get(symbol, []),
            config,
            path=path,
            announcements=None if announcements is None else announcements.get(symbol, []),
            blocked=blocked,
        )
        closed.extend(symbol_closed)
        marks.extend(symbol_marks)
        paths.append(path)
    return {"metrics": measure(closed, marks, paths), "closed": closed, "marks": marks, "blocked": blocked}


def _bucket(days: Decimal) -> str:
    for low, high, label in HOLD_BUCKETS:
        if low <= days < high:
            return label
    return HOLD_BUCKETS[-1][2]


def _band(value: Decimal | None, edges: list[Decimal]) -> str:
    if value is None:
        return "missing"
    for low, high in zip(edges, edges[1:]):
        if low <= value < high:
            return f"{low} to {high}"
    if value == edges[-1]:
        return f"{edges[-2]} to {edges[-1]}"
    return "outside"


def _group(closed: list[dict], marks: list[dict], key) -> list[dict]:
    rows: dict[str, dict] = defaultdict(
        lambda: {"closed": 0, "realized": Decimal("0"), "open": 0, "unrealized": Decimal("0"), "open_notional": Decimal("0")}
    )
    for row in closed:
        label = key(row, False)
        if label is None:
            continue
        rows[label]["closed"] += 1
        rows[label]["realized"] += row["net_pnl"]
    for row in marks:
        label = key(row, True)
        if label is None:
            continue
        rows[label]["open"] += 1
        rows[label]["unrealized"] += row["unrealized_net"]
        rows[label]["open_notional"] += row["entry_notional"]
    out = []
    for label, values in rows.items():
        out.append({"label": label, **values, "total": values["realized"] + values["unrealized"]})
    return out


def _group_table(title: str, rows: list[dict], order: list[str] | None = None, limit: int | None = None) -> list[str]:
    if order is not None:
        rank = {label: index for index, label in enumerate(order)}
        rows = sorted(rows, key=lambda row: rank.get(row["label"], len(rank)))
    else:
        rows = sorted(rows, key=lambda row: row["total"])
    if limit is not None:
        rows = rows[:limit]
    lines = [
        f"### {title}",
        "",
        "| Group | Closed slices | Realized | Open lots | Unrealized | Total | Open notional |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['closed']} | {_money(row['realized'])} | {row['open']} | "
            f"{_money(row['unrealized'])} | {_money(row['total'])} | {_money(row['open_notional'])} |"
        )
    lines.append("")
    return lines


def _hold(row: dict, is_open: bool) -> Decimal:
    return _days(row["entry_time"], row["mark_time"] if is_open else row["exit_time"])


def attribution(closed: list[dict], marks: list[dict]) -> tuple[list[str], dict]:
    by_algo = _group(closed, marks, lambda row, _o: row["algo"] if row["algo"] != "dip" else f"dip tranche {row['tranche']}")
    by_symbol = _group(closed, marks, lambda row, _o: row["symbol"])
    by_reason = _group(closed, [], lambda row, _o: row["exit_reason"])
    by_hold = _group(closed, marks, lambda row, is_open: f"{'open' if is_open else 'closed'}, {_bucket(_hold(row, is_open))}")
    by_open_age_algo = _group([], marks, lambda row, _o: f"{row['algo']}, {_bucket(_hold(row, True))}")
    wide_gain = _group(
        closed, marks, lambda row, _o: None if row["algo"] != "wide" else _band(row["entry_gain"], [Decimal(1), Decimal(2), Decimal(3), Decimal(4)])
    )
    narrow_gain = _group(
        closed,
        marks,
        lambda row, _o: None if row["algo"] != "narrow" else _band(row["entry_gain"], [Decimal("0.50"), Decimal("0.60"), Decimal("0.75")]),
    )
    narrow_ema = _group(
        closed,
        marks,
        lambda row, _o: None if row["algo"] != "narrow" else _band(row["entry_ema_distance"], [Decimal(-2), Decimal(-1), Decimal(0), Decimal(1), Decimal(2)]),
    )
    dip_ema = _group(
        closed,
        marks,
        lambda row, _o: None if row["algo"] != "dip" else _band(row["entry_ema_distance"], [Decimal(-12), Decimal(-10), Decimal(-8), Decimal(-5)]),
    )
    dip_streak = _group(
        closed,
        marks,
        lambda row, _o: None if row["algo"] != "dip" else ("6 or more" if (row["entry_down_days"] or 0) >= 6 else str(row["entry_down_days"])),
    )
    hold_order = [f"{state}, {label}" for state in ("closed", "open") for _l, _h, label in HOLD_BUCKETS]
    age_order = [f"{algo}, {label}" for algo in ("wide", "narrow", "dip") for _l, _h, label in HOLD_BUCKETS]
    lines: list[str] = []
    lines += _group_table("By strategy", by_algo, ["wide", "narrow", "dip tranche 1", "dip tranche 2"])
    lines += _group_table("By holding time", by_hold, hold_order)
    lines += _group_table("Open lots by strategy and age", by_open_age_algo, age_order)
    lines += _group_table("By exit reason, closed slices only", by_reason)
    lines += _group_table("Ten weakest symbols", by_symbol, limit=10)
    lines += _group_table("Wide by day gain at the signal, percent", wide_gain)
    lines += _group_table("Narrow by day gain at the signal, percent", narrow_gain)
    lines += _group_table("Narrow by distance from the prior EMA20, percent", narrow_ema)
    lines += _group_table("Dip by distance from the prior EMA20, percent", dip_ema)
    lines += _group_table("Dip by completed down days", dip_streak, ["3", "4", "5", "6 or more"])
    losers = sum(1 for row in by_symbol if row["total"] < 0)
    payload = {
        "by_strategy": by_algo,
        "by_holding_time": by_hold,
        "open_by_strategy_and_age": by_open_age_algo,
        "by_exit_reason": by_reason,
        "by_symbol": by_symbol,
        "wide_day_gain": wide_gain,
        "narrow_day_gain": narrow_gain,
        "narrow_ema_distance": narrow_ema,
        "dip_ema_distance": dip_ema,
        "dip_down_days": dip_streak,
        "losing_symbols": losers,
    }
    return lines, payload


def _entries(closed: list[dict], marks: list[dict]) -> dict[tuple[str, int], int]:
    seen: set[tuple] = set()
    counts: dict[tuple[str, int], int] = defaultdict(int)
    for row in closed + marks:
        key = (row["symbol"], row["algo"], row["tranche"], str(row["entry_time"]))
        if key in seen:
            continue
        seen.add(key)
        counts[(row["algo"], session_date(row["entry_time"]).year)] += 1
    return counts


def _by_entry_year(closed: list[dict], marks: list[dict]) -> dict[int, Decimal]:
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for row in closed:
        totals[session_date(row["entry_time"]).year] += row["net_pnl"]
    for row in marks:
        totals[session_date(row["entry_time"]).year] += row["unrealized_net"]
    return totals


def load_tape(symbols: tuple[str, ...]) -> tuple[dict[str, list[datetime]] | None, dict]:
    check: dict[str, object] = {"parquet": TAPE.exists(), "manifest": TAPE_MANIFEST.exists()}
    if not (TAPE.exists() and TAPE_MANIFEST.exists()):
        check["status"] = "not run: tape or manifest missing"
        return None, check
    import pyarrow.parquet as pq

    manifest = json.loads(TAPE_MANIFEST.read_text(encoding="utf-8"))
    table = pq.read_table(TAPE, columns=["symbol", "available_at", "exchdisstime_raw"]).to_pylist()
    chosen = set(symbols)
    used: dict[str, list[datetime]] = defaultdict(list)
    outside = 0
    bad = 0
    late = 0
    for row in table:
        if row["symbol"] not in chosen:
            outside += 1
            continue
        try:
            raw = datetime.strptime(row["exchdisstime_raw"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
            stamped = datetime.fromisoformat(row["available_at"])
        except (TypeError, ValueError):
            bad += 1
            continue
        if raw != stamped:
            bad += 1
            continue
        if raw.date() > TAPE_LAST_DAY:
            late += 1
        used[row["symbol"]].append(raw.astimezone(timezone.utc))
    check.update(
        {
            "manifest_rows": manifest.get("row_count"),
            "rows_read": len(table),
            "rows_used": sum(len(times) for times in used.values()),
            "symbols_used": len(used),
            "rows_outside_universe": outside,
            "rows_unparseable_or_mismatched": bad,
            "rows_after_2025": late,
            "dataset_version": manifest.get("dataset_version"),
        }
    )
    if bad or late or manifest.get("row_count") != len(table):
        check["status"] = "not run: point-in-time check failed"
        return None, check
    check["status"] = "passed"
    return dict(used), check


def _row(name: str, metrics: dict, kept: str) -> str:
    def days(value: object) -> str:
        return "" if value in (None, "") else format(Decimal(str(value)).quantize(CENT), "f")

    return (
        f"| {name} | {_money(metrics['total_net'])} | {_money(metrics['realized_net'])} | {_money(metrics['unrealized_net'])} | "
        f"{_money(metrics['max_drawdown'])} | {_money(metrics['average_open_notional'])} | {_money(metrics['ending_open_notional'])} | "
        f"{metrics['open_positions']} | {days(metrics['median_closed_hold_days'])} | {days(metrics['max_closed_hold_days'])} | "
        f"{days(metrics['median_open_hold_days'])} | {days(metrics['max_open_hold_days'])} | {kept} |"
    )


def _delta(run: dict, base: dict, key: str) -> str:
    return _money(Decimal(str(run[key])) - Decimal(str(base[key])))


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

    base_run = run_book(_frozen("combined"), chosen, by_intraday, by_daily)
    base = base_run["metrics"]
    reproduced = Decimal(base["total_net"]).quantize(CENT)
    print("baseline", reproduced, flush=True)
    if reproduced != EXPECTED_TOTAL:
        (OUT / "loss_review.md").write_text(
            f"# Loss review stopped\n\nThe frozen combined book returned {reproduced}, not {EXPECTED_TOTAL}. No experiment was run.\n",
            encoding="utf-8",
        )
        raise SystemExit(f"baseline drifted: {reproduced}")

    attribution_lines, attribution_payload = attribution(base_run["closed"], base_run["marks"])

    experiments = [
        _frozen("time_exit_90", time_exit_days=90),
        _frozen("time_exit_180", time_exit_days=180),
        _frozen("no_wide", wide_enabled=False),
        _frozen("no_narrow", narrow_enabled=False),
        _frozen("no_dip", dip_enabled=False),
    ]
    results: list[tuple[str, dict, str, dict]] = []
    for config in experiments:
        run = run_book(config, chosen, by_intraday, by_daily)
        keep = "yes" if passes(run["metrics"], base) else "no"
        time_exits = [row for row in run["closed"] if row["exit_reason"] == "time_exit"]
        extra = {
            "time_exits": len(time_exits),
            "time_exit_net": format(sum((row["net_pnl"] for row in time_exits), Decimal("0")), "f"),
            "due_at_end": sum(1 for row in run["marks"] if row.get("exit_due") is not None),
        }
        results.append((config.name, run["metrics"], keep, extra))
        print(config.name, run["metrics"]["total_net"], keep, flush=True)

    tape, tape_check = load_tape(chosen)
    news: dict | None = None
    if tape is not None:
        run = run_book(_frozen("news_block", news_block=True), chosen, by_intraday, by_daily, tape)
        keep = "yes" if passes(run["metrics"], base) else "no"
        blocked: dict[tuple[str, int], int] = defaultdict(int)
        for row in run["blocked"]:
            blocked[(row["algo"], row["session"].year)] += 1
        news = {
            "metrics": run["metrics"],
            "kept": keep,
            "blocked": blocked,
            "entries_base": _entries(base_run["closed"], base_run["marks"]),
            "entries_news": _entries(run["closed"], run["marks"]),
            "year_base": _by_entry_year(base_run["closed"], base_run["marks"]),
            "year_news": _by_entry_year(run["closed"], run["marks"]),
        }
        results.append(("news_block", run["metrics"], keep, {"blocked": len(run["blocked"])}))
        print("news_block", run["metrics"]["total_net"], keep, flush=True)

    passing = [(name, metrics) for name, metrics, keep, _extra in results if keep == "yes"]
    winner = max(passing, key=lambda item: Decimal(item[1]["total_net"]))[0] if passing else None

    lines = [
        "# Loss review on the frozen combined book",
        "",
        "Frozen book: Wide without the pullback exit, Narrow within ±2% of the prior EMA20, baseline Dip. Every run uses 5 bps slippage through `slipped_price`, the Zerodha charge table, ₹20,000 per order, and ₹40,000 open notional per symbol. Window 2024-01-01 through 2026-10-05 on `nifty50_5m_20261005` and `nifty50_1d_20261005`, 49 symbols, TATAMOTORS excluded. The holdout was not opened.",
        "",
        f"Baseline reproduction: total net {reproduced}, expected {EXPECTED_TOTAL}. Reproduced.",
        "",
        "A change is kept only when total net is higher, average open notional is not higher, and maximum drawdown is not worse. Each experiment changes one setting from the reproduced baseline.",
        "",
        "## Loss attribution",
        "",
        "Realized is net after charges and slippage on closed slices. Unrealized is the open lot marked at the snapshot close after 5 bps and sell charges. Holding time for open lots is measured to that mark.",
        "",
        f"{attribution_payload['losing_symbols']} of {len(chosen)} symbols have a negative total.",
        "",
        *attribution_lines,
        "## Experiments",
        "",
        "Time exits are decided on the 15:15 bar once a lot is at least the stated number of calendar days old. The sale fills on the first bar of the next session at its open, less 5 bps, with the applicable charges, including when that sale loses money. A lot whose next session is past the snapshot stays open and is marked.",
        "",
        "| Book | Total net | Realized | Unrealized | Max drawdown | Average open notional | Ending open notional | Open positions | Median closed hold | Max closed hold | Median open hold | Max open hold | Kept |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        _row("frozen combined", base, "baseline"),
    ]
    for name, metrics, keep, _extra in results:
        lines.append(_row(name, metrics, keep))
    lines += [
        "",
        "| Book | Change in total net | Change in max drawdown | Change in average open notional | Change in ending open notional | Detail |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, metrics, _keep, extra in results:
        if "time_exits" in extra and extra["time_exits"]:
            detail = f"{extra['time_exits']} time exits, net {_money(extra['time_exit_net'])}; {extra['due_at_end']} marked but not yet sold at the end"
        elif "blocked" in extra:
            detail = f"{extra['blocked']} blocked signals"
        else:
            detail = ""
        lines.append(
            f"| {name} | {_delta(metrics, base, 'total_net')} | {_delta(metrics, base, 'max_drawdown')} | "
            f"{_delta(metrics, base, 'average_open_notional')} | {_delta(metrics, base, 'ending_open_notional')} | {detail} |"
        )
    lines += ["", "## Announcement entry block", ""]
    lines.append(
        f"Tape check: {tape_check['status']}. "
        + ", ".join(f"{key} {value}" for key, value in tape_check.items() if key != "status")
        + "."
    )
    lines.append("")
    if news is not None:
        lines += [
            "A new lot is not opened when the symbol has an NSE corporate announcement whose dissemination time is at or before the signal bar on the same session. A later announcement is invisible to that signal. No subject filter and no text are used. A signal blocked on several bars of one session counts once.",
            "",
            "The tape ends on 2025-12-31. Entries in 2026 are unfiltered, so the 2026 rows are not evidence for or against the filter. The conclusion below uses 2024 and 2025 only.",
            "",
            "| Strategy | Year | Blocked signals | Entries, baseline | Entries, with block |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for algo in ("wide", "narrow", "dip"):
            for year in (2024, 2025, 2026):
                lines.append(
                    f"| {algo} | {year} | {news['blocked'].get((algo, year), 0)} | "
                    f"{news['entries_base'].get((algo, year), 0)} | {news['entries_news'].get((algo, year), 0)} |"
                )
        lines += [
            "",
            "Net by entry year, realized plus open marks, assigned to the year the lot was bought:",
            "",
            "| Entry year | Baseline | With block | Change |",
            "| ---: | ---: | ---: | ---: |",
        ]
        for year in (2024, 2025, 2026):
            before = news["year_base"].get(year, Decimal("0"))
            after = news["year_news"].get(year, Decimal("0"))
            lines.append(f"| {year} | {_money(before)} | {_money(after)} | {_money(after - before)} |")
        validated = sum(news["year_news"].get(y, Decimal("0")) - news["year_base"].get(y, Decimal("0")) for y in (2024, 2025))
        lines += [
            "",
            f"Change in net on 2024 and 2025 entries: {_money(validated)}. Lots bought in 2024 and 2025 can still be open in 2026, and the shared ₹40,000 cap carries effects into later entries, so this split is a guide, not a clean partition.",
            "",
        ]
    lines += ["## Recommendation", ""]
    if winner is None:
        lines.append("No candidate passed the keep rule. The frozen combined book stays the configuration.")
    else:
        lines.append(f"`{winner}` passed the keep rule with the highest total net and is the next change to carry forward.")
    lines.append("")
    lines.append("Research only. Nothing here changes paper execution or places an order.")
    lines.append("")
    (OUT / "loss_review.md").write_text("\n".join(lines), encoding="utf-8")

    def plain(value: object) -> object:
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {(k if isinstance(k, str) else "|".join(map(str, k)) if isinstance(k, tuple) else str(k)): plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        return value

    payload = {
        "baseline": base,
        "reproduced": str(reproduced),
        "attribution": attribution_payload,
        "experiments": [{"name": n, "metrics": m, "kept": k, "detail": e} for n, m, k, e in results],
        "tape_check": tape_check,
        "news": None if news is None else {key: value for key, value in news.items() if key != "metrics"},
        "recommendation": winner,
    }
    (OUT / "loss_review.json").write_text(json.dumps(plain(payload), indent=2), encoding="utf-8")
    print("recommendation", winner, flush=True)


if __name__ == "__main__":
    main()
