"""Deterministic H001-v2 subject rules. Original v1 include-list is immutable."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
EXCH_FMT = "%d-%b-%Y %H:%M:%S"

# Original approved protocol — exact normalized desc. Do not extend in-place.
V1_DESC = frozenset(
    {
        "financial result updates",
        "consolidated result updates ifrs",
        "publish audited results",
    }
)

TRAIN_END = datetime(2024, 6, 30, 23, 59, 59, tzinfo=IST)
VAL_START = datetime(2024, 7, 1, 0, 0, 0, tzinfo=IST)
VAL_END = datetime(2025, 2, 14, 23, 59, 59, tzinfo=IST)

_RESULTS_TEXT = re.compile(
    r"financial results|financial result|audited results|quarterly results|integrated filing",
    re.I,
)

# Quant readiness §15: keep if hasXbrl is true OR desc matches this regex. Do not tighten.
SECTION15_DESC = re.compile(r"result|financial|earnings", re.I)

QUARTERS = tuple(f"{year}Q{quarter}" for year in (2024, 2025) for quarter in range(1, 5))

# desc (normalized) that match §15 regex but are likely not a results print.
_SECTION15_FP_PREFIXES = (
    "financial results",
    "audited",
    "unaudited",
    "integrated filing",
    "consolidated result",
    "publish audited",
    "outcome of board",
    "clarification",
    "reply to clarification",
)


def normalize_desc(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def parse_exchdisstime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, EXCH_FMT).replace(tzinfo=IST)
    except ValueError:
        return None


def _has_xbrl(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and value != 0:
        return True
    text = str(value or "").strip().lower()
    return text in {"true", "1", "yes", "y"}


def results_like_section15(row: dict) -> tuple[bool, str]:
    """Quant h001-data-readiness.md §15. Returns (keep, evidence)."""
    xbrl = _has_xbrl(row.get("hasXbrl"))
    regex = bool(SECTION15_DESC.search(str(row.get("desc") or "")))
    if xbrl and regex:
        return True, "both"
    if xbrl:
        return True, "hasXbrl_only"
    if regex:
        return True, "regex_only"
    return False, "neither"


def ist_calendar_quarter(ts: datetime) -> str | None:
    if ts.year not in (2024, 2025):
        return None
    quarter = (ts.month - 1) // 3 + 1
    return f"{ts.year}Q{quarter}"


def section15_false_positive_bucket(desc: object) -> str:
    """Likely-FP grouping for §15 regex hits that are not a results print. Not a filter."""
    text = normalize_desc(desc)
    if v1_class(desc):
        return "official_v1_subject"
    if "integrated filing" in text and "financial" in text:
        return "nse_cml_2025_20_subject"
    if text.startswith("outcome of board"):
        return "board_outcome_regex_hit"
    if "clarification" in text:
        return "clarification_regex_hit"
    if any(text.startswith(prefix) or prefix in text for prefix in _SECTION15_FP_PREFIXES):
        return "results_language"
    return "ambiguous_regex_or_xbrl"


def v1_class(desc: object) -> bool:
    return normalize_desc(desc) in V1_DESC


def v2_class(row: dict) -> tuple[bool, str]:
    """Return (in_class, evidence_kind). Does not mutate v1."""
    desc = normalize_desc(row.get("desc"))
    if desc in V1_DESC:
        return True, "official_v1_subject"
    if desc in {"integrated filing- financial", "integrated filing - financial", "integrated filing (financial)"}:
        return True, "nse_circular_subject_nse_cml_2025_20"
    if desc == "outcome of board meeting":
        blob = " ".join(
            str(row.get(key) or "") for key in ("attchmntText", "attchmntFile", "desc")
        )
        if _RESULTS_TEXT.search(blob):
            return True, "source_backed_board_outcome_financial_results"
        return False, "board_outcome_unrelated_or_unproven"
    if desc in {"clarification - financial results", "reply to clarification- financial results"}:
        return False, "related_not_in_candidate_print_class"
    return False, "excluded"


def partition(ts: datetime) -> str:
    if ts <= TRAIN_END:
        return "train"
    if VAL_START <= ts <= VAL_END:
        return "validate"
    if ts > VAL_END:
        return "post_validation"
    return "gap"
