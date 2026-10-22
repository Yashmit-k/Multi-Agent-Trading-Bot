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


