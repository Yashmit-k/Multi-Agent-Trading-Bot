# Combined-hypothesis model: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-15, before any result of this study was computed.**

The request was for one model that combines every available hypothesis and has a robust edge. This study builds exactly one model per target and judges it with corrections for everything already tried in this repo.

## Known limits, stated before running

- **No historical news.** The live RSS store starts on 2026-10-14. The NSE announcement dataset belongs to the protected H001 study and needs separate authorization, so it is **not used**.
- **Prior knowledge.** Studies 1 and 2 (`ml-rank-*`, `ml-ensemble-*`) already used this data. Choosing a 10-session hold and a linear model is informed by them. That snooping is disclosed and penalized: the trial count below includes their 46 variants.
- **Power.** About 44 non-overlapping 10-session windows exist after warm-up. Proving an edge at 95% confidence after the trial correction needs an annualized Sharpe of about 2. A result below that is reported as inconclusive, not as an edge.
- `snapshots/holdout_after_20261005` is **not opened**.

## Data

- **Daily bars:** `snapshots 2/nifty50/1D/candles.jsonl`.
- **5-minute bars:** `snapshots 2/nifty50/5m/candles.jsonl`.
- **Context:** `snapshots/context_through_20261005/1D/candles.jsonl` (NIFTY 50, INDIA VIX, sector indices).
- 49 symbols.

## Features (all known at the close of *t*)

All hypothesis families go into one model:

1. **Trend / momentum:** returns over 5, 10, 20 and 60 sessions; distance from the 20- and 50-session means; distance from the 250-session high.
2. **Short-term reversal:** 1-session return; RSI(14); 5-session return relative to the stock's sector index.
3. **Risk:** 20-session volatility; ATR(14) ÷ close; 60-session beta to NIFTY 50.
4. **Volume / liquidity:** 5/20 volume ratio; 20-session volume z-score.
5. **Intraday microstructure,** from that day's 5-minute bars:
   - close location in the day's range;
   - first-hour return (09:15–10:15 IST) and last-hour return (14:30–15:30 IST);
   - open-to-close return and overnight gap;
   - intraday realized volatility (root sum of squared 5-minute log returns);
   - close vs the day's volume-weighted average price;
   - last-hour share of the day's volume.
6. **Sector:** sector index 20-session return; stock 20-session return relative to its sector.
7. **Market regime:**
   - NIFTY 50 returns over 5 and 20 sessions;
   - NIFTY 50 vs its 50-session mean;
   - INDIA VIX level, its 5-session change, and its 120-session percentile;
   - breadth;
   - dispersion.
8. **Calendar:** day of week; sessions to month end.

Each stock-level feature is replaced by its same-day cross-sectional percentile rank. That makes the model scale-free across stocks. Market and calendar features enter raw.

## Model (one per target, fixed in advance)

`LogisticRegression(C=0.1, max_iter=1000)` after median imputation and standardization.

- Walk-forward, refit every 21 sessions.
- Training rows have their outcome known at least 10 sessions before the fit (embargo = 10).
- The first fit needs 120 labelled sessions.

## Target A: return direction

- **Label:** 1 if the stock's return from the open of *t+1* to the open of *t+11* beats the cross-sectional median, else 0. The base rate is 50% by construction.
- **Reported:** out-of-sample accuracy, area under the ROC curve, and accuracy of the top-6 picks.

**Trading test:**
- Every 10 sessions, buy the 6 stocks with the highest predicted probability, ₹20,000 each.
- Zerodha delivery costs plus 5 bp slippage per fill.
- Two exposure rules are reported: always invested, and the NIFTY 50-day trend filter.
- The trial count is therefore 46 + 2 = **48**.

**Edge test — Deflated Sharpe Ratio** (Bailey & López de Prado, 2014):
- The variance of trial Sharpes comes from the 45 variants of study 2.
- Per-window Sharpe; N = 48 trials; skew and kurtosis corrections.

**Candidate only if** DSR > 0.95, net return > 0, and regime means ≥ 0 in at least 3 of 4 regimes.

## Target B: risk (volatility)

- **Label:** 1 if the stock's realized volatility over sessions *t+1..t+10* is above that day's cross-sectional median.
- **Reported:** accuracy and area under the ROC curve, compared with a naive persistence rule (last 20-session volatility above the median).

**Edge test:**
- Paired daily accuracy difference (model − persistence).
- Stationary block bootstrap, mean block 10, 2,000 resamples, seed 0.
- The 90% lower bound must be > 0.
- The model must also beat 50% with a lower bound > 50%.

**Practical test:** every 10 sessions, hold the predicted low-volatility half (equal weight, same costs) vs all stocks. Compare net return, volatility, and maximum drawdown.

## Verdict rules

- **Target A** is "robust return edge" only if it passes its gate. Otherwise it is "inconclusive" or "no edge", whichever the numbers show.
- **Target B** is "robust risk edge" if it passes both of its tests.
- Neither result places orders. Wiring a risk edge into the risk engine (for example, smaller sizes for predicted-volatile names) is a separate, approved change.
