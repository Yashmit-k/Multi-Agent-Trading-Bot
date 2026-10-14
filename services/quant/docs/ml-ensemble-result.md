# ML ensemble study: result

Scored once under [`ml-ensemble-protocol.md`](ml-ensemble-protocol.md), which was committed before this study ran (`7b4a98a`). The raw output is [`results/ml-ensemble-result.json`](results/ml-ensemble-result.json). Code: `services/quant/src/quant_agents/research/ml_ensemble.py`. Tests: `services/quant/tests/unit/test_ml_ensemble.py`. The tests cover:
- no look-ahead in the stock, NIFTY, VIX, and sector features;
- the training embargo;
- costs matching `delivery_costs.py` to the paisa;
- the Reality Check telling noise apart from a real edge.

**Verdict: NO ROBUST EDGE.** 4 of 45 variants made money net of costs, and the best earned +6.4% a year. But White's Reality Check gives **p = 0.76**: if no variant had any skill, the best of 45 would still look this good about 76% of the time. On excess over the basket the best variant (`H5-rf-timing`) has p = 0.22. Nothing is traded.

## Setup

- Walk-forward decisions from 2024-12-19 to 2026-10-05, on 49 NIFTY 50 stocks.
- 45 features: 18 stock features plus their daily ranks, and 9 market features (NIFTY 50 trend, India VIX level/change/percentile, breadth, dispersion). Sector-relative strength uses the NIFTY sector indices.
- Selectors: ridge, gradient boosting, random forest, extra trees, and a rank-average ensemble of the four.
- Exposure rules: always invested, NIFTY trend filter, or a logistic market-timing model.
- Holding periods: 5, 10, 20 sessions.
- Every trade is a ₹20,000 CNC delivery position with Zerodha charges and 5 bp slippage per fill.

## Baseline (equal weight across all stocks, same windows and costs)

| Hold | Net / window | Annualised |
|---|---|---|
| 5 sessions | -0.32% | -16.2% |
| 10 sessions | -0.26% | -6.4% |
| 20 sessions | -0.11% | -1.4% |

## All 45 variants, best first

| Variant | Windows | Net / window | Annualised | Sharpe | Max DD | Invested | Excess vs basket |
|---|---|---|---|---|---|---|---|
| `H10-ridge-timing` | 44 | +0.26% | +6.4% | 0.44 | 12.0% | 43% | +0.51% |
| `H20-ridge-trend` | 22 | +0.50% | +6.2% | 0.49 | 8.2% | 55% | +0.61% |
| `H10-ridge-always` | 44 | +0.20% | +4.9% | 0.28 | 14.6% | 100% | +0.45% |
| `H20-rf-trend` | 22 | +0.10% | +1.3% | 0.14 | 12.1% | 55% | +0.21% |
| `H5-rf-timing` | 88 | -0.02% | -1.0% | -0.08 | 18.9% | 38% | +0.30% |
| `H5-et-timing` | 88 | -0.02% | -1.2% | -0.11 | 17.2% | 38% | +0.30% |
| `H10-ridge-trend` | 44 | -0.06% | -1.6% | -0.15 | 17.4% | 57% | +0.19% |
| `H20-et-trend` | 22 | -0.16% | -1.9% | -0.25 | 10.5% | 55% | -0.05% |
| `H5-ensemble-timing` | 88 | -0.04% | -2.1% | -0.15 | 21.4% | 38% | +0.28% |
| `H5-hgb-timing` | 88 | -0.05% | -2.3% | -0.16 | 19.5% | 38% | +0.28% |
| `H20-ridge-always` | 22 | -0.20% | -2.5% | -0.15 | 22.7% | 100% | -0.09% |
| `H10-et-always` | 44 | -0.10% | -2.6% | -0.17 | 13.5% | 100% | +0.15% |
| `H5-ridge-timing` | 88 | -0.06% | -2.8% | -0.20 | 19.2% | 38% | +0.27% |
| `H10-et-timing` | 44 | -0.12% | -3.0% | -0.28 | 12.1% | 43% | +0.14% |
| `H10-hgb-timing` | 44 | -0.13% | -3.2% | -0.30 | 14.3% | 43% | +0.13% |
| `H10-rf-timing` | 44 | -0.14% | -3.4% | -0.31 | 11.5% | 43% | +0.12% |
| `H20-et-timing` | 22 | -0.37% | -4.6% | -0.35 | 12.5% | 68% | -0.26% |
| `H10-ensemble-timing` | 44 | -0.19% | -4.7% | -0.38 | 12.1% | 43% | +0.07% |
| `H20-ridge-timing` | 22 | -0.38% | -4.7% | -0.32 | 19.0% | 68% | -0.27% |
| `H20-ensemble-trend` | 22 | -0.39% | -4.9% | -0.56 | 14.4% | 55% | -0.29% |
| `H20-hgb-trend` | 22 | -0.41% | -5.1% | -0.55 | 16.7% | 55% | -0.30% |
| `H20-rf-always` | 22 | -0.49% | -6.1% | -0.39 | 19.3% | 100% | -0.38% |
| `H10-et-trend` | 44 | -0.28% | -6.9% | -0.69 | 18.9% | 57% | -0.02% |
| `H20-hgb-timing` | 22 | -0.57% | -7.2% | -0.49 | 12.1% | 68% | -0.46% |
| `H10-hgb-trend` | 44 | -0.33% | -8.2% | -0.95 | 19.8% | 57% | -0.07% |
| `H5-et-trend` | 88 | -0.16% | -8.2% | -0.77 | 19.3% | 53% | +0.16% |
| `H20-et-always` | 22 | -0.67% | -8.4% | -0.58 | 14.9% | 100% | -0.56% |
| `H20-rf-timing` | 22 | -0.68% | -8.5% | -0.65 | 14.4% | 68% | -0.57% |
| `H10-ensemble-always` | 44 | -0.35% | -8.7% | -0.55 | 21.0% | 100% | -0.09% |
| `H5-rf-trend` | 88 | -0.18% | -8.9% | -0.93 | 21.0% | 53% | +0.15% |
| `H5-ensemble-trend` | 88 | -0.18% | -9.1% | -0.89 | 19.0% | 53% | +0.14% |
| `H10-ensemble-trend` | 44 | -0.38% | -9.4% | -0.93 | 21.4% | 57% | -0.12% |
| `H10-rf-trend` | 44 | -0.38% | -9.5% | -1.07 | 22.3% | 57% | -0.12% |
| `H20-hgb-always` | 22 | -0.79% | -9.8% | -0.63 | 17.0% | 100% | -0.68% |
| `H10-hgb-always` | 44 | -0.39% | -9.9% | -0.71 | 26.4% | 100% | -0.14% |
| `H20-ensemble-timing` | 22 | -0.83% | -10.4% | -0.78 | 15.0% | 68% | -0.72% |
| `H5-hgb-trend` | 88 | -0.21% | -10.6% | -1.09 | 19.1% | 53% | +0.11% |
| `H10-rf-always` | 44 | -0.46% | -11.5% | -0.83 | 21.0% | 100% | -0.20% |
| `H5-hgb-always` | 88 | -0.27% | -13.4% | -0.72 | 23.7% | 100% | +0.06% |
| `H5-ridge-trend` | 88 | -0.27% | -13.4% | -1.17 | 27.1% | 53% | +0.06% |
| `H5-ensemble-always` | 88 | -0.27% | -13.6% | -0.69 | 25.9% | 100% | +0.05% |
| `H20-ensemble-always` | 22 | -1.09% | -13.6% | -0.95 | 20.0% | 100% | -0.98% |
| `H5-et-always` | 88 | -0.30% | -15.2% | -0.87 | 26.7% | 100% | +0.02% |
| `H5-rf-always` | 88 | -0.36% | -18.0% | -0.98 | 29.3% | 100% | -0.04% |
| `H5-ridge-always` | 88 | -0.54% | -26.8% | -1.40 | 40.3% | 100% | -0.21% |

## Best variant by market regime: `H10-ridge-timing`

| Regime (NIFTY vs its 50-day mean / VIX vs its 120-day median) | Windows | Net / window |
|---|---|---|
| down-trend/high-vol | 10 | +0.72% |
| down-trend/low-vol | 9 | +0.54% |
| up-trend/high-vol | 9 | -0.78% |
| up-trend/low-vol | 16 | +0.39% |

## What we learned

1. **Costs decide the outcome.** About 0.4% per delivery round trip is about 20% a year at a 5-session hold, but about 5% at 20 sessions. Every always-invested 5-session variant lost money, and the profitable variants all hold 10–20 sessions or sit in cash part of the time.
2. **Staying out helps more than picking.** The variants that made money were in cash 45–57% of the time, through the trend filter or the timing model. In this falling period, avoiding exposure mattered more than which 6 stocks were held.
3. **Simple beat complex.** Ridge regression was the best selector at every profitable horizon. The tree ensembles and the rank-average ensemble did no better, which is what overfitting noise looks like.
4. **No variant is robust.** With only 22–88 windows per variant and 45 tries, the best result is well within luck (p = 0.76). Even the best variant lost money in up-trend, high-volatility windows.

## Next step

Forward-test the leading variant (`H10-ridge-timing`) without placing orders. Record its picks and exposure decision each day from now, and score them in a few months on data that did not exist when this study ran. Only a pass there, plus separate approval, would put a model into paper trading.
