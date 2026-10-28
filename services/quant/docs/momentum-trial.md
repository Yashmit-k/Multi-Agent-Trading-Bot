# Forward paper trial: 12-1 momentum across the NSE Liquid-500

Status: **set up 2026-10-28. The first decision is at the close of 2026-10-30, and the first fills at the open of 2026-11-02.** Paper only: no order is ever sent to a broker.

**Size: 10 stocks × ₹10,000 = ₹1,00,000** (changed 2026-10-29 from 20 × ₹20,000, before the first decision, to match the owner's planned capital). In the backtest this book returned 34.5% a year (2016-02 to 2026-10), with a worst fall of 50%, a worst month of −31% and charges of about 1.75% of capital a year. The 20 × ₹20,000 book returned 34.8% a year, with a worst fall of 58%.

Why: 12-1 momentum was the only rule of 14 to pass [whole-market-result.md](whole-market-result.md). A backtest, however careful, can still be wrong in ways nobody has thought of. This trial runs the **same rule, unchanged**, on prices that did not exist when it was chosen.

## The rule (exactly the backtest's)

- **Universe:** at each month-end close, the 500 most liquid NSE EQ stocks.
  - Liquidity is median daily traded value over 126 sessions.
  - Also required: close ≥ ₹20, not an ETF, and a return on at least 240 of the last 252 sessions.
- **Score:** the return from 252 to 21 sessions ago, using corporate-action-adjusted prices.
- **Portfolio:** the top 10, ₹10,000 each (₹1,00,000 capital), bought at the next session's open.
  - A stock that cannot be bought at that open is skipped and the next one taken: an open locked at the upper circuit, a price above ₹10,000, or no EQ series.
  - Holdings that leave the top 10 are sold at that open. A sell locked at the lower circuit waits a day.
- **Costs:** Zerodha delivery charges, plus 10 bp of slippage each way.

**Code:**
- `quant_agents/momentum_trial.py` runs the book through `research.whole_market.simulate_range`, the backtest engine.
- On the 2026-09 to 2026-10 data it reproduces the backtest's 36 trades exactly, from a two-year data window.
- It runs as the `momentum-trial` service (`deploy/docker-compose.prod.yml`) with its own volume.

## What it does each evening (after 19:30 IST)

1. Downloads any missing NSE bhavcopies (a rolling window from 2024-07-08).
2. On the last session of a month, **appends that close's full ranking to `decisions.jsonl` before the next open**. This is the pre-commitment.
   - If a later recomputation of a logged month differs (for example, NSE revises a file), it is flagged in the report, never rewritten.
3. Re-runs the book from 2026-10-30 and writes `report.json`:
   - equity, P&L and charges;
   - holdings and trades;
   - month by month, against the equal-weight Liquid-500 (gross) and NIFTYBEES.

To read it on the server:

```
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec momentum-trial cat /data/momentum-trial/report.json
```

## How it will be judged (fixed now, before any result)

- **First review: after 12 completed months (the close of 2027-10-29).**
  - It **holds up** if its net return beats both the equal-weight Liquid-500 (gross) and NIFTYBEES over those 12 months.
  - Twelve months of a strategy with a 58% historical drawdown is a small sample. A miss is not proof that it failed, and a beat is not proof that it works.
  - So the trial continues to **24 months** either way, unless stopped by a decision recorded here.
- **Not a reason to stop or change the rule:** a losing month or a losing stretch. The backtest lost money in 5 of 11 years and fell 58% in 2018–20.
- **Reasons to review early:**
  - a data or engine fault (a flagged ranking mismatch, missing files, or a broken corporate-action adjustment);
  - a loss far outside the backtest's range: worse than −40% in a single month (the 10-stock backtest's worst was −31%; set before the first decision).
- Any real-money use is a separate decision. It would need its own review of tax, which the trial does not model: short-term capital gains are taxed at 20%.

## Known limits

- **Holidays:** the NSE holiday list (`calendar/static_nse.py`) covers 2026. **It must be extended with the 2027 holidays before January 2027.** Without them a holiday is taken as a trading day, so a month-end that falls on one would be found a day late.
- **Dividends** are not included, for the strategy or the benchmark.
- Fills are paper fills at the actual NSE open of the day, with slippage. Real fills of ₹10,000 in a 500th-ranked stock should be close, but are not guaranteed.
- A 10-stock book is concentrated: each stock is 10% of it. In the backtest its worst single month was −31%.
