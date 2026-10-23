# Non-H001 live-news deployment verification (2026-10-13)

H001 was not inspected. `core-worker` and PAPER-serve `intelligence` were **not started**. Existing exited containers were left stopped.

## Acceptance table (this Docker session)

| Criterion | Status |
|---|---|
| Docker `intelligence-news` only; no paper worker | `PASS — VERIFIED` |
| Interval 300s; Google News + ET HTTP 200; repeated polls | `PASS — VERIFIED` |
| Store + `/news/{symbol}` live_rss | `PASS — VERIFIED` |
| Restart volume: same `article_id`; post-restart mostly duplicates | `PASS — VERIFIED` |
| `url_kind` labels Google redirect vs publisher article | `PASS — VERIFIED` (label); original publisher URL still usually unavailable |
| Original publisher article URL for all rows | `PARTIAL — EVIDENCE INCOMPLETE` (565/565 sampled were `google_rss_redirect`; Google `<source url>` not pathful) |
| NIFTY 50 full coverage | `PARTIAL — EVIDENCE INCOMPLETE` (42/50 with articles after ~8 min + restart; 8 still 0) |
| Same-feed brand-new article in window | `PARTIAL — EVIDENCE INCOMPLETE` (poll 2 inserts were next symbol-batch feeds) |
| Docker provider 5xx/403 then recovery | `PARTIAL — EVIDENCE INCOMPLETE` (all live feeds 200; 429/malformed covered by unit tests) |
| Core news proxy | `BLOCKED — EXTERNAL DEPENDENCY` |
| Live LLM interpretation | `BLOCKED — EXTERNAL DEPENDENCY` |
| Licensed PIT fundamentals | `BLOCKED — EXTERNAL DEPENDENCY` |
| Moneycontrol / NSE filings | `BLOCKED — EXTERNAL DEPENDENCY` |
| Fixture fundamentals (rss container) | empty list — expected; fixture path is a **separate** process |
| Implementation defect requiring a code fix | none (`FAIL — FIX REQUIRED` not used) |

## Deployment commands actually run

Safe start (only `intelligence-news`; **does not** start `core-worker`):

```text
docker compose -f docker-compose.yml -f docker-compose.intelligence.yml up --build -d intelligence-news
```

Observed `docker compose ps`: `intelligence-news` **Up**; `core-worker` **Exited (1) 4 days ago** (not started); `intelligence` (PAPER serve) **Exited**.

Restart without deleting volume:

```text
docker compose -f docker-compose.yml -f docker-compose.intelligence.yml restart intelligence-news
```

API (container port 8080):

```text
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/health/news
curl -s "http://127.0.0.1:8080/news/RELIANCE?limit=2"
curl -s http://127.0.0.1:8080/news/DOESNOTEXIST
curl -s http://127.0.0.1:8080/fundamentals/TCS
```

Core owner (not run here; Core down): `GET http://localhost:8000/api/v1/stocks/RELIANCE/news` with user auth and `INTELLIGENCE_URL=http://intelligence-news:8080`.

## Docker poll evidence (measured)

Configured interval **300s**. `service_mode=oneshot`, `runner_running=false`, `paper_eval_running=false`.

| Event | UTC | inserted | duplicates | updated | feeds |
|---|---|---|---|---|---|
| Poll 1 | 2026-10-13T07:52:50Z | 476 | 8 | 0 | 7 ok / 0 fail (Google+ET 200) |
| Poll 2 | 2026-10-13T07:57:53Z (~303s later) | 344 | 85 | 0 | 7 ok |
| Restart + poll | 2026-10-13T08:00:44Z | 1 | 483 | 0 | 7 ok |

RELIANCE `article_id` `rss-772916782e7b355a57979da78c4cdc8f` **unchanged** after restart. Sample: Reuters “Jio-BlackRock…”, `published_at=2026-08-04T07:00:00Z`, `retrieved_at=2026-10-13T07:52:27Z`, `data_origin=live_rss`, `url_kind=google_rss_redirect`. Unknown symbol `[]`. Bad `as_of` HTTP 400. Rss-mode `/fundamentals/TCS` `[]`.

Poll 2 **344 inserts** are the next 5-symbol Google batch plus overlapping market feeds — **not** a later headline on the same feed. Same-feed new-article discovery remains incomplete. Window ~8 minutes.

## Publisher URL audit (Docker, sampled 565 rows)

| url_kind | count | meaning |
|---|---|---|
| `google_rss_redirect` | 565 | stored `url` is news.google.com; **not** claimed as publisher article URL |
| `publisher_article` | 0 | Google `<source url>` missing or homepage-only in this feed |

Publisher **name** often from title suffix (e.g. Reuters). `metadata.google_rss_url` retained. Homepages are not used as `url` (`url_kind` would not be `publisher_article`).

## NIFTY 50 coverage (observed in Docker store after poll 1+2+restart)

Configured: **50**. With ≥1 article: **42**. Without: **8** — `DIVISLAB`, `LTIM`, `MARUTI`, `NESTLEIND`, `POWERGRID`, `SBIN`, `TATACONSUM`, `TATAPOWER`.

Zero means **not seen in this window**, not “never has news”. Batch size 5 at 300s needs ~50 min to query all 50 Google feeds once. Feeds: `news.google.com` (all sampled rows); ET market feed ingested but rows without in-universe tickers are dropped.

## Tests this session

`pytest services/intelligence/tests/test_rss.py -q` → **10 passed**. Broader suite **42 passed** is **historical** from the earlier local session, not rerun here.

## Files changed this verification

- `news/rss.py` — `metadata.url_kind` (`publisher_article` / `google_rss_redirect` / `feed_link`).
- `tests/test_rss.py` — asserts those kinds.
- `docker-compose.intelligence.yml` — NIFTY 50 `INTELLIGENCE_SYMBOLS` on `intelligence-news`; start command is **only** `intelligence-news`.
- this handoff.

## Historical (local uvicorn, earlier today — not rerun)

Local smoke: 469 insert / 0 insert on identical second poll / sqlite 465 ids survive. HTTP :8088 interval 30s. 8-symbol subset coverage. See prior section in git history if needed.

## Blockers

| Item | Owner | Next action |
|---|---|---|
| Core proxy | Dev3 | Start `core-api` only; `INTELLIGENCE_URL` → intelligence-news:8080; authenticated `GET /api/v1/stocks/RELIANCE/news` |
| LLM | Operator | `LLM_BASE_URL` + `LLM_API_KEY` + `INTELLIGENCE_NEWS_INTERPRET=true` |
| PIT fundamentals | Data | Licensed vintage / csv-live; fixtures are a separate oneshot |
| Moneycontrol 403, NSE filings | External | Do not scrape; licensed feed |
| Remaining 8 symbols empty | Time / extra source | Let rotation complete (~50 min) or add authorized filings feed |
