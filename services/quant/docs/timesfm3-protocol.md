# TimesFM-3 protocol

Status: **PROTOCOL WRITTEN**. This is not H001. H001 stays a logistic-regression study and is not authorized to run. This study does not vote, does not submit `AgentName.ML` signals, and is not imported by `core-worker` or Core API.

The weights are `google/timesfm-3.0-pytorch`, used zero-shot. Self-hosted TimesFM 3.0 weights are non-commercial and non-production. Fine-tuning is not part of this protocol.

## Data

- Candles: `snapshots 2/nifty50/1D/candles.jsonl` (`nifty50_1d_20261005`) only.
- `snapshots/holdout_after_20261005` is never opened, listed, or used.
- `snapshots/nifty50` (the short 2026 tape) is not a substitute.
- TATAMOTORS stays out.
- A session is a daily bar whose end is exactly 15:30 IST. Other ends do not qualify.

## Question

At a session's 15:30 IST close `P0`, does the model's median forecast of the next session's close `P1` have the same sign as `(P1 - P0) / P0`, and is the traded net return after 2 bp positive against the two baselines below?

The forecast horizon is one next session. A 64-day path is not scored.

## Context and label

- Context for a decision is that symbol's own qualifying closes whose `end` is at or before the decision bar's `end`.
- The label close is the next qualifying session for the same symbol. It is not in the context.
- Fewer than 32 context closes is `short_history` and is not scored. 32 is the published context patch length.
- The first scored year is 2024. Both the decision session and the next session must fall in 2024. A 2024 decision whose next close is in 2025 is not scored. 2025 is not a score window until a 2024 report exists.
- No announcement features. This is not an event study.

## Score

Let `F` be the median one-step forecast.

- Realized sign is the sign of `(P1 - P0) / P0`. A zero return has sign 0.
- Predicted sign is the sign of `F - P0`.
- A hit requires both signs to be nonzero and equal. The hit rate divides hits by scored rows whose realized return is nonzero.
- A long trade is taken only when `F > P0`. Otherwise the row contributes 0. There is no short.
- Traded net is `(P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`. Each 2 bp fee is applied once.
- Price-level absolute error `|F - P1|` is recorded. It is not the pass rule.

## Baselines, fixed before the run

- Always-flat: no trades. Mean net is 0.
- Last close: `F = P0`, so the predicted sign is 0, no trade is taken, and mean net is 0. Its price error is `|P0 - P1|`.

## Stop rule

Write the 2024 comparison and stop. Do not fine-tune. Do not open 2025 or the holdout. Do not change the paper cycle.
