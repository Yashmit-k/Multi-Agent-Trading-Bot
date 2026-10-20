# Market-structure-break study (two targets): result

Scored once under [`structure-breaks-protocol.md`](structure-breaks-protocol.md), which was committed first (`41905ce`). Raw output: [`results/structure-breaks-result.json`](results/structure-breaks-result.json). The period is 2024-04-01 to 2026-10-05 (616 sessions) over 49 NIFTY 50 stocks: 5-minute breaks, 1-hour trend filter, retest entry, half the position out at TP1 then the stop to breakeven, MIS charges, ₹20,000 per trade.

**Verdict: no variant is profitable.** All three lose about 0.22% per trade and lose money in both halves of the period. Each fails every gate condition except the trade count. Nothing changes in paper trading.

| Variant (with 1h trend filter) | Trades | Reached TP1 | Win rate | Mean net R | Mean net / trade | Total net P&L | Profit factor | Halves (1st / 2nd) |
|---|---|---|---|---|---|---|---|---|
| TP1 0.5R, TP2 1R | 22,336 | 52.6% | 26.1% | −0.53 R | −0.23% | −₹9.75 lakh | 0.19 | −₹5.29 / −₹4.46 lakh |
| TP1 1R, TP2 1.5R | 19,593 | 33.6% | 35.2% | −0.51 R | −0.22% | −₹8.20 lakh | 0.35 | −₹4.36 / −₹3.83 lakh |
| TP1 1R, TP2 2R | 18,880 | 33.7% | 34.4% | −0.50 R | −0.22% | −₹7.89 lakh | 0.36 | −₹4.18 / −₹3.71 lakh |

**Diagnostic, without the trend filter:** about twice the trades and the same loss per trade (−0.21% to −0.22%). The 1-hour filter cuts the number of trades but does not improve them.

## Why it loses

- **Retest fills are weaker than a coin flip.** In the 1R/1.5R variant, 6,592 trades reached TP1 and 9,075 hit the stop first; the rest closed at 15:15. That is a 42% first-touch rate where a random walk gives 50%. A limit order on a pullback mostly fills when the pullback keeps going, so the trades it selects are the weaker ones.
- **Costs then finish it.** Intraday charges plus 5 bp slippage each way come to about 0.16% per round trip. The gross result is already slightly negative, about −0.06%.
- **Closer targets do not help.** TP1 at 0.5R is reached 53% of the time, but the remaining half usually comes back to breakeven or the stop. The wins are too small to cover costs.

## Post-hoc check (not part of the registered result)

Does the cautious fill-bar rule drive the loss? Rerunning the 1R/1.5R variant while ignoring the fill bar entirely gives −0.218% per trade (registered: −0.220%) and a 33.5% TP1 rate. Only 364 of 19,593 trades were stopped on their fill bar. The verdict does not depend on that assumption.
