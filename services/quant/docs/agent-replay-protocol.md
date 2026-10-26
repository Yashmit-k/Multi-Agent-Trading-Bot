# Agent replay (swing): pre-registered protocol

Status: **PRE-REGISTERED 2026-10-26, before any result of this study was computed.**

Questions:
1. If each quant agent traded **alone**, with the live swing order rules, would it have made money?
2. In the live **specialists** decision, does each blocker (volume, mean reversion) remove worse trades than it keeps, and does the regime's half-size step land on worse days?
3. Does the full specialists rule beat "trigger only" (technical or momentum, no blockers)?

This is a description of past behaviour, not a tuning study: no setting is chosen from these numbers, and no change follows without a separate, approved decision.

## Data and agents

- The cached daily features of `agent_tuning.py` (Feature Engine 1.2.0, 49 stocks, `datasets/research/agent_tuning/features-<SYM>-1d.npz`), NIFTY 50 and INDIA VIX from the same cache.
- The array re-implementation of the swing agents with `DEFAULTS`. Swing rules are unchanged in 1.4.0 (only intraday changed), and the re-implementation reproduced the real agents with 0 mismatches.
- Periods, as in the tuning study: train 2024-04-01 to 2025-06-30, validate 2025-07-01 to 2025-12-31, test 2026-01-01 to 2026-10-05. All three are reported. Nothing is selected on any of them.
- The LLM agents (news, earnings, fundamental, valuation) cannot be replayed: there is no point-in-time archive of past news or financials. Their live record (since 3 Oct 2026, about 16 sessions) is too short to judge and is not part of this study. In the specialists replay they are treated as "no opinion", which is what the live rule does with a fallback answer.

## Trade rules (the live swing rules)

- **Signal:** at a session's daily close. BUY when signal ≥ 0.30 and confidence ≥ 0.40 (the specialists trigger threshold).
- **Entry:** the next session only. Limit at the signal close + 0.25%, floored to the ₹0.05 tick. It fills at the open if the open ≤ limit, otherwise at the limit if the low ≤ limit, otherwise no trade.
- **Brackets:** stop at 98% and target at 104% of the signal close (the proposal's entry price), as `propose._brackets`.
- **Exits:** checked on each later session's bar:
  - stop first, then target;
  - a gap fills at the open when it is beyond the level: stop at min(stop, open), target at max(target, open);
  - on the entry session, only the stop is checked (as the Strategy Lab does).
- **Time cap:** sell at the close of the 10th session after entry. Live swing holdings have no time cap, so this assumption is stated and its exits are reported separately.
- **Size:** ₹20,000 per trade (₹10,000 when the regime step halves it in question 2 and 3). One position per stock at a time; no daily cap (live has 6 per day: this is noted, not modelled).
- **Costs:** Zerodha delivery charges, `strategy_lab.leg_charges(..., "CNC")`, DP charge included. No slippage on the limit entry; 5 bp slippage on exits.

## Question 2: blockers

The candidates are every session where technical or momentum triggers. Each candidate is simulated as its own trade (no one-position rule here, so each blocker is judged on the same set). For each step:
- volume blocks at ≤ −0.30;
- mean reversion blocks at ≤ −0.50;
- regime risk-off = NIFTY EMA-12 < EMA-26 and the India VIX daily return > 0.

The report gives, for blocked vs passed candidates: count, mean net per trade (₹, at ₹20,000) with a 90% bootstrap interval over trades, and win rate.

**A blocker counts as useful only if**, in at least two of the three periods, the blocked trades' mean net is below the passed trades' mean net and the upper end of the blocked trades' 90% interval is below zero.

## Question 3

Trigger-only vs full specialists (blockers and half size), with the trade rules above, including one position per stock. Reported per period:
- trades, win rate, total net and mean net per trade;
- the 10th-percentile bootstrap of mean session P&L.

## Output

- `services/quant/docs/results/agent-replay-result.json`;
- `services/quant/docs/agent-replay-result.md`, with every table and a plain-language reading.

Run:

```
python -m quant_agents.research.agent_replay
```
