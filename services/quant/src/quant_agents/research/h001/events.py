"""Event class and proxy clock. Callers supply rows. This module opens nothing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

INCLUDE_DESC = frozenset(
    {
        "financial result updates",
        "consolidated result updates ifrs",
        "publish audited results",
    }
)
CONTRADICTION_PHRASES = ("trading window", "divestment", "loss of share")
EXCLUDED_SYMBOL = "TATAMOTORS"
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
WINDOW_START = datetime(2024, 1, 1, 0, 0, 0, tzinfo=IST)
WINDOW_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=IST)


class ExclusionReason(StrEnum):
    DESC_NOT_IN_CLASS = "desc_not_in_class"
    CONTRADICTION = "contradiction"
    UNPARSED_CLOCK = "unparsed_clock"
    CLOCK_MISMATCH = "clock_mismatch"
    SYMBOL_EXCLUDED = "symbol_excluded"
    BEFORE_WINDOW = "before_window"
    AFTER_WINDOW = "after_window"
    MISSING_ENTRY_BAR = "missing_entry_bar"
    MISSING_HORIZON_CLOSE = "missing_horizon_close"
    SHORT_HISTORY = "short_history"
    MISSING_DAILY_HISTORY = "missing_daily_history"
    NONPOSITIVE_PRICE = "nonpositive_price"
    PURGED_EMBARGO = "purged_embargo"


class DuplicateBarError(ValueError):
    """Two stored bars claim the same required slot. Neither is chosen."""


@dataclass(frozen=True, slots=True)
class Exclusion:
    seq_id: str
    symbol: str
    reason: ExclusionReason


@dataclass(frozen=True, slots=True)
class ClassifiedEvent:
    seq_id: str
    symbol: str
    exchdisstime_raw: str
    available_at: datetime
    normalized_desc: str


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    events: tuple[ClassifiedEvent, ...]
    exclusions: tuple[Exclusion, ...]


def normalize_desc(value: object) -> str:
    """Missing or non-text becomes empty. Letters and digits are kept."""
    if not isinstance(value, str):
        return ""
    spaced = "".join(char if char.isalnum() else " " for char in value.casefold())
    return " ".join(spaced.split())


def require_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("naive timestamp")
    return moment.astimezone(IST)


def parse_exchdisstime(raw: str) -> datetime:
    """Parse `%d-%b-%Y %H:%M:%S` and tag Asia/Kolkata. English month names only."""
    try:
        date_part, time_part = raw.split(" ")
        day_text, month_text, year_text = date_part.split("-")
        hour_text, minute_text, second_text = time_part.split(":")
        parsed = datetime(
            int(year_text),
            _MONTHS[month_text.casefold()],
            int(day_text),
            int(hour_text),
            int(minute_text),
            int(second_text),
        )
    except (AttributeError, ValueError, KeyError, IndexError) as exc:
        raise ValueError("unparsed exchdisstime") from exc
    return parsed.replace(tzinfo=IST)


def _attachment_text(row: Mapping[str, object]) -> str:
    value = row.get("attchmntText", row.get("attchmnt_text"))
    if not isinstance(value, str):
        return ""
    return value


def _available_at(value: object) -> datetime:
    if isinstance(value, datetime):
        return require_aware(value)
    if isinstance(value, str):
        return require_aware(datetime.fromisoformat(value))
    raise ValueError("unparsed available_at")


def classify_row(row: Mapping[str, object]) -> ClassifiedEvent | Exclusion:
    """One reason per row. Passing the subject filter is not a completeness claim."""
    seq_id = str(row.get("seq_id", ""))
    symbol = str(row.get("symbol", ""))
    if symbol == EXCLUDED_SYMBOL:
        return Exclusion(seq_id, symbol, ExclusionReason.SYMBOL_EXCLUDED)
    normalized = normalize_desc(row.get("desc"))
    if normalized not in INCLUDE_DESC:
        return Exclusion(seq_id, symbol, ExclusionReason.DESC_NOT_IN_CLASS)
    attachment = _attachment_text(row).casefold()
    if attachment and any(phrase in attachment for phrase in CONTRADICTION_PHRASES):
        return Exclusion(seq_id, symbol, ExclusionReason.CONTRADICTION)
    raw_clock = row.get("exchdisstime")
    if not isinstance(raw_clock, str):
        return Exclusion(seq_id, symbol, ExclusionReason.UNPARSED_CLOCK)
    try:
        parsed = parse_exchdisstime(raw_clock)
        stated = _available_at(row.get("available_at"))
    except ValueError:
        return Exclusion(seq_id, symbol, ExclusionReason.UNPARSED_CLOCK)
    if parsed != stated:
        return Exclusion(seq_id, symbol, ExclusionReason.CLOCK_MISMATCH)
    if stated < WINDOW_START:
        return Exclusion(seq_id, symbol, ExclusionReason.BEFORE_WINDOW)
    if stated > WINDOW_END:
        return Exclusion(seq_id, symbol, ExclusionReason.AFTER_WINDOW)
    return ClassifiedEvent(seq_id, symbol, raw_clock, stated, normalized)


def classify_rows(rows: tuple[Mapping[str, object], ...] | list[Mapping[str, object]]) -> ClassificationResult:
    events: list[ClassifiedEvent] = []
    exclusions: list[Exclusion] = []
    for row in rows:
        outcome = classify_row(row)
        if isinstance(outcome, Exclusion):
            exclusions.append(outcome)
        else:
            events.append(outcome)
    return ClassificationResult(tuple(events), tuple(exclusions))
