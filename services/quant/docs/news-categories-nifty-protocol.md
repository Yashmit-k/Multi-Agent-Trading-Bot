# News categories vs the NIFTY 50 index

Status: **PRE-REGISTERED before any GDELT pull, any price download, or any event study for this question.** No category query, threshold, window, or pass rule below may be edited after the first train table is computed. Validate is scored once.

This file follows the same rule as [dip-reversion-protocol.md](dip-reversion-protocol.md): the method is frozen here, and the result file is a later document.

## Question

Do volume spikes in ten categories of news move the **NIFTY 50 index**, including news that never names a NIFTY 50 company (wars abroad, oil shocks, RBI or Fed decisions, tariffs, elections)?

The outcome is the index only. Individual stocks are not tested. This study does not add a fusion vote, does not change agent scores, and does not change risk or the decision engine.

## What this study will not change

- Live and paper trading behaviour stay as they are.
- Fusion weights, the decision engine, risk limits, and every agent's live score stay as they are.
- No new agent vote is added.
- A later capture switch for market-wide headlines defaults to off. Turning it on is outside this study and is not a trading-rule change by itself.
- Raw GDELT responses and raw price caches are local only. They are not committed. The committed outputs are this protocol, the result note, and one small JSON of summary numbers.

If nothing passes the rule at the end of this file, that negative result is the result. It is not a reason to retune.

## Prices: public read-only candles

Fetch each of these URLs **once**. Do not page, do not retry in a loop, and do not call them again for this study. Cache the body locally.

- `https://13-238-176-73.sslip.io/api/v1/market/candles/NIFTY50?timeframe=1d&limit=2000`
- `https://13-238-176-73.sslip.io/api/v1/market/candles/INDIAVIX?timeframe=1d&limit=2000`
- `https://13-238-176-73.sslip.io/api/v1/market/candles/NIFTY50?timeframe=5m&limit=2000`

The daily responses are the Kite-sourced history the live site exposes from 2024 onward. The 5-minute response is whatever that one call returns (the route caps history, so the intraday window may be short). Record the first and last bar in the result. Do not issue a second intraday call to lengthen it.

A daily bar's session date is the `Asia/Kolkata` date of its `end` timestamp. A 5-minute bar belongs to the session whose IST date is the bar's `start` date, and only if its IST start time is in `[09:15, 15:30)`.

## Prices: Yahoo Finance, and the cross-check

For history before the public API's daily bars, download Yahoo Finance daily bars from 2015-01-01 through the run date:

- `^NSEI` is the NIFTY 50 index.
- `^INDIAVIX` is India VIX.

Use the unadjusted `Close` (`auto_adjust` false). Yahoo's row date is the session date.

Where a session has both an API close and a Yahoo close, the study uses the **API** close. It still compares them. A session is a **mismatch** when `abs(yahoo / api - 1) > 0.005` (half of one percent). Every mismatch is listed in the result (date, Yahoo close, API close, absolute percent gap). Mismatched sessions are not dropped and are not a reason to switch the rule. If the public URL fails or returns no bars, say so, use Yahoo for that series, and do not call the URL again.

## News history: GDELT 2.0 DOC API

Source: `https://api.gdeltproject.org/api/v2/doc/doc`. No key.

For each query below, two calls:

- `mode=timelinevolraw` (article counts)
- `mode=timelinetone` (average tone)

Frozen parameters: `format=json`, `startdatetime=20170101000000`, `enddatetime` = the UTC calendar date of the single study run at `000000`. No other mode, no `timespan`, no source-country filter.

Rate limit: at least **5 seconds** between GDELT HTTP calls. A cache hit does not sleep and is not a new call. Cache every response body under `services/quant/.cache/news-categories/`, which is gitignored. The cache is not a committed artefact.

Parsing, frozen now:

- Read `timeline[0].data` entries of `date` and `value`.
- Accept `YYYYMMDDHHMMSS` and ISO-like `YYYYMMDDTHHMMSSZ`.
- Bucket by the UTC date of that stamp. Sum volume inside the UTC date. Average tone inside the UTC date with weights equal to that query's volume (if volume is missing, equal weights).
- Build a calendar-day series from 2017-01-01 through the last returned date. Missing volume is **0**. Missing tone stays missing. Tone is never filled with 0.

Tone is descriptive. It is stored and may be quoted. It is not an outcome in the test family.

## Stored RSS is not a sample

`/api/v1/stocks/{symbol}/news` on the live site holds our own headlines from about 14 Oct 2026. That window is too short to test anything. It is not an outcome series, not a robustness check, and not a way to pick a category. It is used only later, if at all, to show that forward capture is wired. It cannot confirm or reject a category.

## Categories

There are ten categories. A category that has more than one query is one category: its volume that day is the **sum** of its queries' daily volumes. An event is defined on that sum, not on each query. Queries are copied below exactly, including parentheses, and are the strings sent to GDELT.

### 1. Geopolitics and war

Global wars, missile strikes, military escalation, and terror attacks, plus India–Pakistan and India–China as their own queries.

1. `(war OR warfare OR invasion OR bombardment OR "missile strike" OR "missile strikes" OR "military escalation" OR "terror attack" OR "terrorist attack")`
2. `("India Pakistan" OR "India-Pakistan" OR "Line of Control") AND (strike OR attack OR shelling OR ceasefire OR tension OR conflict)`
3. `("India China" OR "India-China" OR Galwan OR Ladakh OR "Line of Actual Control") AND (clash OR standoff OR incursion OR tension OR border)`

### 2. Crude oil and commodity shocks

1. `(crude OR brent OR OPEC OR "oil price" OR "oil prices") AND (surge OR jump OR plunge OR shock OR spike OR slump OR embargo OR "supply cut")`
2. `("commodity prices" OR "commodities selloff" OR "gold price") AND (surge OR jump OR plunge OR shock OR record)`

### 3. Central banks

1. `("Reserve Bank of India" OR "repo rate" OR "monetary policy committee" OR "RBI policy")`
2. `("Federal Reserve" OR FOMC OR "Fed rate" OR "interest rate decision") AND (hike OR cut OR hold OR pause OR decision)`

### 4. Inflation and macro data

India CPI, GDP, and IIP only. A global CPI print that does not mention India is not in this category.

1. `(CPI OR "consumer price index" OR "retail inflation" OR "wholesale inflation") AND (India OR Indian)`
2. `(GDP OR "gross domestic product" OR IIP OR "industrial production") AND (India OR Indian)`

### 5. Indian government policy, budget, and tax

1. `("Union Budget" OR "India budget" OR "finance bill") AND (India OR Indian)`
2. `(GST OR "tax cut" OR "tax hike" OR "import duty" OR "government policy") AND (India OR Indian OR "New Delhi")`

### 6. Elections and political instability

1. `("Lok Sabha" OR "assembly election" OR "general election" OR "vote counting") AND (India OR Indian)`
2. `("political crisis" OR "no-confidence" OR "coalition" OR resignation) AND (India OR "prime minister" OR "chief minister")`

### 7. Global market sell-offs

United States and China, as separate queries summed into one category.

1. `("S&P 500" OR Nasdaq OR "Dow Jones" OR "Wall Street") AND (plunge OR selloff OR "sell-off" OR crash OR tumble OR slump)`
2. `(Shanghai OR "Hong Kong stocks" OR "China stocks" OR "CSI 300") AND (plunge OR selloff OR crash OR tumble OR slump)`

### 8. Foreign investor flows and the rupee

1. `(FII OR FPI OR "foreign institutional" OR "foreign portfolio") AND (outflow OR inflow OR selling OR buying OR selloff)`
2. `(rupee) AND (slide OR slump OR "record low" OR "all-time low" OR depreciation OR weakens OR tumbles)`

### 9. Disasters and pandemics

Pandemics are global. Storms, quakes, and floods have to mention India.

1. `(pandemic OR COVID OR COVID-19 OR coronavirus OR lockdown)`
2. `(earthquake OR cyclone OR flood OR landslide) AND (India OR Indian)`

### 10. Trade wars, tariffs, and sanctions

1. `("trade war" OR tariff OR tariffs OR sanctions OR "trade dispute") AND (China OR India OR "United States" OR US OR Trump OR Biden)`

No eleventh category will be added after seeing prices. No query above will be widened or narrowed after seeing train.

## Event definition

A category's **event day** is a calendar day whose summed GDELT volume is at least two sample standard deviations above its own trailing 60-day mean.

Using only days strictly before day `t`:

- Need 60 earlier calendar days. Otherwise day `t` is not an event.
- Mean and sample standard deviation (`ddof=1`) of those 60 volumes.
- If the standard deviation is 0, day `t` is not an event.
- Otherwise day `t` is an event when `volume[t] >= mean + 2 * std`.

The test at `t` does not use volume after `t`, and does not use any price. Two event days that map to the same trading session (below) produce one event session, not two.

## Timing: clocks

Everything is judged in `Asia/Kolkata` (IST, UTC+05:30).

The cash session closes at 15:30 IST. A timestamp at or after 15:30 is after the close. The calendar in this repo already treats 15:30:00 as closed. This study uses that boundary.

For a news timestamp:

- Convert it to IST.
- If that IST date is a trading session and the IST time is **strictly before** 15:30, the news belongs to that session.
- Otherwise it belongs to the next trading session after that IST date.

So a headline at 15:30:00 or 15:30:01 IST belongs to the next session, and so does a headline at 09:00 IST on a holiday or a weekend.

## Timing: GDELT days have no clock

`timelinevolraw` does not say whether the articles ran before or after the Indian close. Treating the daily count as known at the open would credit same-day moves that may have happened first.

Frozen rule: a GDELT calendar day `D` (the UTC date bucket defined above) is treated as known only after that IST date is over. Its event session is the first trading session **strictly after** `D`. It never shares `D` even when `D` itself was a session.

The 15:30 rule above is what the code must do for any timestamped headline (the unit test, and any later RSS item). The GDELT study uses the daily rule in this section.

## Trading calendar

A date is a trading session when all of these hold:

1. It is not a Saturday or Sunday.
2. It is not in the closed-holiday set below.
3. The chosen NIFTY 50 daily series has a close on that date.

A weekday with no close is not a session (the exchange was shut, or the bar is missing). A close on a Saturday, Sunday, or listed holiday is not a session. Muhurat trading is in the closed set, matching `quant_agents.calendar.static_nse`, which treats Muhurat as closed rather than as a one-hour session. Close-to-close returns are not computed across a Muhurat print.

News that falls on a non-session waits for the next date that is a session.

The 2024–2026 dates are exactly `HOLIDAYS_2024`, `HOLIDAYS_2025`, and `HOLIDAYS_2026` in `services/quant/src/quant_agents/calendar/static_nse.py` at calendar version `static-nse-2024-2026.1`. They are copied into the research module so a later edit to the live calendar does not move this study.

2017–2023 weekday closures, plus Muhurat days, frozen from the NSE cash circulars and the compiled cash-segment list that matches those circulars for 2017 and 2023:

- 2017: 26 Jan, 24 Feb, 13 Mar, 4 Apr, 14 Apr, 1 May, 26 Jun, 15 Aug, 25 Aug, 2 Oct, 19 Oct, 20 Oct, 25 Dec
- 2018: 26 Jan, 13 Feb, 2 Mar, 29 Mar, 30 Mar, 1 May, 15 Aug, 22 Aug, 13 Sep, 20 Sep, 2 Oct, 18 Oct, 7 Nov, 8 Nov, 23 Nov, 25 Dec
- 2019: 4 Mar, 21 Mar, 17 Apr, 19 Apr, 29 Apr, 1 May, 5 Jun, 12 Aug, 15 Aug, 2 Sep, 10 Sep, 2 Oct, 8 Oct, 21 Oct, 27 Oct, 28 Oct, 12 Nov, 25 Dec
- 2020: 21 Feb, 10 Mar, 2 Apr, 6 Apr, 10 Apr, 14 Apr, 1 May, 25 May, 2 Oct, 14 Nov, 16 Nov, 30 Nov, 25 Dec
- 2021: 26 Jan, 11 Mar, 29 Mar, 2 Apr, 14 Apr, 21 Apr, 13 May, 21 Jul, 19 Aug, 10 Sep, 15 Oct, 4 Nov, 5 Nov, 19 Nov
- 2022: 26 Jan, 1 Mar, 18 Mar, 14 Apr, 15 Apr, 3 May, 9 Aug, 15 Aug, 31 Aug, 5 Oct, 24 Oct, 26 Oct, 8 Nov
- 2023: 26 Jan, 7 Mar, 30 Mar, 4 Apr, 7 Apr, 14 Apr, 1 May, 28 Jun, 15 Aug, 19 Sep, 2 Oct, 24 Oct, 12 Nov, 14 Nov, 27 Nov, 25 Dec

The result reports how many Yahoo `^NSEI` weekday closes were dropped for falling on this list, and how many weekdays in 2017–2026 had no close. Those counts are a calendar audit. They are not a licence to add or remove a date after train.

## Outcomes (index only)

Sessions are ordered by date. `close[t]` is the NIFTY 50 close of session `t`. `vix[t]` is the India VIX close of session `t`.

Close-to-close return of session `t` (needs session `t-1`):

`ret[t] = close[t] / close[t-1] - 1`

India VIX percent change:

`vix_chg[t] = vix[t] / vix[t-1] - 1`

For an event session `t`:

| Name | Definition |
|---|---|
| `ret_0` | `ret[t]`, the return of the assigned session |
| `ret_1` | `ret[t+1]` |
| `ret_1_5` | `close[t+5] / close[t] - 1` (sessions +1 through +5, not including day 0) |
| `abs_0` | `abs(ret_0)` |
| `abs_1` | `abs(ret_1)` |
| `abs_1_5` | `abs(ret_1_5)` |
| `vix_0` | `vix_chg[t]` |
| `vix_1` | `vix_chg[t+1]` |
| `vix_1_5` | `vix[t+5] / vix[t] - 1` |

If `t-1`, `t+1`, or `t+5` does not exist, or a VIX close is missing, that outcome is missing for that session. Missing values are left out of the mean. They are not filled with zero.

## Intraday realised volatility

Only sessions that appear in the single 5-minute response, and only from 2024-01-01 onward. For session `t`, realised variance is the sum of squared 5-minute log returns of the bars that belong to that session (see the price section). The first bar of the session has no return. If the session has fewer than two usable bars, RV is missing.

| Name | Definition |
|---|---|
| `rv_0` | RV of session `t` |
| `rv_1` | RV of session `t+1` |
| `rv_1_5` | mean of RV on `t+1` through `t+5`, and missing if any of those five is missing |

RV is not annualised. There is no second download if 2024 is only partly covered. Outcomes with fewer than two event sessions or fewer than two non-event sessions in a split are undefined: the difference is null and the p-value is 1. They stay in the Holm family.

## Comparison: all other sessions

Inside one split, the statistic for an outcome is:

`mean(outcome | event session) - mean(outcome | every other session in the split with a finite outcome)`

"Other" means not an event session for **that category**. Other categories' event sessions stay in the control group. The study does not build a day that is quiet in every category.

This unmatched difference is the statistic the pass rule uses.

## Comparison: same weekday and VIX tercile

Also compute a matched difference. It does **not** enter the Holm family and it does **not** change the pass rule. It is reported so a weekday or volatility mix is visible.

- The tercile of session `t` uses India VIX at `t-1` (known before the open), not VIX at `t`.
- Cutpoints are the one-third and two-thirds quantiles of those previous-close VIX values on **train** sessions only. Validate uses the same two numbers. They are not refit.
- Stratum = weekday of `t` crossed with that tercile (`<=` lower cut is low, `<=` upper cut is mid, else high).
- Inside a stratum that has at least one event and one non-event, take the difference of means. The matched statistic is the average of those differences weighted by the number of event sessions in the stratum.
- A session with no previous VIX, or a stratum with no control, is left out of the matched statistic only.

## Statistics: block bootstrap

For each category, outcome, and split, on the unmatched difference:

- Circular moving-block bootstrap of the session sequence.
- Block length **5** trading sessions.
- **5,000** resamples.
- Seed **0**, via `numpy.random.Generator(numpy.random.PCG64(0))`. Each test constructs its own generator from seed 0, so the p-value does not depend on call order.
- Two-sided p-value, with the bootstrap distribution recentered by subtracting the observed difference. Add-one smoothing: `(1 + count(|boot - observed| >= |observed|)) / 5001`.
- If either group has fewer than two finite observations, do not draw a bootstrap. Difference is null and p = 1.

The unit test must show that two calls with seed 0 return the same p-value and the same bootstrap draws.

## Statistics: Holm

The family is the 10 categories times these 12 outcomes: `ret_0`, `ret_1`, `ret_1_5`, `abs_0`, `abs_1`, `abs_1_5`, `vix_0`, `vix_1`, `vix_1_5`, `rv_0`, `rv_1`, `rv_1_5`. That is 120 train tests. Validate p-values are not put through Holm again.

Sort train p-values from smallest to largest. For rank `i` starting at 1, the Holm step is `(120 - i + 1) * p`. The adjusted p-value is the running maximum of those steps, capped at 1, so the adjusted values stay ordered.

A train test with p = 1 (too few observations, including RV outside the 5-minute window) still occupies a slot in the family.

## Split

| Split | Sessions | Role |
|---|---|---|
| Train | 2017-01-01 through 2022-12-31 inclusive | the only place exploratory tables may be read |
| Validate | 2023-01-01 through the last session in the price file | scored **once** |

The event rule may use 2022 volume when it labels a 2023 session, because those days are past volume, not past outcomes. Outcome rows do not cross the split: a train mean uses only train sessions, a validate mean uses only validate sessions.

No query, threshold, window, holiday, or pass rule is chosen from validate. Nothing is chosen from train either, beyond what this file already fixes. Seeing the train table is allowed. Editing this file after that table exists is not.

