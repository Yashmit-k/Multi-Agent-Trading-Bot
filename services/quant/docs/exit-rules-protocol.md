# Exit-rules study: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-15, before any result of this study was computed.** The only
computation done beforehand was timing (about 15 ms to replay one symbol-bar) and a check that
special sessions such as Budget Saturday 2025-02-01 come back neutral, as they also do live.

Question: given the entries the live system actually takes, would a different **exit** rule
have done better than the live one (fixed −2% stop, +4% target, signal exit)? Entries are held
fixed, so only the exit rule is tested.

## Data

- 5-minute bars: `snapshots/nifty50/5m/candles.jsonl` (sha256 `0f2df34d…cb9b`), 2024-01-01 to 2026-10-05.
- Daily bars: `snapshots/nifty50/1D/candles.jsonl` (sha256 `0411a895…a7d`).
- Index context for the regime agent: NIFTY 50 and INDIA VIX from `snapshots/context_through_20261005/5m` (sha256 `adfa5720…7fb`) and the matching `1D` file.
- Stocks: every stock in the snapshot except `EXCLUDED_SYMBOL`, the same universe as studies 1–3.

## Entries (identical for every exit rule)

Signals come from replaying the live quant agents (technical, momentum, mean_reversion, volume, regime; agent version 1.2.0) through the live fusion (`core_fusion.fuse`, default weights) and live proposal rule (`build_proposal`: |signal| ≥ 0.2, confidence ≥ 0.3). Features are built as in live: 400 bars for 5-minute and full history for daily. The intelligence agents (news) cannot be replayed historically and are absent. That is a known difference from live SWING entries.

| Book | Signal bars | Period scored | Entry order |
|---|---|---|---|
| INTRADAY | 5m, signal bar ending 09:20–15:15 IST | the last 250 regular sessions of the snapshot | limit = signal close × 1.0025, from the next bar until the 15:15 bar of the same session; fill at min(open, limit) on the first bar with low ≤ limit |
| SWING | daily, at the session close | every regular session from 2024-07-01 to the end of the snapshot | same limit rule, on the next session's 5m bars, 09:20–15:15 |

One position per symbol per book at a time. While a symbol is held or has a working order, its new BUY signals are ignored. Each trade is ₹20,000 with whole shares only. There are no portfolio caps: trades are scored independently. Costs are Zerodha delivery (CNC) charges as in studies 1–3 (`ml_ensemble._charges`) plus 5 bp slippage on every fill.

## Exit rules

All exits are checked on 5-minute bars after the entry fill. If one bar touches both the stop and the target, the stop wins. A stop fills at min(bar open, stop), so a gap through the stop fills at the open. A target fills at the target price.

| Rule | Stop | Target | Extra exits |
|---|---|---|---|
| **E0 live (baseline)** | reference × 0.98 | reference × 1.04 | signal exit |
| E1 volatility-scaled | reference − 1.0 × ATR14 | reference + 2.0 × ATR14 | signal exit |
| E2 maximum hold | as E0 | as E0 | signal exit; close of the 5th session after the entry session |
| E3 15:15 square-off (INTRADAY only) | as E0 | as E0 | signal exit; close of the bar ending 15:15 IST on the entry session |
| E4 combined | as E1 | as E1 | signal exit; E2's time exit; for INTRADAY also E3's square-off |

- **Reference:** the signal bar's close, as live.
- **ATR14:** the simple mean of daily true range over the 14 sessions before the entry session.
- **Signal exit:** a fused SELL proposal on the book's signal timeframe (fused signal ≤ −0.2, confidence ≥ 0.3) while the stock is held exits at the next 5m bar's open. This is the live rule.
- Positions still open at the end of the data are closed at the last close and included.

## Measures (per book and rule)

- trades, win rate, mean net return per trade, total net P&L, profit factor;
- average hold in sessions;
- maximum drawdown of cumulative realized P&L;
- per-session realized P&L: the sum of the net P&L of trades exiting that session, with 0 when nothing exits.

## Gate

E1–E4 are compared with E0 in their own book: 4 comparisons for INTRADAY and 3 for SWING, so 7 in total. A rule **beats live** only if all three hold:
1. its total net P&L is higher than E0's;
2. the mean per-session P&L difference (rule − E0) has a one-sided lower bound above 0. The bound uses a stationary block bootstrap (mean block 5 sessions, 2,000 resamples, seed 0) at quantile 0.10 / 7, i.e. Bonferroni over the 7 comparisons;
3. the difference has the same sign in the first and second half of the scored sessions.

A rule is **profitable** if its total net P&L is above 0 and the same bootstrap's lower bound on its mean per-session P&L (quantile 0.10 / 7) is above 0.

## Use

- If no rule beats live, the live exits stay unchanged.
- If a rule beats live, it may replace the live exit only after explicit approval as a change to the paper rules. If it beats live but is not profitable, the report says it loses less, not that it makes money.
- Nothing is tuned after the result: the multipliers 1.0 and 2.0, the 5 sessions and the 15:15 time are fixed here.
