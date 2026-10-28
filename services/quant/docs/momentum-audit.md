# 12-1 momentum backtest: audit for leaks and bias

> **Correction 2026-10-29:** the CAGRs and drawdowns here compound returns measured on a *fixed* capital, with a fixed ₹ amount per new position and profits not reinvested. That is fine for comparing rules, so the verdicts stand, but it **overstates what a one-time investment would grow to**. For ₹1 lakh invested once and split equally across the 10 every month, see [momentum-compound.md](momentum-compound.md): 26.7% a year, worst fall 39%.

Run 2026-10-28. Code: `quant_agents/research/momentum_audit.py`. Numbers: [results/momentum-audit-result.json](results/momentum-audit-result.json).

The full backtest, as one continuous book from 2016-02-01 to 2026-10-27:
- [results/momentum-backtest-trades.csv](results/momentum-backtest-trades.csv): every buy and sell, with price, quantity, charges and P&L;
- [results/momentum-backtest-monthly.csv](results/momentum-backtest-monthly.csv): each month's net return against the equal-weight Liquid-500 and NIFTYBEES.

## Baseline (one continuous book, ₹4,00,000, monthly returns compounded)

| | CAGR | Worst drawdown |
|---|---|---|
| 12-1 momentum, top 20, net of all charges and 10 bp slippage | **34.8%** | 58% |
| Equal-weight Liquid-500, gross | 13.9% | 53% |
| NIFTYBEES | 12.3% | 27% |

The three-period study's 32.9% differs because there the book restarted at each period boundary.

Trade statistics:
- 875 round trips, 50.6% of them winners, ₹54,151 of charges in total.
- Realised P&L was ₹14.2 lakh on ₹4 lakh. **The 10 best trades made 46% of it**, led by Adani Green in 2020–21 (+₹1.6 lakh on ₹20,000).
- Without those 10 trades the realised P&L is still ₹7.6 lakh.
- This is how momentum works: many small losses and a few very large winners.

## Timing: what each decision can see

| Step | Data used | Known by then? |
|---|---|---|
| Universe at month-end close t | close, traded value and series up to t | yes, at the close |
| Score | adjusted closes at t−252 and t−21 | yes |
| Corporate-action adjustment | each day's own open vs PREVCLOSE; no later day is used | yes, at that open |
| Buy / sell | the open of t+1, plus slippage | the order is placed before it |
| "Can it be bought" check | the price at the open of t+1; **and whether the stock stayed locked all day** (open = high = low) | partly *not* known at the open (see below) |
| Benchmark | the same universe at t, gross | yes |
| Survivorship | every stock that traded each day, including those later delisted. 3 holdings stopped trading and were sold at their last close | — |

The one piece of later information is the lock check. A stock that opened at its upper circuit and **stayed** there all day is skipped, and a holding locked down all day sells a day later. That can only hurt the strategy: it skips stocks that went up and delays selling stocks that went down. Removing the check *raises* the CAGR to 36.2%.

## Tests designed to expose a leak

If the result relied on information it should not have, delaying the signal would make it collapse, and random picks run through the same engine would also beat the benchmark.

| Test | CAGR | Benchmark | Reading |
|---|---|---|---|
| Baseline | 34.8% | 13.9% | — |
| Signal 1 session old (scores from t−1, trade at the t+1 open) | 33.8% | 13.9% | no dependence on the last close |
| Signal 5 sessions old | 39.3% | 13.9% | unchanged within noise |
| Signal 21 sessions (a month) old | 29.7% | 13.9% | still far above the benchmark: momentum is slow |
| No circuit-lock filter | 36.2% | 13.9% | the one later-information step costs return |
| Skip every stock with a corporate-action day in its look-back | 31.7% | 13.9% | not driven by split / bonus handling |
| Slippage 50 bp each way (5× the base) | 30.2% | 13.9% | survives heavy costs |
| **Placebo: 20 random 20-stock picks a month, same engine and costs** | **mean 6.0%, best 12.1%** | 13.9% | **random picks lose to the benchmark**, by the cost of turning over the book monthly. The engine has no hidden upward bias |

**Conclusion of the audit:**
- No look-ahead or engine bias was found.
- The result does not depend on same-day information, on the corporate-action rule, on the circuit filter or on low costs.
- Picks made by chance through the same engine do not reproduce it.

This does not prove the future will repeat it. What it shows is that the backtest measures what it claims to.

## Risks that remain (not leaks)

- **Concentration in a few big winners**, and a 58% drawdown in 2018–20.
- Five losing calendar years out of eleven.
- **Mostly mid and small caps.** Among the 100 largest stocks the edge is weak.
- **Tax is not modelled.** Nearly all gains are short-term (20%), not long-term (12.5%).
- **Dividends are excluded** from both the strategy and the benchmark. Momentum stocks pay fewer dividends, so this slightly flatters momentum against the benchmark, by about 1% a year at most.
- **The decade studied** (2016–2026) was very strong for Indian mid and small caps. Momentum's best years (2017, 2020, 2023) were boom years.
