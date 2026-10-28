# Momentum variants from the literature: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-29, before any variant below was run.** None of them has been computed on this data.

**Baseline:** the rule in the paper trial.
- 12-1 momentum, the top 10 of the NSE Liquid-500.
- ₹1,00,000 invested once, the whole book split equally every month, and the leftover cash filled.
- Engine: `research.momentum_compound.simulate(fill_leftover=True)`.
- Same charges, 10 bp of slippage each way, circuit rules and whole shares.

Each variant changes **only** what is listed below. K = 5.

## Variants

| Id | Change | Source |
|---|---|---|
| V1 `nse_score` | Score = the mean of two cross-sectional z-scores: (6-month return ÷ annualised volatility) and (12-month return ÷ annualised volatility). Returns end at the month-end close with no skipped month, using 126 and 252 sessions; volatility is the standard deviation of daily returns over 252 sessions × √252. Ranking by this mean gives the same order as NSE's "normalised momentum score" | NSE Nifty200 Momentum 30 methodology (factsheet and whitepaper) |
| V2 `mom_12_7` | Score = the return from 252 to 147 sessions ago (12 to 7 months) | Novy-Marx (2012) |
| V3 `factor_timing` | At each month-end, compute the momentum factor's trailing 12-month return. This is the gross equal-weight next-month return of each of the last 12 month-ends' top 10, so it uses only months already complete. If it is ≤ 0, the whole book goes into **NIFTYBEES** for the month, charged as a stock (overstating the ETF's costs). Otherwise the baseline | Ehsani & Linnainmaa (2022) |
| V4 `low_volume` | Take the top 30 by 12-1, then choose the 10 with the lowest ratio of mean daily traded quantity over the last 63 sessions to that over the last 252 (quantity = traded value ÷ close). The other 20 follow, in 12-1 order, if any of the 10 can't be bought | Lee & Swaminathan (2000) |
| V5 `delivery` | Take the top 30 by 12-1, then choose the 10 with the highest mean delivery % over the last 63 sessions (NSE `sec_bhavdata_full`, EQ series), matched by symbol. A stock with no delivery data ranks last within the 30 | India-specific; bulk-deal studies (Rabada & Barretto 2023) report delivery % rising before informed buying |

## Periods (each from a fresh ₹1,00,000)

- **V1–V4:**
  - train 2016-02-01 to 2020-12-31;
  - validate 2021–2023;
  - test 2024-01-01 to 2026-10-27.
- **V5:** NSE delivery data starts in October 2019, so its 63-session window is full from January 2020. Its periods are:
  - train 2020-02-01 to 2022-06-30;
  - validate 2022-07-01 to 2024-06-30;
  - test 2024-07-01 to 2026-10-27.

  The baseline is rerun on the same periods.

## Gate

A variant **improves** on the baseline only if all three hold:
1. Its CAGR beats the baseline's in **each** period.
2. The pooled paired monthly return difference (variant − baseline), bootstrapped over months (2,000 draws), has its **0.10 / 5** quantile above zero.
3. It beats the equal-weight Liquid-500 benchmark (gross) in each period.

**Reported, not gated:** worst fall, charges, and a one-continuous-book run of V1–V4 from 2016-02.

## What follows

- A variant that passes is a candidate for a **second** paper book, with its own approval. The current trial is not changed.
- If none passes, the baseline stays.

Output:
- `services/quant/docs/results/momentum-variants-result.json`
- `services/quant/docs/momentum-variants-result.md`
