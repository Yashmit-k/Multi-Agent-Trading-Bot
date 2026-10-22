"""Which stored articles are real news for a stock, and how much they are worth.

Auto-generated market pages ("X Share Price Live Updates", "Stock Price History", "Stock Details")
restate the price move and carried strong scores from content-free headlines. They are dropped at
ingestion and ignored by the agents. Only recent articles count: a two-week-old story is not today's news.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

BOILERPLATE = re.compile(
    r"share price (live|today|highlights|updates?)|stock price (history|today|live|updates?)|"
    r"stock details|market update|share price:? (live )?blog|live updates?:|price highlights|top gainers|top losers|"
    r"stocks? to (watch|buy) today|sensex,? nifty (live|today)",
    re.IGNORECASE,
)
NEWS_LOOKBACK = timedelta(hours=72)
RESULTS_LOOKBACK = timedelta(days=7)
MAX_ARTICLES = 12


def is_boilerplate(title: str) -> bool:
    return bool(BOILERPLATE.search(title or ""))


def recent_news(articles, as_of: datetime, lookback: timedelta = NEWS_LOOKBACK):  # type: ignore[no-untyped-def]
    """Real articles published within `lookback` of as_of, newest first, at most MAX_ARTICLES."""
    kept = [item for item in articles if not is_boilerplate(item.title) and item.published_at >= as_of - lookback]
    kept.sort(key=lambda item: item.published_at, reverse=True)
    return kept[:MAX_ARTICLES]


def evidence_confidence(articles, as_of: datetime, cap: float) -> float:  # type: ignore[no-untyped-def]
    """More, fresher articles -> more confidence: 1 article ~0.3 of the cap, 4+ articles reach it."""
    if not articles:
        return 0.0
    count_factor = min(1.0, 0.3 + 0.7 * (len(articles) - 1) / 3)
    newest = max(item.published_at for item in articles)
    freshness = 1.0 if as_of - newest <= timedelta(hours=24) else 0.7
    return round(cap * count_factor * freshness, 4)
