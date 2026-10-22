# News categories vs the NIFTY 50 index

Status: **PRE-REGISTERED before any GDELT pull, any price download, or any event study for this question.** No category query, threshold, window, or pass rule below may be edited after the first train table is computed. Validate is scored once.

This file follows the same rule as [dip-reversion-protocol.md](dip-reversion-protocol.md): the method is frozen here, and the result file is a later document.

## Question

Do volume spikes in ten categories of news move the **NIFTY 50 index**, including news that never names a NIFTY 50 company (wars abroad, oil shocks, RBI or Fed decisions, tariffs, elections)?

The outcome is the index only. Individual stocks are not tested. This study does not add a fusion vote, does not change agent scores, and does not change risk or the decision engine.

## What this study will not change

- Live and paper trading behaviour stay as they are.
- Fusion weights, the decision engine, risk limits, and every agent's live score stay as they are.
- No new agent vote is added.
- A later capture switch for market-wide headlines defaults to off. Turning it on is outside this study and is not a trading-rule change by itself.
- Raw GDELT responses and raw price caches are local only. They are not committed. The committed outputs are this protocol, the result note, and one small JSON of summary numbers.

If nothing passes the rule at the end of this file, that negative result is the result. It is not a reason to retune.

