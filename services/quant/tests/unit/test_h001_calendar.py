from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from decimal import Decimal

import pytest

from quant_agents.research.h001.calendar import (
    DailyBar,
    FiveMinuteBar,
    decision_session,
    research_calendar,
    select_entry,
)
from quant_agents.research.h001.events import IST, ExclusionReason

UTC = timezone.utc


def _close(symbol: str, day: date, price: str = "100") -> DailyBar:
    return DailyBar(symbol, datetime.combine(day, time(15, 30), tzinfo=IST), Decimal(price))


def _entry(symbol: str, day: date, price: str = "100") -> FiveMinuteBar:
    start = datetime.combine(day, time(9, 15), tzinfo=IST)
    return FiveMinuteBar(symbol, start, start + timedelta(minutes=5), Decimal(price))


def _at(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=IST)


def test_union_uses_one_symbol_and_ignores_an_all_symbol_gap() -> None:
    monday = date(2024, 1, 8)
    tuesday = date(2024, 1, 9)
    wednesday = date(2024, 1, 10)
    bars = [
        _close("TATAMOTORS", monday),
        _close("RELIANCE", tuesday),
        _close("TCS", tuesday, "101"),
    ]
    assert research_calendar(bars) == (tuesday,)
    assert monday not in research_calendar(bars)
    assert wednesday not in research_calendar(bars)


def test_rule_b_boundaries_weekend_and_timezone() -> None:
    days = [date(2024, 1, 8), date(2024, 1, 9), date(2024, 1, 10), date(2024, 1, 12)]
    calendar = tuple(days)
    monday = days[0]
    assert decision_session(_at(monday, 9, 14, 59), calendar) == monday
    assert decision_session(_at(monday, 9, 15, 0), calendar) == days[1]
    assert decision_session(_at(monday, 9, 15, 1), calendar) == days[1]
    assert decision_session(_at(monday, 15, 30, 0), calendar) == days[1]
    saturday = _at(date(2024, 1, 13), 10, 0)
    assert decision_session(saturday, calendar) is None
    friday = date(2024, 1, 12)
    assert decision_session(_at(friday, 16, 0), calendar) is None
    same_instant = datetime.combine(monday, time(9, 15), tzinfo=IST).astimezone(UTC)
    assert decision_session(same_instant, calendar) == days[1]
    with pytest.raises(ValueError, match="naive"):
        decision_session(datetime(2024, 1, 8, 9, 14, 59), calendar)


def test_missing_entry_is_not_replaced_by_a_later_bar() -> None:
    monday = date(2024, 1, 8)
    tuesday = date(2024, 1, 9)
    calendar = (monday, tuesday)
    later = FiveMinuteBar(
        "RELIANCE",
        _at(monday, 9, 20),
        _at(monday, 9, 25),
        Decimal("100"),
    )
    missing = select_entry("1", "RELIANCE", _at(monday, 9, 0), calendar, [later])
    assert getattr(missing, "reason", None) == ExclusionReason.MISSING_ENTRY_BAR
    selected = select_entry("1", "RELIANCE", _at(monday, 9, 0), calendar, [_entry("RELIANCE", monday, "250")])
    assert selected.decision == monday
    assert selected.p0 == Decimal("250")
    waits = select_entry("2", "RELIANCE", _at(monday, 9, 15), calendar, [_entry("RELIANCE", tuesday, "260")])
    assert waits.decision == tuesday
    assert waits.p0 == Decimal("260")


def test_duplicate_entry_bar_is_rejected() -> None:
    monday = date(2024, 1, 8)
    with pytest.raises(Exception, match="more than one"):
        select_entry(
            "1",
            "RELIANCE",
            _at(monday, 9, 0),
            (monday,),
            [_entry("RELIANCE", monday, "100"), _entry("RELIANCE", monday, "101")],
        )


def test_calendar_module_does_not_consult_static_nse() -> None:
    text = (Path(__file__).resolve().parents[2] / "src" / "quant_agents" / "research" / "h001" / "calendar.py").read_text()
    imports = [line for line in text.splitlines() if line.startswith(("import ", "from "))]
    assert all("static_nse" not in line for line in imports)
