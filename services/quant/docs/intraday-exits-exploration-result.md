# Intraday stop/target exploration: result (exploratory)

Run under [`intraday-exits-exploration-protocol.md`](intraday-exits-exploration-protocol.md) (`4728e32`). Raw output: [`results/intraday-exits-exploration.json`](results/intraday-exits-exploration.json). This is **exploratory**: the 2026 data had already been seen.

**Verdict: no stop/target pair makes the selective intraday entry profitable.** All 20 settings lose on train. Adding a target makes it worse.

## Train (Apr 2024 – Jun 2025), net per trade, 5,598 trades each

| Stop \ Target | none | 0.5% | 1% | 1.5% | 2% |
|---|---|---|---|---|---|
| 1% | −₹35.3 | −₹41.3 | −₹39.2 | −₹37.5 | −₹36.7 |
| 1.5% | −₹35.2 | −₹40.9 | −₹39.1 | −₹37.7 | −₹36.9 |
| 2% | −₹35.6 | −₹41.2 | −₹39.3 | −₹37.9 | −₹37.2 |
| 3% | **−₹34.6** | −₹39.9 | −₹38.2 | −₹37.0 | −₹36.3 |

The least bad setting (3% stop, no target) on later periods:

| Period | Total net |
|---|---|
| Validate (Jul – Dec 2025) | −₹1.01 lakh |
| 2026 (already seen) | −₹1.53 lakh |

## Why

- **The entries have no edge before costs.** They are roughly break-even before the ₹41.26 round-trip cost, so exits can only redistribute outcomes: a stop or target changes how often a trade wins, not the average.
- **Targets cut the winners short.** The few large moves that partly offset the losers are capped, which is why every target makes the result worse and a tighter target makes it worse still.
- **This matches the earlier exit-rules study,** which also found no exit rule that beats the baseline on entries without an edge.

Not worth a fresh test. Intraday auto-entries stay off.
