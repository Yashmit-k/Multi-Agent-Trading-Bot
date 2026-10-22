# Multi-agent trading

> **Assessment submission**
>
> - Live demo: **https://13-238-176-73.sslip.io** (AWS EC2 t3.small, ap-southeast-2; see [`deploy/README.md`](deploy/README.md))
> - [Project synopsis](docs/submission/synopsis.md) — problem, solution, target user, scope vs CA2
> - [Design document](docs/submission/design.md) — architecture diagram, agent roles, orchestration pattern, technology choices
> - [Input definition](docs/submission/input-definition.md) and [Output definition](docs/submission/output-definition.md), with real samples
> - [Agent execution traces](docs/submission/agent-trace/): real Redis bus messages captured by the trace recorder. Start with [one complete real trade](docs/submission/agent-trace/20261021-jswsteel-trade.md) (agent signal → proposal → 18 manager steps with a re-check request → REDUCE → 19 risk checks → order → fill), then [the portfolio-manager reviews](docs/submission/agent-trace/20261020-portfolio-manager-reviews.md): planning, tool calls, critique and revision, an agent-to-agent re-check request and its reply, model failover, and the verdict.
> - Portfolio manager (LLM supervisor agent): [`services/intelligence/src/intelligence_agents/manager/`](services/intelligence/src/intelligence_agents/manager/); live at [/manager](https://13-238-176-73.sslip.io/manager)
> - [Research write-ups](services/quant/docs/): 15 pre-registered studies (each protocol written before its result was run), including the failures
> - [Demo video script](docs/submission/demo-script.md)
>
> Team (commit authors): Yashmit Kotekar ([@Yashmit-k](https://github.com/Yashmit-k)), ishita2403, nimitajestin. Each member should confirm their GitHub username here.
>
> Live market data comes from Zerodha Kite, and live news from public RSS feeds. Trading is **paper only**: `live_enabled` is hard-coded false.

Shared contracts live in [`packages/contracts`](packages/contracts). That package is the only source of truth for schemas, event names, Redis channels, horizons, trading modes, and agent interfaces.

Install it from the repo root:

```bash
python3 -m pip install -e "packages/contracts[dev]"
```

Contract changes ship as a pull request to `packages/contracts` with a semantic version bump. Other services import this package and do not redefine its models or vocabulary.

Core Phase 1–2 lives under `services/core`. Copy `.env.example` and start the stack with `docker compose up --build`. The default trading mode is `PAPER`. `LIVE` is not enabled. Alembic migrations in `services/core/db` use the same review gate as contract changes.

Phase 4 turns stored signals into a paper fill. `PAPER_STARTING_CASH` is in `.env.example`. The worker's paper clock is the latest completed candle end, not the wall clock. Paper and backtest share one execution path. A market decision on candle `t` fills at the next stored bar's open. If that bar does not exist, the order stays unfilled. Quantity is the largest whole share that fits available cash and the 100,000 notional cap. The default transaction cost is 2 bp. An explicit cost schedule, including an explicit 0 bp schedule, overrides that default. The fill price includes configured slippage. Fees and slippage are stored separately. If the stop and the target are both inside the same later bar, the stop wins. The kill switch is separate from paper start and stop. `live_enabled` is false. Risk accepts `PAPER` only. Candle polling is separate from that worker and is described in [`docs/market-data-collector.md`](docs/market-data-collector.md).

## Setup

Python 3.12 or newer. From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "packages/contracts[dev]"
pip install -e "services/core/db"
pip install -e "services/core/candle-engine"
pip install -e "services/core/feature-engine"
pip install -e "services/core/signal-ingestion"
pip install -e "services/core/market-data"
pip install -e "services/core/signal-fusion"
pip install -e "services/core/decision-engine"
pip install -e "services/core/risk-engine"
pip install -e "services/core/paper-execution"
pip install -e "services/core/api"
pip install -e "services/core/worker"
pip install -e "services/quant"
```

Copy `.env.example` to `.env`. Leave `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, and `ZERODHA_ACCESS_TOKEN` empty. `TRADING_MODE` stays `PAPER`. `live_enabled` is hard-coded false in the API.

## Database and startup

`docker compose up --build` starts Postgres 16, Redis, the core API on port 8000, the worker, the quant service, the intelligence service, and the dashboard on port 3000. Compose points `DATABASE_URL` at `postgresql+psycopg://core:core@postgres:5432/core`. The API applies the schema on startup. Do not point this stack at a database you cannot replace.

The dashboard build argument `NEXT_PUBLIC_CORE_API_TOKEN` must match `CORE_API_TOKEN` in `.env`.

Without Docker, the paper tests use an in-memory SQLite database. They do not need Postgres.

## Tests

```bash
.venv/bin/python -m pytest tests/test_phase4.py tests/test_dev3.py tests/test_backtest.py -q
cd apps/frontend && npm test
```

The first command checked the paper fill, risk rejects, and shared backtest path on 2026-10-12: 31 passed. The frontend command checked API, mode, stream, and state helpers: 12 passed. Neither command starts the Docker stack or places a broker order.

A separate Compose check the same day left Postgres and the core API healthy, in paper mode, with `live_enabled` false. Quant completed a paper pass. Intelligence skipped symbols outside the fixture candle set. The dashboard source was not changed.

## Submission notes

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- What is implemented: [`docs/feature-inventory.md`](docs/feature-inventory.md)
- Paper demo checklist: [`docs/paper-demo.md`](docs/paper-demo.md)
- Project report: [`docs/project-report.md`](docs/project-report.md)
- Current system and H001 status: [`docs/current-status.md`](docs/current-status.md)

H001 is approved as a method and is not authorized to run. The eligibility audit is `INCONCLUSIVE` because the training minority class is 34, below the approved bar of 50. No H001 model was fit. Teammates: check out **`dev1/intelligence`** and follow [`services/quant/docs/h001-dev1-handoff.md`](services/quant/docs/h001-dev1-handoff.md) for live RSS ingest and official H001. This is not on `main`. Do not use `experiment/h001-threshold-34` for the official result.

## Optional ML demo

`MlAgent` is not in the default paper pass. `QUANT_ML_DEMO=true` is accepted only with `QUANT_TRADING_MODE=PAPER` and a separate `QUANT_ML_DEMO_DIR`. It trains one synthetic logistic model, not a market outcome model, and labels its signals `demo: true` / `training_data: synthetic_unvalidated_demo`. Inference uses `clip(2p - 1)`. `training_positive_rate` in the manifest is not a threshold. Setting `QUANT_ARTIFACT_DIR` at the same time is a configuration error. A normal artifact directory is loaded and not retrained. An ML failure does not drop the five rule agents.

## Today-Drop ML filter

Algorithm 1 is a research-only logistic filter in `services/quant/src/quant_agents/research/today_drop_ml_filter.py`. It is not the synthetic demo and it is not wired into the paper loop. Strategy A still exits at a 3% stop or a 5% target. The model label is a separate two-session outcome. The run on `snapshots 2/nifty50` wrote `datasets/research/today_drop_ml_filter/algo1-v1/`. Its script label is `CANDIDATE EDGE — REQUIRES PROSPECTIVE PAPER VALIDATION`. Validation ROC AUC was 0.478, the chosen threshold was 0.50, and the filtered evaluation mean was almost the same as a precommitted drop of at least 2%. That period was already used by earlier Today-Drop studies. Do not treat the artifact as production-ready.

## Quant + News

Algorithm 2 stopped at the data-readiness gate and did not train a model. The note is [`datasets/research/quant_news_fusion/algo1-v1/data_readiness_report.md`](datasets/research/quant_news_fusion/algo1-v1/data_readiness_report.md). Fixture sentences and an optional live RSS pull are not a historical news archive. The Today-Drop result above is unchanged.

Focused check, with no H001 data and no broker:

```bash
PYTHONPATH="services/quant/src:packages/contracts/src" .venv/bin/python -m pytest services/quant/tests/unit/test_ml_demo.py -q --override-ini="addopts="
PYTHONPATH="services/intelligence/src:packages/contracts/src" .venv/bin/python -m pytest services/intelligence/tests/test_source_modes.py -q --override-ini="addopts="
```
