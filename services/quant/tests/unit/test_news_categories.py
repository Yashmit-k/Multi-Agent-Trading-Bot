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



from quant_agents.research.news_categories import (
    close_mismatches,
    parse_api_daily,
    parse_api_intraday,
    prefer_api,
    session_realised_variance,
)


def test_cross_check_flags_only_gaps_above_half_a_percent() -> None:
    day = date(2024, 6, 3)
    yahoo = {day: 100.4, date(2024, 6, 4): 110.0}
    api = {day: 100.0, date(2024, 6, 4): 100.0}
    rows = close_mismatches(yahoo, api)
    assert [row["date"] for row in rows] == ["2024-06-04"]
    merged = prefer_api(yahoo, api)
    assert merged[day] == 100.0
    assert merged[date(2024, 6, 4)] == 100.0


def test_api_daily_and_intraday_parsers_use_ist() -> None:
    payload = [
        {
            "close": "200",
            "end": "2024-06-03T10:00:00+00:00",  # 15:30 IST
            "start": "2024-06-03T03:45:00+00:00",
        }
    ]
    assert parse_api_daily(payload) == {date(2024, 6, 3): 200.0}
    bars = parse_api_intraday(
        [
            {"start": "2024-06-03T04:00:00+00:00", "close": "100"},  # 09:30 IST
            {"start": "2024-06-03T04:05:00+00:00", "close": "110"},
            {"start": "2024-06-03T03:00:00+00:00", "close": "90"},  # 08:30, before the open
        ]
    )
    assert len(bars) == 2
    variance = session_realised_variance(bars)
    assert date(2024, 6, 3) in variance
    assert variance[date(2024, 6, 3)] > 0



import pytest

from quant_agents.research.news_categories import (
    filled_volume,
    gdelt_request_url,
    parse_stamped,
    sum_category_volume,
    tone_by_day,
    volume_by_day,
)


def test_gdelt_daily_volume_sums_subdaily_buckets_and_tones_are_weighted() -> None:
    payload = {
        "timeline": [
            {
                "data": [
                    {"date": "20170101000000", "value": 2},
                    {"date": "20170101001500", "value": 4},
                    {"date": "20170102T000000Z", "value": 5},
                ]
            }
        ]
    }
    points = parse_stamped(payload)
    assert volume_by_day(points)[date(2017, 1, 1)] == 6
    tone = {
        "timeline": [
            {
                "data": [
                    {"date": "20170101000000", "value": 0},
                    {"date": "20170101001500", "value": 6},
                ]
            }
        ]
    }
    weighted = tone_by_day(parse_stamped(tone), points)
    assert weighted[date(2017, 1, 1)] == pytest.approx((0 * 2 + 6 * 4) / 6)
    filled = filled_volume({date(2017, 1, 1): 6}, date(2017, 1, 1), date(2017, 1, 3))
    assert filled == [(date(2017, 1, 1), 6.0), (date(2017, 1, 2), 0.0), (date(2017, 1, 3), 0.0)]
    combined = sum_category_volume([{date(2017, 1, 2): 1.0}, {date(2017, 1, 2): 2.0}], date(2017, 1, 1), date(2017, 1, 2))
    assert combined[-1] == (date(2017, 1, 2), 3.0)


def test_gdelt_url_freezes_mode_and_dates() -> None:
    url = gdelt_request_url("(war)", "timelinevolraw", "20170101000000", "20261022000000")
    assert url.startswith("https://api.gdeltproject.org/api/v2/doc/doc?")
    assert "mode=timelinevolraw" in url
    assert "startdatetime=20170101000000" in url
    assert "format=json" in url



from pathlib import Path

import pytest

from quant_agents.research.news_categories import cache_file, fetch_json


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def get(self, url: str) -> _Response:
        self.calls += 1
        return _Response(self.text)


def test_fetch_sleeps_only_on_a_cache_miss(tmp_path: Path) -> None:
    client = _Client('{"timeline":[]}')
    slept: list[float] = []
    url = "https://api.gdeltproject.org/api/v2/doc/doc?query=war"
    first, did_http = fetch_json(url, tmp_path, client, slept.append)
    second, did_http_again = fetch_json(url, tmp_path, client, slept.append)
    assert first == {"timeline": []}
    assert second == first
    assert did_http is True
    assert did_http_again is False
    assert slept == [5.0]
    assert client.calls == 1
    assert cache_file(tmp_path, url).exists()


def test_fetch_rejects_a_non_json_body(tmp_path: Path) -> None:
    client = _Client("please slow down")
    with pytest.raises(RuntimeError, match="GDELT"):
        fetch_json("https://example.test/gdelt", tmp_path, client, lambda _seconds: None)



import pytest

from quant_agents.research.news_categories import block_bootstrap_diff


def test_bootstrap_difference_and_seed_zero_are_deterministic() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    event = [True, False, True, False, True, False, True, False]
    first = block_bootstrap_diff(values, event, n_boot=40, seed=0)
    second = block_bootstrap_diff(values, event, n_boot=40, seed=0)
    other = block_bootstrap_diff(values, event, n_boot=40, seed=1)
    assert first.diff == pytest.approx(-1.0)
    assert first.p == second.p
    assert first.draws == second.draws
    assert first.draws != other.draws
    assert 0.0 < first.p <= 1.0


def test_bootstrap_without_two_per_group_does_not_draw() -> None:
    result = block_bootstrap_diff([1.0, 2.0, 3.0], [True, False, False], n_boot=10, seed=0)
    assert result.diff is None
    assert result.p == 1.0
    assert result.draws == ()


