# Published anomalies across the whole Indian market and across asset classes: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-28, before any rule below was scored on this data.** The NIFTY-50-only versions of S2–S6, S8 and S10 failed in [alpha-papers-result.md](alpha-papers-result.md). The question here is whether the same anomalies, plus a few more, work in the **wider market**, where most papers find them stronger. A second question is whether cross-asset ETF strategies help.

## Data

NSE capital-market bhavcopies (one file per trading day), downloaded 2026-10-28 from `nsearchives.nseindia.com` into `datasets/research/bhavcopy/raw/` (gitignored). The range is 2015-01-01 to 2026-10-27, in the old format up to 2024-07-05 and the UDiFF format after.

- **Identity:** each security is keyed by **ISIN**, so a symbol change (e.g. N100 → MON100) does not break its history.
- **Daily return:** CLOSE ÷ PREVCLOSE − 1, corrected for corporate actions as in Amendment A below. Dividends are not included, which applies equally to the benchmark.
- **Price series used:** EQ, BE and BZ, so a holding that moves to trade-for-trade keeps a price. A stock is **eligible to be bought** only in the EQ series.
- **Delisting:** a holding that stops trading is sold at its last close.
- The bhavcopy lists every security traded that day, including those later delisted. **The universe is therefore free of survivorship bias.**

## Amendment A (2026-10-28, before scoring): corporate actions

A check of the downloaded data showed that **PREVCLOSE is not adjusted for splits and bonuses** in these files. For example:
- Bank of Baroda's 1:5 split on 2015-01-22 shows as −80%;
- GOLDBEES' 1:100 split on 2019-12-19 shows as −99%;
- unadjusted, NIFTYBEES appeared to fall 69% over 2015–2026.

The rule used instead is the one the earlier studies use (`EVENT_GAP`).
- A day whose **open is more than 20% from PREVCLOSE** is a corporate-action (or listing) day. Ordinary NSE price bands cap normal moves at 20%.
- On such a day the return is **close ÷ open − 1**, and a trade at that open is valued as if the open equals the previous close.

After this fix:
- NIFTYBEES grows ×3.15 over 2015–2026, and GOLDBEES ×5.3.
- Reliance's two 1:1 bonuses (2017-09-07 and 2024-10-28) are caught.
- Yes Bank's 2020 fall, which never opened more than 20% down, is kept as a real loss.
- Of the 548 such days among liquid stocks, the 181 that are not near a split or bonus ratio are mostly IPO listing days, where PREVCLOSE is the issue price. Open-to-close is the right return there too.

Disclosure: the pipeline smoke test, run on 2016 data before this fix was found, printed 2016 annual figures for each rule. Those figures were computed on unadjusted data and are not results. No rule, threshold or parameter was changed after seeing them.

## Periods

| Period | Dates |
|---|---|
| Train | 2016-01-01 to 2020-12-31 (scoring starts 2016-02-01, the first month with a full 252-session look-back, since 2015 has only 248 sessions) |
| Validate | 2021-01-01 to 2023-12-31 |
| Test | 2024-01-01 to 2026-10-27 |

## A. Stock anomalies across the market (K = 10)

**Universe ("Liquid 500"), fixed at each month-end close t:**
- EQ series and not an ETF (ISIN not starting `INF`);
- close ≥ ₹20;
- a return on at least 240 of the last 252 sessions;
- the 500 largest by median daily traded value over the last 126 sessions.

Size buckets, for reporting only: ranks 1–100 and 101–500.

**Portfolio:**
- Scores at the month-end close; the top 20 are bought equal-weight, ₹20,000 each (₹4,00,000 capital), at the next session's open.
- A holding that drops out of the top 20 is sold at that open.
- Costs: Zerodha delivery charges (`mentor_strategies.delivery_charges`) plus **10 bp of slippage each way**.

**Circuits (the bhavcopy has no limit data, so a proxy is used):**
- A buy is skipped if that open is locked up: open = high = low and ≥ 4.9% above PREVCLOSE.
- A sell is delayed a day if the open is locked down (the same test, ≥ 4.9% below).

**Scores** use only data up to the close of t. Prices are adjusted with the daily returns above.

| Id | Rule (pick the 20 best) | Source |
|---|---|---|
| S1 `mom_12_1` | highest return from t−252 to t−21 | Jegadeesh & Titman (1993); Sehgal et al. for India |
| S2 `resid_mom` | highest sum ÷ standard deviation of market-model residuals from t−252 to t−21, with beta fitted over t−252..t against the equal-weight Liquid-500 return | Blitz, Huij & Martens (2011) |
| S3 `high_52w` | highest close ÷ 252-session adjusted high | George & Hwang (2004) |
| S4 `frog_pan` | among the top half by S1, the lowest information discreteness | Da, Gurun & Warachka (2014) |
| S5 `low_vol` | lowest standard deviation of daily returns over 252 sessions | Ang et al. (2006); Blitz & van Vliet (2007) |
| S6 `low_max` | lowest mean of the 5 largest daily returns in the last 21 sessions | Bali, Cakici & Whitelaw (2011) |
| S7 `rev_1m` | lowest return over the last 21 sessions | Jegadeesh (1990) |
| S8 `seasonal` | highest mean return in the coming calendar month over earlier years (at least 3; **trading from 2018**) | Heston & Sadka (2008) |
| S9 `amihud` | highest mean of \|return\| ÷ traded value over 252 sessions (the least liquid within Liquid 500) | Amihud (2002); Amihud et al. (2015) for emerging markets |
| S10 `conservative` | lowest mean of the S5 rank and the S1 rank | Blitz & van Vliet (2018), without the payout leg |

**Benchmark:** the equal-weight Liquid-500, rebalanced monthly, **gross of costs**. It stands in for an equal-weight index fund, and is a harder bar than a costed one. NIFTYBEES buy-and-hold is reported too.

**Gate, all three must hold:**
1. The net annual return beats the benchmark in each of train, validate and test.
2. The pooled monthly net excess over the benchmark, bootstrapped over months (2,000 draws), has its **0.10 / 14** quantile above zero.
3. The net annual return beats NIFTYBEES in each period.

**Diagnostic (not gated):** the gross monthly return of the top decile minus the bottom decile of Liquid 500 for each score. This checks whether the anomaly shows up at all in India, in the direction the paper reports.

## B. Cross-asset ETF strategies (K = 4)

**Assets:** NIFTYBEES (India large caps), JUNIORBEES (NIFTY Next 50), MON100 / N100 (Nasdaq-100), GOLDBEES (gold).
- Cash earns 6% a year (a liquid fund; LIQUIDBEES' price is flat, so it can't be used).
- Prices are the ETFs' own NSE prices, including any premium or discount, as a buyer would actually pay.

**Trading:** decided at each month-end close, traded at the next session's open, with ETF delivery costs (`risk_off_nifty.etf_costs`) plus 5 bp of slippage each way. ₹4,00,000 capital, rebalanced to the target weights each month.

| Id | Rule | Source |
|---|---|---|
| A1 `asset_mom` | hold the 2 assets with the highest 12-month return, 50/50 | Faber (2010), "Relative strength strategies"; Asness, Moskowitz & Pedersen (2013) |
| A2 `dual_mom` | of NIFTYBEES and MON100, take the one with the higher 12-month return; hold it if that return beats cash (6%), otherwise cash | Antonacci (2014), Global Equities Momentum |
| A3 `risk_parity` | weights ∝ 1 ÷ standard deviation of daily returns over 63 sessions, across the 4 assets, unlevered | Asness, Frazzini & Pedersen (2012) |
| A4 `gtaa_trend` | 25% in each asset, held only if its month-end price is above its 10-month average, otherwise that 25% in cash | Faber (2007) |

**Benchmark:** 1/N, i.e. 25% in each asset, rebalanced monthly, net of the same costs (DeMiguel, Garlappi & Uppal 2009). NIFTYBEES buy-and-hold is reported too.

**Gate:**
1. CAGR above 1/N in each period.
2. Monthly Sharpe above 1/N in each period.
3. The pooled monthly excess over 1/N has its bootstrap **0.10 / 14** quantile above zero.

## What follows

- A rule that passes is a candidate for a forward paper trial, with its own approval.
- Small-cap rules also need a separate check of real tradability (circuits, impact) before any money is used.
- Rules that fail are reported, and nothing changes.

## Output

- `services/quant/docs/results/whole-market-result.json`
- `services/quant/docs/whole-market-result.md`

Run:

```
python -m quant_agents.research.whole_market
```
