# Project report

## Problem

A multi-agent paper trader needs one path from market bars to a stored fill, with risk checks that refuse live trading. A separate earnings-timing study, H001, asked whether a results announcement predicts the next session's sign after costs. That study is not part of the trading demo.

## Objectives

- Keep one schema for signals, decisions, and orders.
- Fuse agent signals and size a paper order under cash and notional limits.
- Persist the fill, position, and cash.
- Show that state in the dashboard.
- Leave live trading off.
- Finish H001 only if the approved sample rule is met. It was not.

## Architecture

See [`architecture.md`](architecture.md). Contracts are the schema source. Feature, fusion, decision, risk, and paper execution are separate packages. Paper and backtest share the fill rule: next stored open, 2 bp unless an explicit schedule is passed, stop-first if stop and target are in the same bar.

## Implementation

The core services, five quant rule agents, an intelligence service in fixture mode, and a Next.js dashboard are in the repo. Those five agents are the paper path. An optional synthetic `MlAgent` stays off unless `QUANT_ML_DEMO` is set with `QUANT_TRADING_MODE=PAPER` and a separate demo directory. `QUANT_ARTIFACT_DIR` alone loads an existing artifact and does not train. The containers already running do not include this ML code: the newer quant and intelligence images were built and were not started. `live_enabled` is false. Risk's `assess()` accepts `PAPER` only. Fixture valuation quotes exist for `RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, and `ICICIBANK`. RSS and CSV reach the news and fundamentals agents only when those source modes are configured. Compose stays on fixtures. This is a working paper pipeline, not a validated live-data trading system.

H001 has an approved protocol and a local research package. The eligibility audit on the frozen announcement and candle files is recorded in `datasets/research/h001_eligibility_audit_20261012_json_metadata/`. Source rows: 18,235. Provisional three-subject candidates after the class, contradiction check, and clock: 251. Those 251 passed rule B and H1. `short_history` removed 27. Eligible events: 224. Purged: 0. Training: 75 events, 34 positive and 41 negative. Validation: 149 events, 70 positive and 79 negative. The training minority class is 34. The approved bar is 50. The sample rule is `INCONCLUSIVE`. Validation's minority class is 70 and meets the heuristic. No model was fit and no profitability result exists.

The 3,690-row coverage predicate, the 251 candidates, and the 224 eligible events are different counts. The event class is not established as complete. 2025Q2–2025Q4 have no included event. The `exchdisstime` clock is a proxy and does not prove the announcement was actionable. The historical raw digest remains unverified.

Status stays `PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED`, `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO.

## Tests

Run on 2026-10-12:

- `.venv/bin/python -m pytest tests/test_phase4.py tests/test_dev3.py tests/test_backtest.py -q` — 31 passed.
- `cd apps/frontend && npm test` — 12 passed.
- Quant `test_ml_demo.py`, `test_ml.py`, and `test_paper.py` — 17 passed. Intelligence source-mode, valuation, fundamentals, agent, and runner tests — 23 passed. A temporary-directory demo check trained once, rejected a corrupt hash, and left the five rule signals in place. No signal was posted to the running API.

The paper tests use in-memory SQLite and fixture candles. They are not a Docker run. The same day, the Compose stack was already up: `GET /health` returned ok, authenticated system status was `PAPER` with `live_enabled` false, quant logged a 245-signal paper pass, and intelligence skipped fixture symbols it cannot price. The frontend was not modified.

## Results

The paper path rejects non-paper modes, shorts, insufficient cash, and notionals above 100,000, and it stores a fill when a later bar exists. The dashboard unit tests cover client helpers only.

H001 did not produce a trading result. OHLCV direction research remains closed: it did not show a tradable edge after the 2 bp gate.

## Limitations

- Dashboard pages and any remaining UI fixes belong to Developer 2. This pass did not change `apps/frontend`.
- Broker credentials are unused. Live trading is not available.
- `volume_imbalance` and Oil & Gas are unavailable.
- Most quant votes do not use the optional 1.1 feature fields.
- H001 cannot be fit under the approved sample rule without a new decision. The requirements were not weakened. The synthetic ML demo is not an H001 result and is not a market-return model. `training_positive_rate` is not the decision rule.
- RSS and CSV behavior is covered by mocked and temporary-file tests. Compose does not enable either mode.
- The quant and intelligence images built for the ML demo and source-mode wiring were not applied to the running containers. The database was not reset.

## Future work

- Run the Compose checklist in [`paper-demo.md`](paper-demo.md) on a clean database before the demonstration.
- Keep H001 unauthorized until a separate decision addresses the training sample. Do not lower the bar of 50 to make it pass.
