# Trend, volume and options signals: pre-registered protocol

Status: **PRE-REGISTERED 2026-11-01, before any signal below was computed on this data.** The sources are listed in [alpha-research-survey-2026-11.md](alpha-research-survey-2026-11.md).

Every book is the paper trial's:
- ₹1,00,000 invested once, 10 stocks, the whole book split equally every month, the leftover cash filled;
- Zerodha delivery charges and 10 bp of slippage each way, the circuit rules and whole shares;
- engine: `research.momentum_compound.simulate(fill_leftover=True)`;
- **shares only, bought for delivery. No option or future is ever traded.** The options data is only read as a signal.

There are five signals in all (K = 5), so the bootstrap bound is the 0.10 / 5 quantile.

## Batch 1: price and volume, Liquid-500 (data in hand)

| Id | Score at each month-end close t (the 10 highest are bought) | Source |
|---|---|---|
| T1 `trend_factor` | Signals A_L = (L-session moving average of the adjusted price) ÷ price, for L = 3, 5, 10, 20, 50, 100, 200. Each month k, fit a cross-sectional OLS of the month's return (month-end k−1 → k) on the A_L measured at month-end k−1, over that month's Liquid-500. The forecast at t is the mean coefficient over the **previous 12 months** · A_L(t) | Han, Zhou & Zhu (2016). **Deviation:** MAs up to 200 sessions, not 1,000, because the data starts in 2015 |
| T2 `ma_distance` | (21-session MA) ÷ (200-session MA) of the adjusted price | Avramov, Kaplanski & Subrahmanyam (2021) |
| T3 `high_volume` | Mean daily traded quantity over the last 5 sessions ÷ the mean over the 45 sessions before them (quantity = traded value ÷ close) | Gervais, Kaniel & Mingelgrin (2001); Kaniel, Ozoguz & Starks (2012) |

**Baseline:** 12-1 momentum (the paper trial's plain book), run over the same periods.

**Periods, each from a fresh ₹1,00,000:**
- train 2017-01-01 to 2020-12-31 (T1 needs a 200-session MA plus 12 months of fitted coefficients);
- validate 2021–2023;
- test 2024-01-01 to 2026-10-27.

**Gate (each signal):**
1. Its CAGR beats the baseline's in **each** period.
2. The pooled paired monthly difference has its bootstrap 0.10 / 5 quantile above zero.
3. It beats the equal-weight Liquid-500 benchmark (gross) in each period.

## Batch 2: options-market signals, F&O stocks (NSE F&O bhavcopy, 2016 →)

**Universe at month-end t:** Liquid-500 members with stock options traded that day.

**Options used:**
- The nearest expiry at least 7 calendar days after t; at the start of a new monthly cycle that is the next one.
- A price counts only if the contract traded that day (contracts > 0). The settlement price is used.
- **Implied volatility:** Black-Scholes, European (NSE stock options have been European since 2011), with a risk-free rate of 6.5%, no dividends, and the stock's NSE close as spot.

**Each signal is the mean of its daily values over the last 5 sessions of the month**, using only days with a valid value, at least 2 of the 5.

| Id | Daily value (the 10 best are bought) | Source |
|---|---|---|
| O1 `vol_skew` | IV of the put with strike ÷ spot in [0.80, 0.95] closest to 0.95, **minus** the IV of the call with strike ÷ spot in [0.95, 1.05] closest to 1.00. **Lowest is best** | Xing, Zhang & Zhao (2010) |
| O2 `call_put_spread` | Over strikes where both the call and the put traded: the mean of (call IV − put IV), weighted by the pair's combined open interest. **Highest is best** | Cremers & Weinbaum (2010) |

**Comparisons:** each batch-2 signal is a stand-alone large and mid-cap strategy on F&O stocks. So it is compared with:
- **(a)** the equal-weight F&O universe, gross, rebalanced monthly: the main benchmark;
- **(b)** NIFTYBEES.

12-1 momentum is reported alongside but is not the bar: its edge sits mostly outside F&O stocks.

**Periods, each from a fresh ₹1,00,000:**
- train 2016-02-01 to 2020-12-31;
- validate 2021–2023;
- test 2024-01-01 to 2026-10-27.

**Gate (each signal):**
1. Its CAGR beats both (a) and (b) in **each** period.
2. The pooled paired monthly difference against (a) has its bootstrap 0.10 / 5 quantile above zero.

## What follows

- A signal that passes is a candidate for a further paper book, with its own approval. The current trial books are not changed.
- Signals that fail are reported with their numbers.

Output:
- `services/quant/docs/results/trend-volume-options-result.json`
- `services/quant/docs/trend-volume-options-result.md`
