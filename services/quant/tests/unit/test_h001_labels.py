from datetime import date, datetime, time
from decimal import Decimal

from quant_agents.research.h001.calendar import DailyBar
from quant_agents.research.h001.events import IST, ExclusionReason
from quant_agents.research.h001.labels import horizon_close, make_label, require_primary_horizon


def _close(symbol: str, day: date, price: str) -> DailyBar:
    return DailyBar(symbol, datetime.combine(day, time(15, 30), tzinfo=IST), Decimal(price))


def test_sign_label_and_zero() -> None:
    positive = make_label("1", "RELIANCE", Decimal("100"), Decimal("101"))
    assert positive.y == 1
    assert positive.return_gross == Decimal("0.01")
    assert positive.horizon == "H1"
    negative = make_label("1", "RELIANCE", Decimal("100"), Decimal("99"))
    assert negative.y == 0
    zero = make_label("1", "RELIANCE", Decimal("100"), Decimal("100"))
    assert zero.y == 0
    assert zero.return_gross == Decimal(0)


def test_missing_and_nonpositive_prices_are_not_imputed() -> None:
    assert make_label("1", "RELIANCE", None, Decimal("1")).reason == ExclusionReason.MISSING_ENTRY_BAR
    assert make_label("1", "RELIANCE", Decimal("1"), None).reason == ExclusionReason.MISSING_HORIZON_CLOSE
    assert make_label("1", "RELIANCE", Decimal("0"), Decimal("1")).reason == ExclusionReason.NONPOSITIVE_PRICE
    assert make_label("1", "RELIANCE", Decimal("1"), Decimal("-1")).reason == ExclusionReason.NONPOSITIVE_PRICE


def test_next_session_skips_a_weekend_gap() -> None:
    friday = date(2024, 1, 12)
    monday = date(2024, 1, 15)
    tuesday = date(2024, 1, 16)
    calendar = (friday, monday, tuesday)
    session, price = horizon_close("1", "RELIANCE", friday, calendar, [_close("RELIANCE", monday, "110")])
    assert session == monday
    assert price == Decimal("110")
    wednesday = date(2024, 1, 10)
    thursday = date(2024, 1, 11)
    mid, mid_price = horizon_close(
        "1",
        "RELIANCE",
        wednesday,
        (wednesday, thursday),
        [_close("RELIANCE", thursday, "90")],
    )
    assert mid == thursday
    assert mid_price == Decimal("90")
    missing = horizon_close("1", "RELIANCE", friday, calendar, [_close("TCS", monday, "110")])
    assert missing.reason == ExclusionReason.MISSING_HORIZON_CLOSE
    five_minute = DailyBar(
        "RELIANCE",
        datetime.combine(monday, time(15, 15), tzinfo=IST),
        Decimal("999"),
    )
    not_the_intraday_close = horizon_close("1", "RELIANCE", friday, calendar, [five_minute])
    assert not_the_intraday_close.reason == ExclusionReason.MISSING_HORIZON_CLOSE


def test_h5_is_not_primary() -> None:
    assert require_primary_horizon("H1") == "H1"
    try:
        require_primary_horizon("H5")
    except ValueError as exc:
        assert "H5" in str(exc)
    else:
        raise AssertionError("H5 was accepted")
