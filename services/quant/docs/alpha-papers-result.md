# Published alpha papers on NIFTY 50: result

Protocol: [alpha-papers-protocol.md](alpha-papers-protocol.md), pre-registered 2026-10-28 and scored once. Numbers: [results/alpha-papers-result.json](results/alpha-papers-result.json). Code: `quant_agents/research/alpha_papers.py`.

**Verdict: none of the 13 rules passes.**
- No stock-selection rule beats simply holding the same stocks equal-weight, net of charges, in train, validate and test.
- No NIFTY timing rule beats holding NIFTY on the pre-registered terms.
- Two results are worth knowing about, though neither is a tradable edge:
  - **The 10-month trend filter cut drawdowns sharply**, but it gave up return in two of the three periods.
  - **The frog-in-the-pan momentum rule beat NIFTY in every period.** It roughly matched equal-weight holding, but did not beat it.

## A. Stock selection: top 10, monthly, universe A+B (67 stocks), simple annual return after charges

| Rule (paper) | Train 2016–20 | Validate 2021–23 | Test 2024–26 | Mean monthly vs equal-weight | t | Gate |
|---|---|---|---|---|---|---|
| **Equal-weight hold (benchmark)** | **17.9%** | **31.9%** | **7.2%** | — | — | — |
| NIFTY 50 | 15.2% | 18.5% | 1.4% | — | — | — |
| S1 low volatility (Ang et al. 2006) | 15.3% | 15.3% | −1.5% | −0.67% | −1.41 | fail |
| S2 low beta (Frazzini & Pedersen 2014) | 11.2% | 14.7% | −0.7% | −0.82% | −1.74 | fail |
| S3 low MAX (Bali et al. 2011) | 14.2% | 23.0% | 0.8% | −0.49% | −1.14 | fail |
| S4 52-week high (George & Hwang 2004) | 13.1% | 14.0% | −3.4% | −0.82% | −1.95 | fail |
| S5 residual momentum (Blitz et al. 2011) | 15.0% | 25.9% | 3.0% | −0.34% | −0.85 | fail |
| S6 frog-in-the-pan (Da et al. 2014) | 16.7% | 28.0% | **12.4%** | −0.03% | −0.06 | fail |
| S7 same-month seasonality (Heston & Sadka 2008)\* | 8.0% | 21.3% | **13.4%** | −0.15% | −0.41 | fail |
| S8 conservative: low vol + momentum (Blitz & van Vliet 2018) | 15.8% | 21.2% | −1.8% | −0.52% | −1.10 | fail |

\* Seasonality's train period is 2018–20, when equal-weight returned 8.4% and NIFTY 10.9%.

What the table shows:
- **The low-risk rules (S1, S2, S8) did worst.** The Indian papers report a low-volatility premium on a broader NIFTY 500 / NSE 500 universe, mostly over long horizons and in risk-adjusted terms. Within NIFTY 50 over 2016–2026, low-volatility stocks simply lagged.
  - They didn't even cushion the 2024–26 fall: low volatility's worst drawdown was 23% of capital, against NIFTY's 16%.
- **Lottery avoidance (S3) and the 52-week high (S4) lost too.** That fits Sharma & Chakraborty (2021): Indian investors do not seem to overpay for lottery-like stocks.
- **S6 and S7 had strong 2024–26 test periods** (+12.4% and +13.4% against equal-weight's 7.2%), but they lagged equal-weight in the earlier periods. One good period out of three is exactly what multiple testing produces by chance. Their t-statistics (−0.06 and −0.41) are nowhere near the 3.0 Harvey, Liu & Zhu ask for.
- **Universe A (today's members only)** gives the same picture. Every rule lags equal-weight in train and validate.

## B. NIFTY index rules (through a NIFTY ETF)

### Month-end allocation, NIFTY or cash at 6% a year

| Rule | Train CAGR / Sharpe / max DD | Validate | Test | Gate |
|---|---|---|---|---|
| Buy and hold | 11.9% / 0.69 / 38% | 15.8% / 1.16 / 17% | 1.3% / 0.16 / 16% | — |
| I1 10-month SMA (Faber 2007) | 7.7% / 0.72 / **17%** | 13.6% / 1.14 / **12%** | **6.4%** / **0.82** / **11%** | fail (return) |
| I2 12-month TSMOM (Moskowitz et al. 2012) | 1.1% / 0.15 / 38% | 12.6% / 0.97 / 17% | 1.2% / 0.16 / 17% | fail |

- **The 10-month SMA did what trend-following papers say it does.** It cut the worst drawdown in every period (38% → 17% in 2016–20, which includes the 2020 crash).
- But it cost 4.2 points of annual return in train and 2.2 in validate, and the gate allowed at most 2.
- It is a **risk-control tool with a real cost in rising markets**, not a source of extra profit.
- The 12-month TSMOM rule switched at bad moments: it was out for the 2020 rebound.

### Trade-by-trade rules, mean net return per trade

| Rule | Train | Validate | Test | Gate |
|---|---|---|---|---|
| I3 turn of the month (Ariel 1987) | +11 bp (59) | +104 bp (35) | −13 bp (32) | fail |
| I4 overnight: buy at the close, sell at the open (Lou et al. 2019) | +4.6 bp (1,237) | +2.1 bp (741) | −4.6 bp (684) | fail |
| I5 intraday momentum (Gao et al. 2018), 2024 / 2025 / 2026 | −8.6 bp (145) | −10.8 bp (134) | −12.4 bp (92) | fail |

- **Turn of the month** was very strong in 2021–23 (+1.04% a trade, 71% wins) and negative in 2024–26. This matches the "diminishing calendar anomalies" papers on India.
- **Overnight drift is real but fading, and costs eat it.**
  - Gross, NIFTY's close-to-open move averaged +14.1 bp, then +11.5, then +4.8.
  - ETF charges and slippage take about 9.5 bp a round trip.
- **Intraday momentum is reversed in India.** The first-half-hour return is *negatively* correlated with the last half-hour (−0.11, −0.17, −0.01), and the last half-hour after an up morning averages about 0 bp gross. The US finding does not carry over.

## What it means (no change is made without approval)

1. **Thirteen well-known published anomalies, tested honestly, gave no edge on NIFTY 50 after costs.** This agrees with McLean & Pontiff (2016), who found that anomaly returns shrink after publication, and with this project's earlier studies.
2. **The hardest benchmark to beat is equal-weight buy-and-hold of the large-cap universe.** It earned 17.9%, 31.9% and 7.2% a year in the three periods, with almost no charges. Every active rule paid ₹2,500–18,000 a period in charges to try to beat it.
3. **One finding is useful for risk, not return:** the 10-month SMA filter on NIFTY roughly halved the worst drawdowns. It could be offered as a separate, opt-in "reduce exposure in downtrends" setting, if wanted. That would be its own decision.
4. **Frog-in-the-pan and seasonality** are the only rules with a strong recent period. They could be watched forward on paper, but there's no evidence yet that they beat equal-weight holding.

## Caveats

- Universe A+B still has survivorship bias, because delisted former members are missing. The bias flatters rules that pick winners, so the true picture for momentum-type rules is if anything *worse*.
- Allocation rules trade at the month-end close they are computed on (as in Faber 2007). In practice that means trading near 15:25.
- I5 has only 2024–2026 5-minute data.
