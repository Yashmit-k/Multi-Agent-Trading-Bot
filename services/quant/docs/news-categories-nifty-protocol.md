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

