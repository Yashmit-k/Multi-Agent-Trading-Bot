# Trend, volume and options signals: result

Protocol: [trend-volume-options-protocol.md](trend-volume-options-protocol.md), pre-registered 2026-11-01 and scored once per batch. Numbers: [results/trend-volume-options-result.json](results/trend-volume-options-result.json). Code:
- `quant_agents/research/trend_volume_options.py`;
- `quant_agents/research/options_signals.py` (implied-volatility solver checked against known Black-Scholes prices).

Every book is the paper trial's: ₹1,00,000 once, 10 shares, an equal split every month, the leftover filled, all charges. No option is traded.

**Verdict: none of the five signals passes.** The paper trial's books are unchanged.

## Batch 1: price and volume, Liquid-500 (each period from a fresh ₹1,00,000)

| Signal | Train 2017–20 | Validate 2021–23 | Test 2024–26 | Mean monthly vs 12-1 (t) | ₹1 lakh from 2017 → | Worst fall |
|---|---|---|---|---|---|---|
| **12-1 momentum (baseline)** | **37.6%** | **36.4%** | **16.0%** | — | **₹14,89,164** (31.6%) | 39% |
| T1 trend factor (Han, Zhou & Zhu 2016) | 12.2% | 21.3% | 10.4% | −1.16% (−2.02) | ₹3,93,748 (15.0%) | 50% |
| T2 MA distance (Avramov et al. 2021) | 27.9% | 21.1% | 9.1% | −0.71% (−1.46) | ₹6,81,654 (21.6%) | 48% |
| T3 high-volume premium (Gervais et al. 2001) | **−11.4%** | 3.4% | −2.2% | **−2.73% (−4.24)** | ₹61,650 (−4.8%) | 67% |
| Benchmark (equal-weight Liquid-500, gross) | 7.1% | 31.0% | 7.9% | — | — | — |

What batch 1 shows:
- **The trend factor did not deliver its crash protection here.** Its worst fall (50%) was deeper than momentum's (39%), and it earned less than half as much.
- **The high-volume premium is reversed in India, and strongly** (t = −4.2). Stocks whose last-week volume jumped well above their usual level went on to lose. This matches Chinese evidence of attention-driven retail buying, and the earlier "low-volume winners" result pointed the same way. It is a fact worth knowing, a red flag for any buy rule, but not a strategy in itself.

## Batch 2: options-market signals, F&O stocks, 2016–2026 (each period from a fresh ₹1,00,000)

Data: NSE F&O bhavcopies for 2,691 of 2,692 sessions (2021-03-30 is missing). Signals were computed for 124–222 F&O stocks a month (median 179), from contracts that traded that day.

| Signal | Train 2016-02–20 | Validate 2021–23 | Test 2024–26 | Mean monthly vs F&O equal-weight (t) | Worst fall |
|---|---|---|---|---|---|
| O1 volatility skew, lowest bought (Xing, Zhang & Zhao 2010) | **−4.0%** | 12.6% | −0.4% | **−0.84% (−3.82)** | 61% |
| O2 call–put IV spread, highest bought (Cremers & Weinbaum 2010) | −0.6% | 21.1% | 4.7% | −0.34% (−1.12) | 66% |
| F&O universe, equal-weight, gross | 9.2% | 23.2% | 7.0% | — | — |
| NIFTYBEES | 14.8% | 17.0% | 3.5% | — | — |
| 12-1 momentum, for reference (whole Liquid-500) | 25.5% | 36.4% | 16.0% | — | 39% |

What batch 2 shows:
- **The volatility skew is reversed in India, and significantly.** Stocks whose puts were cheapest relative to their at-the-money calls (lowest skew) did *worse* than the F&O average by 0.84% a month.
  - In the US, a low skew means little fear of a fall and good returns ahead.
  - Here, a low or negative skew more often marks **heavy call buying**. India's options market is dominated by retail call speculation, so a low skew flags froth, not safety.
- **The call–put spread** beat NIFTYBEES in 2021–26 but trailed the plain F&O average in every period.
- Neither comes close to momentum. Both are confined to the larger F&O stocks, where momentum is also weaker.

## What it means

- **Ten more published anomalies have now been tested on Indian data in this round and the previous one; none beat 12-1 momentum.**
  - Three of the failures pointed the opposite way to the original papers: high volume, volatility skew, and earlier the lottery (MAX) effect.
  - The common thread is **retail speculation**. In India, stocks drawing attention, volume spikes or call buying tend to be overpriced afterwards.
- These reversed signals are **hypotheses, not strategies.** Using them as "avoid" filters (for example, skip momentum stocks with a volume spike or a very low skew) would need its own pre-registered test, ideally checked forward on paper. Choosing a direction after seeing these results would be data snooping.
- **12-1 momentum and the delivery-filter book in the paper trial remain the only candidates.**
