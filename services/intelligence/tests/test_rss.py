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
  <guid>https://example.test/a1</guid>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>RELIANCE operating update</description>
</item>
<item>
  <title>Unmapped co does a thing</title>
  <link>https://example.test/a2</link>
  <guid>https://example.test/a2</guid>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>no ticker from universe</description>
</item>
</channel></rss>
"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Infosys wins a deal - Moneycontrol</title>
    <link href="https://example.test/atom-1"/>
    <id>https://example.test/atom-1</id>
    <published>2024-06-03T04:00:00Z</published>
    <summary>Infosys signed a contract.</summary>
  </entry>
</feed>
"""

UPDATED = b"""<?xml version="1.0"?>
<rss><channel>
<item>
  <title>RELIANCE posts corrected update</title>
  <link>https://example.test/a1</link>
  <guid>https://example.test/a1</guid>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>RELIANCE correction note</description>
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
    article = store.articles_for("RELIANCE", clock.now())[0]
    assert article.metadata["match_evidence"]["RELIANCE"] == "ticker:RELIANCE"
    assert article.published_at.year == 2024
    assert article.retrieved_at >= article.published_at
    assert str(article.url).startswith("https://example.test/a1")


GOOGLE = b"""<?xml version="1.0"?>
<rss><channel>
<item>
  <title>RELIANCE unit update - Reuters</title>
  <link>https://news.google.com/rss/articles/ABC</link>
  <guid>CBMiEXAMPLE</guid>
  <source url="https://www.reuters.com/markets/reliance-unit">Reuters</source>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>RELIANCE unit filed an update</description>
</item>
</channel></rss>
"""


def test_ignores_homepage_source_url():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    body = b"""<?xml version="1.0"?><rss><channel><item>
      <title>RELIANCE note - Wire</title>
      <link>https://news.google.com/rss/articles/XYZ</link>
      <source url="https://www.indiainfoline.com/">India Infoline</source>
      <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
      <description>RELIANCE note</description>
    </item></channel></rss>"""
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0)
    puller.ingest_bytes(body, feed_url="https://news.google.com/rss", retrieved_at=clock.now())
    article = store.articles_for("RELIANCE", clock.now())[0]
    assert "news.google.com" in str(article.url)
    assert article.metadata["url_kind"] == "google_rss_redirect"
    assert article.source == "India Infoline"


def test_prefers_publisher_source_url():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0)
    puller.ingest_bytes(GOOGLE, feed_url="https://news.google.com/rss", retrieved_at=clock.now())
    article = store.articles_for("RELIANCE", clock.now())[0]
    assert str(article.url).startswith("https://www.reuters.com/")
    assert article.source == "Reuters"
    assert article.metadata["url_kind"] == "publisher_article"
    assert "news.google.com" in str(article.metadata["google_rss_url"])


def test_atom_next_fetched_once():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    page2 = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Infosys second page</title>
        <link href="https://example.test/atom-2"/>
        <id>https://example.test/atom-2</id>
        <published>2024-06-03T05:00:00Z</published>
        <summary>Infosys follow-up</summary>
      </entry>
    </feed>
    """
    page1 = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <link rel="next" href="https://example.test/atom-page-2"/>
      <entry>
        <title>Infosys first page</title>
        <link href="https://example.test/atom-1"/>
        <id>https://example.test/atom-1</id>
        <published>2024-06-03T04:00:00Z</published>
        <summary>Infosys signed a contract.</summary>
      </entry>
    </feed>
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url).endswith("atom-page-2"):
            return httpx.Response(200, content=page2)
        return httpx.Response(200, content=page1)

    puller = RssPuller(
        store,
        clock,
        ("INFY",),
        interval_seconds=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    stats = puller.pull_stats("https://example.test/atom")
    assert stats.inserted == 2
    assert len(seen) == 2


def test_atom_and_alias_mapping():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("INFY",), interval_seconds=0)
    stats = puller.ingest_stats(ATOM, feed_url="https://news.google.com/rss", retrieved_at=clock.now())
    assert stats.inserted == 1
    article = store.articles_for("INFY", clock.now())[0]
    assert article.metadata["content_type"] == "atom"
    assert article.metadata["match_evidence"]["INFY"].startswith("alias:")
    assert article.source == "Moneycontrol"


def test_duplicate_then_content_update():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0)
    first = puller.ingest_stats(FEED, feed_url="https://example.test/rss", retrieved_at=clock.now())
    again = puller.ingest_stats(FEED, feed_url="https://example.test/rss", retrieved_at=clock.now())
    changed = puller.ingest_stats(UPDATED, feed_url="https://example.test/rss", retrieved_at=clock.now())
    assert first.inserted == 1
    assert again.duplicates == 1
    assert again.inserted == 0
    assert changed.updated == 1
    article = store.articles_for("RELIANCE", clock.now())[0]
    assert "corrected" in article.title
    assert article.metadata["content_updated"] is True
    assert len(store.articles_for("RELIANCE", clock.now())) == 1


def test_skips_missing_pubdate():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0)
    body = b"""<?xml version="1.0"?><rss><channel>
    <item><title>RELIANCE</title><link>https://example.test/x</link><description>RELIANCE</description></item>
    </channel></rss>"""
    stats = puller.ingest_stats(body, feed_url="https://example.test/rss", retrieved_at=clock.now())
    assert stats.inserted == 0
    assert stats.skipped_no_date == 1


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


def test_provider_failure_does_not_insert():
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    puller = RssPuller(
        store,
        clock,
        ("RELIANCE",),
        interval_seconds=0,
        retries=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
    )
    stats = puller.pull_stats("https://example.test/rss")
    assert stats.fetch_failed is True
    assert stats.inserted == 0
    assert "rate_limited" in (stats.error or "")
    assert store.articles_for("RELIANCE", clock.now()) == []
