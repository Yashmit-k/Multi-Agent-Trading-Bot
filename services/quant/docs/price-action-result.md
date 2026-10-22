# Price-action models without lagging indicators: result

Scored once under [`price-action-protocol.md`](price-action-protocol.md), which was committed first (`0ef266d`). Raw output: [`results/price-action-result.json`](results/price-action-result.json).

**Verdict: neither family works.**
- Both variants chosen on training data failed validation and lost money on 2026.
- Gross returns before costs are close to zero for every rule, so charges decide the outcome again.
- Paper trading is unchanged.

One fix was made before any result existed: the NIFTY index has no traded volume, and loading it crashed. Index volume is now optional; no rule reads it.

## Chosen variants

| Family | Chosen on train | Train net / trade | Validate net / trade | 2026 net / trade | 2026 trades | Passes |
|---|---|---|---|---|---|---|
| Intraday | I2 gap-down reclaim, gap ≥ 1% | −0.21% | −0.32% | −0.14% | 119 | no |
| Swing | S1 20-day breakout on volume, hold 5 | −0.63% | −0.39% | −1.04% | 75 | no |

## Every variant (net return per trade after charges and slippage)

| Variant | Train | Validate | 2026 | 2026 trades | 2026 total |
|---|---|---|---|---|---|
| I1 opening-range breakout, 15 min | −0.29% | −0.32% | −0.20% | 326 | −₹12,410 |
| I1 opening-range breakout, 15 min, 2R target | −0.30% | −0.31% | −0.20% | 326 | −₹12,455 |
| I1 opening-range breakout, 30 min | −0.23% | −0.36% | −0.24% | 298 | −₹13,184 |
| I1 opening-range breakout, 30 min, 2R target | −0.25% | −0.35% | −0.25% | 298 | −₹13,922 |
| I2 gap-down reclaim, 1% | −0.21% | −0.32% | −0.14% | 119 | −₹3,007 |
| I2 gap-down reclaim, 2% | −0.16% | −0.58% | +0.09% | 44 | +₹689 |
| I3 relative strength into the close | −0.32% | −0.32% | −0.28% | 368 | −₹19,159 |
| I3 relative strength, NIFTY up only | −0.30% | −0.31% | −0.24% | 170 | −₹7,574 |
| S1 breakout on volume, hold 5 | −0.63% | −0.39% | −1.04% | 75 | −₹16,092 |
| S1 breakout on volume, hold 10 | −0.86% | +0.09% | −0.75% | 67 | −₹10,937 |
| S2 capitulation reversal, hold 3 | +1.22% (9 trades) | −0.69% | −2.37% | 8 | −₹3,624 |
| S2 capitulation reversal, hold 5 | +1.80% (9 trades) | +0.47% | −2.50% | 8 | −₹3,829 |

- The only positive 2026 number is I2 at a 2% gap: 44 trades, +0.09% a trade. It lost money on train and validate, was not eligible to be chosen, and is within noise.
- Capitulation reversal fires about 9 times in 15 months, too rarely to judge.

## What it means

- Taking fewer trades did not fix the problem. Every rule here trades on far fewer days than the earlier intraday studies, and still loses about what the charges cost: about 0.30% a round trip for delivery, and about 0.19% intraday as the paper engine charges it.
  - The paper engine's intraday figure includes the ₹15.34 DP fee, by its documented conservative choice. Zerodha's real intraday cost is about 0.11%.
  - At real rates every intraday rule except I2 at a 2% gap would still lose money on 2026. For example, I2 at a 1% gap makes +0.05% gross a trade, against 0.11% in costs.
- Avoiding lagging indicators did not uncover a hidden edge in NIFTY 50 price action and volume.
- These results agree with the 13 earlier studies.
