# Alpha research survey, November 2026

This is a reading of the literature for strategies not yet tested in this project, sorted by how well they are evidenced and whether we can test them.

Already tested (see the other result documents in this folder):
- **Passed:** 12-1 momentum.
- **Failed:** low volatility, low beta, MAX, 52-week high, residual momentum, frog-in-the-pan, seasonality, reversal, Amihud illiquidity, the conservative formula, NIFTY trend and turn-of-month, overnight, intraday momentum, the NSE momentum score, 12-to-7 momentum, factor timing, and low volume.
- **Promising but unproven:** delivery % (now running as a paper book).

**Data checked on 2026-11-01:**

| Source | Coverage | Status |
|---|---|---|
| NSE CM bhavcopy | 2015–2026, every stock, OHLCV | in hand |
| NSE delivery (`sec_bhavdata_full`) | 2019-10 → | in hand |
| NSE F&O bhavcopy | 2016 → (checked 2016-01-01, 2020-01-01 and 2026-10-30): every stock option and future, with close, settlement, open interest and change in OI; about 185 stocks | **available, free** |
| Promoter pledge, shareholding pattern, insider (PIT) and bulk-deal disclosures | — | NSE/BSE filings with no simple bulk archive; would need scraping |

## A. Testable now with data in hand

| # | Idea | Paper and finding | Evidence elsewhere | Notes for us |
|---|---|---|---|---|
| A1 | **Trend factor**: combine moving-average signals of many lengths (3 to 1,000 days, each MA ÷ price) through a rolling cross-sectional regression that forecasts next-month return | [Han, Zhou & Zhu (2016), JFE](https://ideas.repec.org/a/eee/jfinec/v122y2016i2p352-375.html): beats momentum, short-term reversal and long-term reversal, and **earned +0.75%/month in the 2008–09 crisis while momentum lost −3.88%** | Works in China ([r-bloggers](https://www.r-bloggers.com/2014/03/performance-of-trend-factor-in-chinese-market/)); a volume-adjusted version too | Our data starts in 2015, so MAs above about 400 days would shorten the sample. **Its claim to suffer smaller crashes than momentum is exactly what our momentum lacks** |
| A2 | **Moving-average distance (MAD)**: ratio of the 21-day to the 200-day moving average; buy the highest | [Avramov, Kaplanski & Subrahmanyam (2021), RFE](https://anderson-review.ucla.edu/wp-content/uploads/2021/03/Avramov-Kaplanski-Subra_2018_SSRN-id3111334.pdf): predicts beyond momentum, the 52-week high and profitability; survives costs; strongest on the long side | International: [Abudy, Kaplanski & Mugerman (2024)](https://cris.biu.ac.il/en/publications/market-timing-with-moving-average-distance-international-evidence/), abnormal profits after costs that do not reverse | One line of code. The 52-week high (a related anchor) failed here, which is a warning |
| A3 | **High-volume return premium**: stocks with unusually high volume (relative to their own recent past) outperform over the next month | [Gervais, Kaniel & Mingelgrin (2001), JF](https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf); [Kaniel, Ozoguz & Starks (2012), JFE](https://ideas.repec.org/a/eee/jfinec/v103y2012i2p255-279.html): **found in 41 countries, emerging included**, not explained by risk or liquidity | Mixed in China ([PBCSF](https://english.phbs.pku.edu.cn/info/3351/20251.htm)) | The opposite of "low-volume winners", which failed here. Best as a filter on momentum or as a standalone ranking |
| A4 | **Technical timing within volatility groups**: a 10-day moving-average rule applied per volatility decile | [Han, Yang & Zhou (2013), JFQA](https://ideas.repec.org/a/cup/jfinqa/v48y2013i05p1433-1461_00.html): 9–24% a year of alpha, highest in high-volatility stocks | [CFA digest](https://rpc.cfainstitute.org/research/cfa-digest/2014/08/a-new-anomaly-the-cross-sectional-profitability-of-technical-analysis-digest-summary) | **Needs daily switching.** With 0.1% STT on each side, delivery costs about 0.25% a round trip, likely more than the edge. Low priority |
| A5 | **Long-term reversal**: buy 3-year losers, skipping the latest year | De Bondt & Thaler (1985); India: [Maheshwari & Dhankar (2015)](https://journals.uvu.edu/index.php/jbi/article/view/89) find it, but explained by risk; [Joshipura, NSE](https://nsearchives.nseindia.com/content/research/res_paperfinal223.pdf) | Mixed | Needs 4 years of history, so it is testable only from 2019. It contradicts momentum within the same stocks |
| A6 | **Halloween effect**: hold NIFTY November–April, cash May–October | [Bouman & Jacobsen (2002)](https://www.tias.edu/docs/default-source/Kennisartikelen/ssrn-id76248.pdf): 36 of 37 countries; [Jacobsen & Zhang](https://www.bnains.org/backtest/periode/The_Halloween_Indicator_everywhere_and_all_the_time_-_Ben_Jacobsen_%26_Cherry_Y._Zhang.pdf): 108 markets, out of sample; disputed by [Dichtl & Drobetz (2014)](https://www.bnains.org/backtest/periode/Sell_in_May_and_Go_away_Still_Good_Advice_for_Investors_-_Hubert_Dichtl_&_Wolfgang_Drobetz,_2014.pdf) | No rigorous Indian study found | Cheap to test (two trades a year). Our other calendar effects decayed |
| A7 | **Dynamic momentum**: cut momentum exposure in "panic" states, after market falls with high volatility | [Daniel & Moskowitz (2016), JFE](https://www.nber.org/papers/w20439): crashes are forecastable, and a dynamic version roughly doubles the Sharpe ratio | 8 markets and asset classes | Our market-state and volatility checks showed momentum did **well** after falls here. Low priority |

## B. Needs the F&O archive (available, free, about 2 GB, 2016 →)

| # | Idea | Paper and finding | Notes |
|---|---|---|---|
| B1 | **Volatility skew**: OTM put implied volatility minus ATM call implied volatility; a steeper skew means lower future returns | [Xing, Zhang & Zhao (2010), JFQA](https://www.researchgate.net/publication/46543470_What_Does_Individual_Option_Volatility_Smirk_Tell_Us_About_Future_Equity_Returns): about 10.9% a year risk-adjusted, lasting up to 6 months | **Never tested on NSE**, as far as we found. Implied volatility can be computed from closing or settlement prices: NSE stock options have been European since 2011 |
| B2 | **Call–put implied volatility spread**: a positive spread means higher future returns | [Cremers & Weinbaum (2010), JFQA](https://livrepository.liverpool.ac.uk/3002404/1/FuArisoyShackletonUmutlu2016.pdf); explained as a short-selling-cost proxy by [Muravyev, Pearson & Pollet (2022)](https://fmai.memberclicks.net/assets/docs/Derivatives2022/MuravyevPearsonPollet.pdf) | India restricts short selling, so the effect could be **stronger** here |
| B3 | **Futures open-interest build-up** | No rigorous Indian study found ([IIMB](https://repository.iimb.ac.in/handle/2074/18411) studies OI informativeness) | Practitioner idea; would be new evidence either way |

**Limits of B:**
- Only about 185 F&O stocks, mostly large and mid caps.
- Stock-option closing prices can be stale for far strikes, so settlement prices and liquid strikes only.
- It would be used as a filter or ranking within F&O names, bought in the cash market (long only).

## C. Strong evidence, but the data needs building

| # | Idea | Evidence | Data |
|---|---|---|---|
| C1 | **Avoid stocks with high promoter pledging** | India, peer-reviewed: [Kalia (2024)](https://ideas.repec.org/a/eme/jamrpp/jamr-01-2023-0003.html), pledging predicts **higher crash risk and worse performance** (BSE 500, 2011–20); [Chauhan, Mishra & Spahr (2021), Financial Management](https://digitalcommons.memphis.edu/facpubs/11664), more volatility and lower value | Quarterly pledge disclosures on NSE/BSE, per company, with no bulk archive. Natural as an "avoid" filter on momentum (crashes are momentum's weakness) |
| C2 | **Insider / promoter buying** | [India PhD thesis, 2007–15](https://idr.nitk.ac.in/handle/123456789/14150): insider purchases earn positive abnormal returns | SEBI PIT disclosures; scraping |
| C3 | **Bulk-deal buys** | [Rajvanshi & Paul (2022)](https://emerald.com/insight/content/doi/10.1108/MF-08-2021-0374/full/pdf): +5–7% in a week around the deal, **mostly before it is public** | NSE bulk-deal archive. Likely too late to capture |
| C4 | **Rising FII ownership** | Broker trackers only; no rigorous study found | Quarterly shareholding patterns |
| C5 | **Machine learning on price charts (CNN)** | [Jiang, Kelly & Xiu (2023), JF](https://economics.yale.edu/sites/default/files/2023-11/The%20Journal%20of%20Finance%20-%202023%20-%20JIANG%20-%20Re%25E2%2580%2590%20Imag%20in%20ing%20Price%20Trends_0.pdf): strong out-of-sample, also internationally ([Korea](https://koasas.kaist.ac.kr/handle/10203/337992)); emerging-market ML: [Hanauer & Kalsbach (2023)](https://ideas.repec.org/a/eee/ememar/v55y2023ics1566014123000274.html) | Data in hand, but a large project. The price-only ML in this project failed before. Mostly short-horizon (weekly), where costs bite |

## Suggested order

1. **A1 trend factor, A2 MAD and A3 high-volume premium** as a pre-registered batch (K = 3). Use the same setup as the paper trial: ₹1 lakh, 10 stocks, monthly, all charges. Each must beat 12-1 in all three periods.
   - A1 is the most interesting: its evidence is specifically **fewer crashes than momentum**.
2. **Download the F&O archive and test B1–B2** as a second batch on F&O stocks, 2016–2026. This is genuinely new evidence for India.
3. **C1 promoter pledge as an "avoid" filter**, if the pledge history can be assembled. It is the best-evidenced Indian signal that targets momentum's crash risk.
4. A6 Halloween is a cheap side test. A4, A5 and A7 are low priority for the reasons above.
