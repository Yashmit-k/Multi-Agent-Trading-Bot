from datetime import date, datetime, time, timedelta
from decimal import Decimal

from quant_agents.research.h001.calendar import DailyBar
from quant_agents.research.h001.events import IST, ExclusionReason
from quant_agents.research.h001.features import (
    FEATURE_COLUMNS,
    FORBIDDEN_COLUMNS,
    build_features,
    minutes_from_midnight,
)


def _day(index: int) -> date:
    return date(2024, 1, 1) + timedelta(days=index)


def _close(symbol: str, day: date, price: str) -> DailyBar:
    return DailyBar(symbol, datetime.combine(day, time(15, 30), tzinfo=IST), Decimal(price))


def _history(prices: list[str], *, extra: list[DailyBar] | None = None) -> tuple[list[date], date, list[DailyBar]]:
    sessions = [_day(index) for index in range(len(prices))]
    decision = _day(len(prices))
    bars = [_close("RELIANCE", session, price) for session, price in zip(sessions, prices, strict=True)]
    if extra:
        bars.extend(extra)
    return sessions, decision, bars


def test_minutes_and_three_returns_ignore_the_decision_close() -> None:
    moment = datetime(2024, 1, 11, 15, 53, 23, tzinfo=IST)
    assert minutes_from_midnight(moment) == 15 * 60 + 53
    prices = [str(100 + index) for index in range(21)]
    sessions, decision, bars = _history(prices, extra=[_close("RELIANCE", _day(21), "999")])
    built = build_features("1", "RELIANCE", decision, moment, sessions + [decision], bars)
    assert built.minute_of_day == 953
    last = Decimal(prices[-1])
    assert built.return_1 == last / Decimal(prices[-2]) - 1
    assert built.return_5 == last / Decimal(prices[-6]) - 1
    assert built.return_20 == last / Decimal(prices[0]) - 1
    assert Decimal("999") not in built.as_tuple()


def test_hole_is_not_filled_from_an_older_close() -> None:
    prices = ["100"] * 21
    sessions, decision, bars = _history(prices)
    older = _close("RELIANCE", sessions[0] - timedelta(days=3), "1")
    hole = sessions[10]
    kept = [bar for bar in bars if bar.end.astimezone(IST).date() != hole]
    result = build_features("1", "RELIANCE", decision, datetime(2024, 2, 1, tzinfo=IST), sessions + [decision], kept + [older])
    assert result.reason == ExclusionReason.MISSING_DAILY_HISTORY
    last_missing = [bar for bar in bars if bar.end.astimezone(IST).date() != sessions[-1]]
    missing_last = build_features(
        "1",
        "RELIANCE",
        decision,
        datetime(2024, 2, 1, tzinfo=IST),
        sessions + [decision],
        last_missing,
    )
    assert missing_last.reason == ExclusionReason.MISSING_DAILY_HISTORY


def test_short_tape_and_nonpositive_close() -> None:
    sessions, decision, bars = _history(["100"] * 20)
    short = build_features("1", "RELIANCE", decision, datetime(2024, 2, 1, tzinfo=IST), sessions + [decision], bars)
    assert short.reason == ExclusionReason.SHORT_HISTORY
    full_sessions, full_decision, full_bars = _history(["100"] * 20 + ["0"])
    bad = build_features(
        "1",
        "RELIANCE",
        full_decision,
        datetime(2024, 2, 1, tzinfo=IST),
        full_sessions + [full_decision],
        full_bars,
    )
    assert bad.reason == ExclusionReason.NONPOSITIVE_PRICE


def test_forbidden_names_are_not_columns() -> None:
    assert FEATURE_COLUMNS == ("minute_of_day", "return_1", "return_5", "return_20")
    assert FORBIDDEN_COLUMNS.isdisjoint(FEATURE_COLUMNS)
