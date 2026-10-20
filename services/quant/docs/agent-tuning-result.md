# Quant-agent backtest and tuning: result

Scored once under [`agent-tuning-protocol.md`](agent-tuning-protocol.md), which was committed first (`97a6355`). Raw output: [`results/agent-tuning-result.json`](results/agent-tuning-result.json). The study covers 49 NIFTY 50 stocks with the real Feature Engine 1.2.0 features: train on Apr 2024–Jun 2025, validate on Jul–Dec 2025, and test once on Jan–Oct 2026.

**Replication check passed.** The array re-implementation reproduced the real 1.3.0 agents exactly (0 mismatches on 1,960 random bars per timeframe).

**Verdict: the tuned system does not work under the protocol on either horizon.**
- Swing: no agent kept a validated edge.
- Intraday: a small, real edge survives to the test period (fused IC +0.011, 90% lower bound +0.0065), but it is far too small to cover trading costs (−₹4.72 lakh over 10,618 trades).

## Swing (daily bars; next-session return)

| Agent | 1.3.0 train IC | Best setting on train | Train IC | Validate IC (90% low) | Kept |
|---|---|---|---|---|---|
| Technical | +0.009 | no dead band | +0.012 | −0.019 (−0.034) | no |
| Momentum | **−0.020** | **inverted**, z 1.0, ADX 15 | +0.021 | +0.015 (−0.001) | no |
| Mean reversion | −0.001 | inverted, ADX 15 | +0.012 | −0.004 (−0.021) | no |
| Volume | **−0.018** | **inverted**, surge 2 | +0.018 | 0.000 (−0.023) | no |

All fusion weights are 0, so the tuned swing system makes no trades.

| Swing test (2026) | IC (90% low) | Trades | Win rate | Net P&L |
|---|---|---|---|---|
| Tuned | — (no trades) | 0 | — | ₹0 |
| 1.3.0, equal weights | **−0.026 (−0.045)** | 605 | 27% | **−₹82,430** |

The current swing agents are reliably *wrong-signed* on the test period. Stocks that the trend and volume rules favour tend to fall the next day: a short-term reversal effect in large caps.

## Intraday (5-minute bars; 60-minute return)

| Agent | 1.3.0 train IC | Best setting on train | Train IC | Validate IC (90% low) | Kept | Weight |
|---|---|---|---|---|---|---|
| Technical | −0.005 | inverted, dead band ×2 | +0.006 | +0.006 (−0.001) | no | 0 |
| Momentum | **−0.015** | **inverted**, z 1.0, ADX 20 | +0.018 | +0.012 (+0.007) | yes | 0.575 |
| Mean reversion | +0.004 | never abstain (no ADX gate) | +0.009 | +0.006 (+0.001) | yes | 0.300 |
| Volume | −0.004 | inverted, surge 3 | +0.004 | +0.005 (+0.003) | yes | 0.125 |

| Intraday test (2026) | IC (90% low) | Trades | Win rate | Per trade | Net P&L | Session P&L 90% low |
|---|---|---|---|---|---|---|
| Tuned | **+0.011 (+0.0065)** | 10,618 | 42% | −₹44 | **−₹4.72 lakh** | −₹2,899 |
| 1.3.0, equal weights | −0.007 (−0.013) | 14,318 | 28% | −₹38 | −₹5.48 lakh | −₹3,250 |

The tuned intraday signal passes the IC half of the gate on unseen data, which is the first out-of-sample predictive edge in this project. It fails the trading half. An IC of 0.011 is about a basis point of edge per trade, against roughly 15 bp of round-trip charges and slippage. 62% of trades end on a signal flip.

## Regime as a market filter

| | Share of periods risk-off | Next-period return, risk-off | Next-period return, other |
|---|---|---|---|
| Swing, train | 19% | **+14.2 bp** | +3.1 bp |
| Swing, validate | 12% | **+19.5 bp** | +2.3 bp |
| Intraday, train | 21% | −0.8 bp | +0.7 bp |
| Intraday, validate | 21% | −0.8 bp | −0.1 bp |

For swing trades, the filter blocks buys on the days that were followed by the *best* next-day returns (the market rebounds after fear). Intraday it helps slightly.

## What this means (no change is made without approval)

1. **Swing:** the quant agents have no validated edge, and the current versions are wrong-signed. They should not drive swing entries, and the regime filter should not block swing buys.
2. **Momentum, as built, is backwards on NIFTY 50 at both horizons.** Inverting it gives a short-term reversal signal: validated intraday, borderline on swing.
3. **Intraday:** a real but tiny edge. It cannot be traded profitably with one ₹20,000 order per signal under Zerodha charges, so intraday auto-entries should stay off. Pursuing it would need far fewer, higher-conviction trades, which would be a new pre-registered study.
4. None of this tests the intelligence agents; they are judged on the live scorecard only.
