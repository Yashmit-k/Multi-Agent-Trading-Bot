"""Background RSS poller. Independent of the paper evaluation loop."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from intelligence_agents.news.rss import IngestStats, RssPuller
from intelligence_agents.news.universe import google_news_symbol_feed
from intelligence_agents.settings import IntelligenceSettings

logger = logging.getLogger(__name__)


@dataclass
class NewsIngestHealth:
    ingest_running: bool = False
    last_successful_poll: str | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    polls: int = 0
    inserted_last_poll: int = 0
    duplicates_last_poll: int = 0
    updated_last_poll: int = 0
    dropped_last_poll: int = 0
    latest_published_at: str | None = None
    feeds_ok: int = 0
    feeds_failed: int = 0
    stale: bool = False
    interval_seconds: int = 300
    interpretation: str = "unavailable"
    cursor: int = 0
    last_poll_feeds: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "ingest_running": self.ingest_running,
            "last_successful_poll": self.last_successful_poll,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "polls": self.polls,
            "inserted_last_poll": self.inserted_last_poll,
            "duplicates_last_poll": self.duplicates_last_poll,
            "updated_last_poll": self.updated_last_poll,
            "dropped_last_poll": self.dropped_last_poll,
            "latest_published_at": self.latest_published_at,
            "feeds_ok": self.feeds_ok,
            "feeds_failed": self.feeds_failed,
            "stale": self.stale,
            "interval_seconds": self.interval_seconds,
            "interpretation": self.interpretation,
            "last_poll_feeds": list(self.last_poll_feeds),
        }


def feeds_for_poll(settings: IntelligenceSettings, cursor: int) -> tuple[list[str], int]:
    feeds = list(settings.news_rss_urls)
    batch = max(1, settings.rss_symbol_batch)
    symbols = list(settings.symbols)
    if not symbols:
        return feeds, cursor
    start = cursor % len(symbols)
    chosen = []
    for offset in range(min(batch, len(symbols))):
        chosen.append(symbols[(start + offset) % len(symbols)])
    feeds.extend(google_news_symbol_feed(symbol) for symbol in chosen)
    return feeds, (start + len(chosen)) % len(symbols)


def apply_poll_stats(
    health: NewsIngestHealth,
    stats: list[IngestStats],
    *,
    now: datetime,
    latest_published: datetime | None,
) -> None:
    health.polls += 1
    health.inserted_last_poll = sum(item.inserted for item in stats)
    health.duplicates_last_poll = sum(item.duplicates for item in stats)
    health.updated_last_poll = sum(item.updated for item in stats)
    health.dropped_last_poll = sum(item.dropped for item in stats)
    health.feeds_ok = sum(1 for item in stats if not item.fetch_failed)
    health.feeds_failed = sum(1 for item in stats if item.fetch_failed)
    errors = [item.error for item in stats if item.error]
    if health.feeds_ok:
        health.last_successful_poll = now.astimezone(timezone.utc).isoformat()
        health.consecutive_failures = 0
        if not health.feeds_failed:
            health.last_error = None
        else:
            health.last_error = errors[0] if errors else "partial_feed_failure"
    else:
        health.consecutive_failures += 1
        health.last_error = errors[0] if errors else "all_feeds_failed"
    if latest_published is not None:
        health.latest_published_at = latest_published.astimezone(timezone.utc).isoformat()
    health.stale = _stale(health, now)


def _stale(health: NewsIngestHealth, now: datetime) -> bool:
    if health.last_successful_poll is None:
        return health.polls > 0
    last = datetime.fromisoformat(health.last_successful_poll)
    return (now - last).total_seconds() > max(60, health.interval_seconds * 2)


def run_poll(
    settings: IntelligenceSettings,
    puller: RssPuller,
    health: NewsIngestHealth,
    *,
    now: datetime,
    latest_published_fn: Callable[[], datetime | None],
    graduate_fn: Callable[[datetime], int] | None = None,
) -> list[IngestStats]:
    feeds, nxt = feeds_for_poll(settings, health.cursor)
    health.cursor = nxt
    health.last_poll_feeds = [_host(url) for url in feeds]
    stats = [puller.pull_stats(url) for url in feeds]
    if graduate_fn is not None:
        graduate_fn(now)
    apply_poll_stats(health, stats, now=now, latest_published=latest_published_fn())
    logger.info(
        "news_ingest_poll",
        extra={
            "inserted": health.inserted_last_poll,
            "duplicates": health.duplicates_last_poll,
            "updated": health.updated_last_poll,
            "feeds_ok": health.feeds_ok,
            "feeds_failed": health.feeds_failed,
        },
    )
    return stats


async def news_ingest_loop(
    settings: IntelligenceSettings,
    stop: asyncio.Event,
    health: NewsIngestHealth,
    puller: RssPuller,
    latest_published_fn: Callable[[], datetime | None],
    graduate_fn: Callable[[datetime], int] | None = None,
) -> None:
    health.ingest_running = True
    health.interval_seconds = settings.rss_interval_seconds
    health.interpretation = "available" if settings.news_interpret and settings.llm_mode() == "openai" else "unavailable"
    try:
        while not stop.is_set():
            try:
                await asyncio.to_thread(
                    run_poll,
                    settings,
                    puller,
                    health,
                    now=datetime.now(timezone.utc),
                    latest_published_fn=latest_published_fn,
                    graduate_fn=graduate_fn,
                )
            except Exception as exc:
                health.consecutive_failures += 1
                health.last_error = str(exc)[:500]
                health.stale = True
                logger.exception("news_ingest_poll_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.rss_interval_seconds)
            except TimeoutError:
                continue
    finally:
        health.ingest_running = False


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc or url[:80]
