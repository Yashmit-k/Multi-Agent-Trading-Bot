# Alpha research report

**Final decision:** BLOCKED_PRECONDITION
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

H001 has not been run. `BLOCKED_PRECONDITION` is the same research-data blocker as `DATA NOT READY`: historical earnings and events have no trustworthy `available_at`. This is not a failed model, not evidence of poor predictive performance, and not a pass. There is no validation result and no predictive score.

Re-audit tree: `origin/main` **`b4ab1ce`**. See [`research-audit-2026-10.md`](research-audit-2026-10.md) and [`hypothesis-H001.md`](hypothesis-H001.md).

## 1. System verification

- Wire `schema_version` = `"1.0"`. Current `feature_version` = `"1.1.0"`.
- FeatureSet 1.1 verification: **POSSIBLE** (engine emits requested fields; `volume_imbalance` unavailable).
- Agents: five rule agents. MlAgent not loaded. Technical / Momentum / Mean Reversion still vote on 1.0 keys; 1.1 optionals are unused except Regime `volatility_percentile` when present. Volume compares `last_volume` vs `volume_mean` and does **not** consume engine `relative_volume`.
- Leakage: engine `bar.end <= as_of`; agents do not read candles. Holdout unused.
- Baseline status: **NOT RUN**. Costed historical backtest exists. Frozen 2024–2025 snapshots are **MARKET_DATA_READY** at `snapshots 2/nifty50`. H001 still blocked on PIT events. Experiment A is prior context only.

## 2. Baseline results

**NOT RUN.** Do not report zeros.

Samples, signals, proposals, orders, fills, gross P&L, fees, slippage, net P&L, return, volatility, downside volatility, Sharpe (**N/A**), Sortino, Calmar, drawdown, turnover, exposures, trade stats, long/short/flat fractions, concentration: **NOT RUN**.

Cost scenarios (all **NOT RUN**): 0/0, 1/0, 2/0, 3/0, 5/0, 0/1, 2/1 (cost bp / slippage bp).

2 bp validation net edge: **NOT EVALUABLE**. The gate was not modified. It has not been applied because point-in-time earnings and events are unavailable. H001 has not been run, so the gate is neither passed nor failed as a model result.

Required window 2024-01-01 through 2025-12-31. Frozen candles `nifty50_5m_20261005` and `nifty50_1d_20261005` are `MARKET_DATA_READY` at `snapshots 2/nifty50`, per [`data-readiness-2026-10.md`](data-readiness-2026-10.md). The short 2026 tape at `snapshots/nifty50` was **not** substituted.

## 3. New hypothesis

H001: earnings/events; NIFTY 50; LogisticRegression; 2 bp gate; `period_end` never substitutes for `available_at`. Target, features, horizon: **NOT FROZEN**.

## 4. Dataset

**NOT RUN.** No versioned H001 dataset. Contract timestamp fields are not a PIT store. RSS, fixtures, and period_end rejected.

## 5. Model results

**NOT RUN.** No LogisticRegression. Accuracy, AUC, precision, recall, class balance: **NOT RUN**.

## 6. Trading results

**NOT RUN.** Gross/net P&L, costs, slippage, net edge, Sharpe (**N/A**), Sortino, drawdown, turnover, trades, win rate, profit factor: **NOT RUN**. 2 bp edge: **NOT EVALUABLE**.

## 7. Benchmark comparison

Always-flat, always-long/passive, existing agents, H001: **NOT RUN**.

## 8. Robustness

**NOT RUN.** Robustness is allowed only after a 2 bp PASS. Concentration: **NOT RUN**.

## 9. Final decision

**BLOCKED_PRECONDITION** (`DATA NOT READY`)
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

H001 has not been run. Point-in-time earnings and events with a trustworthy `available_at` are missing. The 2024–2025 market candles exist and are `MARKET_DATA_READY`. This is not a pass and not a predictive failure. Stop. Do not tune. Do not use 2026 bars to select H001.

## 10. Safety confirmation

| Item | Yes/No |
|---|---|
| Holdout path not read | Yes |
| Holdout path not listed | Yes |
| Holdout path not traversed | Yes |
| Frozen snapshots not modified (`snapshots 2/nifty50` present and not rewritten; `snapshots/nifty50` not mutated) | Yes |
| No live orders | Yes |
| No KiteTicker | Yes |
| LIVE not enabled | Yes |
| SHADOW not enabled | Yes |
| No boosting (LightGBM/XGBoost/CatBoost) | Yes |
| No neural model | Yes |
| MlAgent not loaded | Yes |
| 2 bp gate not modified | Yes |
| 2026 snapshot not used for hypothesis selection | Yes |
| No synthetic history / interpolated candles | Yes |
| LogisticRegression not fit for H001 | Yes |

## 11. Remaining work

**P0**

- Feature Engine owner: FeatureSet **1.1.0** is on `b4ab1ce` — not blocking.
- Core/backtest owner: next-bar execution, costs, slippage, 2 bp **capability** are on `b4ab1ce` — not blocking.
- Data owner: frozen 2024–2025 snapshots are at `snapshots 2/nifty50` after move/rename (**MARKET_DATA_READY**). Do not open holdout.
- Intelligence owner: PIT earnings/events with trustworthy `available_at` (not `period_end`, not RSS wall-clock, not fixtures).

**P1** Re-run the audit after the point-in-time event file exists, without opening holdout. The candle snapshots are already `MARKET_DATA_READY`.

**P2** Execute H001: freeze target/features/horizon, versioned dataset, LogisticRegression, costed simulation, 2 bp gate, drift and concentration. Robustness only if PASS.

**P3** Optional UI later. Not required while BLOCKED_PRECONDITION.
