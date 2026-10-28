# Published anomalies across the whole Indian market and across asset classes: result

> **Correction 2026-10-29:** the CAGRs and drawdowns here compound returns measured on a *fixed* capital, with a fixed ₹ amount per new position and profits not reinvested. That is fine for comparing rules, so the verdicts stand, but it **overstates what a one-time investment would grow to**. For ₹1 lakh invested once and split equally across the 10 every month, see [momentum-compound.md](momentum-compound.md): 26.7% a year, worst fall 39%.

Protocol: [whole-market-protocol.md](whole-market-protocol.md), pre-registered 2026-10-28, with Amendment A (corporate actions) made before scoring. Scored once. Numbers: [results/whole-market-result.json](results/whole-market-result.json). Code: `quant_agents/research/bhavcopy.py` (data) and `quant_agents/research/whole_market.py` (study).

Data:
- 2,917 NSE sessions, 2015-01-01 to 2026-10-27, and 3,711 securities;
- every stock that traded, including those later delisted, so there is **no survivorship bias**;
- universe: the 500 most liquid EQ stocks at each month-end.

**Verdict:**
- **One rule of 14 passes: 12-1 momentum (S1) across the Liquid-500.** It beats the equal-weight Liquid-500 (gross of costs) and NIFTYBEES in train, validate and test, after charges and 10 bp of slippage each way. Its Bonferroni-adjusted bootstrap bound is above zero.
- **It is a high-return, high-pain strategy**: a 58% drawdown in 2018–20 and five losing calendar years out of eleven.
- **The edge sits in mid and small caps.** Among the 100 largest stocks it is weak, which fits the NIFTY 50 study, where nothing worked.
- No cross-asset rule beats the simple 1/N ETF mix.

## A. Stock anomalies, Liquid-500, top 20, net annual return (12 × mean monthly)

| Rule (paper) | Train 2016-02–20 | Validate 2021–23 | Test 2024–26 | Monthly excess vs benchmark (t) | Decile spread, gross %/month (train / val / test) | Gate |
|---|---|---|---|---|---|---|
| **Benchmark: equal-weight Liquid-500, gross** | 11.5% | 28.7% | 9.8% | — | — | — |
| NIFTYBEES | 15.7% | 16.6% | 4.3% | — | — | — |
| **S1 12-1 momentum (Jegadeesh & Titman 1993)** | **30.9%** | **42.5%** | **35.0%** | **+1.61% (2.96)** | +1.47 / +2.58 / +2.09 | **pass** |
| S4 frog-in-the-pan (Da et al. 2014) | 21.5% | 30.9% | 18.6% | +0.62% (1.99) | +1.46 / −0.85 / −0.00 | fail (bootstrap) |
| S8 seasonality (Heston & Sadka 2008)\* | 0.7% | 24.5% | 15.0% | +0.02% (0.07) | +1.46 / −0.16 / +1.29 | fail |
| S9 Amihud illiquidity (Amihud 2002) | −2.0% | 32.0% | 15.3% | −0.32% (−0.73) | −0.12 / +1.44 / +0.67 | fail |
| S10 conservative: low vol + momentum | 15.4% | 24.6% | 7.7% | +0.01% (0.02) | +1.69 / +0.82 / +0.93 | fail |
| S3 52-week high (George & Hwang 2004) | 16.6% | 17.4% | 4.9% | −0.18% (−0.53) | +1.80 / +0.57 / +0.45 | fail |
| S6 low MAX (Bali et al. 2011) | 15.4% | 16.9% | 2.9% | −0.28% (−0.96) | +1.52 / −1.12 / −0.41 | fail |
| S5 low volatility (Ang et al. 2006) | 14.8% | 13.1% | −1.1% | −0.48% (−1.21) | +1.25 / −1.04 / −0.59 | fail |
| S2 residual momentum (Blitz et al. 2011) | 7.1% | 23.4% | −3.4% | −0.58% (−1.90) | +0.77 / +0.42 / −0.09 | fail |
| S7 1-month reversal (Jegadeesh 1990) | 2.8% | 12.2% | −1.3% | −0.96% (−2.51) | +0.39 / −0.59 / −0.49 | fail |

\* Seasonality trades from 2018. Its train benchmark (2018–20) was 0.6%.

The decile spread is the gross top-decile minus bottom-decile return per month. It checks whether each anomaly exists in India at all:
- **Momentum is the only signal positive in all three periods**, at +1.5% to +2.6% a month.
- The low-risk signals (S5, S6) worked in 2016–20 and **reversed** after 2021: risky stocks beat safe ones.
- Short-term reversal is negative after 2020, so in India recent losers keep losing.

## S1 12-1 momentum in detail

Compounded month by month, February 2016 to October 2026:

| | CAGR | Growth | Worst drawdown |
|---|---|---|---|
| **12-1 momentum, top 20, net** | **+32.9%** | ×21.2 | **58%** (2018-04 → 2020-03) |
| Equal-weight Liquid-500, gross | +13.9% | ×4.1 | 53% (2017-12 → 2020-03) |
| NIFTYBEES | +12.3% | ×3.5 | 27% (2019-12 → 2020-03) |

| Year | Momentum | Equal-weight 500 | NIFTYBEES |
|---|---|---|---|
| 2016 (Feb–Dec) | −25.1% | +11.0% | +9.7% |
| 2017 | **+146.6%** | +49.4% | +29.9% |
| 2018 | −18.6% | −23.5% | +4.8% |
| 2019 | −18.7% | −10.6% | +12.9% |
| 2020 | **+142.0%** | +28.7% | +17.2% |
| 2021 | +53.5% | +49.3% | +26.0% |
| 2022 | −2.9% | +1.0% | +5.5% |
| 2023 | **+109.3%** | +48.9% | +20.5% |
| 2024 | +36.7% | +22.9% | +10.2% |
| 2025 | −2.1% | +0.3% | +12.0% |
| 2026 (Jan–Oct) | **+71.9%** | +0.7% | −10.8% |

- It beat the benchmark in 7 of 11 years. Most of the profit came in a few boom years (2017, 2020, 2023, 2026).
- Between those years there were long flat or losing stretches, including two losing years in a row (2018–19).
- Its worst months were −27% (train), −13% (validate) and −16% (test). The momentum crash of December 2024 – January 2025 cost about 30% in two months.

**Sensitivity** (reported, not part of the gate; net annual return vs the benchmark):

| Variant | Train | Validate | Test |
|---|---|---|---|
| As registered: 20 stocks, 10 bp slippage | 30.9% vs 11.5% | 42.5% vs 28.7% | 35.0% vs 9.8% |
| Slippage 30 bp each way | 29.4% | 40.6% | 33.3% |
| 10 stocks | 39.2% | 38.3% | 34.5% |
| 30 stocks | 25.1% | 46.1% | 27.8% |
| Quarterly rebalance | 30.1% | 41.0% | 30.9% |
| 6-1 momentum | 41.9% | 37.6% | 16.9% |
| **Only ranks 1–100 (large caps)** | **5.7% vs 10.3%** | 29.1% vs 21.4% | 11.0% vs 8.5% |
| Only ranks 101–500 (mid and small) | 33.5% vs 11.8% | 41.8% vs 30.6% | 28.8% vs 10.2% |

The result does not depend on the exact settings: slippage, portfolio size and rebalance frequency all keep it. **It does depend on including mid and small caps.**

Checks made on the result:
- The picks are recognisable momentum leaders of their time, e.g. Cochin Shipyard, Suzlon, BSE, Dixon, Inox Wind.
- The largest monthly winners and losers were checked against their raw daily data. ZENTEC's −42% / +41% was a real lower-circuit fall in February 2025 and a rebound in March.
- **Bonuses with a factor above 0.8 (e.g. 1:5) open less than 20% lower and are not caught by Amendment A.** They show as a fake fall. That makes a stock look weaker (less likely to be picked) and gives a held stock a fake loss. So it biases this test *against* momentum, not for it.

## B. Cross-asset ETF strategies (NIFTYBEES, JUNIORBEES, MON100, GOLDBEES; cash at 6%)

| Rule | Train CAGR / Sharpe / max DD | Validate | Test | Gate |
|---|---|---|---|---|
| **1/N, 25% each (benchmark)** | 18.5% / 1.42 / 25% | 13.4% / 1.13 / 13% | 19.2% / 1.38 / 11% | — |
| NIFTYBEES buy-and-hold | 14.7% / 0.84 / 35% | 14.3% / 1.01 / 16% | 3.2% / 0.31 / 15% | — |
| A1 asset momentum, top 2 (Faber 2010) | 11.6% / 0.79 / 26% | 7.6% / 0.69 / 16% | 25.5% / 1.28 / 15% | fail |
| A2 dual momentum (Antonacci 2014) | 10.2% / 0.55 / 42% | 14.0% / 0.91 / 19% | 21.2% / 0.78 / 26% | fail |
| A3 inverse-vol risk parity | 16.6% / 1.29 / 28% | 13.9% / 1.26 / 11% | 17.6% / 1.29 / 11% | fail |
| A4 trend-filtered 1/N (Faber 2007) | 12.9% / 1.36 / **14%** | 13.2% / **1.41** / **8%** | 16.8% / **1.51** / 11% | fail |

- **The simple 25% mix of Indian large caps, Next 50, Nasdaq-100 and gold was the standout of the cross-asset part.** It beat NIFTYBEES in two of three periods, by a wide margin in 2024–26 (19.2% against 3.2%), with a higher Sharpe in every period. In 2021–23 it fell just short of NIFTYBEES (13.4% against 14.3%), and its train-period drawdown was 25%.
- The timing rules only added turnover. This matches DeMiguel, Garlappi & Uppal (2009): 1/N is hard to beat.
- The trend filter (A4) gave the smallest drawdowns, but less return.

## What it means (no change is made without approval)

1. **12-1 momentum across the 500 most liquid NSE stocks is the first rule in this project to pass a pre-registered, survivorship-free, cost-inclusive test in all three periods.**
   - It replicates the best-documented anomaly in finance (Jegadeesh & Titman 1993; Asness et al. 2013; Jensen, Kelly & Pedersen 2023, who find momentum among the factors that replicate).
   - It agrees with Indian evidence (Sehgal et al.) and with NSE's own momentum indices.
2. **It is not a smooth source of profit.**
   - A 58% drawdown, five losing years in eleven, and −30% in two months (December 2024 – January 2025).
   - Most real investors abandon such a strategy in its bad years, which may be part of why the premium persists.
3. **Not modelled:**
   - **Tax.** Monthly rotation makes almost all gains short-term capital gains (20%), against 12.5% long-term for buy-and-hold.
   - Impact for positions much larger than ₹20,000.
   - Dividends: they are excluded from both sides.
4. **The next step, if wanted, is a forward paper trial with its own approval.** It needs month-end daily bars for about 500 stocks, which is new data plumbing, since the live system covers NIFTY 50 only.
   - It would run as a separate paper book: monthly rebalance, top 20, ₹20,000 each.
   - It would be judged against the equal-weight benchmark over at least 12 months before any thought of real money.
5. **The 1/N ETF mix** is a separate, simple finding about diversification, not a trading signal.
