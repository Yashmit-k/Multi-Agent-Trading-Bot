# Equal split every month vs new buys only: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-29, before either book was run period by period.**

Disclosure: the **whole-period** results of both books are already known from [momentum-compound.md](momentum-compound.md). They come from one continuous run, 2016-02 to 2026-10:
- "new buys only": ₹14,35,665, 28.1% a year;
- "equal split every month": ₹12,70,774, 26.7% a year.

That one number is why this test exists. The per-period results below have not been seen.

## The two books

Both:
- invest ₹1,00,000 once, never topped up or withdrawn;
- use 12-1 momentum, the top 10 of the NSE Liquid-500 at each month-end close, traded at the next open;
- apply Zerodha delivery charges, 10 bp of slippage each way, the circuit rules, and whole shares only;
- use the engine `quant_agents/research/momentum_compound.py`.

| Book | At each rebalance |
|---|---|
| A `equal_split` (the reference) | The whole book is split equally across the 10: leavers sold, stayers trimmed or topped up, new ones bought |
| B `new_buys_only` (the candidate) | Leavers sold. Stayers left exactly as they are. The cash (sale proceeds plus any idle cash) is split equally across the new ones |

## Test

Each of the three periods starts from a fresh ₹1,00,000:
- train: 2016-02-01 to 2020-12-31;
- validate: 2021–2023;
- test: 2024-01-01 to 2026-10-27.

**B is better than A** only if all of these hold:
1. B's CAGR beats A's in **each** of the three periods.
2. The pooled paired monthly return difference (B − A), bootstrapped over months (2,000 draws), has its **10th percentile above zero**. Only one comparison is made, so there is no multiple-testing adjustment.
3. B still beats the equal-weight Liquid-500 benchmark (gross) in each period.

**Reported, not gated:** worst fall and charges in each period. Also the same comparison with the signal one session stale, and with slippage at 30 bp. A real difference should survive both.

## What follows

- **If B passes**, the paper trial can use B, with its own approval.
- **If not**, the trial uses A, the method that was described: an equal split every month.

Output:
- `services/quant/docs/results/momentum-rebalance-result.json`
- `services/quant/docs/momentum-rebalance-result.md`
