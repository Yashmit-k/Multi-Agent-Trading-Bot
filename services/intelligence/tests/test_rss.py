from datetime import datetime, timezone

import httpx

from intelligence_agents.clock import ReplayClock
from intelligence_agents.news.rss import RssPuller
from intelligence_agents.news.store import MemoryNewsStore

FEED = b"""<?xml version="1.0"?>
<rss><channel>
<item>
  <title>RELIANCE posts steady update</title>
  <link>https://example.test/a1</link>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>RELIANCE operating update</description>
</item>
<item>
  <title>Unmapped co does a thing</title>
  <link>https://example.test/a2</link>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>no ticker from universe</description>
</item>
</channel></rss>
"""


def test_rss_maps_and_drops():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0)
    inserted = puller.ingest_bytes(FEED, feed_url="https://example.test/rss", retrieved_at=clock.now())
    assert inserted == 1
    assert store.dropped_empty_symbols == 1


def test_rss_retry_on_500():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, content=FEED)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    slept: list[float] = []
    puller = RssPuller(
        store,
        clock,
        ("RELIANCE",),
        interval_seconds=0,
        retries=3,
        client=client,
        sleeper=slept.append,
    )
    assert puller.pull("https://example.test/rss") == 1
    assert slept


def test_rss_malformed():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0)
    assert puller.ingest_bytes(b"<not-xml", feed_url="https://example.test/rss", retrieved_at=clock.now()) == 0
