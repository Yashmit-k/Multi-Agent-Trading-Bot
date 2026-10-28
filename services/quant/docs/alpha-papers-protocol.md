# Published alpha papers on NIFTY 50: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-28, before any rule below was scored.** None of these rules had been run on this data. Earlier, related work: the slow-rotation study (12-1 and 6-1 momentum, 1-month and 1-week reversal); the daily-rules study (a one-day low-volatility filter, 2024–25 only); and the risk-off-NIFTY study (buying NIFTY after risk-off days). Those rules are not repeated.

Question: do the best-documented anomalies in the academic literature make money **after Zerodha charges** on NIFTY 50 stocks or the NIFTY index, against an honest benchmark?

## Lessons applied from earlier studies

1. **The benchmark is equal-weight buy-and-hold of the same universe**, not NIFTY. The slow-rotation study passed three rules against NIFTY that did no better than holding the same stocks.
2. **Universe A+B**: today's 49 members plus the 18 former members in `dip_reversion.FORMER`. Some survivorship bias remains: delisted members have no data. Universe A is reported, not gated.
3. **Many rules are tested, so the bar is raised.** The bootstrap quantile is Bonferroni-adjusted for all K = 13 rules (Harvey, Liu and Zhu 2016).
4. Each rule is scored **once, as written**. No parameter is tuned.

## Data

- `datasets/research/dip_history/daily_2015_2026.jsonl`: daily OHLCV, 2015-01-01 to 2026-10-05, for the 67 stocks and NIFTY 50.
- `datasets/research/agent_tuning/features-NIFTY50-5m.npz`: NIFTY 50 5-minute bars, 2024-01 to 2026-10 (rule I5 only).

## Periods

| Period | Dates |
|---|---|
| Train | 2016-01-01 to 2020-12-31 |
| Validate | 2021-01-01 to 2023-12-31 |
| Test | 2024-01-01 to 2026-10-05 |

Rule I5 has only 5-minute data from 2024, so it uses 2024, 2025 and 2026 (to 2026-10-05) as its three periods.

## A. Stock-selection rules (K = 8)

The simulation is the slow-rotation engine (`slow_rotation.simulate`, unchanged apart from the ranking):
- **Rebalance:** the score is computed at each month-end close, and trades are made at the next session's open.
- **Holdings:** the top 10, ₹20,000 each, ₹2,00,000 capital.
- **Costs:** Zerodha delivery charges, plus 5 bp of slippage each way.
- **Exclusions:** a stock with a >20% open gap (a split or bonus) in its look-back is skipped, and it is sold if the gap happens while it is held.
- **Look-back:** 252 sessions, all ending at the month-end close.

| Id | Rule | Score (pick the 10 best) | Source |
|---|---|---|---|
| S1 `low_vol` | low volatility | lowest standard deviation of daily returns over 252 sessions | Ang, Hodrick, Xing & Zhang (2006); Blitz & van Vliet (2007); Joshipura (2015, 2020) for India |
| S2 `low_beta` | low beta | lowest beta to NIFTY over 252 sessions | Frazzini & Pedersen (2014), "Betting against beta"; Baker, Bradley & Wurgler (2011) |
| S3 `low_max` | lottery avoidance | lowest MAX: the mean of the 5 largest daily returns in the last 21 sessions | Bali, Cakici & Whitelaw (2011). Sharma & Chakraborty (2021) report the opposite in India |
| S4 `high_52w` | 52-week high | highest close ÷ 252-session high | George & Hwang (2004) |
| S5 `resid_mom` | residual momentum | sum of market-model residuals from t−252 to t−21 ÷ their standard deviation, with beta fitted over t−252..t | Blitz, Huij & Martens (2011). **Deviation:** a 12-month fit instead of 36, because the data starts in 2015 |
| S6 `frog_pan` | frog-in-the-pan | among stocks in the top half by 12-1 return, the 10 with the lowest information discreteness, ID = sign(PRET) × (%negative days − %positive days), over t−252..t−21 | Da, Gurun & Warachka (2014) |
| S7 `seasonal` | same-month seasonality | highest mean return in the coming calendar month across all earlier years, with at least 3 years required. **Trading starts 2018**, so train is 2018–2020 | Heston & Sadka (2008) |
| S8 `conservative` | low vol + momentum | lowest mean of the rank by S1 and the rank by 12-1 return (descending) | Blitz & van Vliet (2018), "The Conservative Formula", without the payout leg (no dividend data) |

**Benchmark:** equal-weight buy-and-hold of A+B, bought at the period's first open, ₹20,000 each (`slow_rotation.equal_weight`).

**Gate (A+B), all three must hold:**
1. The annual return beats the equal-weight hold in **each** of train, validate and test.
2. The pooled monthly return in excess of the equal-weight hold, bootstrapped over months (2,000 draws), has its **0.10 / 13** quantile above zero.
3. The annual return also beats NIFTY in each period.

## B. NIFTY index rules (K = 5), traded through a NIFTY ETF

**Costs:** `risk_off_nifty.etf_costs` for delivery, plus 2 bp of slippage each way. For the intraday rule I5: Zerodha intraday brokerage (0.03%, capped at ₹20 an order), ETF STT 0.001% on the sell, stamp 0.003% on the buy, and exchange, SEBI and GST charges, plus 2 bp of slippage each way. Notional: ₹1,00,000.

| Id | Rule | Source |
|---|---|---|
| I1 `sma10m` | At each month-end, hold NIFTY next month if its close is above the mean of the last 10 month-end closes, otherwise cash | Faber (2007), "A quantitative approach to tactical asset allocation" |
| I2 `tsmom12` | At each month-end, hold NIFTY next month if its 12-month return is positive, otherwise cash | Moskowitz, Ooi & Pedersen (2012), "Time series momentum" |
| I3 `turn_of_month` | Buy at the close of the second-last session of each month, sell at the close of the 3rd session of the next | Ariel (1987); Lakonishok & Smidt (1988); Indian evidence: Review of Finance and Banking (2023) |
| I4 `overnight` | Buy at every close, sell at the next open | Lou, Polk & Skouras (2019), "A tug of war" |
| I5 `intraday_mom` | If NIFTY's return from the previous close to 09:45 is positive, buy at 15:00 and sell at 15:30 (the 15:25 bar's close) | Gao, Han, Li & Zhou (2018), "Market intraday momentum" |

For I1 and I2:
- Idle cash earns 6% a year (a liquid fund).
- Switching costs ETF charges at month-end closes.
- **Benchmark:** buy-and-hold NIFTY.
- **Gate:** the monthly Sharpe ratio beats buy-and-hold in **each** period, **and** the annual return is at least buy-and-hold's minus 2 percentage points in each period. The second condition stops a rule passing as merely "safer" while giving up most of the return.

For I3, I4 and I5, which trade by trade:
- **Gate:** the mean net return per trade is positive in **each** period.
- And the pooled per-trade bootstrap (2,000 draws) has its **0.10 / 13** quantile above zero.

## What follows a result

- A rule that passes is a **candidate for a forward paper trial**, with its own approval. It is not traded live.
- A rule that fails is reported with its numbers, and nothing changes.

## Output

- `services/quant/docs/results/alpha-papers-result.json`
- `services/quant/docs/alpha-papers-result.md`

Run:

```
python -m quant_agents.research.alpha_papers
```
