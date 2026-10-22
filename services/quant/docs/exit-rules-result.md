# Exit-rules study: result

Scored once under [`exit-rules-protocol.md`](exit-rules-protocol.md) (committed first, `32d14fc`). Raw output: [`results/exit-rules-result.json`](results/exit-rules-result.json).

**Verdict: no exit rule beats the live one, and no rule is profitable. The live exits stay unchanged.**

## INTRADAY book (5-minute signals, 250 sessions, 2025-09-24 to 2026-10-05)

| Rule | Trades | Win rate | Mean net / trade | Total net P&L | Profit factor | Beats live? |
|---|---|---|---|---|---|---|
| E0 live (−2% / +4%, signal exit) | 20,706 | 15.6% | −0.40% | −₹15.55 lakh | 0.28 | — |
| E1 volatility-scaled | 20,614 | 15.5% | −0.40% | −₹15.34 lakh | 0.28 | no (bound −7.7) |
| E2 5-session max hold | 20,706 | 15.6% | −0.40% | −₹15.55 lakh | 0.28 | no (identical: no trade lasts 5 sessions) |
| E3 15:15 square-off | 23,771 | 15.4% | −0.41% | −₹18.05 lakh | 0.19 | no (worse in both halves) |
| E4 combined | 23,738 | 15.4% | −0.41% | −₹18.01 lakh | 0.19 | no |

## SWING book (daily signals, 556 sessions, 2024-07-01 to 2026-10-05)

| Rule | Trades | Win rate | Mean net / trade | Total net P&L | Profit factor | Avg hold | Beats live? |
|---|---|---|---|---|---|---|---|
| E0 live | 2,418 | 30.8% | −0.54% | −₹2.47 lakh | 0.67 | 3.8 sessions | — |
| E1 volatility-scaled | 2,203 | 30.9% | −0.52% | −₹2.15 lakh | 0.70 | 4.5 | no (bound −36.8) |
| E2 5-session max hold | 2,925 | 34.7% | −0.51% | −₹2.82 lakh | 0.63 | 2.7 | no (worse in both halves) |
| E4 combined | 2,817 | 35.5% | −0.49% | −₹2.57 lakh | 0.65 | 2.9 | no |

Trades are ₹20,000 each with Zerodha delivery charges and 5 bp slippage per fill. No portfolio caps apply, so totals are far larger than the live book, which takes at most 6 entries a day.

## What it means

- **Volatility-scaled stops (E1) lose slightly less in both books, and in both halves of each period.** The improvement is too small to pass the gate. The Bonferroni lower bound on the per-session difference is below zero. It does not qualify, and the protocol forbids tuning it now.
- **Time exits hurt.** A 15:15 square-off and a 5-session cap both cut trades that would later have recovered or hit their target.
- **The real problem is the entries, not the exits.**
  - Intraday, 97% of trades end on a *signal exit*. The average hold is about 0.25 sessions. The fused 5-minute signal flips from buy to sell within a few bars, so each round trip pays roughly 0.3% in charges and slippage for almost no move.
  - Swing, 63% of trades hit the −2% stop before the +4% target, and the win rate is 31%.
  - No exit rule can rescue entries without an edge. This matches studies 1–3.

## Consequences for paper trading

- The live exit rule is unchanged.
- Not pre-registered here, so not a finding: the intraday churn suggests adding hysteresis to signal exits, such as a minimum hold or a stronger opposite signal. Turning off intraday auto-entries is another option. Either would need its own pre-registered test before any change. Users can already turn auto-entries off in Settings.
