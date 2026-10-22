# Risk-based sizing: result

Scored once under [`risk-sizing-protocol.md`](risk-sizing-protocol.md) (committed first, `11a2a17`). Raw output: [`results/risk-sizing-result.json`](results/risk-sizing-result.json). Walk-forward windows from 2024-11-22 to 2026-09-17, every 10 sessions, Zerodha delivery costs and 5 bp slippage per fill.

**Verdict: risk sizing does not help any book, and no book is profitable.** The paper engine keeps equal ₹20,000 sizing.

| Book | Weights | Annualized net | Annualized vol | Sharpe | Max drawdown |
|---|---|---|---|---|---|
| A. All stocks | equal | -7.7% | 11.7% | -0.65 | 15.3% |
| A. All stocks | risk | -9.3% | 11.3% | -0.82 | 17.1% |
| B. Momentum top 6 | equal | -4.7% | 14.1% | -0.34 | 20.5% |
| B. Momentum top 6 | risk | -5.1% | 14.3% | -0.35 | 21.6% |
| C. Model calm 24 | equal | -10.5% | 11.7% | -0.89 | 19.2% |
| C. Model calm 24 | risk | -10.5% | 11.6% | -0.91 | 19.1% |

| Book | Sharpe change, 90% (risk − equal) | Risk sizing helps? | Risk-weighted profitable? |
|---|---|---|---|
| A. All stocks | -0.30 to -0.03 | no | no |
| B. Momentum top 6 | -0.23 to +0.21 | no | no |
| C. Model calm 24 | -0.06 to +0.03 | no | no |

## Why the risk edge did not translate

- **The weights barely move.** Predicted probabilities mostly sit between 0.3 and 0.7, so the weights 1 − p differ by about 2× at most. That is too little to reshape a portfolio.
- **Portfolio risk is driven by correlation, not by single-stock volatility.** NIFTY 50 stocks move together in a sell-off, so tilting toward individually calm names does not lower the basket's swings.
- **High-volatility names were partly the rebounders.** Underweighting them gave up some recoveries, which is why drawdown got worse in book A.

## What remains true

Study 3's finding stands: the model forecasts which stocks will be volatile, with 62.7% accuracy vs 59.3% for the naive rule. Two uses remain untested:
- **Stop placement:** volatility-scaled stops instead of the fixed −2%.
- **Exposure:** less total exposure when the whole market is predicted to be volatile.

Each needs its own pre-registered test.
