# Global markets and NIFTY: result

Protocol: [global-markets-protocol.md](global-markets-protocol.md), pre-registered 2026-10-27. Numbers: [results/global-markets-result.json](results/global-markets-result.json).

Data:
- 12 Yahoo series and NIFTY 50 daily bars;
- 2,872 Indian sessions, 2015 to 2026-10-05;
- every input uses only what was known before 09:15 IST.

**Verdict:**
- **World markets predict NIFTY's opening gap strongly**, but that move is already in the open price.
- **After the open they predict nothing reliable**, neither the same day nor the next five days.
- The composite fails the gate for both trading targets. The global agent stays **observe-only**: context, not a trading input.

## Correlation of the composite with NIFTY (Spearman)

| Target | Train 2015–20 | Validate 2021–23 | Test 2024–26 | Pooled (90% interval) | Gate |
|---|---|---|---|---|---|
| Opening gap (sanity check) | **+0.41** | **+0.61** | **+0.51** | +0.49 (+0.46, +0.53) | not counted |
| Open to close | +0.10 | −0.02 | −0.06 | +0.02 (−0.01, +0.06) | **fail** |
| Open to 5 days | +0.03 | +0.02 | −0.02 | +0.01 (−0.02, +0.05) | **fail** |

## Global risk-off days (composite in its bottom 20%) vs other days, NIFTY mean in bp

| Period | Gap: risk-off / other | Open to close: risk-off / other | Open to 5 days: risk-off / other |
|---|---|---|---|
| Train | −26.5 / +21.8 | −21.6 / −6.2 | −32.9 / +22.4 |
| Validate | −40.2 / +25.8 | −6.5 / −4.8 | +1.4 / +24.6 |
| Test | −32.7 / +15.5 | −1.0 / −4.7 | +6.8 / −2.0 |

Bad global nights mean India opens about 0.3–0.4% lower. In 2015–20 the weakness also carried on through the day and the week. Since 2021 it has not: once India has opened lower, the rest of the day and week are no worse than usual.

## The best single inputs for the opening gap

| Input | Train | Validate | Test |
|---|---|---|---|
| **Asia gap** (Nikkei, Kospi, Hang Seng at their open) | **+0.54** | **+0.70** | **+0.50** |
| S&P 500 overnight | +0.42 | +0.62 | +0.48 |
| VIX change (inverted) | +0.38 | +0.52 | +0.47 |
| Brent (inverted) | −0.15 | −0.10 | +0.10 |
| USD/INR (inverted) | −0.02 | +0.04 | −0.00 |

Asia's opening move is the best guide to where NIFTY opens, because it already reflects the US close and Asian news. Crude oil and the rupee add almost nothing over a single night.

## What it means (no change is made without approval)

1. **A global-markets agent can honestly say where India is likely to open**, a strong and stable relationship. It cannot say whether buying after the open will pay.
2. **It should not block or size trades.** The 2015–20 risk-off effect has disappeared since 2021, so blocking buys on bad global nights would only have helped in the older period.
3. **Useful live roles that need no trading claim:**
   - an expected-open figure before 09:15, with the inputs shown;
   - a context line on each agent decision ("global risk-off night");
   - a log to keep testing the relationship forward.

## The live agent (built 2026-10-27)

`services/quant/src/quant_agents/global_markets.py` (agent id `global_markets`) runs the composite above, unchanged, on live Yahoo data at **08:45 and 09:10 IST** on NSE trading days.
- It publishes one market-level signal on NIFTY50: the expected opening gap, a usual range (± one residual standard deviation), every input, and a risk-off / risk-on flag.
- The expected gap is a straight-line fit of NIFTY's gap on the composite over the previous 250 sessions.
- It is **observe-only**: weight 0 in fusion (`MARKET_FILTER_AGENTS`), no role in the specialists decision, and not an `agents_agree` choice.
- Its signals are stored like any other agent's, so its calls can be checked against the actual open later.
- It can be turned off with `QUANT_GLOBAL_MARKETS=false`.

Check on live data, 2026-10-27, using the past year's fit (correlation 0.52):

| Session | Expected gap | Actual gap |
|---|---|---|
| 2026-10-23 | −0.13% | +0.24% |
| 2026-10-26 | −0.31% (risk-off) | −0.33% |
| 2026-10-27 | +0.21% | −0.20% |
