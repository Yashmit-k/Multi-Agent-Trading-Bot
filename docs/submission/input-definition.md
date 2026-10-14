# Input definition

The system takes four kinds of input. Every schema is defined once in `packages/contracts` and exported as JSON Schema in [`docs/contracts/schemas/`](../contracts/schemas/). The full HTTP contract is [`docs/contracts/openapi.json`](../contracts/openapi.json). All samples below are **real rows** copied from the running system's Postgres database on 2026-10-14. They were not hand-written.

## 1. Market data — Zerodha Kite candles

Source: the Kite Connect historical-data API, polled every 60 s by the Core collector for the 50 NIFTY 50 constituents. Stored as the `Candle` schema ([`Candle.json`](../contracts/schemas/Candle.json)).

| Field | Type | Notes |
|---|---|---|
| `symbol` | string | NSE trading symbol, e.g. `INFY` |
| `exchange` | `"NSE"` | only NSE is accepted |
| `timeframe` | `"5m"` \| `"1d"` (also `1m`…`1h`) | |
| `open`, `high`, `low`, `close` | decimal (₹) | |
| `volume` | integer | shares |
| `start`, `end` | ISO-8601 UTC | a bar is visible to agents only once `end ≤ as_of` |

**Real sample** (INFY, 5-minute bar ending 15:15 IST on 14 Oct 2026):

```json
{"symbol": "INFY", "exchange": "NSE", "timeframe": "5m",
 "open": "1090.55", "high": "1093.95", "low": "1088.55", "close": "1090.25",
 "volume": 988637, "start": "2026-10-14T09:40:00Z", "end": "2026-10-14T09:45:00Z"}
```

Daily bar for the same day: `open 1073.70, high 1096.40, low 1069.45, close 1090.25, volume 21079358, end 2026-10-14T10:00:00Z`.

## 2. News — public RSS feeds

Source: ET Markets (two feeds), Business Standard Markets, and Mint Markets/Companies (`NEWS_RSS_URLS` in `docker-compose.yml`). Polled every 5 minutes. Each item becomes a `NewsArticle` ([`NewsArticle.json`](../contracts/schemas/NewsArticle.json)) once it maps to at least one NIFTY 50 symbol, using company-name aliases (`services/intelligence/src/intelligence_agents/news/aliases.py`). Unmapped headlines are counted and dropped.

| Field | Type |
|---|---|
| `article_id` | `rss-<sha256 prefix>` |
| `source` | feed host |
| `title`, `url`, `raw_text` | string |
| `published_at`, `retrieved_at` | ISO-8601 UTC; an agent sees an article only after both are ≤ `as_of` |
| `symbols` | NIFTY symbols mentioned |
| `content_hash` | sha256 of the text |

**Real sample** (Economic Times, retrieved 14 Oct 2026):

```json
{"article_id": "rss-d9b6c1a7bfc2ca57ffa902538597f89d",
 "source": "economictimes.indiatimes.com",
 "title": "Market wrap:  Nestle India, Infosys, Shriram Finance, HDFC Life top gainers and losers on Nifty and Sensex on Wednesday",
 "url": "https://economictimes.indiatimes.com/markets/stocks/news/market-wrap-nestle-india-infosys-shriram-finance-hdfc-life-top-gainers-and-losers-on-nifty-and-sensex-on-wednesday/articleshow/134942022.cms",
 "published_at": "2026-10-14T11:56:38Z",
 "symbols": ["HDFCLIFE", "INFY", "NESTLEIND", "SHRIRAMFIN"]}
```

## 3. Agent opinions — `AgentSignal` (agent → Core)

Every agent, deterministic or LLM, sends the same message to `POST /api/v1/internal/signals`, with the internal token and an `X-Trading-Mode: PAPER` header ([`AgentSignal.json`](../contracts/schemas/AgentSignal.json)). For the orchestrator this message is the input. For the agents it is the output.

| Field | Type | Rule |
|---|---|---|
| `signal_id` | string | idempotency key; a repeat is stored once |
| `agent_name` | one of `technical, momentum, mean_reversion, volume, regime, ml, news, fundamental, valuation, earnings` | |
| `symbol`, `exchange` | NIFTY 50 symbol, `NSE` | rejected otherwise |
| `horizon` | `INTRADAY` \| `SWING` \| `LONG_TERM` | fused separately |
| `signal` | float in [-1, 1] | direction score, **not** an order |
| `confidence` | float in [0, 1] | |
| `timestamp`, `as_of`, `valid_until` | ISO-8601 | future-dated signals are rejected; expired ones are ignored by fusion |
| `reason_codes` | list of strings (≥ 1) | why |
| `features` | flat map | the numbers used |
| `metadata` | JSON object | enough to reproduce the opinion (votes, input hash, LLM model, headlines) |

**Real sample — deterministic Momentum agent** (WIPRO, daily bar of 14 Oct 2026):

```json
{"signal_id": "b5edf5284436c3be37b00d024227abb499afc37cc85dc490f37a96ad83ed227f",
 "agent_name": "momentum", "agent_version": "1.0.0", "symbol": "WIPRO", "exchange": "NSE",
 "horizon": "SWING", "signal": 0.4, "confidence": 0.4,
 "timestamp": "2026-10-14T10:00:00Z", "as_of": "2026-10-14T10:00:00Z", "valid_until": "2026-10-22T10:00:00Z",
 "reason_codes": ["momentum.feature_missing.relative_strength_nifty"],
 "features": {"macd": -1.84190429, "roc_10": 0.09254417, "return_1": 0.01360947, "momentum_10": 12.8,
              "trend_strength_adx": 23.4899105, "volume_confirmation": 0.0},
 "metadata": {"votes": [{"name": "return_1", "value": 1, "weight": 0.35},
                        {"name": "momentum_10", "value": 1, "weight": 0.35},
                        {"name": "macd", "value": -1, "weight": 0.3}],
              "timeframe": "1d", "feature_version": "1.1.0",
              "input_hash": "195cfa42febf231177ddcc4d99841b40923e16a7443b1dd40e757c18440abfb7",
              "source_data_timestamp": "2026-10-14T10:00:00+00:00"},
 "schema_version": "1.0"}
```

**Real sample — News agent on a live headline** (SUNPHARMA, 14 Oct 2026). This signal came through the deterministic fallback (`model: "fixture"`), because no LLM key was configured when it was captured. With a key, `model` names the LLM, and `sentiment`/`impact` come from it.

```json
{"signal_id": "sig-news-04430fd5207d5e86d5e11f59", "agent_name": "news", "symbol": "SUNPHARMA",
 "horizon": "SWING", "signal": 0.0, "confidence": 0.4,
 "as_of": "2026-10-14T18:40:00Z", "valid_until": "2026-10-15T00:43:56.402624Z",
 "reason_codes": ["fixture.heuristic"],
 "features": {"article_count": 1, "mean_sentiment": 0.0},
 "metadata": {"llm": [{"tier": "tier1", "model": "fixture", "fallback": false, "sentiment": 0.0, "impact": 0.4,
                       "confidence": 0.4, "event_type": "corporate.update", "high_impact": false}],
              "headlines": [{"title": "Sun Pharma down 2%, stock hits over 5-month low",
                             "source": "www.business-standard.com",
                             "url": "https://www.business-standard.com/markets/news/sun-pharma-share-price-down-2-stock-hits-over-5-month-low-126101400575_1.html"}]}}
```

## 4. Operator controls

| Input | Endpoint | Effect |
|---|---|---|
| Start / stop paper trading | `POST /api/v1/paper/start`, `/paper/stop` | sets the `paper_running` flag (not reachable through the public proxy) |
| Open a paper session | `POST /api/v1/paper/sessions` `{"starting_cash": "1000000"}` | isolated cash book |
| Kill switch | `POST /api/v1/risk/kill-switch` `{"armed": true}` | blocks new buys and queues flatten sells |
| Zerodha login | `GET /api/v1/zerodha/connect` → Kite login → `/zerodha/callback?request_token=…` | daily market-data access token |
| Environment | `.env` / compose | `TRADING_MODE=PAPER`, `FUSION_EXCLUDED_AGENTS`, `NEWS_RSS_URLS`, `LLM_*`, `PAPER_STARTING_CASH` |
