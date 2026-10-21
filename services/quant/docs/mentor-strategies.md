# The mentor's strategies, with and without a stop loss

Source: screenshots of his DAlgo settings and live tiles (2026-10-21). The parameters are his, not tuned here; each strategy was run once.

- Code: [`research/mentor_strategies.py`](../src/quant_agents/research/mentor_strategies.py)
- Raw output: [`results/mentor-strategies.json`](results/mentor-strategies.json)
- Data: 49 NIFTY 50 stocks, 5-minute and daily bars, **2024-04-01 to 2026-10-05**.

**Verdict:**
- **The "no losses" claim is true only for *realised* P&L, and only because losing trades are never sold.**
- Counting the losing positions he still holds or hands off (marked to market), both momentum strategies lose money or break even.
- Adding a stop loss makes them clearly unprofitable: the entries have no edge.
- The EMA-dip strategy makes a small profit, about 2.7% a year on the capital it ties up, which is less than a bank deposit pays.

## Why "no losses" appears

His settings:
- "Exit Same Day if Positive: Yes"
- "Square Off at EOD: No"
- no stop loss
- "Delivery Handoff Days: 30" (to an "Accumulator")

A trade therefore closes only at a target or at a profitable close. A losing trade is carried, and after 30 days it is handed to another strategy. The realised P&L can only show wins. His own tiles show the carried losses: M&M held at ₹3,347.40 against ₹2,754.60 now (−₹2,964, −18%), HYUNDAI −₹553 and INFY −₹653.

## Definitions (from the screenshots; my interpretation where a detail was not visible)

Common to all three strategies:
- ₹20,000 per entry and one position per stock, with at most 35 open positions (his "Position cap").
- A decision on a completed 5-minute bar fills at the next bar's open, plus 5 bp slippage.
- Targets are limit sells at the target price.
- A stop is checked from the fill bar on.

**1. Market Boom / Catalyst (momentum).**
- Scan 09:30–15:00 on every 5-minute bar. A buy needs all of:
  - day gain +0.5% to +0.75% against the previous close;
  - 3 green 5-minute candles in a row;
  - session volume above the prorated 10-day average;
  - price within ±3% of the 20-day EMA;
  - price at least 2% below the 20-day high.
- Exits: target 1 at +1% (sells half), target 2 at +1.5% (the rest). At 15:15, sell if the same-day net P&L after charges is positive; otherwise carry. After 30 calendar days the position is handed off.
- *Interpretation:* the tile values are used where they differ from the older settings page.

**2. New Pivotal.**
- Scan 10:00–13:00. A buy needs all of:
  - day gain +1% to +4%;
  - session volume above the prorated 10-day average;
  - **the first 5-minute close above the previous day's R1 pivot**, R1 = 2 × (H + L + C)/3 − L. This last condition is my interpretation: "Pivotal" implies a pivot level, and the trigger level itself was not visible.
- Exits: target 1 at +2% (half), target 2 at +3.5%. Same end-of-day and 30-day handoff rules as Market Boom. The handoff value for this strategy was cut off in the screenshot, so 30 days is assumed.

**3. EMA dip reversion ("List A" reactive dip).**
- Scan every 30 minutes. A buy needs all of:
  - price 5% to 12% below the 20-day EMA;
  - at least 3 consecutive down days;
  - today down at least 1%.
- A second tranche of ₹20,000 is bought when the price is 8% to 12% below the EMA.
- Exits: the first tranche sells when the price reaches the EMA, the rest at EMA + 3%. No end-of-day exit and no handoff.
- *Interpretation:* the first-tranche exit at the EMA (its exact target field was not visible).

**Not tested: the "Accumulator".** It is not in any screenshot. Positions handed off to it are valued at their market price on the handoff day.

**Stop-loss versions:**
- Market Boom: 1% below average cost (its target 2 is 1.5%).
- New Pivotal: 2% (target 2 is 3.5%).
- EMA dip: 10% below average cost.

Everything else is unchanged.

## Charges (Zerodha, checked against zerodha.com/charges on 2026-10-21)

| Charge | Delivery (held overnight) | Intraday (same-day round trip) |
|---|---|---|
| Brokerage | ₹0 | 0.03% or ₹20 per order, whichever is lower |
| STT | 0.1% buy and sell | 0.025% on the sell |
| NSE transaction | 0.00307% | 0.00307% |
| SEBI | ₹10 per crore | ₹10 per crore |
| Stamp duty | 0.015% on the buy | 0.003% on the buy |
| GST | 18% on brokerage + exchange + SEBI | same |
| DP | ₹15.34 per scrip per sell day (GST included) | none |

- A ₹20,000 round trip costs about ₹60 as delivery (0.30%) and about ₹21 as intraday (0.11%).
- A same-day sell of shares bought that day is priced at intraday rates with no DP fee. A later sell is priced at delivery rates.
- The paper engine, by its documented conservative choice, also charges DP on same-day sells. This study does not.

## Results, 2024-04-01 to 2026-10-05

| Strategy | Stop | Entries / closed sells | Closed losses | Realised net | Still open at end | Handed off after 30 days | **Total incl. open and handed off** | Peak capital tied up | Max drawdown |
|---|---|---|---|---|---|---|---|---|---|
| Market Boom | none (his) | 1,087 / 1,634 | **0** | **+₹1,45,146** | 12, all losing (−₹10,204) | 162 (−₹1,65,445) | **−₹30,503** | ₹3.61 lakh | ₹47,371 |
| Market Boom | 1% | 1,511 / 1,997 | 797 | −₹87,352 | 0 | 0 | **−₹87,352** | ₹1.17 lakh | ₹88,093 |
| New Pivotal | none (his) | 1,118 / 1,397 | **0** | **+₹2,75,235** | 16 (−₹10,555) | 282 (−₹2,58,801) | **+₹5,880** | ₹5.23 lakh | ₹57,032 |
| New Pivotal | 2% | 1,498 / 1,932 | 694 | −₹84,777 | 5 (−₹466) | 2 (+₹319) | **−₹84,924** | ₹2.30 lakh | ₹84,972 |
| EMA dip | none (his) | 238 / 316 | 101 | +₹67,234 | 16 (−₹8,214; oldest 118 days) | n/a | **+₹59,020** | ₹8.56 lakh | ₹67,207 |
| EMA dip | 10% | 253 / 314 | 91 | +₹29,087 | 14 (−₹4,210) | n/a | **+₹24,877** | ₹7.03 lakh | ₹65,450 |

A position sold in two halves (target 1, then target 2) counts as one entry and two closed sells.

**What this shows:**
- **Momentum strategies.** The realised P&L is all wins and looks excellent: +₹1.45 lakh and +₹2.75 lakh. But many entries never come back: 174 of 1,087 (16%) for Market Boom and 298 of 1,118 (27%) for New Pivotal were still losing at the 30-day handoff or at the end of the data. The losses carried in those trades cancel the wins: Market Boom ends **−₹30,503**, New Pivotal **+₹5,880**, essentially zero on ₹5.2 lakh of capital over 2.5 years.
- **With a stop**, the losses are taken instead of carried, and both momentum strategies lose about ₹85,000. The win rate is about 60%, but targets of +1% to +1.5% after charges are smaller than the stops.
- **EMA dip** closes losing trades even without a stop. After a fall the 20-day EMA itself drops below the entry price, so "sell at the EMA" can be a loss.
  - It makes +₹59,020 in total on up to ₹8.56 lakh tied up: **6.9% over 2.5 years**, about 2.7% a year, with drawdowns of ₹67,000 along the way.
  - With a 10% stop: +₹24,877, and it lost money in 2026.

## Practical conclusion

- The strategies do not avoid losses; they defer them into positions that stay open.
- Without stops, capital piles up in losers: the peak capital tied up is 3–9× the money that is actively trading.
- None of the three earns a return worth its risk on this data.
- None of them should be added to paper trading as a profit source. The EMA dip strategy could be an optional Strategy Lab example, if the user asks.
