# ML cross-sectional ranker: result

Scored once under [`ml-rank-protocol.md`](ml-rank-protocol.md), which was committed before any out-of-sample number existed (commit `2ba35db`). The raw numbers are in [`results/ml-rank-result.json`](results/ml-rank-result.json). Code: `services/quant/src/quant_agents/research/ml_rank.py`. Tests: `services/quant/tests/unit/test_ml_rank.py`. The tests cover no look-ahead, label alignment, the training embargo, and costs.

**Verdict: NOT ACCEPTED.** The model shows a selection signal, but it fails the statistical gate and loses money in absolute terms after costs. `MlAgent` stays unloaded, and no paper order uses this model.

## Setup

49 NIFTY 50 stocks (`TATAMOTORS` has no data). Each trade:
- decide after the close;
- buy 6 stocks at the next open, ₹20,000 each;
- sell at the open 5 sessions later;
- pay Zerodha delivery charges (STT 0.1% each side, stamp, exchange, SEBI, GST, ₹15.34 DP) plus 5 bp slippage per fill.

Round-trip costs are about 0.40% per window.

## Development, 2024-04-01 to 2025-12-31 (74 windows, used to choose the model)

| | Model A: gradient boosting | Model B: ridge |
|---|---|---|
| Mean net return per window | −0.199% | −0.284% |
| Equal-weight basket | −0.255% | −0.255% |
| Plain 20-day momentum | −0.229% | −0.229% |
| Random 6 (mean of 200) | −0.265% | −0.265% |
| **Excess vs equal weight** | **+0.056%** | −0.029% |
| 90% interval of excess | −0.208% to +0.321% | −0.284% to +0.217% |
| Windows beating the basket | 52.7% | 50.0% |
| Charges paid (444 trades) | ₹25,479 | ₹25,510 |

The rule picks the model with the higher excess, so **Model A** was chosen.

## Out-of-sample, 2026-01-01 to 2026-10-05 (37 windows, scored once)

| Metric | Model A |
|---|---|
| Mean net return per window | **−0.410%** |
| Equal-weight basket | −0.616% |
| Plain 20-day momentum | −0.888% |
| Random 6 (mean of 200) | −0.609% |
| **Excess vs equal weight** | **+0.206%** |
| 90% block-bootstrap interval | −0.112% to +0.532% |
| Windows beating the basket | 64.9% |
| Trades / charges | 222 / ₹12,769 |
| Net P&L (₹1.2 lakh deployed per window) | −₹17,506 |
| Excess without best stock (ADANIENT) | +0.106% |

| Gate | Result |
|---|---|
| 1. Excess > 0 and 90% lower bound > 0 | **FAIL** (lower bound −0.112%) |
| 2. Beats plain momentum | pass |
| 3. Beats random picks | pass |
| 4. Not driven by one stock | pass |

## What this means

- **There is weak evidence of relative skill.** The model beat the basket in both periods. In 2026 it beat it in 65% of windows and lost about a third less than the basket. Removing the best stock leaves the excess positive. But with 37 windows the interval still includes zero, so this could be luck.
- **It is not profitable.** Long-only, with about 0.4% round-trip delivery costs, it lost money in both periods. 2026 was a falling market for this universe: the equal-weight basket lost about 0.6% per 5-session window. A stock-picker that only loses less than the market still loses.
- **Not done, deliberately:**
  - No hyperparameter search, no feature selection on the out-of-sample period, and no re-run after seeing the result.
  - The protected `snapshots/holdout_after_20261005` was not opened.
  - Changing the rules now and re-scoring 2026 would turn this period into training data.

## Possible next studies (each needs a new pre-registration and fresh out-of-sample data)

- **Forward paper test:** record the model's daily top-6 picks (no orders) from today, then score them in a few months on data that did not exist when this study ran.
- **Market filter:** hold cash when the universe's 20-day trend is negative, since every long-only variant lost money in falling windows.
- **Longer holds** (10–20 sessions), so the ~0.4% round-trip cost is spread over a larger expected move.
