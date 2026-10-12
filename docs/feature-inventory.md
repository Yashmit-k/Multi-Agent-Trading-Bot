# Feature inventory

Checked against the code, the tests run on 2026-10-12, and the Compose stack that was already running that day. Dashboard pages are Developer 2's remaining work and were not edited here.

| Area | State | Evidence |
|---|---|---|
| Shared contracts, schema 1.0 | Implemented | `packages/contracts` |
| Paper cycle: signal, fusion, decision, risk, fill | Implemented and tested here | `tests/test_phase4.py` |
| Risk rejects non-PAPER, insufficient cash, notional cap, and a short | Implemented and tested here | `tests/test_phase4.py` |
| Default 2 bp cost, explicit 0 bp, kill switch | Implemented and tested here | `tests/test_dev3.py` |
| Backtest uses the same fill path and refuses the holdout | Implemented and tested here | `tests/test_backtest.py` |
| Dashboard helpers for API, mode, and stream | Implemented and tested here | `apps/frontend` vitest, 12 tests |
| Dashboard pages for signals, orders, positions, risk, backtests | Implemented in the UI | Developer 2 owns the remaining dashboard fixes. This pass did not edit `apps/frontend`. |
| Docker Compose stack | Running on 2026-10-12 on the earlier images | Postgres healthy, `core-api` healthy, Redis, worker, quant, intelligence, and frontend containers up. Quant and intelligence images were rebuilt later the same day and were not started. Database was not reset. |
| Quant rule agents | Paper pass completed | One pass logged 245 signals for 50 symbols. No connection-refused loop after the API health wait. |
| Intelligence service | Fixture mode, running | Valuation quotes exist for `RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, and `ICICIBANK` only. The NIFTY 50 list is unchanged. Other symbols are skipped with `fixture_symbol_skipped` and get no invented price. News, fundamental, and earnings still submit. |
| Broker login routes | Implemented as status only | `live_enabled` stays false. No order is sent |
| MlAgent | Optional, off in Compose | Five rule agents always run. `QUANT_ML_DEMO` is paper-only and writes a separate synthetic artifact. `QUANT_ARTIFACT_DIR` alone loads an existing artifact and does not train. The two settings cannot both be set. The signal uses `score_probability`. `training_positive_rate` is manifest metadata, not a cutoff. It is not a market-trained model and not an H001 result. |
| H001 event model | Package and synthetic tests exist. Eligibility is `INCONCLUSIVE` | No fit, no gate, no profitability result |
| Live trading | Disabled | Do not demonstrate it |

OHLCV direction research is closed. It did not show a tradable edge after the 2 bp gate. That conclusion is unchanged.

Compose sets `INTELLIGENCE_DATA_SOURCE=fixtures`. In that mode the serve loop does not call `RssPuller` or the CSV loader. `rss` pulls configured feed URLs into the news store before the news agent runs. `csv-live` loads `INTELLIGENCE_FUNDAMENTALS_CSV` into the fundamentals store before the fundamentals agent runs. A bad CSV row is skipped. A repeated `source_id` is not inserted again. BACKTEST still rejects `csv-live`. A stored signal is not itself an order or a fill.
