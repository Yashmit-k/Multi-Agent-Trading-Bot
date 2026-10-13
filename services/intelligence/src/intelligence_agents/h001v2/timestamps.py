"""Timestamp provenance for NSE announcement rows.

`exchdatetime` is not present in this repository or in freeze samples inspected by
the prep pipeline. Candidate availability uses `exchdisstime` only.
Timezone Asia/Kolkata is a convention, not source metadata.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from intelligence_agents.h001v2.normalize import EXCH_FMT, IST, parse_exchdisstime

WATCH_FIELDS = ("exchdisstime", "exchdatetime", "an_dt", "sort_date", "dt", "difference")


def parse_nse_clock(value: object) -> datetime | None:
    return parse_exchdisstime(value)


def lag_seconds(earlier: datetime, later: datetime) -> float:
    return (later - earlier).total_seconds()


def audit_timestamps(rows: list[dict]) -> dict:
    present = {name: 0 for name in WATCH_FIELDS}
    nonempty = {name: 0 for name in WATCH_FIELDS}
    parse_ok = Counter()
    parse_fail = Counter()
    an_after_exch = 0
    an_after_exch_gt2s = 0
    exch_naive_tagged_ist = 0
    duplicate_exch = 0
    seen_exch: dict[tuple[str, str], int] = {}
    session_buckets = Counter()
    missing_exchdatetime_all = True

    for row in rows:
        symbol = str(row.get("symbol") or "")
        seq = str(row.get("seq_id") or "")
        for name in WATCH_FIELDS:
            if name in row:
                present[name] += 1
                if str(row.get(name) or "").strip():
                    nonempty[name] += 1
        if row.get("exchdatetime") not in (None, "", []):
            missing_exchdatetime_all = False

        exch_raw = row.get("exchdisstime")
        exch = parse_nse_clock(exch_raw)
        if exch_raw in (None, ""):
            parse_fail["exchdisstime_empty"] += 1
        elif exch is None:
            parse_fail["exchdisstime"] += 1
        else:
            parse_ok["exchdisstime"] += 1
            exch_naive_tagged_ist += 1
            key = (symbol, str(exch_raw))
            seen_exch[key] = seen_exch.get(key, 0) + 1
            hour = exch.hour
            if hour < 9 or (hour == 9 and exch.minute < 15):
                session_buckets["pre_open_or_before_0915_ist"] += 1
            elif hour > 15 or (hour == 15 and exch.minute >= 30):
                session_buckets["after_close_1530_ist"] += 1
            else:
                session_buckets["regular_session_ist"] += 1

        an = parse_nse_clock(row.get("an_dt"))
        if row.get("an_dt") in (None, ""):
            parse_fail["an_dt_empty"] += 1
        elif an is None:
            parse_fail["an_dt"] += 1
        else:
            parse_ok["an_dt"] += 1

        if exch is not None and an is not None and an > exch:
            an_after_exch += 1
            if lag_seconds(exch, an) > 2:
                an_after_exch_gt2s += 1

        sort_v = row.get("sort_date")
        if sort_v not in (None, "") and parse_nse_clock(sort_v) is None:
            # sort_date is YYYY-MM-DD HH:MM:SS, not DD-MMM-YYYY
            parse_fail["sort_date_not_exch_fmt"] += 1

    duplicate_exch = sum(1 for count in seen_exch.values() if count > 1)
    return {
        "field_present_row_counts": present,
        "field_nonempty_row_counts": nonempty,
        "exchdatetime_found": not missing_exchdatetime_all,
        "exchdatetime_note": (
            "No `exchdatetime` field in this pipeline. Do not treat it as an alias of exchdisstime."
        ),
        "parse_ok": dict(parse_ok),
        "parse_fail": dict(parse_fail),
        "an_dt_after_exchdisstime": an_after_exch,
        "an_dt_after_exchdisstime_gt2s": an_after_exch_gt2s,
        "duplicate_symbol_exchdisstime_pairs": duplicate_exch,
        "exchdisstime_naive_tagged_ist_count": exch_naive_tagged_ist,
        "timezone_assumption": (
            f"parse uses format {EXCH_FMT} and ZoneInfo {IST.key}; convention, not NSE JSON metadata"
        ),
        "session_buckets_exchdisstime": dict(session_buckets),
        "available_at_construction": (
            "Scope A candidate available_at = parse_exchdisstime(exchdisstime) with IST tag"
        ),
        "not_used_for_available_at": [
            "retrieval time",
            "period_end / toDate",
            "filedAt",
            "exchdatetime (absent)",
            "arbitrary +N hours",
        ],
        "limitation": (
            "candidate IST-tagged exchange-dissemination proxy; not proven first public print; "
            "not proven immutable; insufficient for Scope B"
        ),
    }
