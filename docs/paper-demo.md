# Paper-trading demo

This checklist uses the existing paper path. It does not place a broker order and it does not run H001.

## Before you start

1. Copy `.env.example` to `.env`.
2. Leave the Zerodha key, secret, and access token empty.
3. Keep `TRADING_MODE=PAPER`.
4. From the repo root, start the stack: `docker compose up --build`.
5. Wait until Postgres is healthy and the API answers on port 8000.
6. Open `http://127.0.0.1:3000`.

The API token baked into the frontend image must equal `CORE_API_TOKEN`.

## What to show

1. The mode banner shows paper, not live.
2. `GET http://127.0.0.1:8000/health` returns `{"status":"ok"}`. `GET /api/v1/system/status` with `Authorization: Bearer <CORE_API_TOKEN>` returns `"trading_mode": "PAPER"` and `"live_enabled": false`.
3. The worker or a posted fixture signal produces agent signals. The Signals page lists them.
4. A paper cycle fuses those signals, builds one proposal, and runs risk. Risk rejects anything that is not `PAPER`.
5. A market buy fills at the next stored open when that bar exists. If it does not, the order stays unfilled.
6. The Orders page shows the order. The Positions page shows the share quantity. Cash is lower by the fill notional plus fees.
7. Stopping the paper loop does not flatten by itself. The kill switch is a separate action. It blocks new buys and queues a flatten that fills on a later bar.
8. The backtests page can show a stored run. It is not a live order.

## What this session already checked

Without Docker, on 2026-10-12:

```bash
.venv/bin/python -m pytest tests/test_phase4.py tests/test_dev3.py tests/test_backtest.py -q
```

31 passed. Those tests fill a paper order on fixture candles, persist it in SQLite, reject non-paper modes, cash shortfalls, the notional cap, and shorts, and keep the holdout snapshot unread.

```bash
cd apps/frontend && npm test
```

12 passed. Those tests do not open a browser and do not call a running API.

With Docker, on 2026-10-12, after rebuilding `core-api`, `quant`, and `intelligence` without resetting Postgres:

- `core-api` was healthy. `GET /health` returned `{"status":"ok"}`. Authenticated `GET /api/v1/system/status` returned paper mode and `live_enabled` false.
- Quant completed a paper pass (`quant_paper_pass`, 245 signals, 50 symbols) with no `Connection refused` line. A later pass was the normal 300-second cycle.
- Intelligence skipped `TRENT` with `fixture_symbol_skipped` and still submitted news, fundamental, and earnings signals. The valuation `KeyError` did not recur.
- Postgres stayed healthy. The frontend container was left running. Its pages were not changed in this pass.

## Optional ML demo

Leave this off for the standard paper demo. The five rule agents do not depend on it. The quant and intelligence images that contain this code were built and were not started. The containers already running still use the earlier images, and Compose does not set `QUANT_ML_DEMO`.

Set `QUANT_TRADING_MODE=PAPER`, `QUANT_ML_DEMO=true`, and `QUANT_ML_DEMO_DIR` to an empty writable directory. Do not also set `QUANT_ARTIFACT_DIR`. The service trains one synthetic artifact into that directory and submits `AgentName.ML` signals whose metadata says `demo: true` and `training_data: synthetic_unvalidated_demo`. The signed score is `clip(2p - 1)`. The training positive rate stored on the artifact is not the decision rule. The rows are not historical market outcomes, and the demo is not an H001 result.

`QUANT_ARTIFACT_DIR` alone loads an existing artifact and does not train. A missing or incompatible artifact does not submit an ML signal and does not stop the other agents.

## Do not show

- A live Zerodha order.
- An H001 fit, score, or claim of profitability. The training minority class is 34, below 50, so the sample rule is `INCONCLUSIVE`.
- The holdout directory `snapshots/holdout_after_20261005`.
