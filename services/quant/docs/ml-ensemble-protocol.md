# ML ensemble study: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-15, before any result of this study was computed.**

This study asks whether any combination of model, holding period, and market-exposure rule makes money after Zerodha delivery costs, in all market conditions, on NIFTY 50 stocks. The variant grid below is fixed in advance and every variant is reported. The multiple-testing correction is part of the verdict, because picking the best of many backtests overstates its quality.

Data already seen: the 2026 period was scored once by `ml-rank-protocol.md`. In this study 2026 is part of the walk-forward record, not a fresh holdout. The verdict therefore rests on the multiple-testing p-value and on a forward paper test, not on 2026 alone. `snapshots/holdout_after_20261005` is not opened.

## Data

- **Stocks:** `snapshots 2/nifty50/1D/candles.jsonl` (49 symbols; `TATAMOTORS` excluded).
- **Context:** `snapshots/context_through_20261005/1D/candles.jsonl` — NIFTY 50, INDIA VIX, and 10 NIFTY sector indices.
- Official 15:30 IST daily bars only, 2024-01-01 to 2026-10-05.

## Execution (same as the paper engine)

- Decide after the close of *t*; buy at the open of *t+1*; sell at the open of *t+1+H*.
- Buy the top 6 picks at ₹20,000 each.
- **Costs:** Zerodha delivery charges (`research/delivery_costs.py`) plus 5 bp slippage per fill.
- Windows do not overlap: rebalance every H sessions. A window held in cash returns 0 and costs nothing.

## Features (known at the close of *t*)

- **Stock:**
  - returns over 1, 5, 10, 20 and 60 sessions;
  - 20-session volatility; 14-session ATR ÷ close; RSI(14);
  - distance from the 20- and 50-session means;
  - 5/20 volume ratio and 20-session volume z-score;
  - overnight gap;
  - distance from the 250-session high (NaN until 250 bars exist);
  - 60-session beta to NIFTY 50;
  - 20-session return relative to NIFTY 50 and relative to the stock's sector index;
  - the sector index's 20-session return.

  Every stock feature also gets a same-day cross-sectional percentile rank.
- **Market:**
  - NIFTY 50 returns over 5, 20 and 60 sessions;
  - NIFTY 50 close ÷ 50-session mean − 1;
  - INDIA VIX level, its 5-session change, and its percentile within the past 120 sessions;
  - breadth: the share of stocks above their own 50-session mean;
  - cross-sectional dispersion of the 5-session return.
- **Sector map:** fixed in code (`SECTOR_OF`) before any run. Stocks without a matching NIFTY sector index get NaN sector features.

## Grid (45 variants: 3 × 5 × 3)

- **Holding period H:** 5, 10, 20 sessions.
- **Selector** (fixed hyperparameters, no tuning). Each is trained on the excess-over-equal-weight label for that H:
  - `ridge`: Ridge(alpha=10), median-imputed, standardized;
  - `hgb`: HistGradientBoosting(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2=1.0);
  - `rf`: RandomForest(n_estimators=150, max_depth=6, min_samples_leaf=100, max_features=0.5), median-imputed;
  - `et`: ExtraTrees(same as rf);
  - `ensemble`: the mean of the four models' same-day percentile ranks.
- **Exposure rule:**
  - `always`: always invested;
  - `trend`: invest only when NIFTY 50 close > its 50-session mean at *t*;
  - `timing`: a walk-forward logistic regression (C=0.5) on the market features, predicting whether the next-H equal-weight net return beats 0. Invest only when the predicted probability > 0.5.

## Walk-forward

- Refit every 21 decision sessions.
- Training rows have their exit at or before *t − H*. The embargo equals H.
- First fit once 120 labelled decision sessions exist.
- The selector and the timing model refit on the same schedule.

## Reporting

For each variant:
- mean net return per window and annualized (× 250/H);
- annualized Sharpe of window returns;
- hit rate, max drawdown of the compounded window curve, and exposure (the fraction of windows invested);
- excess over equal weight in the same windows (equal weight is always invested and pays costs).

Market regimes are labelled per window from the decision day:
- trend up or down: NIFTY 50 above or below its 50-session mean;
- volatility high or low: VIX above or below its own 120-session median.

That gives 4 regimes. Each variant reports its mean net return per regime.

## Multiple testing and verdict

- Each variant's window returns are spread evenly over their sessions to form daily series.
- **White's Reality Check:** stationary block bootstrap, mean block 10 sessions, 2,000 resamples, seed 0, on mean daily net return. Its p-value tests whether the best variant's mean net return is above 0. The same test is run on excess over equal weight.

**A variant is a candidate only if all of these hold:**
1. the Reality Check p-value is below 0.10 for net return above 0;
2. its own net return is positive;
3. its regime means are ≥ 0 in at least 3 of the 4 regimes;
4. its excess over equal weight is positive.

A candidate is still **not traded**. It goes to a forward paper test: its picks are recorded daily, without orders, and scored on data that does not yet exist. If no variant qualifies, the verdict is "no robust edge", and every variant is still reported.
