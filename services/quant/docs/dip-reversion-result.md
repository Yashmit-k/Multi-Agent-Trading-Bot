# EMA dip reversion, refined: result

Scored once under [`dip-reversion-protocol.md`](dip-reversion-protocol.md). Raw output: [`results/dip-reversion-result.json`](results/dip-reversion-result.json).

**Not committed before the run.** The user chose not to commit the protocol first. Instead, the SHA-256 fingerprints of the protocol and code were recorded at 2026-10-20T20:49:36Z, immediately before the run:
- protocol `eb4347fc…3e274a`
- code `d5f9789f…e3ac3f6`

**Verdict: the refined strategy passes all four pre-registered gates on 2021–2023, nine years of data no study had used. The edge is real but small in rupees, and it depends on rising markets.**

## The chosen variant (`fixed-t15-s10-idio-2tr`)

- Buy a NIFTY 50 stock at the next open after its close is 5–12% below its 20-day EMA, after 3 lower closes and a down day of at least 1%, **when the stock fell at least 4% more than NIFTY over 5 days** (a stock-specific dip).
- Add a second ₹20,000 if it reaches 8–12% below the EMA.
- Sell the first tranche at the **EMA level frozen at the signal**, and the rest 3% above it.
- **Stop at 10%** below average cost, and **exit after 15 sessions** if no target is hit.
- At most 20 positions, ₹20,000 per tranche, Zerodha delivery charges.

## Gates (2021-01-01 to 2023-12-31)

| Gate | Result |
|---|---|
| Total net > 0 | **+₹62,935** (132 positions, 68% winners) |
| Annual return on average deployed capital ≥ max(7%, NIFTY's 15.8%) | **40.1%** |
| 95% lower bound of mean net per position > 0 | **+₹200** |
| Profitable in 2021, 2022 and 2023 separately | +₹18,985 / +₹40,805 / **+₹2,195** |

## The full picture

| Period | Positions | Total net | Return on avg. deployed | **Return on peak capital** | Max drawdown | NIFTY buy-and-hold |
|---|---|---|---|---|---|---|
| Train 2015–2020 (chosen here) | 337 | +₹83,338 | 21.3% a year | **4.3% a year** | ₹44,684 | 7.9% a year |
| **Validate 2021–2023 (unseen)** | 132 | +₹62,935 | 40.1% a year | **6.7% a year** | ₹16,836 | 15.8% a year |
| Seen 2024–2026 | 124 | +₹21,083 | 13.9% a year | **2.1% a year** | ₹21,286 | 0.2% a year |
| Former members, train | 223 | −₹7,213 | −2.8% a year | — | ₹48,052 | 7.9% a year |
| Former members, validate | 82 | +₹22,766 | 24.1% a year | — | ₹18,890 | 15.8% a year |
| Former members, seen | 56 | +₹8,040 | 11.4% a year | — | ₹17,396 | 0.2% a year |
| Mentor's rule, train | 432 | +₹39,097 | 6.0% a year | — | **₹2,24,706** | 7.9% a year |
| Mentor's rule, validate | 197 | +₹97,980 | 36.0% a year | — | ₹35,739 | 15.8% a year |
| Mentor's rule, seen | 178 | +₹11,327 | 3.8% a year | — | ₹55,347 | 0.2% a year |

**Neighbours on validate** (one setting changed at a time): every one is profitable, at 28–49% a year on deployed capital. The result is not a knife-edge choice.

**Delayed-fill check:** shifting fills one session later reduces the totals (validate +₹50,108 instead of +₹62,935) but keeps them positive.

## What this means

- **The refinement works where it was meant to.**
  - Freezing the exit level, the stop and the 15-day time limit cut the mentor rule's ₹2.25 lakh train drawdown to ₹45,000.
  - No position is held more than 60 sessions; the mentor rule held some for months.
  - It beat the mentor rule on train (+₹83,338 vs +₹39,097) and on 2024–2026 (+₹21,083 vs +₹11,327).
  - On 2021–2023 it made less (+₹62,935 vs +₹97,980), using about half the capital and with half the drawdown.
- **Small in absolute terms.** The strategy holds about 3 positions on average but up to 16–20 in a sell-off. To run it you must keep about ₹3.3–4 lakh ready, and on that capital it earned **2–7% a year**: ₹8,000–21,000 a year. The 40% figure counts only the money actually invested on a given day. The idle cash could sit in a liquid fund in between, but that is outside this test.
- **It depends on the market.** It earned most in the 2021–2023 bull market, only +₹2,195 in 2023, and its 2024–2026 lower bound is below zero. On former NIFTY members it lost money in 2015–2020. Buying dips works when the market recovers; a long bear market would hurt it.
- **Recommendation:** a paper forward test is justified. Real money is not, until the forward test confirms it.

## Cross-check: the Strategy Lab's backtester on the same data

The chosen variant was rebuilt as a Strategy Lab definition using three new Lab features (return vs NIFTY, a target frozen at a level read at the signal, and an add-on), then run through the Lab's own backtester on the same 2015–2026 file:

| Period | Research engine | Strategy Lab, 20 positions | Strategy Lab, 10 positions |
|---|---|---|---|
| Train 2015–2020 | +₹83,338 | +₹90,155 | +₹87,649 |
| **Validate 2021–2023** | **+₹62,935** | **+₹36,121** | **+₹38,105** |
| Seen 2024–2026 | +₹21,083 | +₹9,859 | +₹7,841 |

The implementations differ in three ways, all in the Lab's paper-trading rules:
1. **Entry fill.** The Lab, like the paper engine, buys with a limit at the signal close + 0.25%, on the next session only. A stock that gaps up past the limit is not bought. The research engine buys at the next open whatever the price. On 2021–2023 the Lab took 115 trades against the research engine's 132, and the missed ones were mostly winners: a gap up after a dip is the reversal starting.
2. **Target timing.** The Lab checks targets from the bar after the fill; the research engine also checks the fill day.
3. **Add-on timing.** The Lab does not let an add-on signal fire on the fill day itself.

**The paper forward test runs the Lab's rules, so judge it against the Lab column.** That is about half the research result on 2021–2023, and still positive in every period.
