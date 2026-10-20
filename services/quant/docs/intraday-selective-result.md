# Selective intraday trading on the validated signal: result

Scored once under [`intraday-selective-protocol.md`](intraday-selective-protocol.md), which was committed first (`778f8b6`). Raw output: [`results/intraday-selective-result.json`](results/intraday-selective-result.json).

**Verdict: does not work.**
- All 18 settings lose money on train, at ₹35–40 a trade.
- The chosen setting also loses on validation and test.
- Intraday auto-entries stay off.

## Train (Apr 2024 – Jun 2025): every setting loses

| Threshold | Selection | Trades | Net per trade (by hold: 60 min / 2 h / to 15:15) |
|---|---|---|---|
| 0.4 | all | 11,545 | −₹39.6 / −₹37.0 / −₹39.3 |
| 0.4 | top 1 | 6,062 | −₹36.3 / −₹35.3 / −₹35.4 |
| 0.6 | all | 11,187 | −₹39.5 / −₹36.5 / −₹38.8 |
| 0.6 | top 1 | 5,932 | −₹36.1 / −₹35.5 / −₹35.5 |
| 0.8 | all | 10,068 | −₹37.8 / −₹35.3 / −₹37.6 |
| 0.8 | top 1 | 5,598 | −₹36.1 / −₹35.7 / −₹35.6 |

## Chosen setting (threshold 0.8, strongest stock only, hold to 15:15)

| Period | Trades | Win rate | Net per trade | Total net | Session P&L 90% low |
|---|---|---|---|---|---|
| Train | 5,598 | 39% | −₹35.6 | −₹1.99 lakh | −₹768 |
| Validate | 2,463 | 35% | −₹40.9 | −₹1.01 lakh | −₹932 |
| Test (2026) | 3,507 | 36% | −₹43.4 | −₹1.52 lakh | −₹1,003 |

## Why

- **There is no edge before costs for a long-only trader.** A ₹20,000 intraday round trip costs ₹41.26: ₹21.26 in Zerodha MIS charges plus ₹20 of slippage. Adding that back, the chosen setting's *gross* result is +₹5.7, +₹0.4 and −₹2.1 per trade on train, validate and test: break-even before costs, a loss after.
- **The validated edge is relative, not absolute.** The positive IC says which stocks do better than the others over the next hour. A long-only book still carries the whole market's move, which swamps a ranking edge this small. Capturing it would need a long-short, market-neutral book: buy the top-ranked stocks and short the bottom-ranked. The paper engine and cash-equity intraday rules don't support that here.
- **Higher thresholds barely cut trades.** The fused signal is built from discrete votes, so it clusters at its extremes; at most one trade per stock per day is what actually limits the count.

## Consequence

- Intraday auto-entries stay **off**. The intraday agents keep publishing and being scored.
- Across this project's studies, the only predictive edges found are the volatility forecast (study 3) and this small cross-sectional intraday ranking. Neither pays as a long-only trading rule after Indian retail costs.
