# Experiment A — research closed

Quant-only. Does not change production `MlAgent`, fusion, risk, or execution. Metrics are directional diagnostics, not PnL.

## What we ran

One global sklearn logistic regression per timeframe (1d and 5m not mixed). CURRENT is six absolute OHLCV engine columns. NEW is 14 research-only relative columns from `quant_agents.ml.features` on the **same** eligible rows. Splits are unique candle `end` 60/80 with `future_end` purge. Threshold 0.5. AUC lift is timestamp-bootstrap (400 draws), not row-iid.

Snapshot is ~2 months of current NIFTY50 constituents. Cutoff `2026-09-01T10:00:00+00:00`. MACD warmup leaves **14 unique 1d clocks** eligible; the 1d test is a handful of sessions.

## Results

**1d.** NEW test AUC 0.6567 vs CURRENT 0.5385. Timestamp-bootstrap lift 95% **[-0.014, 0.217] includes 0**. Point estimate is not a confirmed lift.

**5m.** NEW 0.5209 vs CURRENT 0.5035. Lift 95% **[0.006, 0.029]** excludes 0 but the level is still ~0.52. Bars are correlated; row count is not independent sample size.

**h=5 labels (1d only).** Same snapshot, cutoff, NEW matrix, and timestamp protocol. Eligible unique clocks drop 14→10. Purge empties validation; reusing the h=1 cut dates empties validation and test. No bootstrap comparison to h=1 NEW.

**Index context.** Snapshot has 49 constituent symbols and no NIFTY / INDIAVIX candle series. We did not invent index `return_1`.

## Decision

This 2-month sample cannot support a trading model. Stop expanding data. Do not collect ≥3 years of bars, do not relabel 5m, do not switch to LightGBM/XGBoost or per-stock models, and do not wire production `MlAgent`.

## Feature Engine still owes

Listed in [`docs/feature-requests.md`](../../../docs/feature-requests.md):

- Index FeatureSets for NIFTY50 and INDIAVIX (RISK_ON / RISK_OFF).
- Research ratios in `ml/features.py` are **not** FeatureSet fields until the engine emits them. Production agents must not compute them.
