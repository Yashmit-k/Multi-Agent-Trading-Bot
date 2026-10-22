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

