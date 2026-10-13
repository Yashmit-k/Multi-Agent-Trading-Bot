from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from quant_agents.research.h001.calendar import DailyBar, FiveMinuteBar
from quant_agents.research.h001.eligibility import (
    ORIGIN_SYNTHETIC,
    PROTOCOL_ID,
    SYNTHETIC_FIXTURE_NOT_PRODUCTION,
    EligibilityBundle,
    run_synthetic_eligibility_audit,
)
from quant_agents.research.h001.events import IST, ExclusionReason
from quant_agents.research.h001.split import INCONCLUSIVE, MINORITY_BAR, SATISFIED

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
SYMBOL = "RELIANCE"
CALENDAR_SYMBOL = "TCS"


def _weekdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


SESSIONS = tuple(_weekdays(date(2023, 11, 1), date(2025, 3, 14)))


def _ist(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=IST)


def _clock(moment: datetime) -> tuple[str, str]:
    raw = (
        f"{moment.day:02d}-{_MONTHS[moment.month - 1]}-{moment.year} "
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}"
    )
    return raw, moment.isoformat()


def _daily(symbol: str, day: date, price: str = "100") -> DailyBar:
    return DailyBar(symbol, _ist(day, 15, 30), Decimal(price))


def _entry(symbol: str, day: date, price: str = "100") -> FiveMinuteBar:
    start = _ist(day, 9, 15)
    return FiveMinuteBar(symbol, start, start + timedelta(minutes=5), Decimal(price))


def _row(seq_id: str, day: date, *, desc: str = "Financial Result Updates") -> dict[str, object]:
    available = _ist(day, 8, 0, 0)
    raw, iso = _clock(available)
    return {
        "seq_id": seq_id,
        "symbol": SYMBOL,
        "desc": desc,
        "exchdisstime": raw,
        "available_at": iso,
        "attchmntText": "results",
        "hasXbrl": False,
    }


def _market(
    *,
    skip_entry: date | None = None,
    skip_close: date | None = None,
    close_overrides: dict[date, str] | None = None,
) -> tuple[tuple[DailyBar, ...], tuple[FiveMinuteBar, ...]]:
    overrides = close_overrides or {}
    daily: list[DailyBar] = []
    intra: list[FiveMinuteBar] = []
    for session in SESSIONS:
        daily.append(_daily(CALENDAR_SYMBOL, session, "50"))
        if skip_close != session:
            daily.append(_daily(SYMBOL, session, overrides.get(session, "100")))
        if skip_entry != session:
            intra.append(_entry(SYMBOL, session, "100"))
        intra.append(_entry(CALENDAR_SYMBOL, session, "50"))
    return tuple(daily), tuple(intra)


def _bundle(rows: list[dict[str, object]], daily: tuple[DailyBar, ...], intra: tuple[FiveMinuteBar, ...]) -> EligibilityBundle:
    return EligibilityBundle(tuple(rows), daily, intra, ORIGIN_SYNTHETIC, ("synthetic-fixture",))


def _next_weekday(day: date) -> date:
    cursor = day + timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor += timedelta(days=1)
    return cursor


def test_timestamp_session_label_and_exclusions_on_synthetic_rows() -> None:
    train_day = date(2024, 2, 1)
    missing_p0_day = date(2024, 2, 2)
    missing_p1_decision = date(2024, 2, 5)
    missing_p1_horizon = _next_weekday(missing_p1_decision)
    val_day = date(2024, 7, 2)
    daily, intra = _market(skip_entry=missing_p0_day, skip_close=missing_p1_horizon)
    rows = [
        _row("keep-train", train_day),
        _row("missing-p0", missing_p0_day),
        _row("missing-p1", missing_p1_decision),
        _row("keep-val", val_day),
        _row("wrong-desc", train_day, desc="Integrated Filing- Financial"),
        _row("board", train_day, desc="Outcome of Board Meeting"),
        {
            **_row("mismatch", train_day),
            "available_at": "2024-02-01T08:00:01+05:30",
        },
    ]
    rows[-1]["seq_id"] = "mismatch"
    report = run_synthetic_eligibility_audit(_bundle(rows, daily, intra))
    assert report.protocol_id == PROTOCOL_ID
    assert report.origin == ORIGIN_SYNTHETIC
    assert report.integrity_verification_status == "UNVERIFIED"
    assert report.execution_authorized is False
    assert report.readiness_decision == SYNTHETIC_FIXTURE_NOT_PRODUCTION
    assert report.stage_counts["input_records"] == 7
    assert report.stage_counts["unique_event_identifiers"] == 7
    assert report.exclusion_counts[ExclusionReason.DESC_NOT_IN_CLASS.value] == 2
    assert report.exclusion_counts[ExclusionReason.CLOCK_MISMATCH.value] == 1
    assert report.exclusion_counts[ExclusionReason.MISSING_ENTRY_BAR.value] == 1
    assert report.exclusion_counts[ExclusionReason.MISSING_HORIZON_CLOSE.value] == 1
    assert report.stage_counts["eligible_labelled_train"] == 1
    assert report.stage_counts["eligible_labelled_validation"] == 1
    assert report.train.n == 1
    assert report.validation.n == 1
    assert report.minority_threshold == MINORITY_BAR
    assert "hasXbrl" not in report.reproducibility["feature_columns"]
    assert report.reproducibility["feature_columns"].startswith("intercept,")


def test_purge_boundary_and_zero_label() -> None:
    daily, intra = _market()
    # Decision 28 Jun 2024 is Friday; next session 1 Jul is after TRAIN_END.
    purge_day = date(2024, 6, 28)
    train_day = date(2024, 6, 27)
    val_day = date(2024, 7, 1)
    too_late = date(2025, 2, 14)
    rows = [
        _row("train-edge", train_day),
        _row("purged", purge_day),
        _row("val-edge", val_day),
        _row("val-end", too_late),
    ]
    report = run_synthetic_eligibility_audit(_bundle(rows, daily, intra))
    assert report.exclusion_counts.get(ExclusionReason.PURGED_EMBARGO.value, 0) == 1
    assert report.train.n == 1
    assert report.validation.n == 2
    assert report.train.positive + report.train.negative == report.train.n
    # P0=100 and next close=100 => y=0
    assert report.train.negative == 1
    assert report.train.positive == 0


def test_unverified_prior_34_stays_inconclusive_on_synthetic_counts() -> None:
    train_days = [day for day in SESSIONS if date(2024, 2, 1) <= day <= date(2024, 6, 20)]
    val_days = [day for day in SESSIONS if date(2024, 7, 2) <= day <= date(2024, 10, 31)]
    rows: list[dict[str, object]] = []
    for index, day in enumerate(train_days[:74]):
        rows.append(_row(f"t{index}", day))
    for index, day in enumerate(val_days[:40]):
        rows.append(_row(f"v{index}", day))
    overrides = {_next_weekday(day): "101" for day in train_days[:34]}
    daily, intra = _market(close_overrides=overrides)
    report = run_synthetic_eligibility_audit(_bundle(rows, daily, intra))
    assert report.prior_training_minority_unverified == 34
    assert report.train.positive == 34
    assert report.train.negative == 40
    assert report.train.minority == 34
    assert report.train.status == INCONCLUSIVE
    assert report.validation.n == 40
    assert report.validation.status == INCONCLUSIVE
    assert report.readiness_decision == SYNTHETIC_FIXTURE_NOT_PRODUCTION
    assert "DATA_READY" not in report.readiness_decision


def test_synthetic_fifty_fifty_is_not_production_data_ready() -> None:
    train_days = [day for day in SESSIONS if date(2024, 2, 1) <= day <= date(2024, 6, 20)]
    val_days = [day for day in SESSIONS if date(2024, 7, 2) <= day <= date(2025, 2, 14)]
    rows: list[dict[str, object]] = []
    for index, day in enumerate(train_days[:100]):
        rows.append(_row(f"t{index}", day))
    for index, day in enumerate(val_days[:100]):
        rows.append(_row(f"v{index}", day))
    overrides = {_next_weekday(day): "101" for day in train_days[:50] + val_days[:50]}
    daily, intra = _market(close_overrides=overrides)
    report = run_synthetic_eligibility_audit(_bundle(rows, daily, intra))
    assert report.train.n == 100
    assert report.validation.n == 100
    assert report.train.minority == MINORITY_BAR
    assert report.validation.minority == MINORITY_BAR
    assert report.train.status == SATISFIED
    assert report.validation.status == SATISFIED
    assert report.readiness_decision == SYNTHETIC_FIXTURE_NOT_PRODUCTION
    assert report.execution_authorized is False


def test_fixtures_cannot_resolve_to_the_frozen_dataset() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "quant_agents" / "research" / "h001"
    daily, intra = _market()
    report = run_synthetic_eligibility_audit(_bundle([_row("s", date(2024, 3, 4))], daily, intra))
    assert report.origin == ORIGIN_SYNTHETIC
    assert report.snapshot_ids == ("synthetic-fixture",)
    assert report.integrity_verification_status == "UNVERIFIED"
    for path in package.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "eligibility.py":
            assert "fit_h001" not in text
            assert "LogisticRegression" not in text
            assert "sklearn" not in text
            assert "datasets" not in text
