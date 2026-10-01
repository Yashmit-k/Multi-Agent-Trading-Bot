from datetime import datetime, timedelta, timezone

from contracts.fixtures import FIXTURE_AS_OF, all_articles, content_hash
from contracts.schemas.news_article import NewsArticle

from intelligence_agents.news.store import MemoryNewsStore, SqliteNewsStore


def test_future_fixture_article_invisible(tmp_path):
    store = SqliteNewsStore(str(tmp_path / "n.db"))
    for article in all_articles("RELIANCE"):
        store.insert(article, now=FIXTURE_AS_OF)
    visible = store.articles_for("RELIANCE", FIXTURE_AS_OF)
    assert len(visible) == 1
    assert visible[0].published_at <= FIXTURE_AS_OF


def test_retrieved_at_after_as_of_hidden():
    store = MemoryNewsStore()
    article = all_articles("TCS")[0]
    late = article.model_copy(
        update={
            "article_id": "late-tcs",
            "retrieved_at": FIXTURE_AS_OF + timedelta(days=1),
            "content_hash": content_hash("late retrieve"),
            "raw_text": "late retrieve",
        }
    )
    store.insert(late, now=FIXTURE_AS_OF + timedelta(days=1))
    assert store.articles_for("TCS", FIXTURE_AS_OF) == []


def test_quarantine_then_graduate():
    store = MemoryNewsStore()
    future_pub = FIXTURE_AS_OF + timedelta(days=2)
    article = NewsArticle(
        article_id="future-rel",
        source="wire",
        title="RELIANCE future",
        url="https://example.test/future",
        published_at=future_pub,
        retrieved_at=future_pub,
        content_hash=content_hash("future-rel"),
        symbols=["RELIANCE"],
        raw_text="future-rel",
        metadata={},
    )
    result = store.insert(article, now=FIXTURE_AS_OF)
    assert result.quarantined is True
    assert store.articles_for("RELIANCE", future_pub) == []
    assert store.graduate_quarantine(future_pub) == 1
    assert len(store.articles_for("RELIANCE", future_pub)) == 1


def test_duplicate_content_hash():
    store = MemoryNewsStore()
    article = all_articles("INFY")[0]
    store.insert(article, now=FIXTURE_AS_OF)
    again = store.insert(article, now=FIXTURE_AS_OF)
    assert again.duplicate is True
