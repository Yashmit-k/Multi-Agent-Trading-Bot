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


def test_a_429_on_a_wide_window_is_split(tmp_path: Path) -> None:
    import urllib.parse
    from datetime import date

    from quant_agents.research.news_categories import load_gdelt_days

    class _SplitClient:
        def get(self, url: str) -> _StatusResponse:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            start = date(int(query["startdatetime"][0][0:4]), int(query["startdatetime"][0][4:6]), int(query["startdatetime"][0][6:8]))
            end = date(int(query["enddatetime"][0][0:4]), int(query["enddatetime"][0][4:6]), int(query["enddatetime"][0][6:8]))
            if (end - start).days > 40:
                return _StatusResponse("busy", 429)
            return _StatusResponse(
                '{"timeline":[{"data":[{"date":"' + query["startdatetime"][0] + '","value":4}]}]}',
                200,
            )

    slept: list[float] = []
    days = load_gdelt_days("(war)", "timelinevolraw", date(2017, 1, 1), date(2017, 3, 15), tmp_path, _SplitClient(), slept.append, "geopolitics_war")
    assert days[date(2017, 1, 1)] == 4.0
    assert any(pause == 15.0 for pause in slept)


def test_a_short_window_counts_omitted_days_as_answered(tmp_path: Path) -> None:
    from quant_agents.research.news_categories import coverage_days, covered_dates, load_gdelt_days

    start, end = date(2017, 1, 1), date(2017, 1, 3)
    assert covered_dates(start, end, {date(2017, 1, 1)}) == (start, end)
    long_start, long_end = date(2017, 1, 1), date(2017, 6, 1)
    assert covered_dates(long_start, long_end, {date(2017, 1, 1), date(2017, 3, 1)}) == (date(2017, 1, 1), date(2017, 3, 1))

    class _Partial:
        def get(self, url: str) -> _StatusResponse:
            return _StatusResponse(
                '{"timeline":[{"series":"Article Count","data":[{"date":"20170101000000","value":4}]}]}',
                200,
            )

    load_gdelt_days("(war)", "timelinevolraw", start, end, tmp_path, _Partial(), lambda _seconds: None, "geopolitics_war")
    answered = coverage_days(tmp_path)[("(war)", "timelinevolraw")]
    assert answered == {date(2017, 1, 1), date(2017, 1, 2), date(2017, 1, 3)}


def test_gap_windows_skip_days_already_in_hand() -> None:
    from datetime import date

    from quant_agents.research.news_categories import gap_windows

    have = {date(2017, 1, 3)}
    assert gap_windows(have, date(2017, 1, 1), date(2017, 1, 6), span_days=2) == [
        (date(2017, 1, 1), date(2017, 1, 2)),
        (date(2017, 1, 4), date(2017, 1, 5)),
        (date(2017, 1, 6), date(2017, 1, 6)),
    ]


def test_gdelt_windows_cover_every_day_once() -> None:
    from datetime import date, timedelta

    from quant_agents.research.news_categories import gdelt_windows

    windows = gdelt_windows(date(2017, 1, 1), date(2026, 10, 22))
    covered: list[date] = []
    for start_stamp, end_stamp in windows:
        start = date(int(start_stamp[0:4]), int(start_stamp[4:6]), int(start_stamp[6:8]))
        end = date(int(end_stamp[0:4]), int(end_stamp[4:6]), int(end_stamp[6:8]))
        assert (end - start).days < 700
        day = start
        while day <= end:
            covered.append(day)
            day += timedelta(days=1)
    assert covered[0] == date(2017, 1, 1)
    assert covered[-1] == date(2026, 10, 22)
    assert len(covered) == len(set(covered))


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


def test_fetch_retries_a_dropped_connection(tmp_path: Path) -> None:
    class _Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str) -> _Response:
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("dropped")
            return _Response('{"timeline":[]}')

    client = _Flaky()
    slept: list[float] = []
    payload, did_http = fetch_json("https://api.gdeltproject.org/api/v2/doc/doc?query=flaky", tmp_path, client, slept.append)
    assert payload == {"timeline": []}
    assert did_http is True
    assert slept == [10.0, 5.0]
    assert client.calls == 2


def test_fetch_rejects_a_non_json_body(tmp_path: Path) -> None:
    client = _Client("please slow down")
    with pytest.raises(RuntimeError, match="GDELT"):
        fetch_json("https://example.test/gdelt", tmp_path, client, lambda _seconds: None)


class _StatusResponse:
    def __init__(self, text: str, status: int) -> None:
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


class _RetryClient:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url: str) -> _StatusResponse:
        self.calls += 1
        if self.calls == 1:
            return _StatusResponse("busy", 429)
        return _StatusResponse('{"timeline":[]}', 200)


def test_fetch_retries_a_429_then_caches(tmp_path: Path) -> None:
    client = _RetryClient()
    slept: list[float] = []
    url = "https://api.gdeltproject.org/api/v2/doc/doc?query=retry"
    payload, did_http = fetch_json(url, tmp_path, client, slept.append)
    assert payload == {"timeline": []}
    assert did_http is True
    assert client.calls == 2
    assert slept == [15.0, 5.0]
    again, did_again = fetch_json(url, tmp_path, client, slept.append)
    assert again == payload
    assert did_again is False
    assert client.calls == 2



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



import pytest

from quant_agents.research.news_categories import holm_adjust


def test_holm_matches_the_worked_example() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted[0] == pytest.approx(0.03)
    assert adjusted[1] == pytest.approx(0.06)
    assert adjusted[2] == pytest.approx(0.06)


def test_holm_caps_at_one() -> None:
    assert holm_adjust([0.9, 0.8]) == [1.0, 1.0]



from datetime import timedelta

import pytest

from quant_agents.research.news_categories import CASH_HOLIDAYS, build_outcomes, split_flags


def _weekday_closes(start: date, count: int, price: float = 100.0) -> tuple[list[date], dict[date, float]]:
    sessions: list[date] = []
    closes: dict[date, float] = {}
    day = start
    while len(sessions) < count:
        if day.weekday() < 5 and day not in CASH_HOLIDAYS:
            sessions.append(day)
            closes[day] = price + len(sessions)
        day += timedelta(days=1)
    return sessions, closes


def test_forward_window_does_not_cross_the_split() -> None:
    sessions, closes = _weekday_closes(date(2022, 12, 20), 12)
    vix = {day: 15.0 for day in sessions}
    mask = split_flags(sessions, date(2022, 12, 1), date(2022, 12, 31))
    assert any(mask) and not all(mask)
    columns = build_outcomes(sessions, closes, vix, {}, mask)
    last_train = max(index for index, flag in enumerate(mask) if flag)
    assert columns["ret_0"][last_train] == pytest.approx(closes[sessions[last_train]] / closes[sessions[last_train - 1]] - 1)
    assert columns["ret_1"][last_train] != columns["ret_1"][last_train]  # NaN: t+1 is in 2023



import pytest

from quant_agents.research.news_categories import stratified_diff, tercile_edges, vix_tercile


def test_tercile_cuts_come_from_the_supplied_train_sample_only() -> None:
    low, high = tercile_edges([1, 2, 3, 4, 5, 6, 7, 8, 9])
    assert vix_tercile(low, (low, high)) == 0
    assert vix_tercile(high, (low, high)) == 1
    assert vix_tercile(high + 1, (low, high)) == 2


def test_matched_difference_weights_by_event_count() -> None:
    values = [1.0, 0.0, 5.0, 1.0]
    event = [True, False, True, False]
    strata = [(0, 0), (0, 0), (1, 0), (1, 0)]
    # stratum (0, 0): 1 - 0 = 1, one event. stratum (1, 0): 5 - 1 = 4, one event.
    assert stratified_diff(values, event, strata) == pytest.approx(2.5)



from quant_agents.research.news_categories import OUTCOMES, category_matters


def _cell(diff: float, p: float, holm: float | None) -> dict[str, object]:
    return {"diff": diff, "p": p, "holm_p": holm}


def test_pass_rule_needs_holm_validate_p_and_the_same_sign() -> None:
    def pack(diff: float, p: float, holm: float | None) -> dict[str, object]:
        return {"outcomes": {name: _cell(0.0, 1.0, 1.0) for name in OUTCOMES} | {"ret_0": _cell(diff, p, holm)}}

    assert category_matters(pack(0.01, 0.001, 0.04), pack(0.02, 0.03, None)) == ["ret_0"]
    assert category_matters(pack(0.01, 0.001, 0.04), pack(-0.02, 0.03, None)) == []
    assert category_matters(pack(0.01, 0.001, 0.06), pack(0.02, 0.03, None)) == []
    assert category_matters(pack(0.01, 0.001, 0.04), pack(0.02, 0.05, None)) == []



from quant_agents.research.news_categories import PUBLIC_DAILY_NIFTY, coverage


def test_public_urls_are_the_single_polite_calls() -> None:
    assert "limit=2000" in PUBLIC_DAILY_NIFTY
    assert coverage([])["bars"] == 0
    assert coverage([{"start": "a", "end": "b"}])["bars"] == 1



import json
from datetime import timedelta

import pytest

from quant_agents.research.news_categories import CATEGORIES, assemble_study


def test_assemble_scores_each_category_without_a_network(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions, closes = _weekday_closes(date(2017, 1, 2), 40)
    # Push the last sessions into 2023 by rebuilding a longer calendar from late 2022.
    sessions, closes = _weekday_closes(date(2022, 11, 1), 80, price=100.0)
    vix = {day: 12.0 + (index % 5) for index, day in enumerate(sessions)}
    days = [(day - timedelta(days=1), index % 17 == 0) for index, day in enumerate(sessions)]
    category_days = {item[0]: days for item in CATEGORIES}
    result = assemble_study(
        sessions,
        closes,
        vix,
        {},
        category_days,
        protocol_commit="abc",
        n_boot=20,
    )
    assert result["protocol_commit"] == "abc"
    assert len(result["categories"]) == 10
    assert "conclusion" in result
    assert all("holm_p" in item["train"]["outcomes"]["ret_0"] for item in result["categories"])
    assert "holm_p" not in result["categories"][0]["validate"]["outcomes"]["ret_0"]



import json

from quant_agents.research.news_categories import NOTHING_PASSES, assemble_study, render_markdown



import json
from datetime import timedelta

from quant_agents.research.news_categories import CATEGORIES, run_train, run_validate


class _Body:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _StudyClient:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url: str) -> _Body:
        self.calls += 1
        if "gdeltproject" in url:
            data = []
            day = date(2017, 1, 1)
            for index in range(70):
                data.append({"date": day.strftime("%Y%m%d") + "000000", "value": 1 + (index % 3)})
                day += timedelta(days=1)
            data.append({"date": "20170320000000", "value": 400})
            return _Body(json.dumps({"timeline": [{"data": data}]}))
        return _Body("[]")


def test_train_process_does_not_score_validate_and_validate_runs_once(tmp_path: Path) -> None:
    def yahoo(_symbol: str, _start: str, _end: str) -> dict[date, float]:
        closes: dict[date, float] = {}
        day = date(2022, 11, 1)
        while day <= date(2023, 3, 31):
            if day.weekday() < 5:
                closes[day] = 100.0 + (day - date(2022, 11, 1)).days
            day += timedelta(days=1)
        return closes

    slept: list[float] = []
    train_path = run_train(
        tmp_path,
        today=date(2023, 3, 31),
        client=_StudyClient(),
        sleeper=slept.append,
        yahoo=yahoo,
        n_boot=8,
        protocol_commit="feedface",
    )
    trained = json.loads(train_path.read_text(encoding="utf-8"))
    assert "validate" not in trained["categories"][0]
    assert slept  # GDELT misses pause; the public candle cache miss also pauses only for GDELT
    result = run_validate(tmp_path, n_boot=8)
    assert result["protocol_commit"] == "feedface"
    assert len(result["categories"]) == len(CATEGORIES)
    try:
        run_validate(tmp_path, n_boot=8)
    except RuntimeError as exc:
        assert "already scored" in str(exc)
    else:
        raise AssertionError("validate ran twice")


def test_result_note_quotes_the_negative_conclusion_when_nothing_passes() -> None:
    sessions, closes = _weekday_closes(date(2022, 11, 1), 80)
    vix = {day: 12.0 + (index % 5) for index, day in enumerate(sessions)}
    days = [(day - timedelta(days=1), False) for day in sessions]
    category_days = {item[0]: days for item in CATEGORIES}
    result = assemble_study(sessions, closes, vix, {}, category_days, protocol_commit="deadbeef", n_boot=15)
    text = render_markdown(result)
    assert "deadbeef" in text
    assert NOTHING_PASSES in text
    assert "Matters: **False**" in text
    json.dumps(result)
