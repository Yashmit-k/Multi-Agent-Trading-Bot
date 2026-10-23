# Live news handoff (2026-10-13)

Paper-trading worker was **not** started. No trading cycle was executed. Live-trading restrictions unchanged.

## What was implemented

Intelligence owns a background RSS ingest loop (`news_ingest_loop`) started from FastAPI lifespan when `INTELLIGENCE_DATA_SOURCE=rss` and `INTELLIGENCE_NEWS_INGEST=true` (opt-in; default false). It does **not** start `evaluation_loop`. `INTELLIGENCE_SERVICE_MODE=oneshot` + `PAPER` is enough; no Core sink token is required for ingest-only.

Default source: **Google News RSS** (`hl=en-IN&gl=IN`) for a Nifty/NSE query plus a rotating per-symbol query over the NIFTY 50 list. No API key.

Articles are stored in SQLite/memory with `published_at` vs `retrieved_at`, publisher, URL, provider id, match evidence, and `data_origin=live_rss`. Same canonical URL is deduplicated; title/body changes mark `metadata.content_updated` instead of a new event.

`GET /news/{symbol}` returns stored rows. `GET /health/news` reports ingest running, last successful poll, latest publication time, last error, stale flag. LLM interpretation is off unless `INTELLIGENCE_NEWS_INTERPRET=true` and real LLM credentials exist; fixture LLM is never labelled as live inference.

## Setup

```text
$env:PYTHONPATH = "packages/contracts/src;services/intelligence/src"
$env:INTELLIGENCE_TRADING_MODE = "PAPER"
$env:INTELLIGENCE_SERVICE_MODE = "oneshot"
$env:INTELLIGENCE_DATA_SOURCE = "rss"
$env:INTELLIGENCE_NEWS_INGEST = "true"
$env:INTELLIGENCE_STORE = "sqlite"
$env:INTELLIGENCE_SQLITE_PATH = "intelligence-news.db"
$env:NEWS_RSS_INTERVAL_SECONDS = "300"
python -m uvicorn intelligence_agents.service:create_app --factory --host 127.0.0.1 --port 8080
```

FastAPI in this workspace needed `fastapi>=0.115` against Starlette 1.7 (0.110.0 constructor failed). Intelligence `pyproject.toml` already allows that range.

## Tests

```text
pytest services/intelligence/tests/test_rss.py services/intelligence/tests/test_news_ingest.py services/intelligence/tests/test_news_store.py services/intelligence/tests/test_sink_service.py -q
python services/intelligence/scripts/news_live_smoke.py
```

Offline: 36 related tests passed (rss parse/atom/aliases/dedupe/update/429, ingest settings, store update).

## Live evidence (this machine, 2026-10-13)

Script smoke (no HTTP server, same feeds twice):

- Provider: Google News RSS (200 OK). Moneycontrol `latestnews.xml` previously **HTTP 403**; removed from defaults.
- Configured interval: **300s**. First poll wall time: **0.773s** (not the poll period).
- First poll: 6 feeds ok, **468 inserted**, 12 in-poll duplicates.
- Second identical poll: **0 inserted, 480 duplicates**.
- Sample: Reuters “Jio-BlackRock enters India's ETF market…” mapped to RELIANCE via `alias:Jio-BlackRock`.
- `published_at`: 2026-08-04T07:00:00+00:00. `retrieved_at`: 2026-10-13T06:57:50Z. Distinct clocks.
- `paper_eval_running`: false.

HTTP ingest process (`oneshot` + rss, port 8087, interval **30s** for the demo, not paper serve):

- Log: `news_ingest_starting` then Google News 200s. `runner_running` false.
- Poll 1: inserted 290, duplicates 3, feeds_ok 4.
- `GET /health/news`: status ok, ingest_running true, paper_eval_running false, polls 1 then 2, stale false, interpretation unavailable.
- `GET /news/RELIANCE`: 97 stored live_rss rows with source, URL, timestamps, match_evidence.
- `GET /news/TCS`: 121 rows.
- `GET /health`: data_origin live_rss, runner false.
- Poll 2 (new symbol batch HDFCBANK/ICICIBANK/TATAMOTORS): inserted 263, duplicates 13. New companies on the round-robin, not a replay of poll 1 URLs.

## Coverage and rate limits

- Google News does **not** cover every NIFTY 50 name on every poll. Batch size default 5 symbols/poll (~10 min to rotate 50 at 300s).
- Not an NSE corporate-announcement feed. Additional source needed: NSE announcement API or a licensed newswire (Reuters/Bloomberg) with a contract.
- Empty `LLM_*`: interpretation marked unavailable. Do not present demo summaries as model output.
- Do not commit `intelligence-news*.db`.

## Follow-up (gap pass)

- Publisher `<source url>` is preferred over the Google redirect (`metadata.google_rss_url` retained).
- Each poll graduates quarantined rows; Atom `rel=next` is fetched once.
- `/health/news` reports per-symbol coverage; `/news/{symbol}?limit=` caps at 100.
- Fixture fundamentals metadata includes `not_historical_nse_vintage` from `_origin_metadata`.
- Overlay service `intelligence-news`: oneshot + rss, no eval loop. Existing `intelligence` PAPER-serve left in place.
- FastAPI pin: `>=0.142.2,<0.143` (aligns with contracts).
- Machine-readable H001 snapshot: `docs/h001-v2-coverage.json` (`READY_TO_RUN` false). Digest `b0f4760f…` remains UNVERIFIED.

## Remaining blockers

- Moneycontrol RSS 403 without site cookies.
- No official Indian exchange filing RSS in this pipeline.
- Index reconstitution: ticker list is a static 50-name snapshot, not a live NIFTY membership feed.
- H001 training still not authorized.
