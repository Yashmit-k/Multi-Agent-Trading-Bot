# 12-1 momentum as one compounding ₹1 lakh book

Run 2026-10-29. Code: `quant_agents/research/momentum_compound.py`. Numbers: [results/momentum-compound-result.json](results/momentum-compound-result.json). Trades: [results/momentum-compound-trades.csv](results/momentum-compound-trades.csv).

**The setup:**
- ₹1,00,000 is invested once, on 2016-02-01. Nothing is ever added or withdrawn.
- At every month-end the **whole book is split equally across the top 10** by 12-1 momentum, traded at the next open:
  - stocks that left the top 10 are sold;
  - those that stayed are trimmed or topped up to an equal share;
  - new ones are bought.
- Same universe, score, Zerodha delivery charges, 10 bp of slippage each way, and circuit rules as the other studies. Whole shares only. Idle cash earns nothing.
- Checks: replaying every trade reproduces the engine's cash exactly (₹341.10 at the end), and cash never went below ₹52.

## Result, 2016-02-01 to 2026-10-27

| | ₹1,00,000 became | CAGR | Worst fall | Charges | Trades |
|---|---|---|---|---|---|
| **Momentum, equal split every month** | **₹12,70,774** | **26.7%** | **39%** | ₹68,404 | 1,690 |
| Momentum, new buys only (holdings left to run) | ₹14,35,665 | 28.1% | 42% | ₹56,559 | 999 |
| Equal-weight Liquid-500, gross | ₹4,06,651 | 14.0% | — | — | — |
| NIFTYBEES | ₹3,48,464 | 12.3% | — | — | — |

| Year | Start value | End value | Momentum | Benchmark | NIFTYBEES | Charges |
|---|---|---|---|---|---|---|
| 2016 (from Feb) | ₹1,00,000 | ₹85,478 | −14.5% | +11.0% | +9.7% | ₹1,941 |
| 2017 | ₹85,478 | ₹1,61,015 | +88.4% | +49.4% | +29.9% | ₹2,016 |
| 2018 | ₹1,61,015 | ₹1,66,615 | +3.5% | −23.5% | +4.8% | ₹2,140 |
| 2019 | ₹1,66,615 | ₹1,60,953 | −3.4% | −10.6% | +12.9% | ₹2,699 |
| 2020 | ₹1,60,953 | ₹3,05,243 | +89.6% | +28.7% | +17.2% | ₹2,549 |
| 2021 | ₹3,05,243 | ₹4,89,907 | +60.5% | +49.3% | +26.0% | ₹5,343 |
| 2022 | ₹4,89,907 | ₹4,80,867 | −1.8% | +1.0% | +5.5% | ₹7,758 |
| 2023 | ₹4,80,867 | ₹7,80,319 | +62.3% | +48.9% | +20.5% | ₹7,497 |
| 2024 | ₹7,80,319 | ₹9,57,966 | +22.8% | +22.9% | +10.2% | ₹12,255 |
| 2025 | ₹9,57,966 | ₹8,95,507 | −6.5% | +0.3% | +12.0% | ₹12,966 |
| 2026 (to 27 Oct) | ₹8,95,507 | ₹12,70,774 | +41.9% | +0.7% | −10.8% | ₹11,239 |

## Correction to earlier figures

[whole-market-result.md](whole-market-result.md), [momentum-audit.md](momentum-audit.md) and the paper trial quoted figures like "34.8% a year, ₹1 → ₹24.8" and worst falls of 50–58%.
- Those books bought a **fixed ₹10,000–20,000 per new position** and let the profits pile up. The figures came from **compounding returns measured on that fixed capital**.
- That is a fair way to compare rules with each other: the gate decisions and the momentum-vs-benchmark conclusion stand.
- But it **overstates what a one-time investment would grow to**. A winner that grows eightfold stays in the fixed-capital book at eight times its original weight, which a self-funded book cannot match once it rebalances.

**For a real one-time ₹1 lakh, the figures above are the ones to use**: about 27% a year, not 35%, and a worst fall of about 39%, not 50–58%. Both still beat the benchmark (14.0%) and NIFTYBEES (12.3%) by a wide margin.

## Notes

- **Charges grow with the book.** At ₹10 lakh, monthly trims and top-ups of 10 stocks cost about ₹1,000 a month (1.3% of the book a year). Most of that is STT (0.1% on each buy and sell) and the ₹15.34 DP charge per stock sold.
- **"New buys only"** left holdings to run and did slightly better here (28.1%, with 40% fewer trades), but it was not part of a pre-registered test. The difference is within what chance alone could produce.
- **Tax is not included.** Gains on stocks held under a year are taxed at 20% (short-term capital gains), and most positions here are held for months.

## Filling the cash left by whole-share rounding (2026-10-29)

**The option:** after the equal split, the leftover cash buys one more share at a time of the most underweight holding that still fits, until no share fits (`simulate(fill_leftover=True)`). Numbers: [results/momentum-fill-result.json](results/momentum-fill-result.json). All figures are after charges.

| ₹1,00,000 once, 2016-02 to 2026-10 | Without fill | With fill |
|---|---|---|
| Final value | ₹12,70,774 | ₹12,78,473 |
| CAGR | 26.70% | 26.77% |
| Worst fall | 39.4% | 39.2% |
| Charges | ₹68,404 | ₹68,828 |
| Trades | 1,690 | 1,826 |
| Idle cash, mean / worst | 0.27% / 2.9% | 0.04% / 0.2% |

| Fresh ₹1,00,000 per period | Without fill | With fill |
|---|---|---|
| 2016-02–20 | ₹3,05,243 (25.4%), idle 0.5% | ₹3,06,084 (25.5%) |
| 2021–23 | ₹2,44,700 (34.9%), idle 2.3% | ₹2,53,071 (36.4%) |
| 2024–26 | ₹1,45,696 (14.2%), idle 6.8% | ₹1,52,147 (16.0%) |

What this shows:
- **The fill is not a better rule.** The monthly difference averages +0.005% (t = 0.43).
- **It keeps the book fully invested.** That matters while the book is small, and today's leaders are expensive shares: up to 13–20% could otherwise sit idle.
- Extra charges are small (about ₹400 over ten years). Top-up buys pay no DP charge.
- It adds market exposure. A run started in January 2025 did 3 points a year worse with the fill.
- **Adopted for the paper trial before its first decision**, to match how the book would be run by hand.
