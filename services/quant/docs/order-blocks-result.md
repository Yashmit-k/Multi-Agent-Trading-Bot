# Multi-timeframe order-block study: result

Scored once under [`order-blocks-protocol.md`](order-blocks-protocol.md), which was committed first (`276cb7b`). Raw output: [`results/order-blocks-result.json`](results/order-blocks-result.json). The period is 2024-04-01 to 2026-10-05 (616 sessions, after a 60-session warm-up), over 49 NIFTY 50 stocks, at ₹20,000 per trade with Zerodha charges and 5 bp slippage per fill.

**Verdict: neither book is profitable. Both fail every gate condition except the trade count, and lose money in both halves of the period. The lower-timeframe refinement lowers the win rate. Nothing changes in paper trading.**

| Book | Variant | Trades | Win rate | Mean net R | Mean net / trade | Total net P&L | Profit factor | Halves (1st / 2nd) |
|---|---|---|---|---|---|---|---|---|
| A: daily zone, 15m entry (CNC) | **MTF refined** | 137 | 24.1% | −1.19 R | −0.43% | −₹11,275 | 0.28 | −₹5,728 / −₹5,548 |
| | HTF-only baseline | 472 | 32.4% | −0.31 R | −0.65% | −₹58,558 | 0.61 | −₹41,136 / −₹17,422 |
| B: 1h zone, 5m entry (MIS) | **MTF refined** | 541 | 24.0% | −0.94 R | −0.21% | −₹21,323 | 0.27 | −₹9,555 / −₹11,768 |
| | HTF-only baseline | 2,990 | 31.7% | −0.39 R | −0.21% | −₹1,19,834 | 0.48 | −₹57,931 / −₹61,903 |

The bootstrap lower bounds on mean per-session P&L are all negative: −24.7 (A refined), −146.6 (A baseline), −39.6 (B refined), −220.9 (B baseline).

## What it means

- **No gross edge.** A 2R target needs a win rate above 33.3% to break even before costs. The refined entries win 24% of the time and the plain zone entries about 32%. Price returning to a bullish order block on these stocks is not followed by the move up that the idea predicts, more often than chance.
- **The refinement makes it worse.** Waiting for a lower-timeframe break and entering at the lower-timeframe block gives a tight stop. That stop is hit 75% of the time in book A and 66% of the time in book B, and the tight risk also makes costs large in R terms (−1.19 R per trade in book A). It loses fewer rupees in total only because it takes far fewer trades.
- **Costs are not the whole story.** Book B uses cheap intraday charges and still loses. The losses come from the entries.
- The result is consistent across both halves of the period and across both timeframe pairs. It holds for this exact definition. The protocol fixes the definition, so other parameter choices would be a new, separately pre-registered study.
