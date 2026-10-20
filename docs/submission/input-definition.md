# Input definition

The system takes four kinds of input. Every schema is defined once in `packages/contracts` and exported as JSON Schema in [`docs/contracts/schemas/`](../contracts/schemas/). The full HTTP contract is [`docs/contracts/openapi.json`](../contracts/openapi.json). All samples below are **real rows** copied from the running system's Postgres database (market data and news from 14 Oct 2026; agent signals and the manager question from 20 Oct 2026). They were not hand-written.

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

Source: 16 public feeds from Economic Times, Business Standard, Mint, The Hindu BusinessLine, NDTV Profit and CNBC-TV18 (`NEWS_RSS_URLS` in `docker-compose.yml`). Polled every intelligence cycle, and again on demand when the portfolio manager asks the News agent to re-check. Each item becomes a `NewsArticle` ([`NewsArticle.json`](../contracts/schemas/NewsArticle.json)) once it maps to at least one NIFTY 50 symbol, using company-name aliases (`services/intelligence/src/intelligence_agents/news/aliases.py`). Unmapped headlines are counted and dropped.

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

**Real sample: deterministic Momentum agent** (TCS, daily bar of 19 Oct 2026, agents 1.4.0):

```json
{"signal_id": "e347b043e93839b9eca181d7b8633e8b3cb67bd472179addda7236168512fbe2",
 "agent_name": "momentum", "agent_version": "1.4.0", "symbol": "TCS", "exchange": "NSE",
 "horizon": "SWING", "signal": 1.0, "confidence": 1.0,
 "timestamp": "2026-10-19T10:00:00Z", "as_of": "2026-10-19T10:00:00Z", "valid_until": "2026-10-27T10:00:00Z",
 "reason_codes": ["momentum.evaluated"],
 "features": {"roc_10_z": 3.35948031, "trend_strength_adx": 29.34223753, "relative_strength_nifty": 0.00948928},
 "metadata": {"votes": [{"name": "roc_10", "value": 1, "weight": 0.45},
                        {"name": "trend_strength", "value": 1, "weight": 0.3},
                        {"name": "relative_strength", "value": 1, "weight": 0.25}],
              "timeframe": "1d", "feature_version": "1.2.0", "features_missing": [],
              "input_hash": "9d3abaea50ffe20b0b3deef32cac6ca8f904c1eb944c08e44794ea9209ec3916",
              "source_data_timestamp": "2026-10-19T10:00:00+00:00"},
 "schema_version": "1.0"}
```

**Real sample: News agent scored by the LLM** (TCS, 20 Oct 2026; nine live headlines, two shown). `model` names the LLM. When the LLM fails or its quota is used up, the same agent falls back to a heuristic: `model` becomes `"fixture"`, the reason code is `fixture.heuristic`, and the portfolio manager treats that opinion as unchecked.

```json
{"agent_name": "news", "agent_version": "1.1.0", "symbol": "TCS", "horizon": "SWING",
 "signal": 0.42, "as_of": "2026-10-20T12:40:00Z",
 "features": {"price_only": false, "article_count": 9, "mean_sentiment": 0.6},
 "metadata": {"llm": [{"tier": "tier1", "model": "gemini-3.1-flash-lite", "sentiment": 0.6, "impact": 0.7,
                       "confidence": 0.9, "event_type": "analyst_view", "high_impact": true, "fallback": false,
                       "reason_codes": ["analyst_view", "price_move", "operating_updates"]}],
              "headlines": [
   {"title": "TCS, HCL Tech, Wipro, Infosys to Tech Mahindra — experts bullish on IT shares after Accenture's shift from AI investment",
    "source": "www.livemint.com", "published_at": "2026-10-19T07:04:21+00:00"},
   {"title": "Dharmesh Kant sees another 5-10% upside in IT stocks; prefers TCS, HCLTech and Tech Mahindra",
    "source": "www.cnbctv18.com", "published_at": "2026-10-19T04:15:21+00:00"}]}}
```

## 4. Operator controls

| Input | Endpoint | Effect |
|---|---|---|
| Start / stop paper trading | `POST /api/v1/paper/start`, `/paper/stop` | sets the `paper_running` flag (not reachable through the public proxy) |
| Open a paper session | `POST /api/v1/paper/sessions` `{"starting_cash": "1000000"}` | isolated cash book |
| Kill switch | `POST /api/v1/risk/kill-switch` `{"armed": true}` | blocks new buys and queues flatten sells |
| Ask the portfolio manager | `POST /api/v1/reviews` `{"symbol": "RELIANCE", "horizon": "SWING"}` (operator sign-in) | a hypothetical review; nothing is traded (section 5) |
| How an applied strategy shares the book | `POST /api/v1/settings/risk` `{"values": {"strategy_mode": "replace" \| "alongside" \| "agents_agree"}}` | strategy replaces agent entries; both trade; or the strategy trades only when the agents agree |
| Manager review on/off | `POST /api/v1/settings/risk` `{"values": {"manager_review": false}}` | agent BUYs skip the manager and go straight to risk |
| Zerodha login | `GET /api/v1/zerodha/connect` → Kite login → `/zerodha/callback?request_token=…` | daily market-data access token |
| Environment | `.env` / compose | `TRADING_MODE=PAPER`, `FUSION_EXCLUDED_AGENTS`, `NEWS_RSS_URLS`, `LLM_*`, `MANAGER_LLM_MODEL`, `MANAGER_FALLBACK_MODEL`, `LLM_REASSESS_MODEL`, `PORTFOLIO_MANAGER_REVIEW`, `PAPER_STARTING_CASH` |

## 5. Portfolio-manager review request: `ReviewRequest`

The portfolio manager's input ([`ReviewRequest.json`](../contracts/schemas/ReviewRequest.json)). The decision engine creates one for every agent BUY (`kind: "pipeline"`, with the `proposal_id`). An operator question creates one with `kind: "ad_hoc"`. The manager claims it from Core (`POST /api/v1/internal/reviews/claim`), and it is published as `review.requested`.

| Field | Type | Notes |
|---|---|---|
| `review_id` | string | `rv-` + sha256 of the proposal id, or `rv-adhoc-…` |
| `kind` | `pipeline` \| `ad_hoc` | only a pipeline verdict gates a trade |
| `proposal_id` | string or null | links the review into the proposal's trace |
| `symbol`, `horizon`, `side`, `quantity`, `entry_price` | | the trade under review |
| `aggregated_signal`, `aggregated_confidence` | float | the fused view it came from |
| `requested_at`, `requested_by` | | `decision-engine` or `operator` |

**Real sample** (operator question, 20 Oct 2026):

```json
{"review_id": "rv-adhoc-da9515777d6742a59fe6958c", "kind": "ad_hoc", "proposal_id": null,
 "symbol": "RELIANCE", "horizon": "SWING", "side": "BUY", "quantity": 16, "entry_price": "1203.0000",
 "aggregated_signal": 0.348, "aggregated_confidence": 0.52,
 "requested_at": "2026-10-20T13:18:45.609377Z", "requested_by": "operator",
 "metadata": {"question": "Would you buy RELIANCE now for the swing book?", "hypothetical": true}}
```

The manager's tools are inputs too. They are read-only `GET /api/v1/internal/tools/{opinions|features|market|portfolio|track_record}` views of the blackboard, plus the intelligence service's `/news/{symbol}` and `/fundamentals/{symbol}`.
