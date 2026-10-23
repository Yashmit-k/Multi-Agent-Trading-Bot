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

Frozen parameters: `format=json`, coverage from `20170101000000` through the UTC calendar date of the single study run at `000000`. No other mode, no `timespan`, no source-country filter.

GDELT answers `429` ("larger queries") for that full span even when the caller is already waiting 5 seconds, and it does so before any train table exists. Each query is therefore requested in non-overlapping windows of at most 700 calendar days, still with the same mode, format, and query string. The windows are concatenated by UTC date. A date that appears in two windows is an error, not an average. This split does not change a category, the event rule, or the pass rule.

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

## What may be chosen on train

Nothing. The trailing window stays 60. The threshold stays 2 standard deviations. The twelve outcomes stay the family. The control stays "all other sessions in the split". There is no model to fit and no variant table to pick from.

The sentence in the task that train is where we explore and choose is satisfied by writing the choices here, before either split is scored, and by refusing any later choice. A train table that looks strong is not a reason to drop a weak outcome from Holm or to add one.

## Pass rule

A category **matters** only if at least one of its 12 outcomes does all of the following:

1. Holm-adjusted train p < 0.05.
2. On validate, the unadjusted p of that same outcome is < 0.05.
3. The sign of the mean difference (event minus other) is the same on train and on validate, and neither difference is zero.

One passing outcome is enough for the category. The matched-weekday statistic is printed beside it and is not required. A category that fails this rule is a miss, including a category that is significant on train and flips sign or loses the validate p-value.

## If nothing passes

Write this conclusion, and stop:

> Under this pre-registered design, no news category has a volume spike that lines up with the NIFTY 50 index on 2017–2022 and then again, in the same direction, on 2023 onward. That is a negative result. It does not support adding a market-wide news vote, changing fusion, or loosening the 2 standard-deviation rule. The forward capture switch stays off unless someone turns it on for storage only.

Do not replace the threshold with 1.5, do not drop RV from Holm after the fact, do not restrict the family to the outcome that looked closest, and do not run a second validate. A near miss is still a miss.

## Limits, written before the run

- GDELT's news crawl is global. A spike can be driven by outlets that Indian markets never read. There is no India-source filter except where a query already requires the word India.
- Article counts are not importance. A duplicated wire story and a policy shock can both clear 2 standard deviations.
- A busy day mixes categories. The control group is not a news-free day.
- The daily bucket has no clock, so the study gives the whole UTC day to the next Indian session. That avoids same-day look-ahead and it can also lag a morning story by one session.
- The holiday list can still disagree with a special NSE circular. The calendar audit reports that. It does not get patched between train and validate.
- A difference in means is not a cause. Nothing here is a trading rule.
- The 5-minute realised-volatility window is only as long as one polite API call. A miss on RV does not get a second download.
- Our RSS store is too short to test, as already stated.

## Run order and committed outputs

1. Commit this protocol.
2. Implement the detector, the clock rule, and the bootstrap, with unit tests on synthetic series. Those tests do not download GDELT or prices.
3. Run **train** only. If the code needs a bugfix that does not change a frozen choice, commit the fix and rerun train. Do not open validate in that same process.
4. Commit a one-line freeze: no specification change after train.
5. Run **validate** once in a later process.
6. Write `services/quant/docs/news-categories-nifty-result.md` and `services/quant/docs/results/news-categories-nifty-result.json`.

The JSON holds category ids, event counts, mean differences, ratios of mean absolute moves, VIX differences, p-values, Holm p-values, and the pass flag. It does not hold the raw daily series. The markdown holds one table per category and the conclusion in plain sentences, including the limits above.

The protocol commit is the evidence that these rules existed before the result. The result note will quote that commit.

## Amendment A — before any train table

No train table has been computed. The sentences below replace the conflicting sentence "Missing volume is **0**" for days that were never successfully fetched. They do not change the ten queries, the 60-day window, the 2 standard-deviation threshold, the outcomes, the Holm family, or the pass rule.

### A day that was never fetched is not a zero

- A calendar day is **observed** for a query only when a successful `timelinevolraw` response covers it.
- Inside one successful response, a date the timeline omits between its first and last returned date has volume **0**. The API answered that span.
- A date outside every successful response is **missing**. It is not stored as 0, it is not an event, and it is not a control day.
- A category day is observed only when every query in that category is observed. The category volume is the sum of those queries. If any query is missing, the category day is missing.
- The trailing 60 days are the previous 60 calendar days. If any of them is missing, that day is not eligible for an event test. The threshold is not computed from a shorter window and not from zeros standing in for failed calls.
- HTTP 429, a dropped connection, a non-JSON body, and an empty body that is not a successful timeline are failures. They do not create volume.

### Article counts cannot be de-duplicated

`timelinevolraw` returns a count per day, not article identifiers. The same story can match two queries in one category and be counted twice in the sum. That double count stays in the volume. It is a limit of this API mode, not a second event rule. Tone stays descriptive and is still not in the Holm family.

### Interval, not only a p-value

The bootstrap draws already defined above also supply a 95% percentile interval: the 2.5 and 97.5 percentiles of the resampled differences, seed 0, same block length. The p-value stays the recentered two-sided test. The interval is reported beside it. A low p-value is not a cause.

### No table until coverage is complete

Train is not scored while any category is missing volume days inside 2017-01-01 through the study end date. The run writes the missing ranges and stops. It does not fill them with zero and it does not print a pass or a fail. Validate is not opened. A later resume uses the cache and does not repeat a request whose body is already stored.

## Amendment B — news source: GDELT raw daily GKG files instead of the DOC API

Status: **PROPOSED, not in force.** It takes effect only when a later commit adds the line "Amendment B approved by <name>, <date>" below this heading. Until then, Amendment A and the sections above apply unchanged, and the study stays BLOCKED.

### Why

No train table has been computed. Everything below changes only *where the daily news volume comes from*. It does not change the 60-day window, the 2 standard-deviation rule, the clock and calendar rules, the twelve outcomes, the Holm family, the split, the bootstrap, the pass rule, or the "if nothing passes" sentence.

The DOC API (`api.gdeltproject.org/api/v2/doc/doc`) returned HTTP 429 to even a single two-week request on 2026-10-22 and again on 2026-10-23, despite 12–90 s waits. About 435 windows remain, so the study cannot finish that way. GDELT also publishes the same crawl as static daily files with no rate limit.

### Disclosure before this amendment

Before this amendment was written, two files were opened to confirm the format, and nothing else:
- `20261020.gkg.csv.zip` (a validate-period date). Its header, its theme vocabulary and that day's row count per theme were printed.
- `20170103.gkg.csv.zip` (a train-period date). This confirmed the same 11-column header, that each of the 27 themes in the rules below already existed then (each with a non-zero row count), and the counts of the three organisation names.

No price was read, no event rule was run, no category volume was built, and nothing was compared with any outcome. The rules were written from GDELT's theme names to match the DOC queries' intent. They were not tuned on those two days' numbers.

### Source

- One file per UTC calendar date `D`, from 2017-01-01 through the day before the single study run: `https://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip` (GDELT 1.0 Global Knowledge Graph, daily).
- **Columns, exactly:** `DATE NUMARTS COUNTS THEMES LOCATIONS PERSONS ORGANIZATIONS TONE CAMEOEVENTIDS SOURCES SOURCEURLS` (tab-separated, with a header row).
- **When a day counts as observed:** the file is downloaded with HTTP 200, unzips, and has exactly that header.
- **When it counts as missing:** any other result (404, a truncated zip, a different header). Missing follows Amendment A: not a zero, not an event, not a control day.
- **Downloads:** at least 2 s apart and at most one at a time. Each zip is streamed, reduced to that day's per-category numbers, and deleted. Only those per-day numbers, plus each file's byte size and SHA-256, are cached under `services/quant/.cache/news-categories/` (gitignored).
- **Old DOC cache:** the partial DOC responses already cached are not used for scoring and are not mixed with GKG numbers.

### One record

For each row:
- `T` is the set of `THEMES` (split on `;`).
- `C` is the set of country codes in `LOCATIONS`: each location is `type#name#COUNTRY#…`, and the third field is the FIPS code (IN India, PK Pakistan, CH China, US United States, HK Hong Kong).
- `O` is the set of `ORGANIZATIONS`, lower-cased.
- `n` is `NUMARTS` (articles).
- `tone` is the first number in `TONE`.

A row whose `DATE` is not the file's date `D` is not counted, and the number of such rows is reported in a calendar audit.

### Category volume, replacing the ten DOC query lists

The category volume for day `D` is the **sum of `n` over rows that match the category's rule**. A row counts **once per category**, even when it matches several clauses. This removes the within-category double count that Amendment A had to accept. A row may count in several categories.

The rules are frozen now:

| # | Category | Rule |
|---|---|---|
| 1 | Geopolitics and war | `T` contains `ARMEDCONFLICT` or `TERROR` |
| 2 | Crude oil and commodity shocks | `T` contains `ECON_OILPRICE`, `ECON_GOLDPRICE` or `FUELPRICES` |
| 3 | Central banks | (`O` contains `reserve bank of india`) **or** (`O` contains `federal reserve` or `federal reserve bank`, **and** `T` contains `ECON_INTEREST_RATES`, `ECON_CENTRALBANK` or `EPU_POLICY_MONETARY_POLICY`) **or** (`IN` in `C` **and** `T` contains `ECON_CENTRALBANK`, `EPU_POLICY_CENTRAL_BANK` or `EPU_POLICY_MONETARY_POLICY`) |
| 4 | Inflation and macro data (India) | `IN` in `C` **and** `T` contains `ECON_INFLATION` |
| 5 | Indian government policy, budget and tax | `IN` in `C` **and** `T` contains `ECON_TAXATION`, `EPU_POLICY_TAX`, `EPU_CATS_TAXES`, `EPU_POLICY_BUDGET` or `ECON_BUDGET_DEFICIT` |
| 6 | Elections and political instability (India) | `IN` in `C` **and** `T` contains `ELECTION`, `ELECTION_FRAUD` or `EPU_POLICY_POLITICAL` |
| 7 | Global market sell-offs | `T` contains `ECON_STOCKMARKET` **and** `C` contains `US`, `CH` or `HK` **and** `IN` not in `C` **and** `tone < 0` |
| 8 | Foreign investor flows and the rupee | (`IN` in `C` **and** `T` contains `ECON_FOREIGNINVEST`) **or** `T` contains `ECON_WORLDCURRENCIES_INDIAN_RUPEE` or `ECON_WORLDCURRENCIES_INDIAN_RUPEES` |
| 9 | Disasters and pandemics | `T` contains `HEALTH_PANDEMIC` **or** (`T` contains `NATURAL_DISASTER` **and** `IN` in `C`) |
| 10 | Trade wars, tariffs and sanctions | `T` contains `ECON_TRADE_DISPUTE`, `SANCTIONS` or `EPU_CATS_TRADE_POLICY` **and** `C` contains `CH`, `IN` or `US` |

**Descriptive sub-series only.** For category 1, also store the volume of matching rows whose `C` contains both `IN` and `PK`, and both `IN` and `CH`. These show the India–Pakistan and India–China parts the DOC queries named. They are **not** extra categories and are **not** in the Holm family.

**Tone.** The `n`-weighted mean of `tone` per category per day replaces DOC `timelinetone`. It is still descriptive only and not an outcome.

**Not a query match.** These are fixed theme rules, not the DOC free-text queries, so they are not the same filter:
- Category 2 cannot require "surge / plunge / shock".
- Category 4 has no GDP or IIP theme.
- Category 7 uses negative tone as its stand-in for "sell-off".

The volume-spike rule is what still picks out unusual days. These differences are a limitation of the new source, and the result must state them.

### Everything else stays

- **Timing:** the GKG `DATE` bucket has no clock, so the "GDELT days have no clock" rule above applies unchanged. Day `D` goes to the first trading session strictly after `D`.
- **Coverage:** Amendment A's "no table until coverage is complete" applies to the GKG days. For example, if any of the 60 trailing days is missing, that day is not tested.
- **Order:** the run order is unchanged. Train first in one process, a freeze commit, then validate once in a later process.

### What changes in the code (after approval)

- A GKG reader that streams one zip, applies the ten rules and returns that day's per-category volume, tone and audit counts.
- Unit tests on small synthetic GKG rows:
  - each rule's clauses;
  - a row counting once per category;
  - a wrong-date row being dropped;
  - a bad header making the day missing.
- The DOC fetch path stays in the module for reference, but is not called by `plan` or `train` once this amendment is in force.

Expected size: about 3,580 daily files of 30–60 MB each, roughly 150 GB downloaded once. Only a few kilobytes per day are kept.
