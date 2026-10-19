# Multi-timeframe order-block study: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-19, before any result of this study was computed.** Only synthetic-bar unit tests (`services/quant/tests/unit/test_order_blocks.py`) have run. The code is `services/quant/src/quant_agents/research/order_blocks.py`.

The rule choices were made by the user: top-down (higher-timeframe zone, lower-timeframe entry), the last down candle before a break of structure, entry at the lower-timeframe order block with the stop below it and a 2R target, long only. Two timeframe pairs are scored separately.

## Data

- 5-minute bars: `snapshots/nifty50/5m/candles.jsonl` (sha256 `0f2df34d…cb9b`). Daily bars: `snapshots/nifty50/1D/candles.jsonl` (sha256 `0411a895…a7d`).
- Period 2024-01-01 to 2026-10-05, regular NSE sessions only. The first 60 sessions are warm-up: no zone known before then is traded.
- 49 stocks: the snapshot minus `EXCLUDED_SYMBOL`, as in studies 1–4.
- 15-minute and 1-hour bars are built from 5-minute bars, anchored at 09:15 IST: 1-hour bars run 09:15–10:15 through 14:15–15:15, then a short 15:15–15:30 bar. A bar is used only if every 5-minute bar inside it exists.

## Definitions (the same at every timeframe)

- **ATR:** simple mean true range over the last 14 bars, known at each bar's close.
- **Pivot high:** a bar whose high is strictly the highest of the 5 bars centred on it. It is *usable only after the 2 bars to its right have closed*.
- **Bullish break of structure (BOS):** a bar closes above the most recent usable, not-yet-broken pivot high.
- **Bullish order block:** the last bearish candle (close < open) from the lowest low between that pivot and the BOS bar, up to the bar before the BOS. The move must be large enough: BOS close − block low ≥ 1.5 × ATR. The zone is the block candle's low to high, known at the BOS bar's close.

## Books

| Book | Zone (HTF) | Entry (LTF) | Product and costs | Time exit |
|---|---|---|---|---|
| A | daily | 15-minute | CNC: Zerodha delivery charges (as studies 1–4) | close of the 10th session after entry |
| B | 1-hour | 5-minute | MIS: Zerodha intraday charges (`ZERODHA_EQUITY_RI` rates) | close of the bar ending 15:15 IST, same day |

## Trade rules (both books)

1. **HTF zone life:** active from its BOS close for 20 HTF bars. It is dead early if an HTF bar closes below the zone low. Each zone gives at most one trade.
2. **Arming:** an LTF bar after the zone is known trades into it (low ≤ zone high).
3. **LTF trigger:** after arming, an LTF break of structure whose LTF order block (a) overlaps the HTF zone and (b) formed after the HTF zone was known.
4. **Order:** buy limit at the LTF block high, placed at the LTF BOS close. It lives 12 LTF bars; in book B it also expires at the end of that day. In book B, no fill on bars starting at or after 15:00. It fills on the first later LTF bar with low ≤ limit, at min(open, limit), plus 5 bp slippage.
5. **Stop:** the LTF block low. **Risk R** = entry − stop; skip the trade if R < 0.1% of entry. **Target** = entry + 2R.
6. **Exits:** checked on LTF bars from the fill bar on.
   - A stop fills at min(open, stop), or at the stop on the fill bar itself. Because the path inside a bar is unknown, a stop touch on the fill bar counts as stopped.
   - A target fills at max(open, target), from the bar after the fill.
   - Stop wins ties. The time exit is as in the table. 5 bp slippage applies on every exit.
7. **Sizing:** ₹20,000 per trade, whole shares. One position per stock per book at a time: candidates are taken in entry-time order, and one that starts before the previous position closed is skipped.

**Diagnostic baseline (not gated), for each book:** an HTF-only entry. A limit rests at the zone top from the moment the zone is known, the stop is the zone low, the target 2R, and the same time exits and costs apply. It shows whether the LTF refinement adds anything.

## Measures and gate

Each book reports: trades, win rate, mean net R per trade, mean net return per trade, total net P&L, profit factor, maximum drawdown of cumulative realized P&L, and exit reasons. Per-session P&L is the sum of the net P&L of trades exiting in that session, with 0 otherwise.

A book is **profitable** only if all of these hold:
1. at least 100 trades;
2. total net P&L > 0;
3. the stationary-block-bootstrap lower bound of mean per-session P&L is above 0 (mean block 5 sessions, 2,000 resamples, seed 0, quantile 0.10 / 2, i.e. Bonferroni over the 2 books);
4. net P&L is positive in both the first and second half of the sessions.

## Use

- If neither book passes, order blocks are reported as not profitable here, and nothing changes in paper trading.
- If a book passes, it may become a Strategy-lab template or a paper agent, but only with the user's approval.
- Nothing is tuned after the result: the 2-bar pivots, 1.5 × ATR, 20-bar zone life, 12-bar order life, 2R, 10 sessions and 15:15 are fixed here.
