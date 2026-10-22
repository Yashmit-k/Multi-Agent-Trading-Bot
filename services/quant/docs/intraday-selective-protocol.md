# Selective intraday trading on the validated signal: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-20, before any result of this study was computed.**

The tuning study ([`agent-tuning-result.md`](agent-tuning-result.md)) found a validated intraday signal: momentum inverted (z 1.0), mean reversion without the ADX gate, and volume inverted (surge 3), fused with weights 0.575 / 0.30 / 0.125 and technical at 0. It predicted the 2026 test period (IC +0.011, 90% lower bound +0.0065). Traded with one order per signal, it lost ₹44 a trade.

Question: does taking **far fewer, stronger** trades from the same signal turn the edge into profit after costs?

## Fixed inputs (none are re-tuned)

- The fused signal and confidence exactly as in the tuning study: same cached Feature Engine features, the 1.4.0 intraday settings, the same weights and the new fusion rule.
- Data: 49 stocks, 5-minute bars. Periods as before: train 2024-04-01 to 2025-06-30, validate 2025-07-01 to 2025-12-31, test 2026-01-01 to 2026-10-05.
- Long only (the paper engine cannot short). Zerodha intraday (MIS) charges on both legs, plus 5 bp slippage per fill. ₹20,000 per trade, in whole shares.

## Trading rules

- **Signal bars:** those ending 09:30–14:30 IST. A trade enters at the next bar's open.
- **Entry:** fused signal ≥ *threshold* and fused confidence ≥ 0.3. At most **one trade per stock per day**. One position per stock at a time.
- **Selection (two variants):**
  - *all*: every qualifying stock;
  - *top 1*: at each bar, only the single stock with the highest fused signal among those qualifying.
- **Exit:**
  - a stop at −2% from entry (filled at min(open, stop); a touch on the fill bar counts as stopped);
  - otherwise the close of the bar *hold* bars after entry;
  - otherwise the bar ending 15:15 IST, whichever comes first.
  - There is no target and no signal-flip exit.

## Settings tried (18)

| Setting | Values |
|---|---|
| Threshold | 0.4, 0.6, 0.8 |
| Hold | 12 bars (60 min), 24 bars (2 h), until 15:15 |
| Selection | all, top 1 |

## Choosing, confirming, testing

1. **Train:** among settings with at least 200 trades, pick the one with the highest mean per-session net P&L.
2. **Validate:** the chosen setting must have positive total net P&L on validation. The validate period was already used to keep agents in the tuning study; this is a second, weaker use of it, and the test period stays untouched.
3. **Test (once):** the chosen setting **works** only if all hold:
   - at least 100 trades;
   - total net P&L > 0;
   - the 90% stationary-block-bootstrap lower bound of mean per-session net P&L is above 0 (mean block 5 sessions, 2,000 resamples, seed 0);
   - net P&L positive in both halves of the test period.

If validation fails, the test is still computed and reported for the record, but the verdict is "does not work". Each period reports, for every setting: trades, win rate, net per trade, total net, and exit reasons. Nothing goes live without the user's approval. Intraday auto-entries stay off unless a setting works.
