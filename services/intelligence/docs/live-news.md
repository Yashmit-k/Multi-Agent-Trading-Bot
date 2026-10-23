# Live news ingestion (Intelligence)

Fixtures are for isolated tests and the labelled demo. They are **not** live news.

## Source

Default live source (no API key):

1. Google News RSS (`news.google.com/rss/search`, `hl=en-IN&gl=IN`) for Nifty/NSE plus a rotating per-symbol query.
2. Economic Times markets RSS (`.../markets/rssfeeds/1977021501.cms`) — live probe HTTP 200, 50 items parsed.
3. Moneycontrol `latestnews.xml` was tried live and returned **HTTP 403**, so it is not a default feed.

Terms: public RSS; respect robots/rate limits. Default poll interval is **300 seconds**. Local per-process limiter plus `NEWS_RSS_INTERVAL_SECONDS >= 30`.

This is **not** NSE’s corporate announcement system. Coverage of all 50 names is **not guaranteed** on every poll. A licensed newswire or NSE filing feed is the additional source if that gap is unacceptable.

## Run ingest without the paper worker

From repo root (PowerShell). Do **not** set `INTELLIGENCE_SERVICE_MODE=serve` and do **not** start `core-worker`.

```text
$env:PYTHONPATH = "packages/contracts/src;services/intelligence/src"
$env:INTELLIGENCE_TRADING_MODE = "PAPER"
$env:INTELLIGENCE_SERVICE_MODE = "oneshot"
$env:INTELLIGENCE_DATA_SOURCE = "rss"
$env:INTELLIGENCE_NEWS_INGEST = "true"
$env:INTELLIGENCE_STORE = "sqlite"
$env:INTELLIGENCE_SQLITE_PATH = "intelligence-news.db"
$env:NEWS_RSS_INTERVAL_SECONDS = "300"
$env:INTELLIGENCE_NEWS_INTERPRET = "false"
python -m uvicorn intelligence_agents.service:create_app --factory --host 127.0.0.1 --port 8080
```

If `NEWS_RSS_URLS` is empty, built-in Indian-market feeds are used. `INTELLIGENCE_SYMBOLS` defaults to the NIFTY 50 list when the data source is `rss`.

## Verify

```text
curl -s http://127.0.0.1:8080/health/news
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/news/RELIANCE
```

Expect `data_origin=live_rss`, `metadata.live=true`, `metadata.fixture=false`, distinct `published_at` and `retrieved_at`, `match_evidence`, `provider_id`. Publisher `<source url>` is stored as `url` when present; the Google redirect is `metadata.google_rss_url`. `/health/news` includes `symbols_with_articles` / `symbols_without_articles`. `GET /news/{symbol}?limit=` caps the list (default 100). Interpretation is `unavailable` unless `INTELLIGENCE_NEWS_INTERPRET=true` **and** `LLM_BASE_URL` + `LLM_API_KEY` are set. Demo LLM fixtures are never labelled as live inference.

Compose ingest without the paper worker (do **not** add `core-worker` or `intelligence`):

```text
docker compose -f docker-compose.yml -f docker-compose.intelligence.yml up --build -d intelligence-news
```

`intelligence-news` has no `depends_on` paper worker. Optional `postgres redis core-api` are not required for ingest. Core proxies `/api/v1/stocks/{symbol}/news` (user auth) but does **not** proxy `/health/news`. `url_kind=google_rss_redirect` means the stored URL is a Google RSS link, not a publisher article URL.

Core proxy (if Core is up): `GET /api/v1/stocks/{symbol}/news`. Ingest does not require the frontend.

News remains an input to Intelligence agents. It does not bypass the risk engine or place orders. The ingest loop is independent of `evaluation_loop`.

## Tests

```text
pytest services/intelligence/tests/test_rss.py services/intelligence/tests/test_news_ingest.py services/intelligence/tests/test_news_store.py services/intelligence/tests/test_sink_service.py -q
python services/intelligence/scripts/news_live_smoke.py
```

The smoke script fetches the real RSS endpoints, stores matching articles, re-polls for duplicates, reopens SQLite, and never starts the paper evaluation loop. Latest measured evidence: `docs/live-news-completion-handoff.md`.

## Configuration

| Env | Role |
|---|---|
| `INTELLIGENCE_DATA_SOURCE=rss` | Live RSS (forbidden with `BACKTEST`) |
| `NEWS_RSS_URLS` | Optional override of default feeds |
| `NEWS_RSS_INTERVAL_SECONDS` | Poll period (default 300, min 30) |
| `NEWS_RSS_SYMBOL_BATCH` | Per-poll Google News symbol queries (default 5) |
| `INTELLIGENCE_NEWS_INGEST` | Default false; set true to run the separate ingest loop (requires source `rss`) |
| `INTELLIGENCE_NEWS_INTERPRET` | Optional LLM notes; default false |
| `LLM_BASE_URL` / `LLM_API_KEY` | Required for interpretation only |
