# Momentum live: opening gaps of the stocks bought

Run on 2026-11-05. Code: `quant_agents/research/momentum_gap_check.py`. Numbers: [results/momentum-gap-check.json](results/momentum-gap-check.json).

It answers two questions for the live orders ([momentum-live-plan.md](momentum-live-plan.md)):
- How often does a limit buy set a band above the decision close miss at the next open?
- Does the global-markets agent see those mornings coming?

It is **descriptive: no trading rule is tested.**

**Data:** every month-end from Jan 2016 to Oct 2026 (129 rebalances), top 10 by 12-1 momentum, Liquid-500.
- Only **new buys** count: stocks entering the top 10 that month, 506 in all, about 4 a month. Holdings that stay need no buy.
- Gap = next open ÷ decision close − 1.
- Gaps above 20% are left out as corporate actions.

## How often a buy would miss

The median new buy opened **+0.46%** above the decision close; the mean was +0.42%.

| Band above the close | Opens above the limit | Never back to the limit all day | Return to next month-end: missed / filled | Cost of the misses to the book |
|---|---|---|---|---|
| **1.5%** (current plan) | **14.6%** | 3.4% | +0.99% / +2.90% | +0.06% a month |
| **3%** | **5.1%** | 1.2% | +4.64% / +2.51% | +0.09% a month |
| 5% | 0.8% | 0.2% | +6.56% / +2.59% | +0.02% a month |

How to read the table:
- **Opens above the limit:** the order does not fill at the open.
- **Never back to the limit all day:** the order is missed even if it stays open all day. The live plan cancels at 10:30, so the real miss rate sits between this column and the previous one.
- **Cost of the misses to the book:** the missed stocks' returns, each a tenth of the book, averaged over all months. A missed buy's money stays as cash until the next month.

**By period**, the share missed at 1.5% / 3% and the cost per month at each band:

| Period | Missed at 1.5% / 3% | Cost at 1.5% | Cost at 3% |
|---|---|---|---|
| 2016–20 | 16.3% / 6.9% | +0.24% | −0.08% |
| 2021–23 | 13.6% / 3.2% | −0.35% | +0.07% |
| 2024–26 | 13.4% / 4.7% | +0.16% | +0.44% |

**What it shows:**
- **With a 1.5% band, about one new buy in seven misses at the open.** With 3%, about one in twenty.
- **What missing costs is small and changes sign from period to period.** In some periods the missed stocks did better than the ones bought, in others worse. It is noise of under 1% a year, not a pattern.
- **The backtest buys every stock at the open, whatever the gap.** So a wider band keeps the live book closer to the tested rule.
- **A wider band does not raise the price paid.** A buy fills at the market price whenever that is at or below the limit. The band only decides which gap-ups are still bought.

## Does the global-markets agent help?

Spearman correlation on the 129 rebalance mornings:

| | Correlation |
|---|---|
| Global composite (known before 09:15) vs the picks' mean gap | **+0.41** |
| NIFTYBEES gap vs the picks' mean gap | +0.34 |

**The composite does point the right way:** on good global nights the momentum picks open higher. But the most a smarter band could recover is what the misses cost, about 0.06–0.09% a month, and that cost is mostly noise. It is not worth running the agent again for 12 mornings a year.

## Sells

The same check for the 495 stocks that left the top 10, with a sell limit set the band **below** the close. The median one opened +0.40% above the close.

| Band below the close | Opens below the limit | Never back up to the limit all day |
|---|---|---|
| 1.5% | 7.7% | 2.2% |
| 3% | 4.4% | 1.0% |
| 5% | 0.8% | 0.2% |

A missed sell keeps a stock that left the top 10 for another month, and leaves less cash for the stocks replacing it.

## The whole book with each limit, side by side

Code: `quant_agents/research/momentum_band_compare.py`. Numbers: [results/momentum-band-compare.json](results/momentum-band-compare.json).

This is the paper trial's book with the orders as limit orders: ₹1,00,000 once, 10 stocks, equal split, leftover filled, all charges.
- A missed buy keeps its cash. A missed sell keeps the stock for another month.
- **"At the open"** fills only when the opening price is within the limit.
- **"During the day"** also fills at the limit when the day's range reaches it.
- Live orders, cancelled at 10:30, fall between the two.
- The "missed" counts include trims and top-ups, not only new stocks.

**Feb 2016 to Oct 2026:**

| Orders | ₹1 lakh became | Per year | Worst fall | Buys missed | Sells missed | Charges |
|---|---|---|---|---|---|---|
| Backtest (every order at the open) | ₹12,78,473 | 26.8% | 39% | 0 of 902 | 0 of 791 | ₹68,828 |
| 1.5%, at the open | ₹14,30,206 | 28.1% | 37% | 137 of 842 | 54 of 844 | ₹76,292 |
| 1.5%, during the day | ₹12,83,181 | 26.8% | 37% | 30 of 878 | 14 of 815 | ₹74,563 |
| 3%, at the open | ₹13,78,491 | 27.7% | 37% | 46 of 872 | 30 of 815 | ₹76,979 |
| 3%, during the day | ₹13,75,963 | 27.6% | 39% | 12 of 897 | 1 of 800 | ₹70,714 |

**Per year, each period from a fresh ₹1 lakh:**

| Orders | 2016–20 | 2021–23 | 2024–26 |
|---|---|---|---|
| Backtest | 25.5% | 36.4% | 16.0% |
| 1.5%, at the open | 24.5% | 44.3% | 15.2% |
| 1.5%, during the day | 26.7% | 39.5% | 9.7% |
| 3%, at the open | 29.5% | 38.1% | 10.2% |
| 3%, during the day | 25.4% | 38.0% | 16.5% |

**What it shows:**
- **Over the whole period every version earned about the same:** 26.8% to 28.1% a year, with a worst fall of 37–39%.
- **No limit wins consistently.** Within a period the order flips, and the gaps can be large: 9.7% to 16.5% in 2024–26.
  - The cause is a handful of missed trades sending the compounding book down a different path, not the limit itself.
  - Those differences are luck, not a reason to pick one band.
- **What does differ is how closely the live book follows the tested rule.**
  - At 3% (during the day) only 12 of about 900 buys and 1 sell were missed.
  - At 1.5% (at the open) it was 137 buys and 54 sells.

## Suggestion (not applied)

Use a **fixed 3% band** for buys and sells instead of 1.5%, and drop the planned Yahoo re-price.
- About 95% of new buys and 96% of sells then fill the way the backtest assumes, against about 85% and 92%.
- Returns are about the same either way; the 3% book simply stays closer to the paper trial, so the two can be compared fairly.
- The global agent stays off.
