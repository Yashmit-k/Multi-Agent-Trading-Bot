"""RSS ingest with defusedxml, size caps, item caps, retries."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlparse

import httpx
from contracts.fixtures import content_hash
from contracts.schemas.news_article import NewsArticle
from defusedxml import ElementTree

from intelligence_agents.clock import Clock
from intelligence_agents.news.store import NewsStore

logger = logging.getLogger(__name__)

_TICKER = re.compile(r"\b([A-Z]{2,12})\b")


class RssPuller:
    def __init__(
        self,
        store: NewsStore,
        clock: Clock,
        universe: tuple[str, ...],
        *,
        max_bytes: int = 1024 * 1024,
        max_items: int = 100,
        interval_seconds: int = 300,
        retries: int = 3,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._clock = clock
        self._universe = {item.upper() for item in universe}
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._interval_seconds = interval_seconds
        self._retries = retries
        self._client = client or httpx.Client(timeout=15.0, follow_redirects=True)
        self._sleep = sleeper
        self._last_fetch: dict[str, datetime] = {}

    def pull(self, url: str) -> int:
        last = self._last_fetch.get(url)
        now = self._clock.now()
        if last is not None and (now - last).total_seconds() < self._interval_seconds:
            logger.info("rss_rate_limited", extra={"url": _safe_host(url)})
            return 0
        body = self._fetch(url)
        self._last_fetch[url] = now
        if body is None:
            return 0
        return self.ingest_bytes(body, feed_url=url, retrieved_at=now)

    def ingest_bytes(self, body: bytes, *, feed_url: str, retrieved_at: datetime) -> int:
        if len(body) > self._max_bytes:
            logger.warning("rss_body_too_large", extra={"bytes": len(body), "host": _safe_host(feed_url)})
            body = body[: self._max_bytes]
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            logger.warning("rss_malformed", extra={"host": _safe_host(feed_url)})
            return 0
        inserted = 0
        for index, item in enumerate(list(root.iter("item"))[: self._max_items]):
            title = _text(item, "title") or "untitled"
            link = _text(item, "link") or f"{feed_url}#{index}"
            description = _text(item, "description") or title
            pub = _parse_date(_text(item, "pubDate"), retrieved_at)
            symbols = self._map_symbols(f"{title} {description}")
            if not symbols:
                self._store.record_empty_symbol_drop(title)
                continue
            raw = description.strip() or title
            article_id = hashlib.sha256(f"{link}|{title}".encode()).hexdigest()[:32]
            url = link if link.startswith("http") else f"https://example.test/rss/{article_id}"
            try:
                article = NewsArticle(
                    article_id=f"rss-{article_id}",
                    source=_safe_host(feed_url),
                    title=title[:500],
                    url=url,
                    published_at=pub,
                    retrieved_at=max(retrieved_at, pub),
                    content_hash=content_hash(raw),
                    symbols=symbols,
                    raw_text=raw,
                    metadata={"feed": _safe_host(feed_url)},
                )
            except Exception:
                logger.warning("rss_item_invalid", extra={"host": _safe_host(feed_url)})
                continue
            if self._store.insert(article, now=retrieved_at).inserted:
                inserted += 1
        return inserted

    def _map_symbols(self, text: str) -> list[str]:
        found = {match.group(1) for match in _TICKER.finditer(text.upper())}
        return sorted(found & self._universe)

    def _fetch(self, url: str) -> bytes | None:
        delay = 0.2
        for attempt in range(self._retries):
            try:
                response = self._client.get(url)
                if response.status_code >= 500:
                    raise httpx.HTTPError(f"status {response.status_code}")
                response.raise_for_status()
                return response.content[: self._max_bytes + 1]
            except httpx.HTTPError:
                logger.warning("rss_fetch_failed", extra={"attempt": attempt, "host": _safe_host(url)})
                if attempt + 1 == self._retries:
                    return None
                self._sleep(delay)
                delay *= 2
        return None


def _text(item: ElementTree.Element, tag: str) -> str | None:
    child = item.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _parse_date(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=fallback.tzinfo)
    return parsed


def _safe_host(url: str) -> str:
    host = urlparse(url).netloc
    return host or "rss"
