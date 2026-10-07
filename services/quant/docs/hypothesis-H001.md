# Hypothesis H001

**Final decision:** FAIL  
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

H001 **could not be validly evaluated**. This is not a finding that it failed to predict returns.

Do not modify this document after seeing validation results. There are no validation results.

## Frozen

| Field | Value |
|---|---|
| Hypothesis ID | H001 |
| Information source | Earnings/events (priority 1; one source only) |
| Universe | NIFTY 50 constituents |
| Model | `sklearn.linear_model.LogisticRegression` (one fixed configuration; no sweep) |
| Cost gate | Positive validation net edge after **2 bp**. The gate was not modified. It could not be applied because this checkout has no costed historical execution path. |
| Timestamp rule | `period_end` never substitutes for `available_at`. Reject RSS wall-clock `retrieved_at` and fixture clocks. Only records with a trustworthy availability time `<=` prediction timestamp may be used. |
| Benchmarks (when evaluable) | Always-flat; always-long/passive where applicable; existing quant-agent baseline; H001 strategy |

## Economic rationale

Earnings and event surprises should change the distribution of near-term returns when the market has not fully incorporated the newly public information. That claim requires reconstructable publication time, not period-end dates.

## NOT FROZEN

Required PIT historical earnings/events are **unavailable**. Do not invent values to fill the template.

| Field | Status |
|---|---|
| Target | **NOT FROZEN** |
| Features | **NOT FROZEN** |
| Horizon | **NOT FROZEN** |

## Why evaluation is blocked

- No PIT earnings/events history with trustworthy `available_at`.
- Required candles: 2024-01-01 through 2025-12-31. Local 2026 snapshot (~Jun–Oct) must not be used for hypothesis selection.
- No costed historical execution path (`/api/v1/backtests` returns 501; paper current-close zero-cost fills are not the baseline).
- FeatureSet 1.1.0 verification is **NOT POSSIBLE** (current `feature_version` is `"1.0.0"`; wire `schema_version` remains `"1.0"`).

No LogisticRegression fit. No MlAgent. No boosting. No robustness sweeps.
