# ML cross-sectional ranker: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-15, before any out-of-sample result was computed.**

This study asks one question. Can a model trained only on past daily OHLCV pick 6 NIFTY 50 stocks that, held for 5 sessions, beat an equal-weight basket after Zerodha delivery costs?

Earlier OHLCV direction research in this repo found no tradable edge. This study does not overturn that finding unless it passes every gate below on data it has never touched.

## Data

- File: `snapshots 2/nifty50/1D/candles.jsonl` (`nifty50_1d_20261005`). Only official daily bars ending 15:30 IST are used. `TATAMOTORS` has no bars and is excluded.
- **Development period:** decision sessions 2024-04-01 to 2025-12-31. The earlier bars are feature warm-up.
- **Out-of-sample period:** decision sessions 2026-01-01 to the last session whose exit bar exists in the file (2026-10-05). No study in this repo has scored this period.
- `snapshots/holdout_after_20261005` is **not opened**. H001 is not part of this study.

## Decision, execution, label

- **Decision:** after the close of session *t*, using only bars that end on or before *t*.
- **Entry:** the open of *t+1*. **Exit:** the open of *t+6*, which is a 5-session hold. This matches the paper engine's morning entry window.
- **Label:** `open[t+6] / open[t+1] − 1`, minus the cross-sectional mean of that same quantity on day *t*. That is excess over equal weight. Labels are never features.

## Features (as of close *t*)

- **Price features:**
  - returns over 1, 5, 10, 20 and 60 sessions;
  - 20-session volatility of daily returns;
  - 14-session average true range ÷ close;
  - distance of close from its 20- and 50-session means;
  - 14-session RSI;
  - 5/20 volume ratio;
  - overnight gap (open[t] / close[t−1] − 1).
- **Cross-sectional ranks:** each price feature above is also converted to its percentile rank across that day's universe.
- **Market context:** the universe mean of the 5- and 20-session returns, and the cross-sectional dispersion of the 5-session return.

## Models (two candidates, fixed hyperparameters, no tuning)

- **A:** `HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0, random_state=0)`.
- **B:** `Ridge(alpha=10.0)` on standardized features.

## Walk-forward training

- Training is expanding-window, refit every 21 decision sessions.
- Each fit uses only rows whose exit bar is on or before the last decision session before the refit, minus a 5-session embargo.
- Training starts once at least 120 decision sessions of labelled history exist.

## Portfolio rule

- Rebalance every 5 sessions, so windows don't overlap.
- Buy the 6 highest-predicted stocks at ₹20,000 each. This matches the paper caps: ₹20,000 per order and 6 entries per day.
- **Costs:** `research/delivery_costs.py`, delivery buy and delivery sell (STT, stamp, exchange, SEBI, GST, DP), plus 5 bp of adverse slippage on each fill.

## Baselines (same windows, same costs)

1. Equal weight across all eligible stocks.
2. The 6 highest 20-session returns (plain momentum).
3. 6 random stocks, seed 0. Reported as the mean of 200 seeds.

## Selection (development only)

Model A or B is chosen by the higher mean net excess per window over baseline 1 in the development period. Ties go to B, the simpler model. The out-of-sample period is scored **once**, for the chosen model only.

## Acceptance gate (out-of-sample)

All of these must hold:

1. Mean net excess per window over equal weight is greater than 0, **and** its 90% block-bootstrap lower bound (block length 4 windows, 5,000 resamples, seed 0) is greater than 0.
2. Mean net return beats plain momentum (baseline 2).
3. Mean net return beats the random-pick mean (baseline 3).
4. The result does not depend on one stock: removing the single most profitable symbol keeps the mean net excess above 0.

If any gate fails, the result is recorded as a failure. `MlAgent` stays unloaded, and no paper order uses this model. If all pass, wiring the model into paper trading still needs separate approval as an experimental paper-only variant.
