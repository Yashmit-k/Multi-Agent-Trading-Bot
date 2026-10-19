# Market-structure-break study with two targets: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-19, before any result of this study was computed.** Only synthetic-bar unit tests (`services/quant/tests/unit/test_structure_breaks.py`) have run. The code is `services/quant/src/quant_agents/research/structure_breaks.py`.

The user chose: 5-minute breaks of structure with a 1-hour trend filter, entry on a retest of the broken level, two modest targets (three pairs tested), and the stop moved to breakeven after the first target. Long only.

## Data

As in the order-block study:
- 5-minute snapshot `snapshots/nifty50/5m/candles.jsonl` (sha256 `0f2df34d…cb9b`), 49 stocks, 2024-01-01 to 2026-10-05, regular sessions only;
- 60 warm-up sessions, so trading starts 2024-04-01;
- 1-hour bars resampled from 5-minute bars, anchored at 09:15 IST, used only when complete.

## Rules

- **Structure:** pivot highs are the strict maximum of 5 bars centred on them, usable only after the 2 bars to the right have closed. A bullish **break** is a 5-minute close above the most recent usable, not-yet-broken pivot high.
- **Trend filter:** the last *completed* 1-hour bar at the break closes above its 50-bar EMA. The EMA is undefined, and counts as "not up", before 50 hourly bars exist.
- **Entry:** a buy limit at the broken pivot high (the retest), live for the next 12 five-minute bars, on the same day only, and never filled on a bar starting at or after 15:00. It fills on the first bar whose low ≤ the limit, at min(open, limit), plus 5 bp slippage.
- **Stop:** the lowest low from the pivot high to the break bar. **R** = entry − stop. Skip the trade if R < 0.25% of entry, or if fewer than 2 shares fit in ₹20,000.
- **Targets (three variants):**

| Variant | TP1 (half the shares) | TP2 (the rest) |
|---|---|---|
| T_0.5R_1R | entry + 0.5R | entry + 1R |
| T_1R_1.5R | entry + 1R | entry + 1.5R |
| T_1R_2R | entry + 1R | entry + 2R |

- **After TP1:** the stop on the remaining shares moves to the entry price (breakeven).
- **Exit mechanics:**
  - Exits are checked on 5-minute bars. On the fill bar, a touch of the stop counts as stopped, and targets are not checked.
  - Stop fills at min(open, stop). Targets fill at max(open, target). If one bar reaches TP1 and also trades back to entry, the remaining shares exit at breakeven in that bar. The stop wins any tie.
  - Anything left is sold at the close of the bar ending 15:15 IST. 5 bp slippage applies on every exit.
- **Costs and sizing:** Zerodha intraday (MIS) charges on every leg (`ZERODHA_EQUITY_RI` rates), ₹20,000 per trade in whole shares. One position per stock at a time, taken in entry-time order. One trade per break.

**Diagnostic (not gated):** every variant is also run without the trend filter, to show what the filter adds.

## Measures and gate

Each variant reports:
- trades, the share reaching TP1, win rate (net P&L > 0), mean net R, mean net return per trade;
- total net P&L, profit factor, maximum drawdown, exit reasons.

A variant (with the filter) is **profitable** only if all of these hold:
1. at least 100 trades;
2. total net P&L > 0;
3. the stationary-block-bootstrap lower bound of mean per-session P&L is above 0 (mean block 5 sessions, 2,000 resamples, seed 0, quantile 0.10 / 3, i.e. Bonferroni over the 3 variants);
4. net P&L is positive in both halves of the sessions.

## Use

- If no variant passes, nothing changes, and the result is reported as not profitable.
- If one passes, it may become a Strategy-lab template or a paper agent, but only with the user's approval. MIS is not yet supported by the paper engine.
- Nothing is tuned after the result: the 2-bar pivots, EMA 50, 12-bar order life, 0.25% minimum risk, the three target pairs and 15:15 are fixed here.
