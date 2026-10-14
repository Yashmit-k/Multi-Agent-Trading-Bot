# Daily-rule audit

This audit reads [`services/quant/docs/daily-rules-result.md`](../services/quant/docs/daily-rules-result.md). It does not re-score the study, edit that table, fit a model, or open the holdout.

## What the artifact says

The study was scored once from [`services/quant/docs/daily-rules-protocol.md`](../services/quant/docs/daily-rules-protocol.md). No model was fit.

Six rule-horizon pairs were compared with equal-weight buy-and-hold after delivery costs. One pair passed its own interval: `momentum_20` at horizon 5.

- Mean excess about 0.00097943, roughly 9.8 bp.
- Date-block interval about 0.00003951 to 0.00188018. The lower bound is above zero.
- Fraction selected about 0.56, which is below the protocol's 0.90 cutoff.
- 95 windows.

The other five pairs failed that same per-pair rule: `momentum_12_1` and `low_volatility` at horizon 5, and `momentum_20`, `momentum_12_1`, and `low_volatility` at horizon 10. Buy-and-hold is the baseline in the table. Its excess is zero and it does not pass.

## Six-pair caveat

The protocol builds the interval for each pair on its own: a moving-block bootstrap of that pair's excesses, block length 4, 1000 draws, seed 0, percentiles 2.5 and 97.5. A pass is a lower bound above zero and a selected fraction below 0.90.

That interval does not adjust for looking at six pairs and keeping the best one. One pass out of six is the recorded result. It is not a multiplicity-adjusted claim that a daily-rule edge was confirmed.

## What stays closed

H001 stays blocked. The holdout path was not opened and was not hashed. No Ridge, LightGBM, or second target is added. This study stops.
