# Momentum variants from the literature: result

Protocol: [momentum-variants-protocol.md](momentum-variants-protocol.md), pre-registered 2026-10-29 and scored once. Numbers: [results/momentum-variants-result.json](results/momentum-variants-result.json). Code: `quant_agents/research/momentum_variants.py`.

Every book is the paper trial's: ₹1,00,000 once, 10 stocks, an equal split every month, the leftover cash filled, Zerodha charges and 10 bp of slippage each way.
- Delivery data: NSE `sec_bhavdata_full`, 1,745 of 1,746 sessions from October 2019 (2022-08-08 is missing).
- 3.2 million stock-days were matched to the price data; 0.7% could not be matched.

**Verdict:**
- **No variant passes the gate. The paper trial keeps plain 12-1 momentum.**
- **One variant came close: delivery %** (V5). It beat the baseline in all three of its periods but failed the multiple-testing bound (t = 1.59; the bound needed about t = 2.05).

## V1–V4, each period from a fresh ₹1,00,000 (CAGR, worst fall)

| Variant | Train 2016-02–20 | Validate 2021–23 | Test 2024–26 | Mean monthly vs baseline (t) | Gate |
|---|---|---|---|---|---|
| **Baseline: 12-1** | 25.5%, 39% | 36.4%, 32% | 16.0%, 41% | — | — |
| V1 NSE volatility-adjusted score | 23.4%, 55% | 18.0%, 33% | 11.3%, 38% | −0.49% (−1.20) | fail: worse in all three |
| V2 12-to-7-month momentum | 12.0%, 40% | **53.0%**, 28% | 17.8%, 31% | −0.21% (−0.42) | fail: much worse in train |
| V3 factor timing (NIFTYBEES when momentum's last 12 months ≤ 0) | 21.5%, **33%** | 33.9%, **20%** | 19.4%, 34% | −0.21% (−0.61) | fail: worse in train and validate |
| V4 low-volume winners | 24.9%, 41% | 43.1%, 23% | **28.3%**, 29% | +0.26% (+0.56) | fail: just worse in train |
| Benchmark (equal-weight Liquid-500, gross) | 8.0% | 31.0% | 7.9% | — | — |

One continuous book, 2016-02 to 2026-10 (reported, not gated):

| Book | Final value | CAGR | Worst fall | Charges |
|---|---|---|---|---|
| Baseline 12-1 | ₹12,78,473 | 26.8% | 39% | ₹68,828 |
| V1 NSE score | ₹7,27,821 | 20.3% | 55% | ₹58,634 |
| V2 12-to-7 | ₹9,87,556 | 23.8% | 40% | ₹61,876 |
| V3 factor timing | ₹10,90,787 | 24.9% | **33%** | ₹47,723 |
| V4 low volume | **₹18,16,778** | **31.0%** | 41% | ₹99,698 |

## V5 delivery %, 2020–2026 (each period from a fresh ₹1,00,000)

| | Train 2020-02 – 2022-06 | Validate 2022-07 – 2024-06 | Test 2024-07 – 2026-10 |
|---|---|---|---|
| Baseline 12-1 | 58.1% | 47.7% | 4.3% |
| **V5: top 30 by 12-1, then the 10 with the highest delivery %** | **71.7%** | **63.2%** | **25.6%** |
| Benchmark | 21.1% | 45.1% | 1.1% |
| Worst fall, V5 | 31% | 22% | 27% |

- Mean monthly difference: **+1.03%** (t = 1.59).
- The Bonferroni-adjusted 2nd percentile is **−0.28%**, below zero, so the gate fails.

## What it means

- **The NSE index's volatility-adjusted score (V1) did worst.** Favouring steadier large-cap risers cut the returns that come from mid- and small-cap leaders, and made the worst fall *larger* (55%). That fits the earlier finding that momentum's edge here lies outside the largest stocks.
- **12-to-7-month momentum (V2) is unstable.** It was the best by far in 2021–23 and the worst in 2016–20. That is the "momentum echo" disagreement in the literature (Novy-Marx against Goyal & Wahal), seen in one market.
- **Factor timing (V3) worked as a risk control, not as a return booster.**
  - It had the smallest drawdowns (33%, 20%, 34%) and the lowest charges.
  - It gave up return in two of three periods, because sitting in NIFTYBEES missed momentum's rebounds.
- **Low-volume winners (V4) look attractive over the whole decade** (31.0% a year, against 26.8%). But they lost to the baseline in 2016–20 (24.9% against 25.5%), and their charges were about 45% higher.
- **Delivery % (V5) is the strongest new signal found in this project.**
  - It beat the baseline in all three periods, by 14–21 points a year, with smaller worst falls.
  - In the weak 2024–26 stretch it made 25.6% against the baseline's 4.3%.
  - But its history is only about 6.7 years (80 months). With five variants tested, the evidence is not yet strong enough to rule out luck.
- **Next, if wanted (each its own decision):**
  - V5 could be watched forward as a **second paper book** alongside the trial, without changing the trial. If it keeps beating the baseline on live data, that is new, independent evidence.
  - V4 would need a fresh test on a different period, or a different market, to settle its 2016–20 miss.
