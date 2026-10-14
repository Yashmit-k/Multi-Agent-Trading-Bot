# Dev 1 handoff — live news and official H001

Use branch **`dev1/intelligence`**. Do not use `main` for this work. Do not use `experiment/h001-threshold-34` (that branch is a separate bar-34 sensitivity; it is not official).

## Checkout

```text
git fetch origin
git checkout dev1/intelligence
git pull
```

## Live news

From the repo root. Do **not** start `core-worker` or the paper `intelligence` service.

```text
docker compose -f docker-compose.yml -f docker-compose.intelligence.yml up --build -d intelligence-news
```

Then:

```text
curl.exe -s http://127.0.0.1:8080/health
curl.exe -s http://127.0.0.1:8080/health/news
curl.exe -s "http://127.0.0.1:8080/news/RELIANCE?limit=2"
```

Expect `data_origin=live_rss`. LLM interpretation is off unless you set keys; that is optional.

News unit tests (from `services/intelligence`):

```text
python -m pytest tests/test_rss.py tests/test_news_ingest.py tests/test_news_store.py tests/test_sink_service.py -q
```

Details: `services/intelligence/docs/live-news.md`.

## Official H001 (bar 50)

Official minority bar is **50**. Eligibility audit result is **`AUDIT_COMPLETE_INCONCLUSIVE`** (train minority 34). That is the finished official result. Execution is not authorized. No official fit.

Unit tests do **not** need candles. From `services/quant`, with `PYTHONPATH` pointing at **this** checkout’s `services/quant/src`:

```text
python -m pytest tests/unit/test_h001_authorization.py tests/unit/test_h001_calendar.py tests/unit/test_h001_eligibility.py tests/unit/test_h001_events.py tests/unit/test_h001_features.py tests/unit/test_h001_integrity.py tests/unit/test_h001_labels.py tests/unit/test_h001_model.py tests/unit/test_h001_net.py tests/unit/test_h001_scores.py tests/unit/test_h001_split.py -q
```

Frozen-tape audit needs gitignored files. Copy them once using `services/quant/docs/h001-candle-restore-instructions.md`. Do not regenerate candles. Do not open `snapshots/holdout_after_20261005`.

Machine-readable official result: `services/quant/docs/h001-eligibility-audit-result.json`.
