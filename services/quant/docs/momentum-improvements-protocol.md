# 12-1 momentum improvements: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-28, before any variant below was run.** The baseline is the rule that passed [whole-market-result.md](whole-market-result.md) and is in the paper trial ([momentum-trial.md](momentum-trial.md)). The baseline's results are known. The variants' are not.

Already measured, and so **not** tested here as rules ([momentum-monthly-review.md](momentum-monthly-review.md)): a market-trend filter, a market-state filter, and volatility scaling. None helped consistently.

## Variants (K = 4)

Everything not listed is the baseline: the Liquid-500, the 12-1 score, ₹20,000 a position, Zerodha delivery charges, 10 bp of slippage each way, month-end decisions, next-open fills, and the circuit rules.

| Id | Change | Why (source) |
|---|---|---|
| V1 `buffer40` | A holding is kept while its rank is within the top **40**. Free slots are filled with the best-ranked stocks not held, up to 20 | Less turnover, so lower costs: Novy-Marx & Velikov (2016), "A taxonomy of anomalies and their trading costs" |
| V2 `hold30` | Hold the top **30**, not 20 (₹6,00,000 capital) | Less dependence on a few winners |
| V3 `skip_top5pct` | Skip the 25 highest 12-1 scores (the top 5% of the universe), then take the next 20 | The most extreme winners lead the sell-offs (the monthly review; also the "momentum crashes" literature, Daniel & Moskowitz 2016) |
| V4 `buffer40_hold30` | V1 and V2 together | Fixed now, before results, so it is not chosen after seeing them |

## Gate

A variant **improves** on the baseline only if all three hold:
1. Its net annual return (12 × mean monthly return on capital) beats the baseline's in **each** of train (2016-02–2020), validate (2021–23) and test (2024-01 to 2026-10-27). Each period starts from cash, as in the whole-market study.
2. The pooled paired monthly difference (variant minus baseline), bootstrapped over months (2,000 draws), has its **0.10 / 4** quantile above zero.
3. It still beats the equal-weight Liquid-500 benchmark (gross) in each period.

Also reported, not gated: CAGR and worst drawdown of one continuous book (2016-02 to 2026-10), charges, and buys.

## What follows

- A variant that passes is added to the paper trial as a **second, separate book**, with its own approval. The baseline book is not changed.
- If none passes, the baseline stays as it is.

Output:
- `services/quant/docs/results/momentum-improvements-result.json`
- `services/quant/docs/momentum-improvements-result.md`

Run:

```
python -m quant_agents.research.momentum_improvements
```
