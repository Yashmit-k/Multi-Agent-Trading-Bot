# Combined-hypothesis model: result

Scored once under [`ml-combined-protocol.md`](ml-combined-protocol.md), committed before this run (`2047c59`). Raw output: [`results/ml-combined-result.json`](results/ml-combined-result.json). Code: `services/quant/src/quant_agents/research/ml_combined.py`. Tests: `services/quant/tests/unit/test_ml_combined.py`. The tests cover:
- intraday aggregation against hand-computed values;
- no look-ahead across all 37 features;
- the embargo;
- Deflated Sharpe behaviour.

One logistic model per target, walk-forward from 2024-11-22 to 2026-09-17 on 49 stocks. It combines every hypothesis family available:
- trend and momentum;
- short-term reversal;
- risk;
- volume and liquidity;
- **intraday microstructure from 2.5 million 5-minute bars** (first and last hour returns, intraday realized volatility, close vs VWAP, last-hour volume share, close location);
- sector-relative strength;
- market regime (NIFTY 50, India VIX, breadth, dispersion);
- calendar.

There is no historical news in this repo outside the protected H001 dataset, so news is not a feature.

## Target A: will the stock beat the median over the next 10 sessions? **NO RETURN EDGE**

| Metric | Value | Coin flip |
|---|---|---|
| Accuracy | 50.2% (90%: 49.2%–51.2%) | 50% |
| ROC AUC | 0.497 | 0.500 |
| Top-6 picks correct | 49.3% | 50% |

| Trading (top 6, ₹20k each, delivery costs) | Windows | Net / window | Annualised | Sharpe | Max DD | Invested | Excess vs basket | Deflated Sharpe (48 trials) |
|---|---|---|---|---|---|---|---|---|
| Always invested | 46 | -0.30% | -7.5% | -0.53 | 18.6% | 100% | +0.01% | 0.023 |
| NIFTY trend filter | 46 | -0.12% | -3.0% | -0.38 | 9.9% | 54% | +0.19% | 0.036 |

Always-invested, by market regime:

| Regime | Windows | Net / window |
|---|---|---|
| down-trend/high-vol | 13 | -0.08% |
| down-trend/low-vol | 8 | -0.91% |
| up-trend/high-vol | 10 | -0.59% |
| up-trend/low-vol | 15 | +0.03% |

Adding every feature family made the direction signal *weaker* than the simpler models of study 2. With roughly 50 features and a noisy target, a regularised model learns almost nothing, which is consistent with large-cap NIFTY stocks being efficiently priced at this horizon.

## Target B: will the stock be more volatile than the median over the next 10 sessions? **ROBUST RISK EDGE**

| Metric | Model | Persistence rule (last 20-day volatility) |
|---|---|---|
| Accuracy | **62.7%** (90%: 61.2%–64.1%) | 59.3% |
| ROC AUC | **0.669** | 0.632 |
| Improvement over persistence | **+2.2 to +4.6 points** (90% block bootstrap) | — |

Practical test (pre-registered): hold the predicted calm half vs all stocks, every 10 sessions, same costs.

| Portfolio | Annualised net | Annualised volatility | Max drawdown |
|---|---|---|---|
| Predicted calm half | -10.8% | 11.6% | 19.4% |
| All stocks | -7.8% | 11.6% | 15.4% |

The model reliably knows which individual stocks will move more, and that holds out of sample with a lower bound above zero. But choosing the calm half did not lower portfolio volatility, and it did worse. Calm stocks were more correlated with each other, so the smaller basket diversified less.

## Verdict

- **No robust return edge.** This is the third study, and across 48 tracked trials nothing predicts NIFTY 50 returns well enough to survive Zerodha delivery costs and a multiple-testing correction.
- **A robust risk edge: about 63% accuracy on next-period volatility, reliably better than the naive rule.** It belongs in risk management, where it would size positions by predicted risk, not in stock selection. That use is a new hypothesis and needs its own test and approval.
- Nothing from this study places orders.

## What would actually move the needle

1. **Event data.** The NSE announcements dataset (earnings results) could test post-earnings drift, one of the few return anomalies with long published evidence. It is the protected H001 study and needs explicit authorization. Its training sample is also below its approved minimum.
2. **News history.** The live RSS feed and LLM scores are now stored every 10 minutes. After a few months they form a real, point-in-time news dataset that can be tested without look-ahead.
3. **Forward testing.** Record model outputs daily from now on and judge them on data that does not yet exist. With roughly 3 years of history, any backtest needs an annualised Sharpe of about 2 to be convincing.
