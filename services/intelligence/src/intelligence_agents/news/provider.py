"""Point-in-time news provider. BACKTEST leakage is enforced by the runner."""

from __future__ import annotations

from datetime import datetime

from contracts.schemas.news_article import NewsArticle
from contracts.time import require_aware

from intelligence_agents.news.store import NewsStore


class IntelligenceNewsProvider:
    def __init__(self, store: NewsStore) -> None:
        self._store = store

    def get_articles(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        aware = require_aware(as_of, "as_of")
        return self._store.articles_for(symbol, aware)
