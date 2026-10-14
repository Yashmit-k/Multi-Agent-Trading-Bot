# Hypothesis H001

**Final decision:** BLOCKED_PRECONDITION
**Research status:** BLOCKED_PRECONDITION  
**HOLDOUT_READY:** NO  

H001 has not been run. `BLOCKED_PRECONDITION` is the same research-data blocker as `DATA NOT READY`. `exchdisstime`, parsed and tagged `Asia/Kolkata`, is the accepted proxy for `available_at` in this preliminary experiment. That proxy does not prove when an announcement first became public or when a strategy could act. The limitation stays explicit. This is not a failed model, not evidence of poor predictive performance, and not a pass. There is no validation result and no predictive score. The method is **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**. It is not implemented.

Do not modify this document after seeing validation results. There are no validation results.

## Frozen

| Field | Value |
|---|---|
| Hypothesis ID | H001 |
| Information source | Earnings/events (priority 1; one source only) |
| Universe | NIFTY 50 constituents |
| Model | `sklearn.linear_model.LogisticRegression` (one fixed configuration; no sweep) |
| Cost gate | Positive validation net edge after 2 bp on the entry fill notional and 2 bp on the exit fill notional: `net = (P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`. Unchanged prices are about 4 bp round-trip. The cost code was not modified, the gate has not been applied, and this wording has not been checked against the implementation. The frozen candles `nifty50_5m_20261005` and `nifty50_1d_20261005` are `MARKET_DATA_READY` at `snapshots 2/nifty50`. The gate stays unevaluated. |
| Timestamp rule | `period_end` never substitutes for `available_at`. Reject RSS wall-clock `retrieved_at` and fixture clocks. Only records with a trustworthy availability time `<=` prediction timestamp may be used. |
| Benchmarks (when evaluable) | Always-flat; always-long/passive where applicable; existing quant-agent baseline; H001 strategy |

## Economic rationale

Earnings and event surprises should change the distribution of near-term returns when the market has not fully incorporated the newly public information. That claim requires reconstructable publication time, not period-end dates.

## Specified later, not implemented

The labels below described this file before the 2026-10-12 approval. They are not the live method. Target, features, and horizon are specified in `h001-protocol-approval.md`. That specification is not built in code. Eligible observations are still unknown. Do not invent values to fill a gap.

| Field | Status |
|---|---|
| Target | Specified as L-sign in the approval table. Not implemented. |
| Features | Four approved predictors in the approval table. Not implemented. |
| Horizon | Specified as H1 in the approval table. Not implemented. |

## Why evaluation is blocked

- The proxy clock is not proof of public access or actionability. Eligible event counts and the smaller label class are unknown. The three-subject class is not shown to be complete. 2025Q2–2025Q4 have no include-list row.
- Required candles: 2024-01-01 through 2025-12-31. Frozen IDs `nifty50_5m_20261005` / `nifty50_1d_20261005` are at `snapshots 2/nifty50` after a move/rename (**MARKET_DATA_READY**). Do not use the short 2026 `snapshots/nifty50` tape for hypothesis selection.
- FeatureSet 1.1.0 and the costed backtest path are present. They are not the H001 implementation. The historical raw digest stays unverified.

No LogisticRegression fit. No MlAgent. No boosting. No robustness sweeps.
