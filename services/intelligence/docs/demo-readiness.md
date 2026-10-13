# Intelligence demo readiness (Developer 1)

**Live vs demo:** default Compose overlay and `.env.example` use `INTELLIGENCE_DATA_SOURCE=fixtures` and empty `LLM_API_KEY`. That is a **labelled demo**, not live NSE news, not a licensed fundamentals vintage, and not live LLM inference unless you configure otherwise.

Do **not** start `INTELLIGENCE_SERVICE_MODE=serve` or the paper evaluation loop for this demo. News and fundamentals are served in `oneshot` + `BACKTEST` without posting signals.

## What works

| Capability | Default | How you can tell |
|---|---|---|
| `GET /health` | ok/degraded JSON | `data_origin`, `data_source`, `llm_mode` |
| `GET /news/{symbol}` | Contract `NewsArticle` list | `metadata.fixture=true`, `metadata.data_origin=demo_fixture`, `metadata.live=false` |
| `GET /fundamentals/{symbol}` | Contract `FundamentalDataPoint` list | same fixture tags; `not_historical_nse_vintage=true` |
| LLM agents | `llm_mode=fixture` | no API key |
| RSS live news | off unless `INTELLIGENCE_DATA_SOURCE=rss` | see `docs/live-news.md`; `GET /health/news` |
| Historical PIT NSE fundamentals | **unavailable** | licensed vintage (e.g. ProwessDx) not configured |

Supported **fixture** symbols: `RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`. Other NIFTY names return `[]` (not invented headlines).

Core already proxies:

- `GET /api/v1/stocks/{symbol}/news`
- `GET /api/v1/stocks/{symbol}/fundamentals`
- `GET /api/v1/agents/{news\|fundamental\|valuation\|earnings}/health`

`INTELLIGENCE_URL` (default `http://intelligence:8080`). Core ownership: do not change Core for this demo; if Core is down, call Intelligence directly.

## Launch (local, no paper worker)

From repo root, with `contracts` and `intelligence-agents` installed editable:

```text
set INTELLIGENCE_TRADING_MODE=BACKTEST
set INTELLIGENCE_SERVICE_MODE=oneshot
set INTELLIGENCE_DATA_SOURCE=fixtures
set INTELLIGENCE_STORE=memory
python -m uvicorn intelligence_agents.service:create_app --factory --host 127.0.0.1 --port 8080
```

Verify:

```text
curl -s http://127.0.0.1:8080/health
curl -s "http://127.0.0.1:8080/news/RELIANCE?as_of=2024-06-03T10:00:00+00:00"
curl -s "http://127.0.0.1:8080/fundamentals/TCS?as_of=2024-06-03T10:00:00+00:00"
curl -s "http://127.0.0.1:8080/news/TATAMOTORS?as_of=2024-06-03T10:00:00+00:00"
```

Tests:

```text
pytest services/intelligence/tests/test_demo_routes.py services/intelligence/tests/test_news_store.py services/intelligence/tests/test_fundamentals.py services/intelligence/tests/test_rss.py -q
```

## Live providers (no secrets in git)

| Env | Purpose |
|---|---|
| `INTELLIGENCE_DATA_SOURCE=rss` | Live RSS ingest (PAPER/oneshot, not BACKTEST) |
| `NEWS_RSS_URLS` | Optional; defaults to Google News India RSS (Moneycontrol 403, not default) |
| `LLM_BASE_URL` + `LLM_API_KEY` | OpenAI-compatible or Ollama (`http://host.docker.internal:11434/v1`, key `ollama`) |
| `LLM_TIER1_MODEL` | e.g. `phi3:mini` |
| CSV fundamentals | `INTELLIGENCE_DATA_SOURCE=csv-live` — **not** NSE PIT unless the CSV itself is a vintage |

Never put tokens in the repo. Overlay `docker-compose.intelligence.yml` still uses `INTERNAL_SIGNAL_TOKEN=change-me` for PAPER serve; that path posts signals — **out of scope** for this demo.

## Five-minute demo script

1. Start uvicorn as above.
2. Show `/health`: `data_origin=demo_fixture`, `llm_mode=fixture`.
3. Show RELIANCE news: fixture headline, URL on `example.test`, timezone-aware timestamps.
4. Show TCS fundamentals at `2024-06-03T10:00:00+00:00`: FY2024 EPS visible, Q1FY2025 hidden (PIT).
5. Show TATAMOTORS news: empty list, not fake live copy.
6. Optional: if Core is up with `INTELLIGENCE_URL`, hit `/api/v1/stocks/RELIANCE/news` (needs user auth owned by Core).

## Ownership blockers

- Frontend contract: uses Core stock news/fundamentals. Dev1 does not redesign UI.
- Live RSS: Google News ingest is documented in `docs/live-news.md`. Overlay service `intelligence-news` runs ingest without `core-worker`.
- Live RSS/LLM: LLM interpretation still needs `LLM_*` credentials.
- H001 training: separate; still `READY_TO_RUN = NO`.
