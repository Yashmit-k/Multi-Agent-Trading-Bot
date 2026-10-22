# EMA dip reversion, refined: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-21, before any of these variants was run on any period.**

Origin: the mentor's EMA-dip strategy was the only one of his three with a positive total on 2024–2026, at about 2.7% a year on the capital it tied up ([mentor-strategies.md](mentor-strategies.md)). This study asks whether a refinement holds up on **nine years of data no study has used** (2015–2023).

## Data

- Daily bars from 2015-01-01 to 2026-10-05, pulled read-only from Zerodha Kite on 2026-10-21 into `datasets/research/dip_history/daily_2015_2026.jsonl`. Split and bonus adjusted.
- **Universe A:** the 49 current NIFTY 50 stocks with history (TATAMOTORS has none after its symbol change).
- **Universe B (survivorship check):** 18 former NIFTY 50 members that are still listed: YESBANK, IDEA, ZEEL, VEDL, IOC, GAIL, UPL, BOSCHLTD, AUROPHARMA, LUPIN, BHEL, ACC, AMBUJACEM, BANKBARODA, HINDPETRO, DIVISLAB, SHREECEM, INDUSTOWER.
  - This is a best-effort list; exact membership dates are not used.
  - Delisted former members, such as HDFC Ltd, have no data, so some survivorship bias remains.
- **Corporate actions:** a session that opens more than 20% away from the previous close is treated as a corporate action, not a price move. Any open position in that stock is closed at the previous close, with charges, and no signal fires in that stock for the next 20 sessions.

| Period | Dates | Use |
|---|---|---|
| Train | 2015-03-01 to 2020-12-31 | choose one variant (Universe A) |
| Validate | 2021-01-01 to 2023-12-31 | **gate, never seen** (Universe A) |
| Seen | 2024-04-01 to 2026-10-05 | reported only: the mentor run used it |

Each period starts with an empty book. Positions still open at a period's end are marked at the last close, less delivery charges.

## Base rule (the mentor's, on daily bars)

The EMA is the 20-day EMA of closes through the previous session.

- **Signal:** on day *k*'s close, all of:
  - close 5% to 12% below the EMA;
  - at least 3 consecutive lower closes ending on day *k*−1;
  - day *k* down at least 1%.
- **Entry:** buy ₹20,000 at day *k*+1's open, plus 5 bp slippage.
- **Second tranche (when enabled):** on a later close 8% to 12% below the EMA, buy another ₹20,000 at the next open, once per position.
- **Exits:**
  - the first tranche's quantity sells when the day's high reaches the exit level (at the open if it opens above);
  - the rest sells at the exit level + 3%.
- **Book:** at most 20 open positions, counting pending entries; one position per stock.
- **Ordering:** when more signals fire than there are free slots, the stocks furthest below their EMA go first.
- **Daily order of operations:** corporate-action check → fills at the open → price stop → exit levels → time stop at the close → new signals at the close.
- **Charges:** Zerodha delivery (zero brokerage, STT 0.1% both sides, stamp 0.015%, NSE 0.00307%, SEBI, GST, DP ₹15.34 per sell). Same-day round trips cannot happen on daily bars.

## Refinements (2 × 2 × 2 × 2 × 2 = 32 variants)

| Dimension | Options | Why |
|---|---|---|
| Exit level | `ema`: the current EMA (mentor) · `fixed`: the EMA at the signal, frozen | After a fall the EMA itself drops, so "sell at the EMA" can sell below cost (101 of the mentor run's 316 sells were losses) |
| Time stop | none · 15 sessions | Free capital from positions that do not recover |
| Price stop | none · 10% below average cost | Limit the damage from a real collapse |
| Market filter | none · stock-specific dips only: the stock's 5-day return minus NIFTY's ≤ −4% | Buy a stock's own over-reaction, not a market-wide fall |
| Second tranche | on · off | Averaging down raises both return and risk |

Time stops and price stops are checked on the close (time) and the low (price; at the open on a gap).

## Measures (per variant, period and universe)

- Entries; closed positions; win rate.
- Realised net; open positions marked to market.
- **Total net**, **average capital deployed** and **annualised return on average deployed capital** (total net ÷ average deployed ÷ years).
- Peak capital; maximum drawdown of total net.
- Positions held more than 60 sessions.
- NIFTY 50 buy-and-hold annualised return over the same period.

## Selection (train, Universe A)

Choose the variant with the highest annualised return on average deployed capital among those with at least 150 entries. A tie goes to the smaller maximum drawdown.

## Gate (validate, Universe A, scored once)

The refined strategy **passes** only if all of these hold:
1. total net > 0;
2. annualised return on average deployed capital ≥ the larger of 7% (a bank deposit) and NIFTY 50 buy-and-hold's annualised return over 2021–2023;
3. the 95% bootstrap lower bound (2,000 resamples, seed 0) of the mean net per position is > 0, counting positions open at the end at market value;
4. total net > 0 in each of 2021, 2022 and 2023, each run on its own with an empty book and marked at the year's last close.

## Reported, not gated

- The same chosen variant on Universe B and on the seen 2024–2026 period.
- Its neighbours, meaning each variant that differs from it in one dimension, on validate.
- The mentor's base rule (`ema`, no stops, no filter, second tranche on) on every period.

If it passes, the next step is a paper forward test, with the user's approval. If it fails, the result is published as a failure.
