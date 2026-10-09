# Research audit (2026-10)

Re-audit on `origin/main` **`b4ab1ce`** (local `main` fast-forwarded). Holdout path not read, listed, or traversed.

**Final decision:** FAIL  
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

Hypothesis H001 **could not be validly evaluated**. This is not a finding that it failed to predict returns.

Core FeatureSet 1.1.0 and a costed historical backtest path **are present**. Remaining block is **data/intelligence**: no frozen 2024–2025 snapshot on this machine, no PIT earnings/events history.

## Versions (keep separate)

| Concept | Value |
|---|---|
| Wire `schema_version` | `"1.0"` |
| Current `feature_version` | `"1.1.0"` |
| Previously requested `feature_version` | `"1.1.0"` (now emitted) |

1.1 verification is **POSSIBLE** (engine emits the requested fields; omit if history is insufficient; do not zero-fill). `unavailable=["volume_imbalance"]`. Oil & Gas remains unavailable. Leakage filter: `bar.end <= as_of`. `relative_strength_nifty` needs `nifty_return` passed into `build_feature_set`.

Emitted 1.1 keys include: `bollinger_pct_b`, `distance_from_mean`, `zscore_20`, `reversion_half_life`, `relative_volume`, `volume_acceleration`, `price_volume_corr`, `roc_10`, `trend_strength_adx`, `relative_strength_nifty` (when NIFTY return is supplied), `volume_confirmation`, `support_level`, `resistance_level`, `trend_slope`, `volatility_percentile`.

## Registered agents

Paper `_AGENTS`: Technical, Momentum, Mean Reversion, Volume, Regime. **MlAgent is not loaded.** Agents consume FeatureSet via `FeatureProvider`. They do not access candles or wall-clock time. Optional 1.1 fields are **present on FeatureSet when the engine can compute them**; agents that still ignore them do **not** synthesize replacements.

### Agent × feature

| Agent | Feature | Source | present in current FeatureSet | requested in 1.1 | recomputed by agent | future leakage |
|---|---|---|---|---|---|---|
| Technical | ema_12, ema_26, sma_10, sma_20, last_close, vwap, rsi_14, macd, macd_signal | engine 1.1.0 | yes | n/a (1.0 keys) | no (comparisons only) | no |
| Technical | support_level, resistance_level, trend_slope | optional, unused in interpret | yes when history suffices | yes | no | no |
| Momentum | return_1, momentum_10, macd | engine 1.1.0 | yes | n/a | no (sign checks) | no |
| Momentum | roc_10, trend_strength_adx, relative_strength_nifty, volume_confirmation | optional, unused in interpret | yes when history / NIFTY return suffices | yes | no | no |
| Mean Reversion | last_close, bollinger_upper, bollinger_lower, bollinger_mid | engine 1.1.0 | yes | n/a | no (close vs bands) | no |
| Mean Reversion | bollinger_pct_b, distance_from_mean, zscore_20, reversion_half_life | optional, unused in interpret | yes when history suffices | yes | no | no |
| Volume | last_volume, volume_mean, return_1 | engine 1.1.0 | yes | n/a | **compares `last_volume` vs `volume_mean`** then `return_1` sign; does **not** consume `relative_volume` | no |
| Volume | relative_volume, volume_acceleration, price_volume_corr | optional, unused | yes when history suffices | yes | **do not add `relative_volume`** | no |
| Volume | volume_imbalance | optional | no (`unavailable`) | stays unavailable | no | no |
| Regime | ema_12, ema_26, sma_10, sma_20 | engine 1.1.0 | yes | n/a | no (trend/range labels) | no |
| Regime | volatility_percentile | optional, used if present | yes when history suffices | yes | no | no |
| Regime | trend_strength_adx | optional, unused | yes when history suffices | yes | no | no |
| Regime | NIFTY50, INDIAVIX extra views | FeatureProvider extras | index FeatureSets via context when provided | yes | no | no |

Paper `_SWING` still sets `regime_index_symbols: ()`.

Volume still does **not** vote on engine `relative_volume`.

## Datasets, snapshots, windows

Required research window: **2024-01-01 through 2025-12-31** (train 2024-01-01–2025-06-30, validation 2025-07-01–2025-12-31).

Local `Test-Path` only (no listing of holdout children): `snapshots/nifty50` yes (~Jun–Oct **2026**); `snapshots 2`, `snapshots 2/nifty50`, `nifty50_5m_20261005`, `nifty50_1d_20261005` **no**. The 2026 snapshot **must not** be substituted.

Holdout path `snapshots/holdout_after_20261005`: **not read, not listed, not traversed.** Existence check only: absent.

`scripts/backtest_july.py` expects `snapshots 2/nifty50` and `nifty50_5m_20261005`. **NOT RUN** here (files absent).

## Backtest vs paper vs Experiment A

Costed historical path exists: `POST /api/v1/backtests` (API defaults `transaction_cost_bps=2`, `slippage_bps=1`), `core_paper.backtest.run_backtest`, `CostSchedule.research`. Paper default schedule is **2 bp, never zero**, next later bar **open**. Paper is **not** the H001 baseline; the baseline is the historical backtester. Baseline **NOT RUN** (no frozen 2024–2025 snapshot on this machine).

Experiment A is **prior context only** (classification, `no_costs: true`).

## Costs

The 2 bp research gate was **not modified**. It **could not be applied** because this checkout has **no frozen 2024–2025 snapshot** to run. Seven cost scenarios are **NOT RUN**. Sharpe is **N/A**. The 2 bp edge is **NOT EVALUABLE**.

## Intelligence: schema vs data

Contract fields `published_at`, `retrieved_at`, and `available_at` do **not** mean a PIT history exists.

Rejected as H001 inputs: RSS (`retrieved_at` is wall-clock), fixture timestamps, and **`period_end` as availability**. `period_end` never substitutes for `available_at`.
