"""Point-in-time fundamental visibility."""

from datetime import datetime, timezone

import pytest

from contracts.fixtures import FIXTURE_AS_OF, FIXTURE_SYMBOLS, all_fundamentals, fundamentals_for
from contracts.pit import FutureDataError, assert_available


def test_future_fundamental_data_is_rejected_for_historical_as_of() -> None:
    future = next(point for point in all_fundamentals("INFY") if point.period == "Q1FY2025")
    with pytest.raises(FutureDataError):
        assert_available(future, FIXTURE_AS_OF)
    visible = assert_available(
        next(point for point in all_fundamentals("INFY") if point.period == "FY2024"),
        FIXTURE_AS_OF,
    )
    assert visible.available_at <= FIXTURE_AS_OF


def test_naive_as_of_is_rejected() -> None:
    point = next(point for point in all_fundamentals("TCS") if point.period == "FY2024")
    with pytest.raises(ValueError, match="timezone-aware"):
        assert_available(point, datetime(2024, 6, 3, 10, 0))


def test_provider_hides_future_rows_for_every_fixture_symbol() -> None:
    for symbol in FIXTURE_SYMBOLS:
        rows = fundamentals_for(symbol, FIXTURE_AS_OF)
        assert [row.period for row in rows] == ["FY2024"]
        assert all(row.available_at <= FIXTURE_AS_OF for row in rows)


def test_future_as_of_can_see_the_later_filing() -> None:
    as_of = datetime(2024, 7, 20, 12, 0, tzinfo=timezone.utc)
    periods = [row.period for row in fundamentals_for("HDFCBANK", as_of)]
    assert periods == ["FY2024", "Q1FY2025"]
