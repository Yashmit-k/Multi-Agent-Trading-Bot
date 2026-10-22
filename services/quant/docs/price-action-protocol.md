# Price-action models without lagging indicators: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-21. No result of these rules on any period has been computed.**

Goal (from the user): a model that trades **few, high-quality** setups, at most **2 trades a day**, using **no lagging indicators**.

## Allowed and forbidden inputs

**Allowed:**
- raw open/high/low/close of completed bars;
- levels: the previous session's close, the opening range, the high of the previous 20 sessions;
- gaps;
- returns over fixed windows;
- bar volume compared with the **same time of day** on the previous 20 sessions (the median), or daily volume compared with the median of the previous 20 days;
- the stock's return since the open minus NIFTY 50's return since the open;
- the India VIX daily close.

**Forbidden:** moving averages, EMA, MACD, RSI, Bollinger bands, ADX, ATR or ATR bands, VWAP, z-scores of smoothed series, and any agent signal.

## Data and periods

The tuning study's cache, built from `snapshots/context_through_20261005`: 5-minute and daily bars for the 49 NIFTY 50 stocks, NIFTY 50 and India VIX.

| Period | Dates | Use |
|---|---|---|
| Train | 2024-04-01 to 2025-06-30 | choose one variant per family |
| Validate | 2025-07-01 to 2025-12-31 | the chosen variant must hold up |
| Test | 2026-01-01 to 2026-10-05 | scored once |

Earlier studies used 2026 for other rules. These rules have never been run on any period.

## Execution (same as paper trading)

- A decision on a completed bar fills at the **next bar's open**, plus 5 bp slippage on each fill.
- Stops and targets are checked from the fill bar on: the fill bar's own low counts, which is the conservative choice.
- A bar that opens beyond the stop exits at that open.
- When a bar touches both the stop and the target, the stop wins.
- ₹20,000 per trade.
- Charges: Zerodha MIS for intraday (the Strategy Lab's `leg_charges`, including the DP fee the paper engine charges); CNC delivery for swing.
- At most 2 new trades a day per variant, with one position per stock at a time.
- Candidates are taken **in time order**. Candidates on the same bar are taken by the variant's ranking key, highest first. A later, stronger signal never displaces an earlier one, because that would use the future.
- Swing positions may overlap across days; each uses its own ₹20,000.

## Intraday family (MIS, flat by the bar ending 15:15)

- **I1 Opening-range breakout.**
  - The opening range (OR) is the high and low of the first *k* minutes (bars ending up to 09:15 + *k*).
  - Signal: the first 5-minute close above the OR high, between the end of the OR and 11:00, provided that:
    - the session's cumulative volume so far is at least 1.5× its same-time median over the previous 20 sessions; and
    - the stock's return since the open is above NIFTY's.
  - The first close above the OR high is the day's only chance: if either condition fails on that bar, there is no trade that day.
  - Stop: the OR low.
  - Rank by relative cumulative volume.
  - Variants: *k* ∈ {15, 30} min × target ∈ {none, 2R}. 4 variants.
- **I2 Gap-down reclaim.**
  - Signal: the session opens at least *g* below the previous close, and the bar ending 09:45 closes above the session's open.
  - Target: the previous close; no trade if the fill is already at or above it. Stop: the session's low up to the signal bar.
  - Rank by gap size.
  - Variants: *g* ∈ {1%, 2%}. 2 variants.
- **I3 Relative strength into the close.**
  - At the bar ending 14:00, take the stocks whose return since the open minus NIFTY's is largest, and above +1%. Hold to 15:15.
  - Stop: the session's low up to 14:00.
  - Variants: always, or only when NIFTY is up since the open. 2 variants.

## Swing family (CNC, decided on the daily close, filled at the next session's open)

- **S1 Breakout on volume.**
  - Signal: the close is above the highest high of the previous 20 sessions, daily volume is at least 2× the median of the previous 20 days, and the close is in the top 25% of the day's range.
  - Stop: the signal day's low.
  - Rank by the volume ratio.
  - Variants: hold *h* ∈ {5, 10} sessions, exiting at the close of the last day.
- **S2 Capitulation reversal.**
  - Signal: the day's return is −4% or worse, volume is at least 2× the 20-day median, and the close is in the top 50% of the day's range (buyers stepped in).
  - Stop: the signal day's low.
  - Variants: hold *h* ∈ {3, 5} sessions.

That is 8 intraday and 4 swing variants: 12 in all.

## Selection and gates (per family)

1. **Train.** Pick the variant with the highest mean net return per trade among those with at least 60 trades. A tie goes to fewer trades.
2. **Validate.** The chosen variant must have mean net return per trade > 0. If it fails, the family stops; the test period is still reported, but marked as not passing.
3. **Test (scored once).** The per-session P&L series counts every trading day in the period, with 0 on days without a trade, so trading less is not rewarded by itself. The family **works** only if all of these hold:
   - at least 40 trades;
   - mean net return per trade > 0;
   - the 95% one-sided bootstrap lower bound of the mean per-session P&L is > 0 (2,000 resamples of trading days, seed 0, quantile 0.025: Bonferroni over the 2 families);
   - net P&L > 0 in each half of the test period.

## Reported for every variant on every period

Trades, trades per active day, win rate, mean gross and net return per trade, total net P&L, profit factor, and the share of days with any trade. Nothing is tuned after the test result exists.

If a family works, it becomes a Strategy Lab-style paper forward test only with the user's approval. If neither works, the result is published as a failure, like the earlier studies.
