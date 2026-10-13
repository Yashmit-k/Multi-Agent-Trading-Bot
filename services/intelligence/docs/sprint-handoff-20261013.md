# Developer 1 sprint handoff — 2026-10-13

## Status

Intelligence **demo path works on labelled fixtures**. Live Google News RSS ingest works in `oneshot` + `PAPER` without the paper evaluation loop (see `docs/live-news.md`). LLM is **fixture** unless keys/Ollama are configured; news interpretation stays unavailable without those credentials.  
H001: controlling protocol `services/quant/docs/h001-protocol-approval.md`. Approved scope **A** (not B). `DATA_PREP_READY = NO` · `READY_TO_RUN = NO` · eligibility **INCONCLUSIVE** (34 &lt; 50). `USER APPROVED — NOT AUTHORIZED TO EXECUTE`. **Not trained.** See `docs/h001-scope-decision.md`.

## 1. What works

- Intelligence `GET /health`, `GET /news/{symbol}`, `GET /fundamentals/{symbol}` with contract models.
- Fixture load for RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK.
- PIT: Q1FY2025 EPS hidden at `2024-06-03T10:00:00+00:00`.
- Invalid `as_of` returns 400.
- Empty list for symbols without fixtures (e.g. TATAMOTORS) — not fake live news.
- RSS ingest: `INTELLIGENCE_DATA_SOURCE=rss` starts `news_ingest_loop`; overlay service `intelligence-news` does not start `core-worker`.
- Core already proxies `/api/v1/stocks/{symbol}/news` and `/fundamentals` when `INTELLIGENCE_URL` is reachable.

## 2. Live vs fixture

Default: **`data_origin=demo_fixture`**, `metadata.fixture=true`, `metadata.live=false`.  
Fundamentals also set `not_historical_nse_vintage=true`.  
`llm_mode=fixture` when `LLM_API_KEY` is empty.

Default Compose `intelligence` service is still **fixtures + PAPER serve**. Live news is a separate path (`rss` / `intelligence-news`). Do not treat fixtures as live.

## 3. Launch (do not start paper worker)

```text
set PYTHONPATH=packages/contracts/src;services/intelligence/src
set INTELLIGENCE_TRADING_MODE=BACKTEST
set INTELLIGENCE_SERVICE_MODE=oneshot
set INTELLIGENCE_DATA_SOURCE=fixtures
set INTELLIGENCE_STORE=memory
python -m uvicorn intelligence_agents.service:create_app --factory --host 127.0.0.1 --port 8080
```

```text
pytest services/intelligence/tests/test_demo_routes.py services/intelligence/tests/test_h001v2_normalize.py -q
```

(8 passed in this sprint environment.)

## 4. Example (fixture) shapes

News article: `title`, `source=fixture-wire`, `url` on `example.test`, `published_at`/`retrieved_at` UTC, `symbols`, `raw_text`, `metadata.fixture`.  
Fundamentals: `metric=eps`, `period=FY2024`, `source=fixture-filings`, `available_at` after `announced_at`.

## 5. Other owners

- **Core:** user-auth on `/api/v1/stocks/...`; 503 if Intelligence down. Timeout 3s. No Core code changed.
- **Frontend:** still Core contract. No UI redesign.
- **Compose PAPER serve:** starts evaluation loop — **not** used for this demo.

## 6. Files touched

- `services/intelligence/src/intelligence_agents/service.py`
- `services/intelligence/src/intelligence_agents/news/rss.py`
- `services/intelligence/src/intelligence_agents/h001v2/` (`normalize.py`, `scan.py`, `integrity.py`, `__init__.py`)
- `services/intelligence/tests/test_demo_routes.py`
- `services/intelligence/tests/test_h001v2_normalize.py`
- `services/intelligence/docs/demo-readiness.md`
- `services/intelligence/docs/h001-v2-candidate.md`
- `services/intelligence/docs/h001-timestamp-leakage.md`
- `services/intelligence/docs/sprint-handoff-20261013.md`
- gitignored `datasets/h001-v2-research-20261013/coverage.json`

## 7–10. H001

Freeze reused: `datasets/h001-nse-raw-20261010T140237Z` (not overwritten).

Approved research scope is **A** (Quant `h001-protocol-approval.md`); Scope B is not required. Eligibility **INCONCLUSIVE** (train minority 34 &lt; 50). Sponsor: **neither** paid fundamentals nor XBRL harvest.

Scope A audit (hasher + §15 + 49×8) is in `docs/h001-scope-a-coverage.md`, `h001-scope-a-integrity.json`, `h001-scope-a-SHA256SUMS.txt`. **Still not ready to run.** New listing digest `18dbec4a…` re-measured (493 files); `b0f4760f…` **UNVERIFIED** and **not equivalent**. §15 kept **3690** under the written rule (dominated by `hasXbrl`-only non-results subjects). §16: **345 / 392** cells; **47** missing, all `2025Q2`. v1 unique announcements: 247 (train 99, validate 148). v2 remains candidate-only.

`exchdisstime` proxy limitation documented (accepted as proxy only). No labels. No train.  
**Readiness: FAIL overall** (`DATA_PREP_READY = NO` · `READY_TO_RUN = NO`). `USER APPROVED — NOT AUTHORIZED TO EXECUTE`.

## 11. Five-minute demo

1. Uvicorn oneshot fixtures.  
2. `/health` → `data_origin=demo_fixture`, `llm_mode=fixture`.  
3. `/news/RELIANCE?as_of=2024-06-03T10:00:00+00:00` → fixture article.  
4. `/fundamentals/TCS?as_of=...` → FY2024 only.  
5. `/news/TATAMOTORS?...` → `[]`.  
6. Show H001-v2 candidate doc: counts vs still not ready to train.

## 12. Blockers

| Blocker | Owner |
|---|---|
| Moneycontrol RSS 403; no NSE filing RSS | External / licensed source |
| Live LLM interpretation | Operator `LLM_*` |
| Core auth + `INTELLIGENCE_URL` for UI path | Core (Dev3) |
| Frontend display | Frontend owner |
| H001 v1 execution authorization | Governance |
| H001 v2 protocol approval | Governance |
| H001 Scope B / paid feed / XBRL harvest | Unapproved (sponsor: neither) |
| Historical digest recipe | Unrecovered |
| Paper/live agent loop | Out of scope (do not start) |
