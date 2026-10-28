# 12-1 momentum with the delivery filter: detailed backtest

Run 2026-10-29. Code: `quant_agents/research/momentum_delivery_detail.py`. Numbers: [results/momentum-delivery-detail.json](results/momentum-delivery-detail.json). Every trade: [results/momentum-delivery-trades.csv](results/momentum-delivery-trades.csv).

**Status:**
- This is variant V5 of the pre-registered study [momentum-variants-protocol.md](momentum-variants-protocol.md).
- There it **beat plain momentum in all three periods but failed the multiple-testing bound** ([momentum-variants-result.md](momentum-variants-result.md)).
- This page is a descriptive deep-dive, not a new test.

## The strategy

**Once, at the start:** put ₹1,00,000 in. Nothing is ever added or withdrawn.

**On the last trading day of every month, after the close:**
1. **Universe:** take the 500 most liquid NSE stocks.
   - Ranked by median daily traded value over the last 6 months.
   - EQ series only, price at least ₹20, no ETFs, and at least a year of trading.
2. **Momentum:** rank them by their price change from 12 months ago to 1 month ago.
   - Prices are adjusted for splits and bonuses.
   - The latest month is skipped, because very recent winners often dip back briefly.
   - Keep the **top 30**.
3. **Delivery filter:** for each of the 30, take the average **delivery %** over the last 63 trading days (about 3 months).
   - Delivery % is the share of each day's traded quantity that buyers actually took into their demat accounts, as opposed to intraday trades squared off the same day.
   - NSE publishes it every evening in its `sec_bhavdata_full` file.
4. **Pick the 10 with the highest delivery %.**

**At the next morning's open:**
5. Sell the holdings that are no longer among the 10.
6. Split the **whole portfolio** (holdings plus cash) equally across the 10:
   - trim the stocks above a tenth;
   - top up those below;
   - buy the new ones.
7. Buy whole shares only. Use the cash left over to buy one more share at a time of the most underweight stock, until no share fits.

All Zerodha delivery charges are included: 0.1% STT on each buy and sell, stamp duty, exchange and SEBI fees, GST, and ₹15.34 DP per stock sold. So is 0.1% slippage each way. A stock locked at its upper circuit at the open is skipped and the next one taken.

**Why delivery might help.** Among stocks that have already risen strongly, a high delivery % means the buying comes from people holding the shares, not intraday traders churning them. Momentum driven by investors may last longer than momentum driven by speculation. In the worked example below, the two strongest momentum stocks (CUPID +523%, ATHERENERG +188%) had some of the *lowest* delivery (about 30%), and the filter left them out.

## A worked example: the decision at the close of 2026-09-30

The top 30 by 12-1 momentum, with their 3-month delivery %. The 10 with the highest delivery are bought.

| Momentum rank | Stock | 12-1 return | Delivery % (63 days) | |
|---|---|---|---|---|
| 1 | CUPID | +523% | 29.5% |  |
| 2 | ATHERENERG | +188% | 31.9% |  |
| 3 | TDPOWERSYS | +180% | 45.5% | **bought** |
| 4 | AEROFLEX | +176% | 37.9% |  |
| 5 | SANSERA | +174% | 49.3% | **bought** |
| 6 | SKYGOLD | +173% | 45.0% | **bought** |
| 7 | THANGAMAYL | +169% | 43.0% |  |
| 8 | WELCORP | +165% | 43.8% |  |
| 9 | RPTECH | +150% | 44.2% |  |
| 10 | CPPLUS | +149% | 55.8% | **bought** |
| 11 | AVALON | +139% | 38.5% |  |
| 12 | MCX | +137% | 42.6% |  |
| 13 | SHREEJISPG | +135% | 39.1% |  |
| 14 | RRKABEL | +131% | 44.7% | **bought** |
| 15 | ACUTAAS | +127% | 50.1% | **bought** |
| 16 | SHILPAMED | +126% | 41.3% |  |
| 17 | AETHER | +124% | 44.1% |  |
| 18 | KIRLOSENG | +124% | 49.6% | **bought** |
| 19 | RATNAVEER | +121% | 28.9% |  |
| 20 | GRWRHITECH | +120% | 49.0% | **bought** |
| 21 | LAURUSLABS | +120% | 53.0% | **bought** |
| 22 | PARAS | +112% | 26.5% |  |
| 23 | FCL | +109% | 34.8% |  |
| 24 | SENORES | +103% | 43.1% |  |
| 25 | HINDCOPPER | +103% | 37.5% |  |
| 26 | GCSL | +102% | 34.7% |  |
| 27 | APARINDS | +101% | 38.8% |  |
| 28 | TFCILTD | +101% | 41.5% |  |
| 29 | MOREPENLAB | +100% | 29.7% |  |
| 30 | BAJAJCON | +99% | 49.7% | **bought** |

## Result: ₹1,00,000 once, 2020-02-01 to 2026-10-27 (6.7 years), after all charges

| | Final value | CAGR | Worst fall | Charges | Trades |
|---|---|---|---|---|---|
| **Momentum + delivery filter** | **₹1,951,419** | **+55.4%** | 31% (2020-02-01 → 2020-03-31, the COVID crash) | ₹74,511 | 1,515 |
| Plain momentum (the paper trial's rule) | ₹912,373 | +38.8% | 39% (2024-07-31 → 2025-02-28) | ₹45,711 | 1,465 |
| Equal-weight Liquid-500, gross | ₹341,986 | | | | |
| NIFTYBEES | ₹209,817 | | | | |

| Year | Start | End | **Delivery filter** | Plain momentum | Benchmark | NIFTYBEES | Charges | Trades |
|---|---|---|---|---|---|---|---|---|
| 2020 (from Feb) | ₹100,000 | ₹185,525 | **+85.5%** | +109.0% | +22.8% | +19.0% | ₹2,457 | 206 |
| 2021 | ₹185,525 | ₹407,028 | **+119.4%** | +62.9% | +49.3% | +26.0% | ₹5,298 | 230 |
| 2022 | ₹407,028 | ₹485,654 | **+19.3%** | -1.0% | +1.0% | +5.5% | ₹7,459 | 231 |
| 2023 | ₹485,654 | ₹812,473 | **+67.3%** | +63.3% | +48.9% | +20.5% | ₹7,665 | 211 |
| 2024 | ₹812,473 | ₹1,441,676 | **+77.4%** | +23.7% | +22.9% | +10.2% | ₹15,941 | 230 |
| 2025 | ₹1,441,676 | ₹1,383,065 | **-4.1%** | -6.0% | +0.3% | +12.0% | ₹20,652 | 222 |
| 2026 (to 27 Oct) | ₹1,383,065 | ₹1,951,419 | **+41.1%** | +42.5% | +0.7% | -10.8% | ₹15,041 | 185 |

### Month by month: momentum + delivery filter (net)

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 |  | -2.6% | -29.2% | +31.7% | -4.7% | +16.4% | +5.0% | +16.3% | +12.9% | +4.4% | +21.3% | +5.5% | **+85.5%** |
| 2021 | -3.2% | +27.5% | +16.1% | +9.5% | +10.5% | -0.4% | +3.0% | -0.6% | +8.1% | +4.6% | +1.5% | +8.0% | **+119.4%** |
| 2022 | +12.4% | -7.4% | +11.0% | +0.4% | -10.4% | -12.9% | +16.9% | +4.9% | -0.4% | +4.6% | +4.5% | -1.3% | **+19.3%** |
| 2023 | -10.6% | -11.4% | +4.6% | +5.3% | +9.9% | +16.0% | +15.6% | +17.6% | +0.3% | -5.5% | +10.1% | +6.1% | **+67.3%** |
| 2024 | +14.1% | +2.4% | -7.8% | +15.2% | -5.6% | +11.3% | +8.6% | +13.2% | +8.3% | -4.6% | +0.9% | +6.2% | **+77.4%** |
| 2025 | -12.1% | -17.8% | +17.7% | -5.4% | +14.0% | -0.1% | -1.4% | -5.0% | +1.3% | +5.0% | +3.2% | +1.9% | **-4.1%** |
| 2026 | -4.0% | +8.8% | -11.2% | +20.9% | +11.1% | +5.3% | +2.0% | +6.2% | +2.1% | -2.7% |  |  | **+41.1%** |

### Month by month: plain momentum, for comparison

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 |  | -2.8% | -23.1% | +33.7% | -2.9% | +12.4% | +16.5% | +27.3% | +4.3% | -0.8% | +15.9% | +7.6% | **+109.0%** |
| 2021 | -3.1% | +9.9% | -2.8% | +8.6% | +14.4% | +0.7% | +1.7% | +3.9% | +6.4% | +5.2% | -2.4% | +9.1% | **+62.9%** |
| 2022 | +11.2% | -14.1% | +7.0% | +6.4% | -10.3% | -9.1% | +13.7% | +8.8% | -5.7% | -0.4% | +9.4% | -12.2% | **-1.0%** |
| 2023 | -4.9% | -18.7% | +1.0% | +10.4% | +7.9% | +20.5% | +17.8% | +6.7% | +6.8% | +2.7% | +6.0% | -0.4% | **+63.3%** |
| 2024 | +18.7% | -0.7% | -5.9% | +13.1% | -2.8% | +4.1% | +11.3% | -4.8% | -3.5% | -4.6% | -4.4% | +4.5% | **+23.7%** |
| 2025 | -15.4% | -17.7% | +16.4% | -1.4% | +12.2% | -0.5% | -2.0% | -1.9% | -5.0% | +1.7% | +5.7% | +7.4% | **-6.0%** |
| 2026 | -9.6% | +8.9% | -8.8% | +25.2% | +13.6% | +3.1% | -0.7% | +9.7% | +1.1% | -1.7% |  |  | **+42.5%** |

### Month by month: benchmark (equal-weight Liquid-500, gross)

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 |  | -6.5% | -30.0% | +17.4% | -2.0% | +15.6% | +5.2% | +10.2% | +0.6% | -0.2% | +12.5% | +7.8% | **+22.8%** |
| 2021 | -0.0% | +11.7% | +0.6% | +4.5% | +10.1% | +6.0% | +4.6% | -1.9% | +5.8% | -0.3% | -2.9% | +3.7% | **+49.3%** |
| 2022 | +0.7% | -8.0% | +4.9% | +2.9% | -7.7% | -6.3% | +9.9% | +6.1% | -2.2% | +1.6% | +3.1% | -2.3% | **+1.0%** |
| 2023 | -2.7% | -4.1% | -0.1% | +7.8% | +5.2% | +6.6% | +7.2% | +4.7% | +2.9% | -2.1% | +8.4% | +7.8% | **+48.9%** |
| 2024 | +7.6% | -0.1% | -3.8% | +9.0% | -1.1% | +8.6% | +6.5% | +0.5% | +1.6% | -6.0% | -0.1% | -0.4% | **+22.9%** |
| 2025 | -7.1% | -12.4% | +8.9% | +2.7% | +9.0% | +3.7% | -2.8% | -2.9% | +1.9% | +4.0% | -2.0% | -0.4% | **+0.3%** |
| 2026 | -5.2% | +3.6% | -11.4% | +17.8% | +1.8% | +2.7% | +1.7% | +1.3% | -3.9% | -5.2% |  |  | **+0.7%** |

The delivery filter beat plain momentum in 52% of months. Its lead comes from a few big months and years (2021, 2022, 2024), not from steadily small wins.

**Biggest winners** (net rupee P&L over all holding periods, including the current position): ACUTAAS (+₹136,123), SMLMAH (+₹119,515), SANSERA (+₹100,720), GMRP&UI (+₹87,872), PGEL (+₹74,671), TITAGARH (+₹71,008), KALYANKJIL (+₹70,171), LAURUSLABS (+₹63,656), SHAKTIPUMP (+₹63,462), BSE (+₹62,261).

**Biggest losers:** GRWRHITECH (−₹67,456), POLICYBZR (−₹45,944), OFSS (−₹43,986), PCJEWELLER (−₹39,926), STALLION (−₹39,471), TRENT (−₹36,530), IIFLCAPS (−₹32,745), ZAGGLE (−₹30,256), CEMPRO (−₹27,712), RRKABEL (−₹26,475).

**Holdings at the end of the backtest:** ACUTAAS 12%, SKYGOLD 12%, LAURUSLABS 11%, GRWRHITECH 11%, CPPLUS 11%, SANSERA 10%, TDPOWERSYS 9%, RRKABEL 9%, KIRLOSENG 8%, BAJAJCON 8%.

## Checks against chance and look-ahead

| Check | CAGR | Reading |
|---|---|---|
| Momentum + delivery filter | +55.4% | — |
| **20 random choices of 10 from the same top 30** (same engine and costs) | mean +32.6%, range +22.2% to +47.2% | **the delivery choice beat all 20.** Choosing by delivery adds value beyond "any 10 of the top 30" |
| Plain momentum (top 10 by momentum itself) | +38.8% | also above the random mean, so momentum rank within the 30 matters too |
| Delivery data 5 sessions stale | +49.8% | most of the edge remains, so it is not a same-day artefact |

Timing: the delivery % for day t is published by NSE that evening, alongside the price file. The ranking at month-end uses only days up to that close, and trades happen at the next open.

## Caveats

- **Only 6.7 years of data** (NSE's delivery archive starts in October 2019), and **all of it in a strong market for Indian mid and small caps.**
  - This period includes the 2020 rebound and the 2021 and 2023 rallies.
  - The weak 2025 still lost (−4.1%).
- **Five variants were tested.** This one failed the bound that allows for that (t = 1.59, needing about 2.05). The random-pick check above makes it more convincing, but it is not a pre-registered pass.
- **It is concentrated:** 10 stocks, mostly mid and small caps. The worst fall was 31%, and losers such as GRWRHITECH cost ₹67,000 at the end of the book's life.
- **Charges are higher** than plain momentum (₹74,511 against ₹45,711), because a bigger book pays proportionally more STT.
- **Tax is not included.** Most gains would be short-term capital gains, taxed at 20%.
- **Delivery % can be distorted** by block trades or operator activity. The 3-month average dampens this, but does not remove it.
- **Nothing here is advice.** The only honest next step is forward evidence: a second paper book.
