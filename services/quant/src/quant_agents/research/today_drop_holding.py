"""Forward-return path of the frozen today-drop entries.

The entry rule is Strategy A. These checkpoints do not replace the +5% / -3%
delivery exit, and they are not a search for a new holding period.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import median, quantiles

from contracts.enums import Side
from contracts.schemas.market import Candle
from core_paper.backtest import exit_on_bar
from core_paper.costs import CostSchedule, fee_on, slipped_price

from quant_agents.research.rebound import session_date

HORIZONS = (1, 2, 3, 5, 10, 15, 20)
COST_BPS = (Decimal("0"), Decimal("2"), Decimal("5"))
STOP_PCT = Decimal("0.03")
TARGET_PCT = Decimal("0.05")


def _unique_sessions(bars: list[Candle]) -> list[Candle]:
    chosen: list[Candle] = []
    for bar in sorted(bars, key=lambda item: item.end):
        if chosen and session_date(chosen[-1].end) == session_date(bar.end):
            chosen[-1] = bar
            continue
        chosen.append(bar)
    return chosen


def net_return(entry: Decimal, exit_price: Decimal, quantity: int, bps: Decimal) -> Decimal:
    """Same fee math as price_trade. Slippage stays zero, so the prices do not move."""
    schedule = CostSchedule.research(bps, Decimal("0"))
    filled = slipped_price(Side.BUY, entry, schedule.slippage_bps)
    sold = slipped_price(Side.SELL, exit_price, schedule.slippage_bps)
    notional = filled * quantity
    cost = fee_on(notional, schedule) + fee_on(sold * quantity, schedule)
    return ((sold - filled) * quantity - cost) / notional


def measure_path(trade: dict, bars_5m: list[Candle], bars_1d: list[Candle]) -> dict:
    """Checkpoint returns after the fill. Missing future sessions stay unresolved."""
    entry_time = trade["entry_time"]
    entry_end = trade["entry_bar_end"]
    entry = trade["entry_price"]
    daily = [bar for bar in _unique_sessions(bars_1d) if bar.symbol == trade["symbol"] and bar.end > entry_time]
    five = [bar for bar in bars_5m if bar.symbol == trade["symbol"] and bar.end > entry_end]
    five.sort(key=lambda bar: bar.end)
    stops = trade["stop"]
    target = trade["target"]
    high: Decimal | None = None
    low: Decimal | None = None
    seen_exit: str | None = None
    seen_exit_time: datetime | None = None
    cursor = 0
    checkpoints = []
    for horizon in HORIZONS:
        if horizon > len(daily):
            checkpoints.append({"horizon": horizon, "status": "unresolved", "original_exit": "unresolved"})
            continue
        limit = daily[horizon - 1].end
        while cursor < len(five) and five[cursor].end <= limit:
            bar = five[cursor]
            cursor += 1
            high = bar.high if high is None else max(high, bar.high)
            low = bar.low if low is None else min(low, bar.low)
            if seen_exit is None:
                reason = exit_on_bar(Side.BUY, stops, target, bar)
                if reason is not None:
                    seen_exit = reason
                    seen_exit_time = bar.end
        close = daily[horizon - 1].close
        if seen_exit_time is not None and seen_exit_time <= limit:
            original = seen_exit
        else:
            original = "neither"
        row = {
            "horizon": horizon,
            "status": "resolved",
            "close_time": limit,
            "close": close,
            "gross_return": close / entry - 1,
            "mfe": None if high is None else high / entry - 1,
            "mae": None if low is None else low / entry - 1,
            "original_exit": original,
        }
        for bps in COST_BPS:
            row[f"net_{int(bps)}bp"] = net_return(entry, close, trade["quantity"], bps)
        checkpoints.append(row)
    return {
        "symbol": trade["symbol"],
        "signal_time": trade["signal_time"],
        "entry_time": entry_time,
        "entry_bar_end": entry_end,
        "entry_price": entry,
        "quantity": trade["quantity"],
        "session_date": trade["session_date"],
        "today_drop_pct": trade["today_drop_pct"],
        "previous_close": trade["previous_close"],
        "original_exit_reason": trade["exit_reason"],
        "original_exit_time": trade["exit_time"],
        "year": str(trade["session_date"].year),
        "checkpoints": checkpoints,
        "detected_exit": seen_exit,
        "detected_exit_time": seen_exit_time,
    }


def _numbers(values: list[Decimal]) -> dict:
    if not values:
        return {"observations": 0, "mean": None, "median": None, "win_rate": None, "p25": None, "p75": None}
    ordered = sorted(values)
    middle = quantiles(ordered, n=4, method="inclusive") if len(ordered) >= 2 else [ordered[0], ordered[0]]
    wins = sum(1 for value in ordered if value > 0)
    return {
        "observations": len(ordered),
        "mean": sum(ordered, Decimal("0")) / len(ordered),
        "median": Decimal(str(median(ordered))),
        "win_rate": Decimal(wins) / Decimal(len(ordered)),
        "p25": middle[0],
        "p75": middle[-1],
    }


def _horizon_summary(rows: list[dict], horizon: int) -> dict:
    chosen = []
    exits = {"target": 0, "stop": 0, "neither": 0, "unresolved": 0}
    for row in rows:
        checkpoint = next(item for item in row["checkpoints"] if item["horizon"] == horizon)
        exits[checkpoint["original_exit"]] += 1
        if checkpoint["status"] == "resolved":
            chosen.append(checkpoint)
    summary = {"horizon": horizon, "unresolved": exits["unresolved"], "original_exit": exits}
    summary["gross"] = _numbers([item["gross_return"] for item in chosen])
    for bps in COST_BPS:
        summary[f"net_{int(bps)}bp"] = _numbers([item[f"net_{int(bps)}bp"] for item in chosen])
    summary["mfe"] = _numbers([item["mfe"] for item in chosen if item["mfe"] is not None])
    summary["mae"] = _numbers([item["mae"] for item in chosen if item["mae"] is not None])
    summary["gross"]["observations"] = len(chosen)
    return summary


def summarize_paths(rows: list[dict]) -> dict:
    def block(group: list[dict]) -> dict:
        return {str(horizon): _horizon_summary(group, horizon) for horizon in HORIZONS}

    by_year = {year: block([row for row in rows if row["year"] == year]) for year in ("2024", "2025", "2026")}
    winners = block([row for row in rows if row["original_exit_reason"] == "target"])
    losers = block([row for row in rows if row["original_exit_reason"] == "stop"])
    return {"all": block(rows), "years": by_year, "winners": winners, "losers": losers, "entries": len(rows)}


def stock_table(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["symbol"]].append(row)
    table = {}
    positive: list[str] = []
    negative: list[str] = []
    thin: list[str] = []
    mixed: list[str] = []
    for symbol, group in sorted(grouped.items()):
        horizons = {str(horizon): _horizon_summary(group, horizon) for horizon in HORIZONS}
        table[symbol] = {"trades": len(group), "horizons": horizons}
        medians = []
        enough = True
        for horizon in (1, 5, 20):
            stats = horizons[str(horizon)]["gross"]
            if stats["observations"] < 5 or stats["median"] is None:
                enough = False
                break
            medians.append(stats["median"])
        if not enough:
            thin.append(symbol)
        elif all(value > 0 for value in medians):
            positive.append(symbol)
        elif all(value < 0 for value in medians):
            negative.append(symbol)
        else:
            mixed.append(symbol)
    return {
        "by_symbol": table,
        "consistently_positive": positive,
        "consistently_negative": negative,
        "mixed": mixed,
        "too_thin": thin,
        "rule": "Median gross return is positive, or negative, at 1, 5, and 20 trading days, with at least 5 resolved observations at each. This is a description, not a trading rule.",
    }


def _median(block: dict, horizon: str) -> Decimal | None:
    return block[horizon]["gross"]["median"]


def answer_questions(summary: dict) -> list[str]:
    """Fixed readings of the checkpoints. They do not select a new exit."""
    book = summary["all"]
    early = [_median(book, "1"), _median(book, "2")]
    early_means = [book["1"]["gross"]["mean"], book["2"]["gross"]["mean"]]
    if all(value is not None and value > 0 for value in early + early_means):
        first = "Yes. Before costs, the mean and the median are positive at the first and second daily closes after entry."
        if book["1"]["net_5bp"]["median"] is not None and book["1"]["net_5bp"]["median"] <= 0:
            first += " The 1-day median does not stay positive after 5 bp."
    elif all(value is not None and value < 0 for value in early):
        first = "No. The median return is negative at the first and second daily closes after entry."
    else:
        first = "The mean and the median do not agree in the first two daily closes, so there is no clean short-horizon rebound in the typical trade."
    positive_horizons = [horizon for horizon in HORIZONS if (value := _median(book, str(horizon))) is not None and value > 0 and book[str(horizon)]["gross"]["mean"] > 0]
    if not positive_horizons:
        second = "The median close-to-close path does not turn positive at any checkpoint from 1 through 20 trading days."
    else:
        second = (
            f"The first checkpoint where both the mean and the median are positive is {positive_horizons[0]} trading day{'s' if positive_horizons[0] != 1 else ''}. "
            "That checkpoint is a description of this sample, not a selected holding rule."
        )
    last = [_median(book, horizon) for horizon in ("10", "20")]
    if positive_horizons and all(value is not None and value > 0 for value in last):
        third = "Yes. The median is still positive at 10 and at 20 trading days."
    elif positive_horizons:
        third = "The early positive checkpoint does not stay positive through both the 10-day and 20-day closes."
    else:
        third = "No positive median appears, so there is no rebound here that persists across the later checkpoints."
    winner_gap_1 = _median(summary["winners"], "1")
    loser_gap_1 = _median(summary["losers"], "1")
    winner_gap_10 = _median(summary["winners"], "10")
    loser_gap_10 = _median(summary["losers"], "10")
    if None in (winner_gap_1, loser_gap_1, winner_gap_10, loser_gap_10):
        fourth = "Winner and loser paths do not both have a 1-day and a 10-day median."
    else:
        gap_1 = winner_gap_1 - loser_gap_1
        gap_10 = winner_gap_10 - loser_gap_10
        if gap_1 > 0 and gap_1 >= gap_10 / 2:
            fourth = "Winners are already ahead of losers at the first daily close. The labels use the eventual +5% or -3% exit, which is not known at entry."
        elif gap_10 > gap_1 and winner_gap_1 > 0 > loser_gap_1:
            fourth = "Winners are already ahead at the first daily close, and the median gap is wider at 10 trading days. The labels use the eventual exit and are not known at entry."
        elif gap_10 > gap_1:
            fourth = "The winner-minus-loser median gap is wider at 10 trading days than at the first close. The labels use the eventual exit and are not known at entry."
        else:
            fourth = "Winners and losers do not separate cleanly at the first close or by 10 trading days. The labels use the eventual exit and are not known at entry."
    signs = []
    for year in ("2024", "2025", "2026"):
        signs.append((_median(summary["years"][year], "5"), _median(summary["years"][year], "10")))
    def _sign(value: Decimal | None) -> int:
        if value is None or value == 0:
            return 0
        return 1 if value > 0 else -1
    if any(value is None for pair in signs for value in pair):
        fifth = "One of the year checkpoints has no median, so 2026 cannot be compared on equal terms."
    elif _sign(signs[2][0]) != _sign(signs[0][0]) or _sign(signs[2][1]) != _sign(signs[0][1]) or _sign(signs[2][0]) != _sign(signs[1][0]):
        fifth = "Yes. The 2026 median sign at 5 or 10 trading days differs from 2024 or 2025."
    else:
        fifth = "No. The 2026 median has the same sign as 2024 and 2025 at both 5 and 10 trading days."
        later = _median(summary["years"]["2026"], "15")
        if later is not None and later < 0:
            fifth += " The 2026 median is negative at 15 trading days, so the agreement does not cover every later checkpoint."
    median_10 = _median(book, "10")
    exits = book["10"]["original_exit"]
    acted = exits["target"] + exits["stop"]
    resting = acted + exits["neither"]
    inside = median_10 is not None and Decimal("-0.03") < median_10 < Decimal("0.05")
    majority = resting > 0 and Decimal(acted) / Decimal(resting) > Decimal("0.5")
    if inside and majority:
        sixth = "Yes. By 10 trading days most original trades have already hit +5% or -3%, and the daily-close median still sits between those two levels."
    else:
        sixth = "The 10-day daily-close median and the share of trades that have already hit +5% or -3% do not sit together in the way the frozen brackets would suggest. This does not authorize a new take-profit or stop."
    agree = (
        _sign(signs[0][0]) == _sign(signs[1][0]) != 0
        and _sign(signs[0][1]) == _sign(signs[1][1]) != 0
        and _sign(signs[0][0]) == _sign(signs[0][1])
    )
    same_2026 = _sign(signs[2][0]) == _sign(signs[0][0]) and _sign(signs[2][1]) == _sign(signs[0][1])
    if agree and same_2026:
        seventh = "Yes. 2024, 2025, and 2026 share one median sign at 5 and 10 trading days, so a separate holding-period test can be pre-registered. This run does not choose the horizon, the take-profit, or the stop."
    elif agree:
        seventh = "No. 2024 and 2025 agree at 5 and 10 trading days, and 2026 does not. An exit chosen from the earlier path would be fit to a pattern that already changed."
    else:
        seventh = "No. 2024 and 2025 do not share one median sign at both 5 and 10 trading days, so this path does not justify a pre-registered exit experiment."
    return [first, second, third, fourth, fifth, sixth, seventh]


def lookahead_audit(trades: list[dict], paths: list[dict]) -> dict:
    failures: list[str] = []
    for trade, path in zip(trades, paths, strict=True):
        symbol = trade["symbol"]
        if trade["today_drop_pct"] is None or trade["today_drop_pct"] > Decimal("-1"):
            failures.append(f"{symbol} signal is not a drop of at least 1%")
        if trade["ema_through"] is not None and trade["ema_through"] >= trade["session_date"]:
            failures.append(f"{symbol} signal context includes the signal session")
        if trade["entry_bar_end"] <= trade["signal_time"] or session_date(trade["entry_time"]) != trade["session_date"]:
            failures.append(f"{symbol} entry is not the next same-session open")
        if trade["stop"] != trade["entry_price"] * (Decimal(1) - STOP_PCT) or trade["target"] != trade["entry_price"] * (Decimal(1) + TARGET_PCT):
            failures.append(f"{symbol} original brackets are not -3% and +5%")
        resolved_limits = [item["close_time"] for item in path["checkpoints"] if item["status"] == "resolved"]
        if trade["exit_time"] is not None and resolved_limits and trade["exit_time"] <= resolved_limits[-1]:
            if path["detected_exit"] != trade["exit_reason"] or path["detected_exit_time"] != trade["exit_time"]:
                failures.append(f"{symbol} replayed exit does not match the delivery rule")
        for checkpoint in path["checkpoints"]:
            if checkpoint["status"] != "resolved":
                continue
            if checkpoint["close_time"] <= trade["entry_time"]:
                failures.append(f"{symbol} horizon close is not after the entry")
    checks = [
        {"item": "Signal uses the completed bar and a drop of at least 1% versus the prior session", "status": "FAIL" if any("signal" in item for item in failures) else "PASS"},
        {"item": "Entry is the next same-session 5-minute open", "status": "FAIL" if any("entry" in item for item in failures) else "PASS"},
        {"item": "Forward closes are strictly after the entry", "status": "FAIL" if any("horizon" in item for item in failures) else "PASS"},
        {"item": "The original -3% / +5% delivery brackets are unchanged", "status": "FAIL" if any("brackets" in item or "replayed" in item for item in failures) else "PASS"},
        {"item": "Future bars are used only to score the path", "status": "PASS" if not failures else "FAIL"},
    ]
    status = "FAIL" if failures else "PASS"
    return {"status": status, "valid": status == "PASS", "checks": checks, "failure_count": len(failures), "failures": failures[:50]}
