"""Synthetic tests for the pre-registered news-category study. No network."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from quant_agents.research.news_categories import CATEGORIES, OUTCOMES


PROTOCOL = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "news-categories-nifty-protocol.md"
)


def test_ten_categories_and_twelve_outcomes_match_the_protocol() -> None:
    assert len(CATEGORIES) == 10
    assert len(OUTCOMES) == 12
    assert len({item[0] for item in CATEGORIES}) == 10
    text = PROTOCOL.read_text(encoding="utf-8")
    for _category_id, _name, queries in CATEGORIES:
        assert queries
        for query in queries:
            assert query in text



from quant_agents.research.news_categories import event_flags


def test_event_detector_uses_only_past_days() -> None:
    # The past window has to have some variance. A zero standard deviation is not an event.
    quiet = [1.0, 2.0] * 30
    series = quiet + [100.0, 1.0]
    flags = event_flags(series)
    assert flags[:60] == [False] * 60
    assert flags[60] is True
    assert flags[61] is False
    changed = series.copy()
    changed[61] = 10_000.0
    again = event_flags(changed)
    assert again[60] is flags[60]
    assert again[:60] == flags[:60]


def test_flat_history_is_not_an_event() -> None:
    assert event_flags([3.0] * 80) == [False] * 80


def test_threshold_is_at_least_two_standard_deviations() -> None:
    past = [0.0] * 30 + [2.0] * 30
    mean = sum(past) / 60
    var = sum((item - mean) ** 2 for item in past) / 59
    std = var ** 0.5
    just_under = mean + 2 * std - 1e-9
    exact = mean + 2 * std
    assert event_flags(past + [just_under])[-1] is False
    assert event_flags(past + [exact])[-1] is True



from datetime import datetime, time, timezone

import pytest

from quant_agents.research.news_categories import IST, assign_gdelt_day, assign_timestamp, event_sessions

MONDAY = date(2024, 1, 8)
TUESDAY = date(2024, 1, 9)
FRIDAY = date(2024, 1, 12)
NEXT_MONDAY = date(2024, 1, 15)
SESSIONS = (MONDAY, TUESDAY, date(2024, 1, 10), FRIDAY, NEXT_MONDAY)


def _at(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=IST)


def test_news_at_or_after_1530_moves_to_the_next_session() -> None:
    assert assign_timestamp(_at(MONDAY, 15, 29, 59), SESSIONS) == MONDAY
    assert assign_timestamp(_at(MONDAY, 15, 30, 0), SESSIONS) == TUESDAY
    assert assign_timestamp(_at(MONDAY, 18, 0), SESSIONS) == TUESDAY
    utc = datetime(2024, 1, 8, 10, 0, tzinfo=timezone.utc)  # 15:30 IST
    assert assign_timestamp(utc, SESSIONS) == TUESDAY


def test_weekend_and_missing_session_wait_for_the_next_open_day() -> None:
    saturday = _at(date(2024, 1, 13), 10, 0)
    assert assign_timestamp(saturday, SESSIONS) == NEXT_MONDAY
    thursday = date(2024, 1, 11)
    assert thursday not in SESSIONS
    assert assign_timestamp(_at(thursday, 11, 0), SESSIONS) == FRIDAY


def test_gdelt_day_never_uses_the_same_session() -> None:
    assert assign_gdelt_day(MONDAY, SESSIONS) == TUESDAY
    assert assign_gdelt_day(FRIDAY, SESSIONS) == NEXT_MONDAY
    days = [(MONDAY, True), (TUESDAY, True), (date(2024, 1, 7), False)]
    assert event_sessions(days, SESSIONS) == {TUESDAY, date(2024, 1, 10)}


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assign_timestamp(datetime(2024, 1, 8, 10, 0), SESSIONS)



from quant_agents.calendar.static_nse import HOLIDAYS_2024, HOLIDAYS_2025, HOLIDAYS_2026
from quant_agents.research.news_categories import CASH_HOLIDAYS, calendar_audit, trading_sessions


def test_listed_holiday_is_not_a_session_even_with_a_close() -> None:
    closes = {
        date(2024, 1, 25): 100.0,
        date(2024, 1, 26): 101.0,  # Republic Day, frozen holiday
        date(2024, 1, 27): 102.0,  # Saturday
        date(2024, 1, 29): 103.0,
    }
    assert trading_sessions(closes) == [date(2024, 1, 25), date(2024, 1, 29)]
    audit = calendar_audit(closes)
    assert audit["holiday_closes_dropped"] == 1
    assert audit["weekend_closes_dropped"] == 1


def test_cash_holidays_copy_the_static_nse_list() -> None:
    assert HOLIDAYS_2024 | HOLIDAYS_2025 | HOLIDAYS_2026 <= CASH_HOLIDAYS
    assert date(2017, 10, 19) in CASH_HOLIDAYS  # Muhurat, treated as closed
    assert date(2023, 11, 12) in CASH_HOLIDAYS


