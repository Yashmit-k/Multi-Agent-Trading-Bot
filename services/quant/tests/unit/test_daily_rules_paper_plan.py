"""Synthetic checks for the research-only momentum_20 paper plan. No snapshot, no paper tables."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle

from quant_agents.research.daily_rules.paper_plan import PAPER_DAILY_ENTRY_LIMIT, PAPER_NOTIONAL, plan_momentum_20

IST = ZoneInfo("Asia/Kolkata")
START = date(2026, 9, 1)


def _bar(symbol: str, day: date, close: str, end_clock: time = time(15, 30)) -> Candle:
    start = datetime.combine(day, time(9, 15), tzinfo=IST)
    end = datetime.combine(day, end_clock, tzinfo=IST)
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.D1,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1,
        start=start,
        end=end,
    )


def _days(count: int) -> list[date]:
    return [START + timedelta(days=offset) for offset in range(count)]


def _closes(symbol: str, days: list[date], prices: list[str]) -> list[Candle]:
    return [_bar(symbol, day, price) for day, price in zip(days, prices, strict=True)]


def _after(day: date) -> datetime:
    return datetime.combine(day, time(16, 0), tzinfo=IST)


def _future(last: date, count: int = 6) -> list[date]:
    return [last + timedelta(days=offset) for offset in range(1, count + 1)]


def test_twenty_session_boundary_uses_the_close_twenty_bars_back() -> None:
    days = _days(21)
    above = ["100"] + ["90"] * 19 + ["100.01"]
    equal = ["100"] + ["90"] * 19 + ["100"]
    bars = _closes("UP", days, above) + _closes("EQ", days, equal)
    plan = plan_momentum_20(bars, _after(days[-1]), _future(days[-1]))
    assert plan.selected == ("UP",)
    assert plan.not_selected == ("EQ",)
    assert plan.decision_date == days[-1]
    assert plan.notional_per_symbol == PAPER_NOTIONAL
    assert plan.proposed_notional == Decimal("20000")


def test_twenty_bars_is_insufficient_history() -> None:
    days = _days(21)
    bars = _closes("FULL", days, ["100"] + ["101"] * 20) + _closes("SHORT", days[1:], ["101"] * 20)
    plan = plan_momentum_20(bars, _after(days[-1]), _future(days[-1]))
    assert plan.selected == ("FULL",)
    assert plan.excluded == {"SHORT": "insufficient_history"}


def test_incomplete_bar_is_not_a_session() -> None:
    days = _days(22)
    bars = _closes("ABC", days[:21], ["100"] + ["101"] * 20)
    bars.append(_bar("ABC", days[21], "50", end_clock=time(13, 0)))
    plan = plan_momentum_20(bars, _after(days[21]), _future(days[21]))
    assert plan.excluded == {"ABC": "incomplete_daily_bar"}
    assert plan.selected == ()


def test_missing_decision_bar_is_reported_not_filled() -> None:
    days = _days(22)
    bars = _closes("LIVE", days, ["100"] * 2 + ["101"] * 20) + _closes("STALE", days[:21], ["100"] + ["101"] * 20)
    plan = plan_momentum_20(bars, _after(days[-1]), _future(days[-1]))
    assert plan.selected == ("LIVE",)
    assert plan.excluded == {"STALE": "missing_decision_bar"}


def test_gap_inside_history_is_reported_and_not_filled() -> None:
    days = _days(23)
    gapped = [day for index, day in enumerate(days) if index != 10]
    bars = _closes("FULL", days, ["100"] * 3 + ["101"] * 20) + _closes("GAP", gapped, ["100"] * 2 + ["101"] * 20)
    plan = plan_momentum_20(bars, _after(days[-1]), _future(days[-1]))
    assert plan.history_gaps == {"GAP": 1}
    assert plan.selected == ("FULL", "GAP")


def test_future_bars_are_ignored() -> None:
    days = _days(23)
    bars = _closes("ABC", days, ["100"] + ["90"] * 20 + ["200", "200"])
    decision = days[20]
    plan = plan_momentum_20(bars, _after(decision), _future(decision))
    assert plan.decision_date == decision
    assert plan.selected == ()
    assert plan.not_selected == ("ABC",)


def test_entry_and_exit_come_from_the_calendar() -> None:
    days = _days(21)
    bars = _closes("ABC", days, ["100"] + ["101"] * 20)
    decision = days[-1]
    calendar = [
        decision - timedelta(days=1),
        decision,
        date(2026, 9, 23),
        date(2026, 9, 24),
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
    ]
    plan = plan_momentum_20(bars, _after(decision), calendar)
    assert plan.entry_date == date(2026, 9, 23)
    assert plan.exit_date == date(2026, 9, 30)
    assert plan.issues == ()
    short = plan_momentum_20(bars, _after(decision), calendar[:5])
    assert short.entry_date == date(2026, 9, 23)
    assert short.exit_date is None
    assert "calendar_too_short_for_exit" in short.issues


def test_large_basket_is_reported_not_truncated() -> None:
    days = _days(21)
    bars = []
    names = [f"S{index:02d}" for index in range(PAPER_DAILY_ENTRY_LIMIT + 2)]
    for name in names:
        bars += _closes(name, days, ["100"] + ["101"] * 20)
    plan = plan_momentum_20(bars, _after(days[-1]), _future(days[-1]))
    assert plan.selected == tuple(names)
    assert plan.fits_daily_entry_limit is False
    assert any(issue.startswith("basket_exceeds_daily_entry_limit") for issue in plan.issues)


def test_planner_is_not_wired_into_paper_execution() -> None:
    root = Path(__file__).resolve().parents[3]
    for path in (root / "core").rglob("*.py"):
        assert "paper_plan" not in path.read_text(encoding="utf-8"), path
