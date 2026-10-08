"""Calendar completeness of a stock snapshot. Does not invent candles.

The expected grid is the NSE session calendar, not the half-symbol empirical grid.
A clock missing for every name stays visible.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from contracts.enums import Timeframe
from core_market_data.nse_sessions import HOLIDAYS, expected_starts, is_trading_day
from quant_agents.direction.inventory import EXCLUDED, IST

SHORT_SESSIONS = {date(2024, 3, 2), date(2024, 5, 18)}
TAIL_CLOCKS = (time(15, 15), time(15, 20), time(15, 25))
TAIL_FROM = date(2026, 8, 3)
FIVE_MINUTES = timedelta(minutes=5)


def audit_candles(path: Path, timeframe: str, *, symbols: set[str] | None = None) -> dict[str, object]:
    """Missing days, missing clocks, duplicates, and stored flat gaps."""
    owned, duplicates, flats = _scan(path, timeframe, symbols)
    names = sorted(owned)
    if not names:
        return {"timeframe": timeframe, "symbols": 0, "bars": 0}
    span_start, span_end = _span(owned)
    frame = Timeframe(timeframe)
    expected = expected_starts(
        datetime.combine(span_start, time(0, 0), tzinfo=IST),
        datetime.combine(span_end + timedelta(days=1), time(0, 0), tzinfo=IST),
        frame,
    )
    expected = {stamp.astimezone(timezone.utc) for stamp in expected}
    per_symbol = {name: sorted(expected - stamps) for name, stamps in owned.items()}
    by_stamp: dict[datetime, list[str]] = defaultdict(list)
    for name, missing in per_symbol.items():
        for stamp in missing:
            by_stamp[stamp].append(name)
    universe = len(names)
    exchange: dict[date, list[str]] = defaultdict(list)
    partial: list[dict[str, object]] = []
    for stamp in sorted(by_stamp):
        missing_names = by_stamp[stamp]
        local = stamp.astimezone(IST)
        if len(missing_names) == universe:
            exchange[local.date()].append(local.strftime("%H:%M"))
        else:
            partial.append(
                {
                    "start": stamp.astimezone(timezone.utc).isoformat(),
                    "clock_ist": local.strftime("%H:%M"),
                    "session": local.date().isoformat(),
                    "symbols": missing_names,
                }
            )
    days = []
    inside = []
    for session, clocks in sorted(exchange.items()):
        item = {
            "session": session.isoformat(),
            "clocks_ist": clocks,
            "symbols": universe,
            "class": _exchange_class(session, clocks, timeframe),
        }
        if len(clocks) == (1 if timeframe == "1d" else 75):
            days.append(item)
        else:
            inside.append(item)
    missing_days_partial = _partial_days(per_symbol, expected, timeframe)
    all_missing_days = {item["session"] for item in days}
    for row in missing_days_partial:
        row["sessions"] = [session for session in row["sessions"] if session not in all_missing_days]
        row["count"] = len(row["sessions"])
    missing_days_partial = [row for row in missing_days_partial if row["sessions"]]
    weekend = _weekend_sessions(owned)
    return {
        "timeframe": timeframe,
        "symbols": names,
        "excluded": EXCLUDED,
        "span": [span_start.isoformat(), span_end.isoformat()],
        "bars": sum(len(stamps) for stamps in owned.values()),
        "expected_bars_per_symbol": len(expected),
        "duplicate_starts": duplicates["starts"],
        "duplicate_ends": duplicates["ends"],
        "missing_trading_days_all_symbols": days,
        "missing_clocks_all_symbols": inside,
        "missing_clocks_some_symbols": _compact_partial(partial),
        "symbols_missing_whole_days": missing_days_partial,
        "stored_flat_gaps": flats,
        "weekend_sessions_already_stored": weekend,
        "holiday_list_not_expected": sorted(day.isoformat() for day in HOLIDAYS if span_start <= day <= span_end),
    }


def _exchange_class(session: date, clocks: list[str], timeframe: str) -> str:
    if session in SHORT_SESSIONS:
        return "short_session_candidate"
    if timeframe == "5m" and session >= TAIL_FROM and tuple(time.fromisoformat(item) for item in clocks) == TAIL_CLOCKS:
        return "late_session_tail"
    if not is_trading_day(session):
        return "outside_calendar"
    return "exchange_wide"


def _scan(path: Path, timeframe: str, symbols: set[str] | None):
    owned: dict[str, set[datetime]] = defaultdict(set)
    seen_end: set[tuple[str, str]] = set()
    duplicates = {"starts": 0, "ends": 0}
    previous: dict[str, tuple[datetime, datetime, bool]] = {}
    flats: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("timeframe")) != timeframe:
                continue
            symbol = str(row["symbol"])
            if symbol == EXCLUDED or (symbols is not None and symbol not in symbols):
                continue
            start = datetime.fromisoformat(str(row["start"])).astimezone(timezone.utc)
            end = datetime.fromisoformat(str(row["end"])).astimezone(timezone.utc)
            if start in owned[symbol]:
                duplicates["starts"] += 1
            else:
                owned[symbol].add(start)
            end_key = (symbol, end.isoformat())
            if end_key in seen_end:
                duplicates["ends"] += 1
            else:
                seen_end.add(end_key)
            flat = row["open"] == row["high"] == row["low"] == row["close"]
            prior = previous.get(symbol)
            if prior is not None:
                prior_start, prior_end, prior_flat = prior
                same_day = prior_start.astimezone(IST).date() == start.astimezone(IST).date()
                gap = start - prior_end
                if prior_flat and same_day and gap > FIVE_MINUTES:
                    flats.append(
                        {
                            "symbol": symbol,
                            "flat_end": prior_end.isoformat(),
                            "next_start": start.isoformat(),
                            "gap_minutes": gap.total_seconds() / 60,
                        }
                    )
            previous[symbol] = (start, end, bool(flat))
    return owned, duplicates, flats


def _span(owned: dict[str, set[datetime]]) -> tuple[date, date]:
    stamps = [stamp for stamps in owned.values() for stamp in stamps]
    first = min(stamps).astimezone(IST).date()
    last = max(stamps).astimezone(IST).date()
    return first, last


def _partial_days(per_symbol: dict[str, list[datetime]], expected: set[datetime], timeframe: str) -> list[dict[str, object]]:
    by_day: dict[date, int] = defaultdict(int)
    for stamp in expected:
        by_day[stamp.astimezone(IST).date()] += 1
    full = 1 if timeframe == "1d" else 75
    rows = []
    for name, missing in sorted(per_symbol.items()):
        lost: dict[date, int] = defaultdict(int)
        for stamp in missing:
            lost[stamp.astimezone(IST).date()] += 1
        whole = [day.isoformat() for day, count in sorted(lost.items()) if count == by_day[day] == full]
        if whole:
            rows.append({"symbol": name, "sessions": whole, "count": len(whole)})
    return rows


def _weekend_sessions(owned: dict[str, set[datetime]]) -> list[dict[str, object]]:
    counts: dict[date, list[int]] = defaultdict(list)
    for stamps in owned.values():
        per_day: dict[date, int] = defaultdict(int)
        for stamp in stamps:
            per_day[stamp.astimezone(IST).date()] += 1
        for day, count in per_day.items():
            if day.weekday() >= 5:
                counts[day].append(count)
    described = []
    for day, lengths in sorted(counts.items()):
        described.append(
            {
                "session": day.isoformat(),
                "symbols": len(lengths),
                "bars_min": min(lengths),
                "bars_max": max(lengths),
                "class": "short_session_candidate" if day in SHORT_SESSIONS else "weekend_session",
                "backfill": False,
            }
        )
    return described


def _compact_partial(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    for row in rows:
        key = (str(row["session"]), tuple(row["symbols"]))
        grouped[key].append(str(row["clock_ist"]))
    compact = []
    for (session, names), clocks in sorted(grouped.items()):
        compact.append({"session": session, "clocks_ist": clocks, "symbols": list(names), "class": "symbol_specific"})
    return compact
