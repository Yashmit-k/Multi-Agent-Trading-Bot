# Slow rotation (monthly momentum, monthly and weekly reversal): pre-registered protocol

Status: **PRE-REGISTERED 2026-10-26, before any of these rules was run on any period.**

Origin: the [agent replay](agent-replay-result.md) and the [exit-rules study](exit-rules-result.md) show that 1–10 day swing trades from the quant agents lose, mostly to charges (about ₹62, roughly 0.3%, per ₹20,000 round trip). This study asks whether **fewer, longer trades** from a cross-sectional ranking do better:
- **long-horizon momentum**, held for a month;
- **short-term reversal**, as a ranked portfolio.

The event-driven EMA-dip rule is already studied ([dip-reversion-result.md](dip-reversion-result.md)) and is not repeated here.

Balance-sheet factors (quality, value) are **not** tested. There is no point-in-time archive of published results, and the latest Yahoo figures would leak the future.

## Data

- `datasets/research/dip_history/daily_2015_2026.jsonl`: daily bars from 2015-01-01 to 2026-10-05, read-only from Zerodha Kite, split and bonus adjusted. NIFTY 50 is included as the benchmark.
- **Universe A:** the 49 current NIFTY 50 stocks.
- **Universe A+B (survivorship check):** A plus the 18 former members listed in `dip_reversion.FORMER`. Delisted former members have no data, so some survivorship bias remains. Momentum is the rule most flattered by it, because today's members are partly yesterday's winners.
- **Corporate actions:** a session that opens more than 20% away from the previous close is treated as a corporate action. The stock is not ranked while such a gap is inside its look-back window. A held stock is sold at the previous close, with charges, and may be bought back at the next rebalance.

| Period | Dates | Use |
|---|---|---|
| Warm-up | 2015-01-01 to 2015-12-31 | look-back only |
| Train | 2016-01-01 to 2020-12-31 | gate |
| Validate | 2021-01-01 to 2023-12-31 | gate |
| Test | 2024-01-01 to 2026-10-05 | gate |

Nothing is chosen on any period: the five rules below are fixed here, and all are reported. Each period starts with an empty book.

## Rules (fixed, no tuning)

Ranks use closes up to and including the rebalance session. Trades happen at the **next session's open**, with 5 bp slippage:
- sell the names that left the list;
- buy the new names at ₹20,000 each;
- names that stay are left alone (no top-up), to save charges.

| Rule | Rebalance | Rank by | Hold |
|---|---|---|---|
| `mom_12_1` | last session of each month | return from 252 to 21 sessions ago (highest) | top 10 |
| `mom_6_1` | last session of each month | return from 126 to 21 sessions ago (highest) | top 10 |
| `mom_12_1_q` | last session of each quarter | return from 252 to 21 sessions ago (highest) | top 10 |
| `rev_21` | last session of each month | return over the last 21 sessions (lowest) | top 10 |
| `rev_5` | every 5th session | return over the last 5 sessions (lowest) | top 5 |

- A stock is eligible only with the full look-back, a close on the rebalance session and an open on the next session.
- Capital: ₹20,000 × the number held (₹2,00,000 for top 10, ₹1,00,000 for top 5). Return is the rupee P&L on that capital. Cash is not reinvested and earns nothing.
- Charges: Zerodha delivery (`mentor_strategies.delivery_charges`, as in the dip study). Open positions at a period's end are marked at the last close, less sell charges.

## Benchmarks

- **NIFTY 50**, price index, held for the same period with no charges. This is roughly what an index fund gives, before dividends and a small expense ratio.
- **Equal-weight universe**: ₹20,000 in every eligible stock at the start of the period, held, with charges.

## Measures (per rule, period and universe)

- Annualised return on capital, and the same for NIFTY.
- Excess over NIFTY per year.
- Total net, charges paid, number of buys.
- Maximum drawdown of the marked-to-market P&L (₹ and % of capital).
- Monthly excess return over NIFTY: its mean, and its 10th-percentile bootstrap mean (2,000 resamples of months).

## Gate (Universe A)

A rule **works** only if all of these hold:
1. Its annualised return beats NIFTY's in **each** of train, validate and test.
2. The 10th-percentile bootstrap of the mean monthly excess, pooled over all three periods, is **above zero**.
3. On Universe A+B, it still beats NIFTY in validate and test.

If no rule passes, the conclusion is that slow price-only rotation adds nothing over an index fund on NIFTY 50, and no rule is moved to paper trading.

## Output

- `services/quant/docs/results/slow-rotation-result.json`;
- `services/quant/docs/slow-rotation-result.md`.

Run:

```
python -m quant_agents.research.slow_rotation
```
