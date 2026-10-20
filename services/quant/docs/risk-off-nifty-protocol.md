# Buy NIFTY after risk-off days: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-20. No result on the 2026 test period has been computed.**

Origin: in the tuning study, swing risk-off days were followed by stronger next-day returns: +14.2 bp on train and +19.5 bp on validate, against about +3 bp on other days. That measured the 49 stocks' next-day returns on train and validate only; 2026 was never used for it. This study tests whether the effect pays as a trade in the index itself, through an ETF, on 2026 data.

## Data

- NIFTY 50 and INDIA VIX daily bars and Feature Engine 1.2.0 features: the tuning study's cache, built from `snapshots/context_through_20261005`.
- Periods:
  - in-sample, for context only: 2024-04-01 to 2025-12-31;
  - **test: 2026-01-01 to 2026-10-05** (scored once).

## Rule (no parameters are tuned)

**Risk-off day:** at the day's close, NIFTY EMA12 < EMA26 *and* INDIA VIX closed up on the day (VIX `return_1` > 0). This is the regime filter's exact definition.

Two variants, each scored on its own:

| Variant | Buy | Sell | Note |
|---|---|---|---|
| **A** | NIFTY close on the risk-off day | next session's close | the measured effect; needs a trade in the last minutes of the session, at roughly the closing price |
| **B** | next session's open | that session's close | fully implementable; misses the overnight move |

- One trade per signal. A signal on the day after a risk-off day just continues as a new one-day trade.
- **Instrument:** a NIFTY 50 ETF (e.g. NIFTYBEES), approximated by the index; tracking error is ignored.
- ₹1,00,000 per trade, 2 bp slippage per fill.
- **ETF costs per round trip:**
  - STT 0.001% on the sell;
  - stamp duty 0.015% on the buy;
  - exchange transaction charge 0.00307% on both legs, and SEBI ₹10 per crore;
  - GST 18% on exchange and SEBI charges (Zerodha delivery brokerage is ₹0);
  - DP ₹15.34 per sell.
- **Also reported, not gated:** the same trades under stock-like delivery costs (0.1% STT on both legs), as a conservative bound.

## Measures

For each variant and period:
- trades, win rate, mean net return per trade (bp), total net P&L;
- the 90% bootstrap lower bound of the mean trade return (iid over trades, 2,000 resamples, seed 0, quantile 0.05: Bonferroni over the 2 variants).

For comparison only:
- buy-and-hold NIFTY over the test period;
- the mean next-day return of *non*-risk-off days.

## Gate (test period, per variant)

A variant **works** only if all hold:
1. at least 15 trades;
2. mean net return per trade > 0 under ETF costs;
3. the lower bound of the mean trade return > 0.

If one works, it may become a paper-trading forward test (the paper engine would first need an ETF instrument), but only with the user's approval. If neither works, the regime finding is reported as not tradeable on 2026.
