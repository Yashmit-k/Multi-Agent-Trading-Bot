# 12-1 momentum improvements: result

Protocol: [momentum-improvements-protocol.md](momentum-improvements-protocol.md), pre-registered 2026-10-28 and scored once. Numbers: [results/momentum-improvements-result.json](results/momentum-improvements-result.json). Code: `quant_agents/research/momentum_improvements.py`.

**Verdict: none of the four variants improves on the baseline.**
- Each beats the baseline only in 2021–23, the strongest momentum period, and loses to it in 2016–20 and 2024–26.
- All but one still beat the benchmark, but none does better than the plain rule.
- **The baseline stays unchanged, in the backtest and in the paper trial.**

## Net annual return (12 × mean monthly), each period starting from cash

| Variant | Train 2016-02–20 | Validate 2021–23 | Test 2024–26 | Continuous CAGR | Worst drawdown | Charges (continuous) | Gate |
|---|---|---|---|---|---|---|---|
| **Baseline: top 20** | **30.9%** | 42.5% | **35.0%** | **34.8%** | 58% | ₹54,151 | — |
| V1 buffer: keep while in the top 40 | 30.5% | 45.6% | 29.2% | 33.3% | 61% | **₹31,972** | fail |
| V2 top 30 | 25.1% | 46.1% | 27.8% | 30.9% | 56% | ₹75,587 | fail |
| V3 skip the 25 most extreme winners | 8.8% | 47.3% | 13.1% | 18.9% | 49% | ₹1,00,752 | fail |
| V4 buffer 40 + top 30 | 23.9% | 47.9% | 30.7% | 32.7% | 57% | ₹57,520 | fail |
| Benchmark: equal-weight Liquid-500, gross | 11.5% | 28.7% | 9.8% | 13.9% | 53% | — | — |

Mean monthly difference against the baseline (t):
- buffer: −0.07% (−0.33);
- top 30: −0.30% (−1.54);
- skip extremes: −1.21% (−2.05);
- buffer + top 30: −0.24% (−1.29).

## What it means

- **The buffer (V1) did what it was meant to do**: 41% lower charges (₹54k → ₹32k) and about 40% fewer trades. It did not raise the return. A stock that falls out of the top 20 but stays in the top 40 is usually losing momentum, and **holding it longer cost about as much as the charges saved.** Of the four variants it came closest to the baseline (−0.07% a month, not significant), but it did not beat it.
- **Spreading over 30 stocks (V2) diluted the winners.** Ranks 21–30 earn less than ranks 1–20, and the drawdown barely improved (56% against 58%).
- **Skipping the most extreme winners (V3) was the worst idea.** The highest-ranked stocks are where most of the profit is, even though they also lead the sell-offs. Removing them gave up return everywhere except 2021–23. It cut the drawdown (49%), but at the cost of 16 points of CAGR.
- Together with the earlier checks (trend filter, market-state filter, volatility scaling; see [momentum-monthly-review.md](momentum-monthly-review.md)), **seven ways of "fixing" momentum have now been tried, and none beats the plain rule.**
  - The bad months are the price of the good ones: the same concentrated, extreme winners cause both.
  - The realistic ways to live with the drawdowns are sizing (putting only part of the capital in the strategy) and patience, not a cleverer rule.
