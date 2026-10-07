# Alpha research report

**Final decision:** FAIL  
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

H001 **could not be validly evaluated**. This is not a finding that it failed to predict returns.

See [`research-audit-2026-10.md`](research-audit-2026-10.md) and [`hypothesis-H001.md`](hypothesis-H001.md).

## 1. System verification

- Wire `schema_version` = `"1.0"`. Current `feature_version` = `"1.0.0"`. Requested `feature_version` = `"1.1.0"`.
- FeatureSet 1.1 verification: **NOT POSSIBLE**.
- Agents: five rule agents consume 1.0 fields. Optional 1.1 fields are absent, not synthesized. MlAgent not loaded. Volume compares `last_volume` vs `volume_mean`; `relative_volume` was not added.
- Leakage: engine `bar.end <= as_of`; agents do not read candles. Holdout unused.
- Baseline status: **NOT RUN**. Paper is not the baseline (`/api/v1/backtests` returns 501; paper fills current close, zero fees, zero slippage). Experiment A is prior context only (`no_costs: true`).

## 2. Baseline results

**NOT RUN.** Do not report zeros.

Samples, signals, proposals, orders, fills, gross P&L, fees, slippage, net P&L, return, volatility, downside volatility, Sharpe (**N/A**), Sortino, Calmar, drawdown, turnover, exposures, trade stats, long/short/flat fractions, concentration: **NOT RUN**.

Cost scenarios (all **NOT RUN**): 0/0, 1/0, 2/0, 3/0, 5/0, 0/1, 2/1 (cost bp / slippage bp).

2 bp validation net edge: **NOT EVALUABLE**. The gate was not modified. It could not be applied because this checkout has no costed historical execution path.

Required window 2024-01-01 through 2025-12-31. Available local snapshot is 2026 (~Jun–Oct) and was **not** substituted.

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

**FAIL**  
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

Preconditions for a valid evaluation are missing. Stop. Do not tune.

## 10. Safety confirmation

| Item | Yes/No |
|---|---|
| Holdout path not read | Yes |
| Holdout path not listed | Yes |
| Holdout path not traversed | Yes |
| Frozen snapshots not modified (`snapshots 2/nifty50` absent; `snapshots/nifty50` not mutated) | Yes |
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

## 11. Remaining work

**P0**

- Feature Engine owner: emit FeatureSet **1.1.0** (omit insufficient history; do not zero-fill).
- Core/backtest owner: next-bar historical execution, costs, slippage, 2 bp **capability**.
- Data owner: frozen **non-holdout** 2024–2025 snapshots (`nifty50_*_20261005` / `snapshots 2/nifty50` as specified). Do not open holdout.
- Intelligence owner: PIT earnings/events with trustworthy `available_at` (not `period_end`, not RSS wall-clock, not fixtures).

**P1** Re-run this audit on the completed tree (versions, agents, leakage, backtest, snapshots) without opening holdout.

**P2** Execute H001: freeze target/features/horizon, versioned dataset, LogisticRegression, costed simulation, 2 bp gate, drift and concentration. Robustness only if PASS.

**P3** Optional UI later (experiment, hypothesis, periods, model, feature version, net edge, costs, trades, PASS/FAIL). Not required while BLOCKED_PRECONDITION.
