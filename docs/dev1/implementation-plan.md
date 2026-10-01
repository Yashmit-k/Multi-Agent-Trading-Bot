# Developer 1 — Intelligence Subsystem Implementation Plan

This document is the planning artifact for Developer 1. It is based on a scan of the repository as it exists on `main`. It is not an architecture wish-list treated as already implemented.

**Phase of this document:** SCAN → UNDERSTAND → BRANCH → ANALYZE → IDENTIFY DEPENDENCIES → PLAN → DOCUMENT.

Full Intelligence implementation must not start until this file exists. This file existing is the gate.

---

```
========================================
DEVELOPER 1 REPOSITORY ANALYSIS
========================================

BRANCH: dev1/intelligence (created from clean main; not merged to main/master/development)
WORKING TREE: clean at branch creation; this file is the only planned addition for this phase

REPOSITORY STRUCTURE:
- packages/contracts — shared schemas, events, protocols (v1.0.0)
- services/core — API, worker, DB, market-data, candles, features, signal ingestion/fusion, decision, risk, paper execution
- services/quant — real quant agents; not wired in root docker-compose
- services/placeholders — health-only HTTP for compose stubs
- services/intelligence — DOES NOT EXIST
- apps/frontend — Next.js + mock API
- docker/ — Dockerfile.core, Dockerfile.placeholder
- docs/ — naming, core-requests, compose-snippet, generated contracts
- tests/ — root pytest for contracts + core phases
- No root pyproject.toml or requirements.txt

CURRENT ARCHITECTURE:
Market Data (Zerodha/replay) → Candles → Feature Engine → (Quant agents) →
POST /api/v1/internal/signals → agent_signals table → Redis agent.events →
Signal Fusion → Decision → Risk → Portfolio → Paper execution.
Intelligence is not on this path. News/fundamentals exist as contracts/fakes/frontend mock only.

INTELLIGENCE CURRENT STATE:
Placeholder container only. docker-compose service `intelligence` builds docker/Dockerfile.placeholder,
sets SERVICE_NAME=intelligence, publishes host 8101 → container 8080. GET /health returns SERVICE_NAME.
No Python package, no worker, no tests, no LLM, no news ingest.

SHARED CONTRACT VERSION:
packages/contracts 1.0.0; wire schema_version "1.0" (not semver).

RELEVANT EXISTING CONTRACTS:
TradingAgent, AgentContext, SignalSink, MarketDataProvider, FeatureProvider,
NewsProvider, FundamentalProvider, AgentSignal, NewsArticle, NewsSignal,
FundamentalDataPoint, EventEnvelope, SubmissionResult, FeatureSet, Quote, Candle,
AgentName (includes news, fundamental, valuation, earnings), TradingMode, Horizon,
EventType news.article / news.signal / fundamental.updated / agent.signal,
RedisChannel news.events / agent.events / market.events,
pit.filter_available / FutureDataError, FakeNewsProvider, FakeFundamentalProvider, FakeSignalSink.

EXISTING INTELLIGENCE COMPONENTS:
None in services/. Contracts fakes and fixtures only. Frontend mock GET /stocks/{symbol}/news and /fundamentals serve fixtures.

IMPLEMENTED:
Core signal ingest for AgentSignal; fusion default-weights all AgentName including intelligence ids;
quant TradingAgent.evaluate pattern; contracts news/fundamental models and PIT for fundamentals.

PARTIALLY IMPLEMENTED:
NewsProvider/FundamentalProvider (protocol + fake, no live store);
Redis news.events vocabulary (no publisher);
Core GET news/fundamentals routes listed as 501;
docker intelligence stub.

MISSING:
services/intelligence; NewsStore; RSS ingest; LLM stack; intelligence agents;
HttpSignalSink client; intelligence Dockerfile; intelligence tests/CI/env;
article PIT helper in contracts.pit (logic lives in fixtures.articles_for only).

BLOCKED:
Not blocked for fixture-mode agent work. Live LLM optional (env). Compose wiring of a real image is Developer 3 owned.
Core product news/fundamentals HTTP is not required for signal generation.

CONTRACT ISSUES:
No Agent type (use TradingAgent). No FundamentalSignal (use AgentSignal).
No LLM schemas (keep internal). No NewsSignalSink (NewsSignal is event payload only).
AgentContext.configuration forbids api_key and similar — LLM secrets stay in process env.

DEPENDENCIES ON DEVELOPER 2:
Do not implement quant agents, feature arithmetic, or frontend.
Optional: shared HTTP SignalSink client pattern (quant also lacks it).
Feature read HTTP is Core work requested by Dev 2 — optional for intelligence.

DEPENDENCIES ON DEVELOPER 3:
docker-compose.yml including placeholder services. Provide a compose snippet later; do not rewrite compose in this phase.

PROPOSED INTELLIGENCE ARCHITECTURE:
RSS/fixtures → NewsStore (PIT) → NewsProvider
CSV/fixtures → FundamentalStore (PIT) → FundamentalProvider
LLMRouter (OpenAI-compatible, tier1 default, tier2 high-impact, FixtureLLM when unset)
→ NewsAgent / FundamentalAgent / ValuationAgent / EarningsAgent
→ TradingAgent.evaluate → AgentSignal → HttpSignalSink → Core ingest → fusion.
No LangGraph in v1. No orders, Zerodha, risk, or Core Postgres writes.

PROPOSED IMPLEMENTATION ORDER:
1. Package scaffold + health (after this plan)
2. News store + NewsProvider + PIT
3. LLM abstraction + router + fixtures
4. News agent → AgentSignal
5. Fundamental store + provider
6. Fundamental / valuation / earnings agents
7. HttpSignalSink + BACKTEST headers
8. Tests, observability, Dockerfile + compose snippet for Dev 3

FILES TO CREATE (later implementation, not this phase):
services/intelligence/**, services/intelligence/tests/** or tests/intelligence/**,
services/intelligence/Dockerfile, services/intelligence/.env.example,
docs/dev1 compose snippet.

FILES TO MODIFY (later, if needed):
pytest.ini / CI to include intelligence tests.
packages/contracts only if a backward-compatible pit.filter_articles is agreed (semver + CHANGELOG).

FILES NOT TO TOUCH:
services/core/**, services/quant/**, apps/frontend/**, docker-compose.yml (unless Dev 3 asks),
unrelated docs/contracts generated schemas.

TESTING PLAN:
Unit PIT leakage; NewsArticle validation; LLM structured/invalid/timeout/fallback;
agent evaluate determinism with fixtures; FakeSignalSink then HTTP sink mocks;
BACKTEST as_of respected. Pattern: services/quant tests + contracts fakes.

COST CONSIDERATIONS:
Fixtures/RSS/CSV free. OpenAI-compatible LLM optional paid. No paid news/fundamental APIs, embeddings, or vector DB in v1.
Controls: caching, tier routing, daily budget, rate limits, dedup, retry caps, fixture mode default.

SECURITY CONSIDERATIONS:
Secrets in env only. AgentContext must not carry API keys. Never log tokens.
Intelligence must not call Zerodha or hold broker credentials.

HISTORICAL LOOK-AHEAD RISKS:
Future news (published_at or retrieved_at > as_of); restated fundamentals dated as original announce;
using announced_at instead of available_at; live valuation screenshots in BACKTEST;
guidance text retrieved late but backdated; wall-clock LLM knowledge in backtests (use FixtureLLM).

DOCKER REQUIREMENTS:
Later: services/intelligence/Dockerfile copying packages/contracts + service, uvicorn on 8080.
Compose remains Dev 3. Document snippet analogous to docs/compose-snippet.md.

OPEN ARCHITECTURAL QUESTIONS (resolved for v1 unless revisited):
- LLM: OpenAI-compatible HTTP; FixtureLLM when key unset.
- News: RSS + fixtures; no paid news API.
- Fundamentals: fixtures + CSV; no paid fundamental API.
- LangGraph: not in v1.
- NewsSignal: internal intermediate; fusion sees AgentSignal only.
- Redis news.events publish: optional later, not required for fusion.

DEFINITION OF DONE (this planning phase):
dev1/intelligence checked out; existing work preserved; this document exists;
no Intelligence service code; no unrelated subsystem edits.

DEFINITION OF DONE (later implementation):
Four TradingAgent implementations emit valid AgentSignal; PIT enforced;
HttpSignalSink in non-fixture live modes; tests pass; health service;
no Core/Quant/Frontend ownership violations.
========================================
```

---

## 1. Executive Summary

Developer 1 owns the Intelligence / AI subsystem. The repository already has a complete contracts package and a working Core path from `AgentSignal` ingest through paper execution. Quant agents (Developer 2) implement `TradingAgent`. Intelligence is only a Docker health placeholder on port 8101.

This plan tells Developer 1 to build news ingestion, an OpenAI-compatible two-tier LLM stack, and four agents (`news`, `fundamental`, `valuation`, `earnings`) that submit `AgentSignal` to Core via `SignalSink`. It forbids duplicating contracts, implementing Quant/Core/Frontend, using LangGraph in v1, and starting full implementation before this document.

v1 data/LLM default (confirmed): OpenAI-compatible LLM, RSS + fixtures for news, fixture/CSV for fundamentals, no LangGraph.

---

## 2. Current Repository State

Inspected (not assumed from an external spec):

| Path | State |
|------|--------|
| [README.md](../../README.md) | Contracts are source of truth; Core Phase 1–2 + paper Phase 4; `PAPER` default; `LIVE` not enabled |
| [docker-compose.yml](../../docker-compose.yml) | Developer 3 owned. Real: postgres, redis, core-api, core-worker. Stubs: intelligence, quant, frontend |
| [.env.example](../../.env.example) | Core tokens, DB, Redis, paper cash, empty Zerodha keys. No LLM/news keys |
| [.gitignore](../../.gitignore) | Python/node caches; `.env.local` |
| Root `pyproject.toml` / `requirements.txt` / `package.json` | Absent at root. Python packages are per-service. Node: [apps/frontend/package.json](../../apps/frontend/package.json) |
| [pytest.ini](../../pytest.ini) | pythonpath for contracts + core packages; testpaths `packages/contracts/tests` and `tests/` |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | contracts-and-core |
| [.github/workflows/quant-frontend.yml](../../.github/workflows/quant-frontend.yml) | quant + frontend |
| [docs/naming-convention.md](../naming-convention.md) | Agent ids include news/fundamental/valuation/earnings |
| [docs/core-requests.md](../core-requests.md) | Developer 2 requests to Core (SignalSink HTTP, features API, calendar) |
| [docs/compose-snippet.md](../compose-snippet.md) | Future real quant/frontend compose; intelligence not listed |
| Alembic | `0001_initial`, `0002_paper` — `agent_signals`, no news tables |
| LLM / LangGraph | No usage in Python source |

Git at planning time: `main` was clean and up to date with `origin/main`. Commits: `6eba81f` phase 4 + frontend; `6a9ca0d` core; `ad50ac9` contracts 1.0.0.

---

## 3. Current Git Branch / Status

```text
CURRENT BRANCH: dev1/intelligence
WORKING TREE STATUS: this document is the only file this phase should add
```

Process used: `git status`, `git branch`, `git log --oneline -10`, then `git checkout -b dev1/intelligence` from clean `main`.

Never merge this branch into `main`, `master`, or `development` unless explicitly instructed. No `reset --hard`, force-push, or deletion of other work.

---

## 4. Existing Intelligence Components

| Question | Answer |
|----------|--------|
| Does `services/intelligence/` exist? | No |
| Is intelligence a placeholder? | Yes, compose-only |
| Files | [docker-compose.yml](../../docker-compose.yml) lines 55–62; [docker/Dockerfile.placeholder](../../docker/Dockerfile.placeholder); [services/placeholders/health_server.py](../../services/placeholders/health_server.py) |
| Interfaces in-service | None |
| Dependencies | Python 3.12-slim image only |
| API | GET `/health` → 200, body is `SERVICE_NAME` |
| Worker | No |
| Configuration | `SERVICE_NAME=intelligence` |
| Tests | None |
| Docker | Placeholder Dockerfile, port 8101→8080 |

Expected compose run: `docker compose up --build` starts a health stub, not agents.

---

## 5. Shared Contract Analysis

Package: [packages/contracts](../../packages/contracts), version **1.0.0**, `SCHEMA_VERSION = "1.0"`.

### 5.1 Interfaces ([interfaces.py](../../packages/contracts/src/contracts/interfaces.py))

There is no type named `Agent`. The agent contract is:

```python
class TradingAgent(Protocol):
    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal: ...

class SignalSink(Protocol):
    def submit(self, signal: AgentSignal) -> SubmissionResult: ...
```

`AgentContext` is a frozen dataclass requiring:

- `market_data_provider`
- `feature_provider`
- `news_provider`
- `fundamental_provider`
- `configuration` (Mapping; rejects credential keys including `api_key`, `api_secret`, `access_token`, Zerodha keys)
- optional `current_portfolio_snapshot`

Intelligence agents must implement `TradingAgent` even if they ignore market/feature data. They must not recompute technical indicators (`FeatureProvider` docstring).

`NewsProvider.get_articles(symbol, as_of)` — published **and** retrieved at or before `as_of`.

`FundamentalProvider.get_fundamentals(symbol, as_of)` — `available_at <= as_of`.

### 5.2 Agent IDs and modes ([enums.py](../../packages/contracts/src/contracts/enums.py))

Intelligence must use:

- `AgentName.NEWS` = `news`
- `AgentName.FUNDAMENTAL` = `fundamental`
- `AgentName.VALUATION` = `valuation`
- `AgentName.EARNINGS` = `earnings`

Do not invent new agent id strings. Quant owns `technical`, `momentum`, `mean_reversion`, `volume`, `regime`, `ml`.

`TradingMode`: `BACKTEST`, `PAPER`, `SHADOW`, `LIVE`. Same `evaluate` for all modes.

`Horizon`: `INTRADAY`, `SWING`, `LONG_TERM`.

### 5.3 Models (no duplicates)

| Name in the brief | Actual contract |
|-------------------|-----------------|
| AgentSignal | `AgentSignal` — fusion input |
| AgentContext | dataclass in interfaces, not Pydantic |
| Agent | **does not exist** — use `TradingAgent` |
| NewsArticle | `NewsArticle` |
| NewsSignal | `NewsSignal` — article-level NLP |
| FundamentalData | **does not exist** — `FundamentalDataPoint` |
| FundamentalSignal | **does not exist** — use `AgentSignal` with `agent_name=fundamental` (or valuation/earnings) |
| TradeProposal | exists; Core/decision, not Dev1 output |
| EventEnvelope | exists |
| SignalSink | protocol |
| FeatureSet | exists; Core feature engine |
| MarketData | **does not exist** — `Quote` / `Candle` via `MarketDataProvider` |

### 5.4 Events and Redis ([events.py](../../packages/contracts/src/contracts/events.py))

| EventType | Channel |
|-----------|---------|
| `agent.signal` | `agent.events` |
| `news.article` | `news.events` |
| `news.signal` | `news.events` |
| `fundamental.updated` | `market.events` (no `fundamental.events` bus) |
| `agent.heartbeat` | `agent.events` |

No per-agent Redis channel. Payload models: `NewsArticle`, `NewsSignal`, `FundamentalDataPoint`, `AgentSignal`.

### 5.5 Timestamps (not interchangeable)

| Field | Meaning |
|-------|---------|
| `published_at` | Source publication time (`NewsArticle`) |
| `retrieved_at` | When this system obtained the article |
| `announced_at` | When a fundamental was announced |
| `available_at` | First time a backtest may observe a fundamental |
| `as_of` | Knowledge cutoff for providers and `evaluate` |
| `timestamp` | Production/emission time on signals (Quant: injected clock) |
| `valid_until` | Signal expiry; Core rejects stale |
| `source_data_timestamp` | FeatureSet knowable time |

News rule: `retrieved_at >= published_at` (model validator). Visibility: both `<= as_of`.

Fundamental rule: `available_at >= announced_at`. Visibility: `available_at <= as_of` via [pit.py](../../packages/contracts/src/contracts/pit.py). **Do not** use `announced_at` as the backtest clock.

### 5.6 Gaps (contract dependencies, do not silently replace)

1. No LLM request/response, token, or prompt models — keep internal to `services/intelligence`.
2. No `NewsSignalSink` and no Core HTTP for `NewsSignal`.
3. No `filter_articles` in `pit.py` (only [fixtures.articles_for](../../packages/contracts/src/contracts/fixtures.py)).
4. `Features` on `AgentSignal` is an untyped dict with `^[a-z0-9_]+$` keys.

If a PIT helper for news is added to contracts later: backward-compatible, documented, semver bump, CHANGELOG. Not required to start.

---

## 6. Current Architecture

```text
Market Data (Zerodha / HistoricalReplay)
      ↓
Candle Engine
      ↓
Feature Engine
      ↓
Quant TradingAgents (Dev 2) — evaluate → AgentSignal
      ↓
Core Signal Ingestion (POST /api/v1/internal/signals)
      ↓
PostgreSQL agent_signals + Redis agent.events
      ↓
Signal Fusion (newest AgentSignal per AgentName, default weight 1.0)
      ↓
Decision Engine (TradeProposal)
      ↓
Risk Engine
      ↓
Portfolio
      ↓
Paper Execution
```

Redis is publish-only in Core; the paper worker reads stored signals from the DB.

Frontend mock independently serves fixture news/fundamentals. Core product routes for those are 501.

---

## 7. Target Developer 1 Architecture

```text
News (RSS / fixtures)          Fundamental (CSV / fixtures)
        ↓                                  ↓
 Intelligence NewsStore              FundamentalStore
        ↓                                  ↓
 NewsProvider (PIT)                  FundamentalProvider (PIT)
        ↓                                  ↓
        +------ AgentContext --------------+
        |  (also inject market/feature     |
        |   providers: fakes or Core reads)|
        ↓
 Intelligence Agents (TradingAgent.evaluate)
   news | fundamental | valuation | earnings
        ↓
 Internal NewsSignal (optional, article-level)
        ↓
 AgentSignal (required, fusion vocabulary)
        ↓
 SignalSink (Fake in tests; HttpSignalSink → Core)
        ↓
 Core Signal Ingestion → Persistence → Redis agent.events → Signal Fusion
```

Intelligence belongs **beside** Quant as another producer of `AgentSignal`, not inside fusion, risk, or execution.

LLM stays inside Intelligence. It must not place orders, call Zerodha, modify positions, or bypass risk.

---

## 8. Developer 1 Ownership

**Owns:** `services/intelligence/`, `docs/dev1/`, intelligence tests.

**In scope:**

- news ingestion/processing
- news agent
- LLM abstraction, routing, prompts, structured output
- fundamental data integration (provider + store)
- fundamental, valuation, earnings agents
- AI reasoning as ordinary Python (not LangGraph in v1)
- intelligence signal generation via `AgentSignal`
- intelligence-side testing, logging, local Dockerfile

**Does not own and must not implement:**

Zerodha, market data ingest, technical indicators, feature engine, technical/momentum/volume/mean-reversion/ML agents, signal fusion, decision, risk, portfolio, execution, paper/live trading engines, frontend, root `docker-compose.yml`.

---

## 9. Developer 2 Dependencies

Developer 2 (from [docs/core-requests.md](../core-requests.md)): quant + frontend.

| Need | Status | Action |
|------|--------|--------|
| Quant `TradingAgent` / `Runner` / JSON logs / leakage tests | Reference only | Copy patterns, do not edit `services/quant` |
| HTTP SignalSink client | Quant also missing | Dev1 implements own client of Core HTTP |
| Feature read API | Missing (Dev2 asked Core) | OPTIONAL; inject `FakeFeatureProvider` or skip features in news logic |
| Frontend news pages | Mock uses fixtures | Core GET 501 is not Dev1 |

Do not implement Quant agents because they are “already designed.”

---

## 10. Developer 3 Dependencies

Developer 3 owns [docker-compose.yml](../../docker-compose.yml) and health placeholders.

| Need | Status | Action |
|------|--------|--------|
| Placeholder intelligence service | Present | Leave until Dev3 wires a real Dockerfile |
| Real compose service | Not in root compose | Later: snippet in `docs/dev1/` like [docs/compose-snippet.md](../compose-snippet.md) |
| Postgres/Redis | Present for Core | Intelligence talks to Core HTTP; optional Redis publish of `news.events` later |

Do not rewrite `docker-compose.yml` in the planning phase or as a drive-by.

---

## 11. News Architecture

**Exists today:** `NewsArticle`, `NewsSignal`, `NewsProvider`, `FakeNewsProvider`, fixture articles (one visible at `FIXTURE_AS_OF`, one future), frontend mock.

**Missing:** RSS, news API, article storage, ingest worker, symbol mapping beyond fixtures, rate limit/retry for live fetch, Redis `news.article` publisher, Core persistence.

**v1 plan:**

1. `NewsStore` in Intelligence (in-memory + optional JSON/SQLite local to the service — **not** Core PostgreSQL).
2. Ingest: fixture loader + RSS puller. Map items onto `NewsArticle` (`content_hash` = sha256 of `raw_text`).
3. Dedup: `content_hash` and `article_id`.
4. Symbol mapping: configurable map / ticker-in-title heuristics; reject articles with empty `symbols` (contract requires `min_length=1`).
5. `published_at` from feed; `retrieved_at` = ingest clock (must be `>= published_at`; if feed time is in the future vs retrieve, do not coerce clocks—drop or delay until valid).
6. `IntelligenceNewsProvider.get_articles` filters `published_at <= as_of and retrieved_at <= as_of`.
7. Rate limit + retry on RSS fetch; failures log, do not crash evaluate (return empty or last good store).
8. Optional later: publish `EventEnvelope` `news.article` on `news.events`. Not required for fusion.

**Historical availability rule:**

An article is visible to `evaluate(..., as_of, ...)` if and only if:

```text
published_at <= as_of AND retrieved_at <= as_of
```

If `retrieved_at > as_of`, the article is unknown even if it was published earlier. This prevents future retrieval from leaking into backtests.

---

## 12. LLM Architecture

**Exists today:** nothing.

**v1 plan (do not over-build):**

```text
LLMProvider (protocol)
    ├── FixtureLLMProvider          # tests / INTELLIGENCE_DATA_SOURCE=fixtures
    └── OpenAICompatibleProvider    # POST {base}/chat/completions, JSON mode
            ↓
    FallbackProvider (tier1 → cheaper/fixture; never raise into order path)
            ↓
    LLMRouter (tier1 vs tier2 by task + impact flags)
            ↓
    ResponseValidator (JSON schema → internal dataclass)
            ↓
    CostTracker (tokens, estimated USD, daily budget)
```

Also: retries with cap, timeouts, no API keys in logs, cache by `(prompt_version, content_hash, model)`.

LLM output is **not** `AgentSignal`. Agents map validated structure into `AgentSignal` / optional `NewsSignal`.

Forbidden LLM behaviors: orders, Zerodha, portfolio, risk, fusion, Core SQL.

---

## 13. Two-Tier LLM Strategy

**Tier 1 (default, inexpensive):** news classification, sentiment, event/entity extraction, routine summaries.

**Tier 2 (expensive, gated):** ambiguous corporate actions, major regulation, earnings interpretation, conflicting evidence, high-impact headlines.

Router inputs: impact score/heuristics from tier1, `INTELLIGENCE_TIER2_ENABLED`, remaining daily budget. If budget exhausted: skip tier2, emit lower-confidence `AgentSignal` or hold last valid signal policy (document in code; prefer explicit `confidence` reduction over silence unless no articles).

Structured intelligence only. Final trade decision remains Core fusion + decision + risk.

---

## 14. LangGraph Decision

**Installed?** No. **Used?** No.

**v1 decision: do not add LangGraph.**

| Criterion | Assessment |
|-----------|------------|
| Complexity | Graph runtime + checkpointing vs four `evaluate` methods |
| Dependency cost | New major dep; quant already ships without it |
| Testability | Harder than pure functions + FakeLLM |
| Observability | Extra framework vs JSON logs already used by quant |
| Failure handling | Need custom anyway (timeouts, fallback) |
| Benefit vs Python | Bull/bear/synthesis is a short pipeline of functions |

Revisit only if high-impact synthesis cannot stay a testable function chain. If added later, it must still terminate in `AgentSignal` and must not call Core internals.

---

## 15. Fundamental Data Architecture

**Exists:** `FundamentalDataPoint`, `FundamentalProvider`, `FakeFundamentalProvider`, `filter_available`, fixtures EPS FY2024 (visible at `FIXTURE_AS_OF`) and Q1FY2025 (hidden until July 2024).

**Missing:** live provider, storage, update jobs, metric catalog beyond free-form `metric` strings.

**v1:**

```text
CSV / fixtures → FundamentalStore → FundamentalProvider.get_fundamentals(symbol, as_of)
```

Metrics to support when present in files (same `metric` snake_case in `FundamentalDataPoint.metric`): `eps`, `revenue`, `profit`, `pe`, `pb`, `roe`, `roce`, `debt`, `cash_flow`, plus `period` like `FY2024` / `Q1FY2025`.

Timestamps: persist both `announced_at` and `available_at`. Backtests use **`available_at`**. Restatements are new rows with new `available_at`, not silent overwrites of history.

Update frequency: batch load in v1, not a paid streaming API.

Publish `fundamental.updated` on `market.events` is optional later; fusion does not consume it.

---

## 16. Fundamental Agent

`AgentName.FUNDAMENTAL`. Implements `TradingAgent.evaluate`.

Reads `context.fundamental_provider.get_fundamentals(symbol, as_of)` only. Produces `AgentSignal` (`signal` in [-1, 1], `confidence`, `reason_codes`, `features` with allowed keys, `metadata` for reproducibility).

Does not execute trades. Missing data: low-confidence or skip-with-defined-policy (quant raises/logs; intelligence should log and still return a valid `AgentSignal` or let runner catch—prefer a valid neutral signal with `reason_codes` including `insufficient_data` so fusion stays defined).

---

## 17. Valuation Agent

`AgentName.VALUATION`. Inputs: PE, PB, EPS, growth, ROE, ROCE, debt, earnings rows knowable at `as_of`; optional `FeatureSet` for price context only (no new indicators).

Output: **`AgentSignal`**, not a new valuation schema. Sector-relative views go in `features` / `metadata` when data exists; do not invent contract fields.

---

## 18. Earnings Agent

`AgentName.EARNINGS`. Inputs: quarterly/annual `FundamentalDataPoint`s plus news with PIT (surprises, growth, margins, guidance language).

**Timestamp rule:** a result is usable iff `available_at <= as_of`. Related news follows the news PIT rule. Management commentary in an article dated after `as_of` is invisible even if it discusses an older quarter.

---

## 19. Agent Interface

All four agents:

```python
def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
```

Do not add an incompatible interface. `BACKTEST` / `PAPER` / `SHADOW` / `LIVE` share this method. Mode-specific behavior lives in providers (fixtures vs RSS vs HTTP) and `SignalSink`, not in four copies of scoring.

Follow Quant: injected clock for `timestamp`; `as_of` is the knowledge cutoff; `as_of <= timestamp` on `AgentSignal`.

Deterministic `signal_id` (hash of agent, version, symbol, as_of, horizon) so Core duplicate `signal_id` is idempotent.

Refuse PAPER/SHADOW/LIVE process start without a real `SignalSink` (same as [quant_agents/service.py](../../services/quant/src/quant_agents/service.py)).

---

## 20. Signal Submission Architecture

```text
Intelligence Agent
        ↓
SignalSink.submit(AgentSignal)
        ↓
Core POST /api/v1/internal/signals
  Authorization: Bearer INTERNAL_SIGNAL_TOKEN
  X-Trading-Mode, X-Replay-As-Of (required for BACKTEST)
        ↓
Validation → Persistence (agent_signals) → Redis agent.events
        ↓
Signal Fusion
```

Core ingest already rejects: non-NSE, unknown symbol, BACKTEST missing replay boundary, future timestamps, stale `valid_until`.

**Developer 1 must not:** write Core PostgreSQL, call Zerodha, place orders, modify portfolio/positions, call execution, bypass risk, bypass ingest, manipulate fusion state.

If `SignalSink` **protocol** were missing it would be blocking. It exists. The **HTTP client** is missing; Dev1 implements it. Tests use `FakeSignalSink`.

`NewsSignal` is not submitted to `/internal/signals`. Do not invent a second ingest. Optional Redis `news.signal` is observability, not fusion input.

---

## 21. Backtesting Architecture

Same agent code. Providers honor `as_of`. FixtureLLM so the model cannot inject post-cutoff world knowledge. HttpSignalSink sets `X-Trading-Mode: BACKTEST` and `X-Replay-As-Of`. Core checks `timestamp`/`as_of` against that boundary.

Paper worker clock is latest completed candle end (Core), not Intelligence wall clock. Intelligence `as_of` must be the evaluation instant supplied by the runner/clock.

---

## 22. Historical Leakage Controls

| Agent | Required data | Timestamp | Historical rule | Leakage risk | Control |
| ----- | ------------- | --------- | --------------- | ------------ | ------- |
| News | `NewsArticle` | `published_at`, `retrieved_at` | both `<= as_of` | Future RSS; backdated retrieve; wall clock | Filter in provider; tests with future fixture article |
| Fundamental | `FundamentalDataPoint` | `available_at` | `available_at <= as_of` | Using `announced_at`; restatements | `filter_available`; new rows for revisions |
| Valuation | fundamentals + optional features | `available_at`, `source_data_timestamp` | same PIT | Live PE snapshot in BACKTEST | Fixture/CSV only in BACKTEST unless PIT store |
| Earnings | points + news | `available_at` + news PIT | same | Guidance retrieved late, dated early | Dual filter; FixtureLLM |

Additional: never pass raw LLM web-browse; never use `datetime.now()` as news `published_at`; `AgentContext` has no broker.

---

## 23. Cost-Control Strategy

| Dependency | Cost class | v1 |
|------------|------------|-----|
| Fixture / CSV / local store | FREE | Default |
| RSS | FREE | Allowed |
| OpenAI-compatible LLM | OPTIONAL PAID | Env key; disable → FixtureLLM |
| Paid news APIs | OPTIONAL PAID | Not in v1 |
| Paid fundamental APIs | OPTIONAL PAID | Not in v1 |
| Embeddings / vector DB | OPTIONAL PAID | Not in v1 |

Controls: content_hash cache, tier1 default, daily `LLM_DAILY_BUDGET_USD`, max tokens, batch nothing that breaks PIT, RSS rate limits, retry caps, skip tier2 over budget.

---

## 24. Rate Limiting

- RSS: per-source interval.
- LLM: requests/minute and concurrent cap.
- Core ingest: rely on Core; client timeouts/retries with idempotent `signal_id`.
- Do not hammer Core on agent exceptions (quant runner logs and continues).

---

## 25. Error Handling

- Provider failure: log, do not place orders; evaluate returns defined signal or runner catches.
- LLM timeout/invalid JSON: retry then fallback to Fixture/heuristic/low confidence.
- Duplicate `signal_id`: treat `SubmissionResult.duplicate` as success-idempotent.
- Leakage detected in BACKTEST: fail the test/run (quant raises `LeakageError` in BACKTEST). Intelligence should fail closed in BACKTEST if a provider returns a future point.

---

## 26. Observability

JSON logs modeled on [quant_agents/logging.py](../../services/quant/src/quant_agents/logging.py).

Fields: `agent_name`, `symbol`, evaluation `as_of`, `published_at`/`retrieved_at`/`available_at` as applicable, `model`, `llm_tier`, latency, token usage, estimated cost, provider errors, fallback events, `signal_id`, `correlation_id`.

Never log API keys, tokens, or raw `.env`.

Optional later: `AgentHeartbeat` on `agent.events` — only if it does not require Core changes; not v1 blocking.

---

## 27. Configuration

Do not put secrets in `AgentContext.configuration`. Use process environment.

Proposed `services/intelligence/.env.example` (later):

```text
INTELLIGENCE_DATA_SOURCE=fixtures
INTELLIGENCE_TRADING_MODE=BACKTEST
INTELLIGENCE_LOG_LEVEL=INFO
CORE_API_URL=http://localhost:8000
INTERNAL_SIGNAL_TOKEN=
CORE_API_TOKEN=
LLM_BASE_URL=
LLM_API_KEY=
LLM_TIER1_MODEL=
LLM_TIER2_MODEL=
LLM_DAILY_BUDGET_USD=0
LLM_TIMEOUT_SECONDS=30
NEWS_RSS_URLS=
INTELLIGENCE_TIER2_ENABLED=false
```

Root [.env.example](../../.env.example) stays Core-owned; do not dump LLM keys there unless Dev3 agrees. Feature flags: fixtures vs live RSS/LLM.

`TRADING_MODE` for Core remains separate from `INTELLIGENCE_TRADING_MODE`.

---

## 28. Testing Strategy

Conventions: pytest, Python 3.12, contracts fakes, quant-style unit vs integration markers.

### News

Duplicate articles, malformed feeds, missing timestamps, wrong symbols, provider failure, rate limit, retry, historical filtering (`articles_for` future article must stay hidden).

### LLM

Valid JSON, invalid JSON, timeout, provider failure, fallback, schema validation, cost tracker increments, FixtureLLM determinism.

### Agents

Deterministic `evaluate` on fixtures; `AgentSignal` schema; `as_of` correctness; leakage tests; missing/stale data; `FakeSignalSink` then mocked HTTP.

### Backtesting

Future news/fundamentals unavailable; same agent class for BACKTEST/PAPER; `as_of` respected; Core header behavior unit-tested on the client.

Do not add intelligence tests to Core packages.

---

## 29. Docker Integration

Current: placeholder on 8101.

**Later, not this phase:**

- `services/intelligence/Dockerfile` following [services/quant/Dockerfile](../../services/quant/Dockerfile): copy `packages/contracts` and `services/intelligence`, install editable, uvicorn on 8080.
- `docs/dev1/compose-snippet.md` for Developer 3 (`build.context: .`, not a service-directory-only context).
- Do not blindly rewrite [docker-compose.yml](../../docker-compose.yml).
- Local: `pip install -e packages/contracts -e services/intelligence`; pytest in the intelligence tree.
- Future deploy: same image; secrets via env.

Health: `/health` like quant (`degraded` without sink in live modes).

---

## 30. Required Files (later implementation)

```text
docs/dev1/implementation-plan.md          # this file (planning phase)
docs/dev1/compose-snippet.md              # later
services/intelligence/pyproject.toml
services/intelligence/Dockerfile
services/intelligence/.env.example
services/intelligence/src/intelligence_service/  # package name TBD; avoid colliding with stdlib
  __init__.py, service.py, settings.py, logging.py, clock.py, runner.py
  news/store.py, news/rss.py, news/provider.py
  fundamentals/store.py, fundamentals/provider.py
  llm/provider.py, llm/openai_compat.py, llm/fixture.py, llm/router.py, llm/validate.py, llm/cost.py
  agents/news.py, agents/fundamental.py, agents/valuation.py, agents/earnings.py
  sink/http.py
services/intelligence/tests/unit/...
```

Exact package directory name can match quant (`src/quant_agents`) as `src/intelligence_agents` to stay consistent.

---

## 31. Files To Modify (later)

- [pytest.ini](../../pytest.ini) and/or a dedicated workflow to run intelligence tests.
- [packages/contracts](../../packages/contracts) **only** if a missing contract is genuinely required, backward-compatible, versioned, and CHANGELOG’d (e.g. `pit.filter_articles`). Prefer implementing the filter inside Intelligence first.

---

## 32. Files NOT To Modify

```text
services/core/**
services/quant/**
apps/frontend/**
docker-compose.yml
docker/Dockerfile.core
docker/Dockerfile.placeholder          # leave until Dev3 switches the service
services/placeholders/health_server.py
docs/contracts/**                      # generated
```

No drive-by refactors.

---

## 33. Implementation Dependencies

| Dependency | Status | Blocking? |
|------------|--------|-----------|
| contracts 1.0.0 | AVAILABLE | No |
| Core ingest HTTP | AVAILABLE | No |
| Fake providers/sink | AVAILABLE | No |
| Live LLM | OPTIONAL | No for fixture v1 |
| RSS | OPTIONAL | No for fixture v1 |
| Dev3 compose wire-up | OPTIONAL | No for local pytest |
| Feature HTTP | MISSING | No |
| Core news GET | 501 | No for signals |
| LangGraph | N/A | No |

---

## 34. Blocking Issues

**None** for fixture-mode implementation after this plan.

Non-blocking gaps: no HTTP SignalSink client (Dev1 will add); no article PIT helper in contracts; Core 501 news/fundamentals; compose still a stub; `AgentContext` credential denylist means LLM keys cannot ride in `configuration`.

---

## 35. Implementation Order

Default from the brief, **adjusted** because contracts and Core ingest already exist, and LangGraph is rejected for v1:

1. Verify shared contracts — **done in this scan**
2. Define/verify interfaces — **done; use TradingAgent / SignalSink**
3. Package scaffold + health (quant-like) — **first code after this document**
4. Provider abstractions (news/fundamental stores wrapping contracts)
5. News ingestion (fixtures + RSS)
6. LLM abstraction + routing + FixtureLLM
7. News agent
8. Fundamental data provider
9. Fundamental agent
10. Valuation agent
11. Earnings agent
12. LangGraph — **skipped in v1**
13. SignalSink HTTP client
14. Backtest compatibility (PIT + headers)
15. Tests (progressively with each step; not a single dump at the end)
16. Observability
17. Docker image + Dev3 snippet
18. Integration tests against Core ingest (optional, marked)

**Why the change:** step 1–2 are analysis; LangGraph is not justified; tests should land with each agent; Docker last because compose is Dev3-owned.

---

## 36. Definition of Done

### This planning phase (current)

- [x] Repository scanned; contracts treated as source of truth
- [x] `dev1/intelligence` exists and is checked out
- [x] Existing work preserved
- [x] This file exists at `docs/dev1/implementation-plan.md`
- [x] No full Intelligence implementation started
- [x] No unrelated subsystem modified

### Later implementation phase

- Four `TradingAgent`s emit valid `AgentSignal` with canonical `agent_name`s
- News PIT and fundamental PIT enforced and tested
- LLM optional, never on the order path
- `HttpSignalSink` used for PAPER/SHADOW/LIVE; `FakeSignalSink` in unit tests
- No Core Postgres, Zerodha, risk, fusion, or frontend ownership violations
- Health endpoint; Dockerfile ready for Dev3; secrets in env; JSON logs without keys

---

## Appendix A — Compose intelligence block (current)

From [docker-compose.yml](../../docker-compose.yml):

```yaml
  intelligence:
    build:
      context: .
      dockerfile: docker/Dockerfile.placeholder
    environment:
      SERVICE_NAME: intelligence
    ports:
      - "8101:8080"
```

## Appendix B — Core ingest contract Dev1 must honor

`POST /api/v1/internal/signals` in [core_api/app.py](../../services/core/api/src/core_api/app.py): Bearer `INTERNAL_SIGNAL_TOKEN`; body `AgentSignal`; headers `X-Trading-Mode`, `X-Replay-As-Of`.

Fusion in [core_fusion/fuse.py](../../services/core/signal-fusion/src/core_fusion/fuse.py) already includes intelligence agent names at default weight 1.0. No Core change is required for those signals to participate once ingested.
