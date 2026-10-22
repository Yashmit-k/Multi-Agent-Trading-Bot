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


