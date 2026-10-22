# Quant-agent backtest and tuning: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-20, before any result of this study was computed.** The only work done beforehand was timing (about 8.6 ms of feature computation per 5-minute bar).

Questions:
1. Do the quant agents (1.3.0) predict the next move on past data?
2. Can a small, pre-declared set of settings make them better, confirmed on data not used for tuning?
3. Does the tuned, fused system make money on a final period that is never used for tuning?

The intelligence agents (news, fundamental, valuation, earnings) **cannot** be backtested: there is no point-in-time archive of past news or financials. They are judged only on the live scorecard.

## Data and periods

- Snapshots: `snapshots/nifty50/5m` (sha256 `0f2df34d…cb9b`) and `1D` (`0411a895…a7d`); NIFTY 50 / INDIA VIX context from `snapshots/context_through_20261005`. 49 stocks (snapshot minus `EXCLUDED_SYMBOL`), regular sessions only.
- Features: the real Feature Engine 1.2.0 (`build_feature_set`), exactly as live. Intraday uses the last 400 five-minute bars, daily uses the full history. NIFTY's last-bar return is passed in, as live.
- Periods (by IST session date):

| Period | Dates | Use |
|---|---|---|
| Warm-up | 2024-01-01 to 2024-03-31 | features only |
| **Train** | 2024-04-01 to 2025-06-30 | choose each agent's settings and the fusion weights |
| **Validate** | 2025-07-01 to 2025-12-31 | keep or drop each tuned agent |
| **Test** | 2026-01-01 to 2026-10-05 | scored once, at the end; never used for any choice |

## What is measured

- **Forward return.** Intraday: close of the signal bar to the close 12 bars (60 minutes) later, same session, otherwise none. Swing: daily close to the next session's close. This is the same definition the live scorecard uses.
- **Per agent and setting:**
  - **cross-sectional IC:** for each bar (intraday) or day (swing), the rank correlation across stocks between the agent's effective vote (signal × confidence) and the forward return, then averaged over bars or days;
  - hit rate of the signal's sign where signal ≠ 0;
  - mean signed forward return (bp);
  - participation (share of non-zero signals).
- **Selection score:** mean cross-sectional IC.

## Agents and the settings tried (fixed here; nothing else is tuned)

Agent rules are re-implemented as array code with their constants exposed. **Before any number is used, the re-implementation must reproduce the real 1.3.0 agents' signal and confidence on 2,000 random bars per timeframe.** If it does not, the study stops.

| Agent | Settings tried | Current (1.3.0) |
|---|---|---|
| Technical | ATR dead-band scale × {0, 1, 2} (0 = plain side-of comparisons) | 1 |
| Momentum | noise z ∈ {0.25, 0.5, 1.0} × ADX trend ∈ {15, 20, 25} | 0.5, 20 |
| Mean reversion | ADX weak-trend cutoff ∈ {15, 20, 25, ∞ (never abstain)} | 20 |
| Volume | relative-volume surge ∈ {1.5, 2, 3} | 2 |
| Each agent | also **inverted** (signal × −1) | — |

Inverting is included because an agent that is reliably wrong is a signal too, but only if validation confirms it. Including the inverted rule doubles each grid.

**Regime** (a market filter, not a vote) is evaluated, not tuned. On train and validate, the study compares the mean next-period return of stocks on risk-off bars and days (NIFTY EMA12 < EMA26 and India VIX rising) with all other bars and days.

## Rules for choosing (train), keeping (validate), and weighting

1. **Train:** for each agent and horizon, pick the setting (inverted or not) with the highest mean IC.
2. **Validate:** keep it only if its validation mean IC is above 0 *and* the 90% stationary-block-bootstrap lower bound of the daily mean IC is above 0 (mean block 5 days, 2,000 resamples, seed 0). Otherwise the agent's fusion weight is 0 for that horizon.
3. **Weights:** among kept agents, proportional to the *train* mean IC, normalised to sum to 1 per horizon.

## Final test (once)

On the test period, compute for each horizon:
- **Fused IC:** the cross-sectional IC of the tuned, weighted fused signal, against (a) the current 1.3.0 agents with equal weights, the old fusion rule, regime excluded; and (b) zero (no skill).
- **Trading:** the swing and intraday books with the live paper rules:
  - entry when the fused signal ≥ 0.2 and confidence ≥ 0.3, filled at the next bar's open;
  - one position per stock, stop −2%, target +4%, and a signal exit at fused ≤ −0.2;
  - ₹20,000 per trade, Zerodha CNC charges plus 5 bp slippage per fill; intraday also squares off at 15:15 with MIS charges.

**The tuned system "works"** only if both hold on the test period, for at least one horizon:
1. its fused IC has a 90% bootstrap lower bound above 0;
2. its trading book has positive total net P&L, with a 90% bootstrap lower bound on mean session P&L above 0 (block 5 sessions, 2,000 resamples, seed 0).

If neither horizon works, nothing changes in paper trading except what validation removed (agents with no confirmed edge get weight 0 for that horizon). Every result is reported, including failures. Tuned settings change the live agents only with the user's approval.
