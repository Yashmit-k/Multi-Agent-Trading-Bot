"""RSS/Atom ingest with size caps, retries, alias mapping, and provenance."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlparse

import httpx
from contracts.fixtures import content_hash
from contracts.schemas.news_article import NewsArticle
from defusedxml import ElementTree

from intelligence_agents.clock import Clock
from intelligence_agents.news.store import NewsStore
from intelligence_agents.news.universe import match_symbols

logger = logging.getLogger(__name__)

_HTML = re.compile(r"<[^>]+>")
_DEFAULT_UA = "MultiAgentTradingBot-Intelligence/1.0 (academic RSS ingest)"


@dataclass
class IngestStats:
    inserted: int = 0
    duplicates: int = 0
    updated: int = 0
    dropped: int = 0
    fetch_failed: bool = False
    error: str | None = None
    latest_published_at: datetime | None = None
    skipped_no_date: int = 0
    skipped_no_url: int = 0
    next_feed_url: str | None = None


class RssPuller:
    def __init__(
        self,
        store: NewsStore,
        clock: Clock,
        universe: tuple[str, ...],
        *,
        max_bytes: int = 1024 * 1024,
        max_items: int = 100,
        interval_seconds: int = 0,
        retries: int = 3,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        interpreter: Callable[..., dict] | None = None,
        user_agent: str = _DEFAULT_UA,
    ) -> None:
        self._store = store
        self._clock = clock
        self._universe = {item.upper() for item in universe}
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._interval_seconds = interval_seconds
        self._retries = retries
        self._client = client or httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
        )
        self._sleep = sleeper
        self._interpreter = interpreter
        self._last_fetch: dict[str, datetime] = {}
        self.last_stats: IngestStats = IngestStats()

    def pull(self, url: str) -> int:
        return self.pull_stats(url).inserted

    def pull_stats(self, url: str) -> IngestStats:
        last = self._last_fetch.get(url)
        now = self._clock.now()
        if last is not None and self._interval_seconds > 0 and (now - last).total_seconds() < self._interval_seconds:
            logger.info("rss_rate_limited", extra={"url": _safe_host(url)})
            stats = IngestStats(error="rate_limited_local_interval")
            self.last_stats = stats
            return stats
        body, error = self._fetch(url)
        self._last_fetch[url] = now
        if body is None:
            stats = IngestStats(fetch_failed=True, error=error or "fetch_failed")
            self.last_stats = stats
            return stats
        stats = self.ingest_stats(body, feed_url=url, retrieved_at=now)
        nxt = stats.next_feed_url
        if nxt and nxt != url:
            extra_body, extra_error = self._fetch(nxt)
            if extra_body is not None:
                extra = self.ingest_stats(extra_body, feed_url=nxt, retrieved_at=now)
                extra.next_feed_url = None
                stats = _merge_stats(stats, extra)
            elif extra_error:
                stats.error = stats.error or extra_error
        self.last_stats = stats
        return stats

    def ingest_bytes(self, body: bytes, *, feed_url: str, retrieved_at: datetime) -> int:
        return self.ingest_stats(body, feed_url=feed_url, retrieved_at=retrieved_at).inserted

    def ingest_stats(self, body: bytes, *, feed_url: str, retrieved_at: datetime) -> IngestStats:
        stats = IngestStats()
        if len(body) > self._max_bytes:
            logger.warning("rss_body_too_large", extra={"bytes": len(body), "host": _safe_host(feed_url)})
            body = body[: self._max_bytes]
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            logger.warning("rss_malformed", extra={"host": _safe_host(feed_url)})
            stats.fetch_failed = True
            stats.error = "malformed_xml"
            return stats
        stats.next_feed_url = _atom_next(root)
        items = _items(root)[: self._max_items]
        for index, item in enumerate(items):
            title = _strip(_child_text(item, ("title",)) or "untitled")
            link = _link(item)
            guid = _child_text(item, ("guid", "id"))
            description = _strip(_child_text(item, ("description", "summary", "content")) or title)
            pub_raw = _child_text(item, ("pubDate", "published", "updated"))
            pub = _parse_date(pub_raw, None)
            publisher = _publisher(item, title, feed_url)
            content_type = "atom" if _tag(item) == "entry" else "rss_item"
            if pub is None:
                stats.skipped_no_date += 1
                stats.dropped += 1
                continue
            source_url = _http_url(_source_url(item))
            google_link = link if link and "news.google.com" in urlparse(link).netloc else None
            canonical, url_kind = _canonical_url(source_url, link, guid)
            if canonical is None:
                stats.skipped_no_url += 1
                stats.dropped += 1
                continue
            symbols, evidence = match_symbols(f"{title} {description} {canonical}", self._universe)
            if not symbols:
                self._store.record_empty_symbol_drop(title)
                stats.dropped += 1
                continue
            raw = description.strip() or title
            article_id = "rss-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
            retrieved = retrieved_at if retrieved_at >= pub else pub
            interpretation = interpretation_placeholder()
            if self._interpreter is not None:
                interpretation = self._interpreter(title=title, raw_text=raw, url=canonical)
            metadata: dict[str, object] = {
                "feed": _safe_host(feed_url),
                "feed_url": feed_url,
                "data_origin": "live_rss",
                "fixture": False,
                "live": True,
                "publisher": publisher,
                "provider_id": guid or canonical,
                "canonical_url": canonical,
                "google_rss_url": google_link,
                "url_kind": url_kind,
                "content_type": content_type,
                "published_at_source": pub_raw,
                "published_tz": str(pub.tzinfo) if pub.tzinfo else None,
                "match_evidence": evidence,
                "interpretation": interpretation,
                "item_index": index,
            }
            try:
                article = NewsArticle(
                    article_id=article_id,
                    source=publisher[:120] or _safe_host(feed_url),
                    title=title[:500],
                    url=canonical,
                    published_at=pub,
                    retrieved_at=retrieved,
                    content_hash=content_hash(f"{title}\n{raw}"),
                    symbols=symbols,
                    raw_text=raw[:8000],
                    metadata=metadata,
                )
            except Exception:
                logger.warning("rss_item_invalid", extra={"host": _safe_host(feed_url)})
                stats.dropped += 1
                continue
            result = self._store.insert(article, now=retrieved_at)
            if result.inserted:
                stats.inserted += 1
            elif getattr(result, "updated", False):
                stats.updated += 1
            elif result.duplicate:
                stats.duplicates += 1
            else:
                stats.dropped += 1
            if stats.latest_published_at is None or pub > stats.latest_published_at:
                stats.latest_published_at = pub
        return stats

    def _map_symbols(self, text: str) -> list[str]:
        symbols, _ = match_symbols(text, self._universe)
        return symbols

    def _fetch(self, url: str) -> tuple[bytes | None, str | None]:
        delay = 0.2
        last_error = "fetch_failed"
        for attempt in range(self._retries):
            try:
                response = self._client.get(url)
                if response.status_code == 429:
                    last_error = f"rate_limited:{_safe_host(url)}"
                    raise httpx.HTTPError(last_error)
                if response.status_code >= 500:
                    last_error = f"http_{response.status_code}:{_safe_host(url)}"
                    raise httpx.HTTPError(last_error)
                if response.status_code >= 400:
                    return None, f"http_{response.status_code}:{_safe_host(url)}"
                return response.content[: self._max_bytes + 1], None
            except httpx.TimeoutException:
                last_error = f"timeout:{_safe_host(url)}"
                logger.warning("rss_fetch_timeout", extra={"attempt": attempt, "host": _safe_host(url)})
            except httpx.HTTPError as exc:
                last_error = str(exc)[:200]
                logger.warning("rss_fetch_failed", extra={"attempt": attempt, "host": _safe_host(url)})
            if attempt + 1 == self._retries:
                return None, last_error
            self._sleep(delay)
            delay *= 2
        return None, last_error


def interpretation_placeholder() -> dict[str, object]:
    return {
        "available": False,
        "reason": "interpretation_disabled",
        "model_generated": False,
        "source_reported": True,
    }


def _items(root: ElementTree.Element) -> list[ElementTree.Element]:
    found = [el for el in root.iter() if _tag(el) in {"item", "entry"}]
    return found


def _tag(el: ElementTree.Element) -> str:
    return el.tag.split("}")[-1]


def _child_text(item: ElementTree.Element, names: tuple[str, ...]) -> str | None:
    for child in list(item):
        if _tag(child) in names:
            text = (child.text or "").strip()
            if text:
                return text
            if _tag(child) == "content":
                inner = "".join(child.itertext()).strip()
                if inner:
                    return inner
    return None


def _source_url(item: ElementTree.Element) -> str | None:
    for child in list(item):
        if _tag(child) == "source":
            href = (child.get("url") or child.get("href") or "").strip()
            if href.startswith("http"):
                return href
    return None


def _publisher(item: ElementTree.Element, title: str, feed_url: str) -> str:
    text = _child_text(item, ("source",))
    if text:
        return text[:120]
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()[:120]
    return _safe_host(feed_url)


def _atom_next(root: ElementTree.Element) -> str | None:
    for el in root.iter():
        if _tag(el) == "link" and (el.get("rel") or "").lower() == "next":
            href = (el.get("href") or "").strip()
            if href.startswith("http"):
                return href
    return None


def _merge_stats(left: IngestStats, right: IngestStats) -> IngestStats:
    latest = left.latest_published_at
    if right.latest_published_at is not None and (latest is None or right.latest_published_at > latest):
        latest = right.latest_published_at
    error = left.error or right.error
    return IngestStats(
        inserted=left.inserted + right.inserted,
        duplicates=left.duplicates + right.duplicates,
        updated=left.updated + right.updated,
        dropped=left.dropped + right.dropped,
        fetch_failed=left.fetch_failed or right.fetch_failed,
        error=error,
        latest_published_at=latest,
        skipped_no_date=left.skipped_no_date + right.skipped_no_date,
        skipped_no_url=left.skipped_no_url + right.skipped_no_url,
        next_feed_url=None,
    )


def _link(item: ElementTree.Element) -> str | None:
    text = _child_text(item, ("link",))
    if text and text.startswith("http"):
        return text
    for child in list(item):
        if _tag(child) == "link":
            href = (child.get("href") or "").strip()
            if href:
                return href
    return None


def _canonical_url(source_url: str | None, link: str | None, guid: str | None) -> tuple[str | None, str]:
    if source_url and _article_path(source_url):
        return source_url, "publisher_article"
    if link and "news.google.com" in urlparse(link).netloc:
        return _http_url(link), "google_rss_redirect"
    if _http_url(link):
        return _http_url(link), "feed_link"
    if _http_url(guid):
        return _http_url(guid), "provider_id"
    return None, "missing"


def _article_path(url: str | None) -> bool:
    if not url:
        return False
    path = (urlparse(url).path or "").strip("/")
    return bool(path)


def _http_url(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    return None


def _strip(value: str) -> str:
    return _HTML.sub(" ", value).replace("&nbsp;", " ").strip()


def _parse_date(value: str | None, fallback: datetime | None) -> datetime | None:
    if not value:
        return fallback
    raw = value.strip()
    try:
        parsed = parsedate_to_datetime(raw)
        return _ensure_tz(parsed)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        iso = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso)
        return _ensure_tz(parsed)
    except ValueError:
        return fallback


def _ensure_tz(parsed: datetime) -> datetime:
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _safe_host(url: str) -> str:
    host = urlparse(url).netloc
    return host or "rss"
