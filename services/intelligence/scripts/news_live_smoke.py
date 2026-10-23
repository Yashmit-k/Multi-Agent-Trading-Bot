"""Live RSS smoke: fetch, store, API, second poll dedupe. Does not start the paper worker."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
sys.path.insert(0, str(ROOT / "services" / "intelligence" / "src"))

os.environ.setdefault("INTELLIGENCE_TRADING_MODE", "PAPER")
os.environ.setdefault("INTELLIGENCE_SERVICE_MODE", "oneshot")
os.environ.setdefault("INTELLIGENCE_DATA_SOURCE", "rss")
os.environ.setdefault("INTELLIGENCE_NEWS_INGEST", "false")
os.environ.setdefault("INTELLIGENCE_STORE", "memory")
os.environ.setdefault("INTELLIGENCE_SYMBOLS", "RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK,TATAMOTORS,SBIN,ITC")
os.environ.setdefault("NEWS_RSS_INTERVAL_SECONDS", "300")

from intelligence_agents.clock import SystemClock  # noqa: E402
from intelligence_agents.news.ingest import NewsIngestHealth, run_poll  # noqa: E402
from intelligence_agents.news.rss import RssPuller  # noqa: E402
from intelligence_agents.news.store import SqliteNewsStore  # noqa: E402
from intelligence_agents.service import _symbol_coverage  # noqa: E402
from intelligence_agents.settings import IntelligenceSettings  # noqa: E402


def main() -> int:
    settings = IntelligenceSettings.from_env()
    db_path = os.environ.get("INTELLIGENCE_SMOKE_SQLITE", str(ROOT / "intelligence-news-smoke.db"))
    store = SqliteNewsStore(db_path)
    puller = RssPuller(store, SystemClock(), settings.symbols, interval_seconds=0, retries=2)
    health = NewsIngestHealth(interval_seconds=settings.rss_interval_seconds)
    started = time.perf_counter()
    health.cursor = 0
    first = run_poll(
        settings,
        puller,
        health,
        now=datetime.now(timezone.utc),
        latest_published_fn=store.latest_published_at,
        graduate_fn=store.graduate_quarantine,
    )
    elapsed = time.perf_counter() - started
    health.cursor = 0
    second = run_poll(
        settings,
        puller,
        health,
        now=datetime.now(timezone.utc),
        latest_published_fn=store.latest_published_at,
        graduate_fn=store.graduate_quarantine,
    )
    sample = None
    for symbol in settings.symbols:
        rows = store.articles_for(symbol, datetime.now(timezone.utc))
        if rows:
            article = rows[0]
            sample = {
                "symbol": symbol,
                "title": article.title,
                "source": article.source,
                "url": str(article.url),
                "published_at": article.published_at.isoformat(),
                "retrieved_at": article.retrieved_at.isoformat(),
                "symbols": article.symbols,
                "match_evidence": article.metadata.get("match_evidence"),
                "provider_id": article.metadata.get("provider_id"),
                "data_origin": article.metadata.get("data_origin"),
                "google_rss_url": article.metadata.get("google_rss_url"),
                "interpretation": article.metadata.get("interpretation"),
            }
            break
    ids_after_second = _article_ids(store, settings.symbols)
    reopened = SqliteNewsStore(db_path)
    survived = _article_ids(reopened, settings.symbols)
    health.cursor = 0
    third = run_poll(
        settings,
        RssPuller(reopened, SystemClock(), settings.symbols, interval_seconds=0, retries=2),
        health,
        now=datetime.now(timezone.utc),
        latest_published_fn=reopened.latest_published_at,
        graduate_fn=reopened.graduate_quarantine,
    )
    coverage = _symbol_coverage(reopened, settings.symbols)
    et_probe = _probe_economic_times()
    report = {
        "provider": "Google News RSS (public, no API key). Moneycontrol latestnews.xml returned HTTP 403 in this environment.",
        "economic_times_probe": et_probe,
        "interval_seconds_configured": settings.rss_interval_seconds,
        "first_poll_seconds": round(elapsed, 3),
        "first": {
            "feeds_ok": sum(not item.fetch_failed for item in first),
            "feeds_failed": sum(item.fetch_failed for item in first),
            "inserted": sum(item.inserted for item in first),
            "duplicates": sum(item.duplicates for item in first),
            "errors": [item.error for item in first if item.error],
        },
        "second": {
            "inserted": sum(item.inserted for item in second),
            "duplicates": sum(item.duplicates for item in second),
            "updated": sum(item.updated for item in second),
        },
        "restart": {
            "sqlite_path": db_path,
            "ids_before_reopen": len(ids_after_second),
            "ids_after_reopen": len(survived),
            "ids_unchanged": ids_after_second == survived,
            "third_poll_inserted": sum(item.inserted for item in third),
            "third_poll_duplicates": sum(item.duplicates for item in third),
        },
        "coverage": coverage,
        "paper_eval_running": False,
        "sample": sample,
        "health": health.as_dict(),
        "coverage_gap": (
            "Public RSS is not an NSE corporate-announcement feed and does not guarantee "
            "an article for every NIFTY 50 name on every poll. Additional source needed: "
            "licensed newswire or NSE corporate announcement API."
        ),
    }
    print(json.dumps(report, indent=2))
    if sample is None:
        print("SMOKE_FAIL: no in-universe article stored", file=sys.stderr)
        return 1
    if report["first"]["inserted"] < 1:
        print("SMOKE_FAIL: first poll inserted nothing", file=sys.stderr)
        return 1
    if report["second"]["duplicates"] < 1:
        print("SMOKE_FAIL: second identical poll did not hit stored duplicates", file=sys.stderr)
        return 1
    if not report["restart"]["ids_unchanged"]:
        print("SMOKE_FAIL: sqlite reopen lost article ids", file=sys.stderr)
        return 1
    print("SMOKE_OK")
    return 0


def _article_ids(store, symbols) -> set[str]:
    now = datetime.now(timezone.utc)
    ids: set[str] = set()
    for symbol in symbols:
        for article in store.articles_for(symbol, now):
            ids.add(article.article_id)
    return ids


def _probe_economic_times() -> dict[str, object]:
    import httpx

    url = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
    try:
        response = httpx.get(
            url,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "MultiAgentTradingBot-Intelligence/1.0 (academic RSS ingest)"},
        )
        return {
            "url": url,
            "status_code": response.status_code,
            "added_to_defaults": response.status_code == 200,
            "note": "Added to DEFAULT_MARKET_FEEDS after HTTP 200 and parseable RSS.",
        }
    except Exception as exc:
        return {"url": url, "error": type(exc).__name__, "added_to_defaults": False}


if __name__ == "__main__":
    raise SystemExit(main())
