# Daily rule protocol

Status: **PRE-REGISTERED**. This scores four rules once. It does not fit a model, open `snapshots/holdout_after_20261005`, or submit an `AgentName.ML` signal. H001 is not part of this study.

## Data

- File: `snapshots 2/nifty50/1D/candles.jsonl` (`nifty50_1d_20261005`).
- A session is a daily bar ending at 15:30 IST. TATAMOTORS is excluded.
- Decision sessions are on or before 2025-12-31. The horizon close must also be on or before 2025-12-31. Bars after that date, including the 2026 portion of this file, are not scored. The holdout directory is not opened.

## Portfolio

- Book cash is ₹10,00,000. A selected name receives an equal slice, capped at ₹1,00,000.
- Entry price is the decision close plus 5 bp. Quantity is the largest whole share that fits the slice. A name that cannot buy one share is skipped.
- Exit price is the close H sessions later for that symbol. H is 5 and, separately, 10. Rebalance dates do not overlap.
- The position is held across sessions, so the sell is a delivery sell and includes the ₹15.34 DP charge.
- Charges are `delivery_buy` and `delivery_sell` from `ZERODHA_EQUITY_RI`. The 2 bp research schedule is not the pass rule.
- Window return is total rupee PnL divided by book cash. Cash that is not invested earns zero.

## Rules

On each rebalance date a name is eligible when it has a decision close and a close H sessions later.

- `buy_and_hold`: every eligible name.
- `momentum_20`: names whose close is higher than their own close 20 sessions earlier. A name without those 20 sessions is not eligible.
- `momentum_12_1`: eligible names whose close 21 sessions earlier is higher than their own close 252 sessions earlier. The most recent month is not in the signal.
- `low_volatility`: eligible names whose standard deviation of the last 20 daily returns is at or below the cross-sectional median that day.

A date with no selected name returns zero. A 12-minus-1 date with fewer than 20 names that have the required history is not scored.

## Pass rule

For each rule and horizon, the excess is that rule's window return minus buy-and-hold on the same dates. The interval is a moving-block bootstrap of those excesses: block length 4, 1000 draws, seed 0, percentiles 2.5 and 97.5.

A pass requires the lower bound to be above zero and the average fraction of eligible names selected to be below 0.90. A rule that is long almost every name is buy-and-hold, not a separate edge.

If no rule passes, the result is "no tradable daily-rule edge under CNC costs." Do not add another target or a fitted model.
