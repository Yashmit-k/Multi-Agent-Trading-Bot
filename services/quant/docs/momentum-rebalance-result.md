# Equal split every month vs new buys only: result

Protocol: [momentum-rebalance-protocol.md](momentum-rebalance-protocol.md), pre-registered 2026-10-29 and scored once. Numbers: [results/momentum-rebalance-result.json](results/momentum-rebalance-result.json). Code: `quant_agents/research/momentum_rebalance.py`.

**Verdict:**
- **"New buys only" is not shown to be better than an equal split every month.** It wins two periods of three, loses 2021–23, and the monthly difference is within chance: +0.14% a month, t = 0.75, 10th percentile −0.09%.
- **The paper trial should therefore use the equal split (A)**, as planned.

## Each period from a fresh ₹1,00,000 (CAGR, worst fall, charges, trades)

| Period | A: equal split every month | B: new buys only | Benchmark |
|---|---|---|---|
| Train 2016-02–20 | 25.4%, 36%, ₹11,346, 707 | **26.2%**, 42%, ₹8,111, 385 | 8.0% |
| Validate 2021–23 | **34.9%**, 32%, ₹8,834, 478 | 34.0%, 32%, ₹7,245, 312 | 31.0% |
| Test 2024–26 | 14.2%, 38%, ₹6,852, 430 | **18.2%**, 43%, ₹5,411, 302 | 7.9% |

Both beat the benchmark in every period. B trades about 40% less and pays about 25% less in charges, but **its worst falls are deeper** (42–43% against 36–38%), because it lets the winners grow into large positions.

## Robustness (reported, not gated)

| Check | B beats A in | Mean monthly B − A | 10th percentile | Reading |
|---|---|---|---|---|
| As registered (10 bp slippage) | train, test | +0.14% | −0.09% | not shown better |
| Signal one session stale | validate, test | +0.01% | −0.21% | no difference |
| Slippage 30 bp each way | all three | +0.24% | +0.01% | B better, just |

## What it means

- **At realistic costs the two methods earn about the same.** The gap seen in the whole-period run (₹14.4 lakh against ₹12.7 lakh) is mostly path: which winners happened to be left to run.
- **B's real advantage is fewer trades.** It pulls ahead only when trading costs are high (30 bp slippage). If real fills turn out worse than the 10 bp assumed, B would be the better choice. The trial's fills will show which.
- **A is smoother.** It caps each stock at 10% of the book every month, so its worst falls are 5–7 points shallower.
- Both versions still beat the benchmark by a wide margin in 2016–20 and 2024–26. In 2021–23 the margin was thin (34.9% against 31.0%), because the whole market rose strongly then.
