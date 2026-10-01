"""Load contract fixtures into stores. BACKTEST news/fundamentals come from here."""

from __future__ import annotations

from datetime import datetime, timezone

from contracts.fixtures import FIXTURE_SYMBOLS, all_articles, all_fundamentals

from intelligence_agents.fundamentals.store import FundamentalStore
from intelligence_agents.news.store import NewsStore


def load_news_fixtures(store: NewsStore, *, now: datetime | None = None) -> int:
    moment = now or datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)
    inserted = 0
    for symbol in FIXTURE_SYMBOLS:
        for article in all_articles(symbol):
            result = store.insert(article, now=moment)
            if result.inserted:
                inserted += 1
    return inserted


def load_fundamental_fixtures(store: FundamentalStore) -> int:
    inserted = 0
    for symbol in FIXTURE_SYMBOLS:
        for point in all_fundamentals(symbol):
            if store.insert(point):
                inserted += 1
    return inserted
