# Buy NIFTY after risk-off days: result

Scored once under [`risk-off-nifty-protocol.md`](risk-off-nifty-protocol.md), which was committed first (`5c14028`). Raw output: [`results/risk-off-nifty-result.json`](results/risk-off-nifty-result.json).

**Verdict: neither variant works on the 2026 test period.**

| Variant | Period | Trades | Win rate | Mean net per trade (ETF costs) | Total (₹1 lakh per trade) | 95% lower bound |
|---|---|---|---|---|---|---|
| A: close → next close | in-sample 2024-04 to 2025-12 | 72 | 56% | +7.2 bp | +₹5,162 | −8.4 bp |
| **A** | **test 2026** | 51 | 51% | **−8.0 bp** | −₹4,073 | −34.4 bp |
| B: next open → close | in-sample | 72 | 47% | −3.3 bp | −₹2,409 | −16.4 bp |
| **B** | **test 2026** | 51 | 51% | **−7.2 bp** | −₹3,692 | −25.0 bp |

Under stock-like delivery costs (0.1% STT on both legs), both variants lose about 27 bp a trade on the test period.

For context on 2026:
- NIFTY buy-and-hold: −13.7%.
- Days that were *not* risk-off were followed by −10.5 bp on average.
- 28% of days were risk-off.

## Why

- **The tuning study's +14 to +20 bp was a stock-level average.** On the index itself the in-sample effect was only +7 bp per trade for variant A, and its lower bound was below zero. The cross-sectional average overstated what an index trade could capture.
- **On 2026 data the effect is gone in absolute terms.** In a falling year, risk-off days were followed by slightly *less bad* days (−8 bp against −10.5 bp), not good ones.
- **Most of the in-sample effect was overnight.** Variant B, which skips the overnight move, was negative even in-sample.

## Consequence

- No ETF strategy is added.
- The regime filter stays as decided: off for swing buys, on for intraday. Nothing else changes.
