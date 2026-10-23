"""NIFTY 50 tickers and name aliases used to attach RSS items to symbols."""

from __future__ import annotations

import re
from functools import lru_cache

from intelligence_agents.news.aliases import _TICKER, ALIASES, build_matcher, map_symbols

# One source of truth: the alias table production already uses (news/aliases.py), which lists exactly the
# current NIFTY 50 (BEL, SHRIRAMFIN, TMPV and TRENT in; DIVISLAB, LTIM, TATAMOTORS and TATAPOWER out).
NIFTY50_SYMBOLS: tuple[str, ...] = tuple(sorted(ALIASES))
COMPANY_ALIASES: dict[str, tuple[str, ...]] = ALIASES

DEFAULT_MARKET_FEEDS: tuple[str, ...] = (
    "https://news.google.com/rss/search?q=Nifty+50+OR+NSE+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
)


def google_news_symbol_feed(symbol: str) -> str:
    query = f"{symbol} NSE OR {symbol} BSE"
    aliases = COMPANY_ALIASES.get(symbol.upper(), ())
    if aliases:
        query = f"{aliases[0]} OR {symbol} NSE"
    from urllib.parse import quote_plus

    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )


@lru_cache(maxsize=8)
def _matcher(universe: frozenset[str]) -> list[tuple[re.Pattern[str], str]]:
    return build_matcher(set(universe))


def match_symbols(text: str, universe: set[str]) -> tuple[list[str], dict[str, str]]:
    """Return mapped tickers and the evidence string used for each match.

    Same rules as production's map_symbols (news/aliases.py): company names match on word boundaries
    ("Titan" never matches "Titanic", "ITC" never matches "pitch"), then exact upper-case tickers.
    """
    haystack = text or ""
    evidence: dict[str, str] = {}
    remaining = haystack
    for pattern, symbol in _matcher(frozenset(universe)):
        found = pattern.search(remaining)
        if found:
            evidence.setdefault(symbol, f"alias:{found.group(0)}")
            remaining = pattern.sub(" ", remaining)
    for found in _TICKER.finditer(remaining):
        token = found.group(1)
        if token in universe:
            evidence.setdefault(token, f"ticker:{token}")
    symbols = map_symbols(haystack, set(universe), _matcher(frozenset(universe)))
    return symbols, {symbol: evidence.get(symbol, "alias") for symbol in symbols}
