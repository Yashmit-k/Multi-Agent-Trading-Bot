# Research audit (2026-10)

Read-only. No Feature Engine changes, no backtester, no downloads, no synthetic history.

**Final decision:** FAIL  
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

Hypothesis H001 **could not be validly evaluated**. This is not a finding that it failed to predict returns.

Branch check (names and `git ls-tree` / `Test-Path` only; holdout path not read, listed, or traversed): `origin/main` = `9e417ad`, `origin/developer-2` = `2834310`, `origin/developer-3` = `3506ca5`. None of those remotes emit FeatureSet 1.1.0 or a costed historical backtester.

## Versions (keep separate)

| Concept | Value |
|---|---|
| Wire `schema_version` | `"1.0"` |
| Current `feature_version` | `"1.0.0"` |
| Requested `feature_version` | `"1.1.0"` |

1.1 verification is **NOT POSSIBLE**. That is not a failed validation of 1.1 fields.

Current engine keys (omit if history is insufficient; do not zero-fill): `last_close`, `period_high`, `period_low`, `last_volume`, `volume_mean`, `sma_10`, `sma_20`, `ema_12`, `ema_26`, `macd`, `macd_signal`, `rsi_14`, `atr_14`, `vwap`, `bollinger_mid`, `bollinger_upper`, `bollinger_lower`, `return_1`, `volatility`, `momentum_10`. Leakage filter: `bar.end <= as_of`.

Requested 1.1 fields (not emitted): `bollinger_pct_b`, `distance_from_mean`, `zscore_20`, `reversion_half_life`, `relative_volume`, `volume_acceleration`, `price_volume_corr`, `roc_10`, `trend_strength_adx`, `relative_strength_nifty`, `volume_confirmation`, `support_level`, `resistance_level`, `trend_slope`, `volatility_percentile`, plus NIFTY50 / INDIAVIX FeatureSets. `volume_imbalance` remains unavailable. Oil & Gas remains unavailable.

## Registered agents

Paper `_AGENTS`: Technical, Momentum, Mean Reversion, Volume, Regime. **MlAgent is not loaded.** Agents consume FeatureSet via `FeatureProvider`. They do not access candles or wall-clock time. Optional 1.1 names are **absent, not synthesized**.

### Agent × feature

| Agent | Feature | Source | present in current FeatureSet | requested in 1.1 | recomputed by agent | future leakage |
|---|---|---|---|---|---|---|
| Technical | ema_12, ema_26, sma_10, sma_20, last_close, vwap, rsi_14, macd, macd_signal | engine 1.0.0 | yes | no | no (comparisons only) | no |
| Technical | support_level, resistance_level, trend_slope | optional, unused in interpret | no | yes | no | no |
| Momentum | return_1, momentum_10, macd | engine 1.0.0 | yes | no | no (sign checks) | no |
| Momentum | roc_10, trend_strength_adx, relative_strength_nifty, volume_confirmation | optional, unused in interpret | no | yes | no | no |
| Mean Reversion | last_close, bollinger_upper, bollinger_lower, bollinger_mid | engine 1.0.0 | yes | no | no (close vs bands) | no |
| Mean Reversion | bollinger_pct_b, distance_from_mean, zscore_20, reversion_half_life | optional, unused in interpret | no | yes | no | no |
| Volume | last_volume, volume_mean, return_1 | engine 1.0.0 | yes | no | no FeatureSet field; **compares `last_volume` vs `volume_mean`** then `return_1` sign | no |
| Volume | relative_volume, volume_acceleration, volume_imbalance, price_volume_corr | optional, unused | no (`volume_imbalance` stays unavailable) | relative_volume, volume_acceleration, price_volume_corr yes | **do not add `relative_volume`** | no |
| Regime | ema_12, ema_26, sma_10, sma_20 | engine 1.0.0 | yes | no | no (trend/range labels) | no |
| Regime | volatility_percentile, trend_strength_adx | optional | no | yes | no (ADX unused; percentile omitted if missing) | no |
| Regime | NIFTY50, INDIAVIX extra views | FeatureProvider extras | no engine FeatureSets | yes | no | no |

Paper sets `regime_index_symbols: ()`, so Regime does not fetch index views on that path.

Volume does **not** emit or consume a `relative_volume` FeatureSet field.

## Datasets, snapshots, windows

Required research window: **2024-01-01 through 2025-12-31** (train 2024-01-01–2025-06-30, validation 2025-07-01–2025-12-31).

Available locally: gitignored `snapshots/nifty50` (about **Jun–Oct 2026**). `snapshots 2/nifty50`, `nifty50_5m_20261005`, `nifty50_1d_20261005` are absent. The 2026 snapshot **must not** be substituted; the brief bars 2026 data for hypothesis selection.

Holdout path `snapshots/holdout_after_20261005`: **not read, not listed, not traversed.** Existence check only: absent.

## Backtest vs paper vs Experiment A

The required baseline is the realistic historical backtester. **`POST /api/v1/backtests` returns 501.** Paper fills use the **current close** with **zero fees** and **zero slippage**. Paper is **not** the baseline.

Experiment A is **prior context only**: classification metrics, `no_costs: true`. Not this PnL baseline.

## Costs

The 2 bp research gate was **not modified**. It **could not be applied** because this checkout has **no costed historical execution path**. Seven cost scenarios are **NOT RUN**.

## Intelligence: schema vs data

Contract fields `published_at`, `retrieved_at`, and `available_at` describe timestamps **if a record exists**. They do **not** mean a point-in-time history exists.

Rejected as H001 inputs: RSS (`retrieved_at` is wall-clock), fixture timestamps, and **`period_end` as availability**. `period_end` never substitutes for `available_at`.
