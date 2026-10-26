"""The LLM agents score only inside INTELLIGENCE_ACTIVE_HOURS, so the free quota lasts into market hours."""

from datetime import datetime, timezone

import pytest

from intelligence_agents.errors import ConfigError
from intelligence_agents.schedule import parse_active_hours, scoring_allowed

UTC = timezone.utc


def test_the_window_is_ist_weekdays_only() -> None:
    window = "08:30-15:45"
    assert scoring_allowed(window, datetime(2026, 10, 26, 3, 0, tzinfo=UTC))  # Monday 08:30 IST
    assert scoring_allowed(window, datetime(2026, 10, 26, 10, 14, tzinfo=UTC))  # Monday 15:44 IST
    assert not scoring_allowed(window, datetime(2026, 10, 26, 10, 15, tzinfo=UTC))  # 15:45 IST: closed
    assert not scoring_allowed(window, datetime(2026, 10, 26, 20, 0, tzinfo=UTC))  # 01:30 IST overnight
    assert not scoring_allowed(window, datetime(2026, 10, 25, 5, 0, tzinfo=UTC))  # Sunday
    assert scoring_allowed("", datetime(2026, 10, 25, 20, 0, tzinfo=UTC))  # empty: always


def test_a_bad_window_is_refused() -> None:
    for raw in ("9-5", "15:45-08:30", "08:30"):
        with pytest.raises(ConfigError):
            parse_active_hours(raw)


def test_outside_the_window_news_is_pulled_but_nothing_is_scored(monkeypatch) -> None:
    import intelligence_agents.loop as loop
    from intelligence_agents.runtime import RunnerHealth

    calls: list[str] = []

    class Clock:
        def now(self):  # type: ignore[no-untyped-def]
            return datetime(2026, 10, 26, 20, 0, tzinfo=UTC)  # 01:30 IST

    class Runner:
        clock = Clock()

        def run(self, symbols, as_of):  # type: ignore[no-untyped-def]
            calls.append("scored")
            return []

    class Settings:
        active_hours = "08:30-15:45"
        eval_interval_seconds = 600
        symbols = ("RELIANCE",)

    monkeypatch.setattr(loop, "refresh_sources", lambda settings, runner, puller=None: calls.append("pulled"))
    loop.run_cycle(Settings(), Runner(), RunnerHealth(), router=None)  # type: ignore[arg-type]
    assert calls == ["pulled"]
