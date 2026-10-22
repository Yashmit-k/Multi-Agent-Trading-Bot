"""News inputs: boilerplate price pages are dropped, old articles do not count, confidence follows evidence."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from intelligence_agents.news.quality import evidence_confidence, is_boilerplate, recent_news

NOW = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


def _article(title: str, hours_ago: float):  # type: ignore[no-untyped-def]
    return SimpleNamespace(title=title, published_at=NOW - timedelta(hours=hours_ago))


def test_boilerplate_titles_are_recognised() -> None:
    for title in (
        "Bajaj Finance Share Price Live Updates: Bajaj Finance Stock Details",
        "Adani Ports SEZ Share Price Highlights: Adani Ports SEZ Stock Price History",
        "Bharti Airtel Share Price Today Live Updates",
    ):
        assert is_boilerplate(title), title
    for title in ("Adani, Jabil sign MoU for AI data centre JV", "TCS Q2 results: net profit rises 9%", "Crude above $100: BPCL could face earnings pressure"):
        assert not is_boilerplate(title), title


def test_recent_news_drops_old_and_boilerplate_and_caps_count() -> None:
    articles = [_article("Real story", 2), _article("Old story", 100), _article("X Share Price Live Updates: X Stock Details", 1)] + [_article(f"Story {i}", 3 + i) for i in range(20)]
    kept = recent_news(articles, NOW)
    titles = [item.title for item in kept]
    assert "Old story" not in titles and not any("Live Updates" in t for t in titles)
    assert titles[0] == "Real story" and len(kept) == 12


def test_evidence_confidence_grows_with_count_and_freshness() -> None:
    one = evidence_confidence([_article("a", 2)], NOW, 0.55)
    four = evidence_confidence([_article(str(i), 2) for i in range(4)], NOW, 0.55)
    stale = evidence_confidence([_article(str(i), 40) for i in range(4)], NOW, 0.55)
    assert 0 < one < four == 0.55 and stale < four
    assert evidence_confidence([], NOW, 0.55) == 0.0
