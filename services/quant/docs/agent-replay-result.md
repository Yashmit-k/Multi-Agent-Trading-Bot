# Agent replay (swing): result

Protocol: [agent-replay-protocol.md](agent-replay-protocol.md), pre-registered 2026-10-26. Numbers: [results/agent-replay-result.json](results/agent-replay-result.json).

Setup:
- 49 NIFTY 50 stocks, daily bars;
- the live swing order rules: limit at close + 0.25%, stop −2% and target +4% from the signal close, gap fills at the open;
- a 10-session cap, which is an assumption (live has none);
- ₹20,000 per trade, Zerodha delivery charges.

A round trip of ₹20,000 costs about ₹62 in charges (STT alone is ₹40), so a trade needs about +0.3% before it breaks even.

## 1. Each quant agent trading alone

| Agent | Period | Trades | Win rate | Net P&L | Per trade (90% CI) |
|---|---|---|---|---|---|
| Technical | train | 1,838 | 33% | −₹1,24,949 | −₹68 (−89, −47) |
| | validate | 582 | 35% | −₹46,607 | −₹80 (−114, −46) |
| | test | 887 | 28% | −₹1,16,003 | −₹131 (−160, −103) |
| Momentum | train | 1,421 | 31% | −₹1,26,260 | −₹89 (−113, −64) |
| | validate | 394 | 37% | −₹22,684 | −₹58 (−100, −12) |
| | test | 743 | 28% | −₹84,598 | −₹114 (−146, −84) |
| Mean reversion | train | 167 | 38% | −₹936 | −₹6 (−76, +64) |
| | validate | 83 | 42% | −₹1,524 | −₹18 (−111, +76) |
| | test | 178 | 19% | −₹32,168 | −₹181 (−234, −125) |
| Volume | train | 736 | 32% | −₹60,953 | −₹83 (−115, −49) |
| | validate | 213 | 45% | +₹6,803 | +₹32 (−33, +98) |
| | test | 426 | 23% | −₹67,544 | −₹159 (−197, −119) |

**No agent makes money alone.** Technical and momentum lose in every period, with the whole 90% interval below zero. Mean reversion and volume each have one near-flat period, but their intervals include zero and both lose clearly in 2026.

About two-thirds of all exits are stops. In train the average trade's gross is close to zero, so the loss is mostly charges. In 2026 the gross is negative as well.

## 2. Are the specialists blockers useful?

The candidates are every session where technical or momentum triggers (filled: 6,763 train, 2,653 validate, 3,396 test). Mean net per candidate, at ₹20,000:

| Step | Period | Blocked (n) | Blocked mean (90% CI) | Passed mean |
|---|---|---|---|---|
| Volume ≤ −0.30 | train | 293 | −₹67 (−119, −12) | −₹78 |
| | validate | 69 | −₹20 (−117, +91) | −₹67 |
| | test | 190 | **−₹155 (−213, −96)** | −₹125 |
| Mean reversion ≤ −0.50 | train | 455 | −₹58 (−99, −17) | −₹79 |
| | validate | 136 | −₹54 (−125, +22) | −₹66 |
| | test | 184 | **−₹150 (−203, −97)** | −₹125 |
| Regime risk-off (half size) | train | 717 | −₹58 (−91, −24) | −₹80 |
| | validate | 213 | −₹27 (−88, +35) | −₹69 |
| | test | 555 | **−₹136 (−171, −100)** | −₹124 |

Under the pre-registered rule (blocked worse than passed, with the blocked interval below zero, in at least two of three periods), **none of the three steps is useful**. Each one meets the rule only in 2026. In 2024–25 the trades they removed were, if anything, a little *less* bad than the ones they kept. This agrees with the tuning study, where risk-off days were followed by better-than-average next-day returns.

## 3. Trigger only vs full specialists

| Period | Rule | Trades | Win rate | Net P&L | Per trade (90% CI) |
|---|---|---|---|---|---|
| train | trigger only | 1,966 | 33% | −₹1,27,022 | −₹65 (−84, −45) |
| | specialists | 1,837 | 32% | −₹1,29,609 | −₹71 (−91, −50) |
| validate | trigger only | 599 | 34% | −₹50,986 | −₹85 (−118, −50) |
| | specialists | 556 | 35% | −₹44,891 | −₹81 (−115, −47) |
| test | trigger only | 998 | 28% | −₹1,22,915 | −₹123 (−150, −97) |
| | specialists | 922 | 28% | −₹99,402 | −₹108 (−133, −81) |

The blockers remove only about 7% of trades, and the per-trade loss barely moves. The specialists rule loses less money in 2026 mostly because it trades less and the half size shrinks some losers. It does not change the sign.

## What this means (no change is made without approval)

1. **The live swing entries have no edge on past data.** The trigger agents (technical, momentum) lose in every period, and the blockers do not fix it. This matches the tuning study, where the swing quant agents are wrong-signed or flat.
2. **The specialists mode is a clear, explainable structure, not a profitable strategy.** That is how it should be presented: every agent has a visible job, and the risk engine, the ₹20k size and the 6-per-day cap are what keep the losses small.
3. **The LLM agents were not tested here.** No past news archive exists. Whether the news and earnings blocks help can only be learned from the live record, which needs months, not 16 sessions.
4. **Limits of this replay:**
   - no daily cap of 6 and no portfolio cash limit, so there are more trades than live;
   - the 10-session time cap is an assumption;
   - the regime test uses NIFTY EMA-12/26 and the VIX daily change, which approximates the regime agent's two votes.
