# Market data collector

The collector keeps stored NSE candles current. It does not place orders, submit signals, or run the paper cycle. `core-worker` still owns paper execution and stays a separate process.

This is not a live websocket feed. It polls Zerodha historical candles. Automated tests use a fake client. A passing test does not mean the live Zerodha session has been verified.

## Two paths

The one-time seed remains `ingest_seed_history`. The login callback still queues it for `SEED_HISTORY_DAYS` (100 days) of daily and 5-minute bars. Complete chunks are skipped. A repeated download updates the same candle id (`instrument`, timeframe, bar start) and does not insert a duplicate. One symbol or timeframe timeout is recorded as `Timeframe:ErrorName` and the next symbol continues. A historical read is retried up to three times with delays of 0.5s, 1s, and 2s, and the existing pace keeps calls at or below three per second. Timeouts and HTTP 429 responses are retried. An invalid or rejected access token is not retried; the seed stops and the symbols already written stay stored, so a later seed resumes them.

The scheduler does not repeat that 100-day download. `run_incremental_once` asks only for the gap after each symbol's last stored bar. A symbol with no stored bar is marked `needs_seed` and left for the callback seed. A second pass while one is running is skipped.

## When it polls

`core-api` starts the loop only when `MARKET_DATA_COLLECTOR=true`. Compose sets that value. The running container does not pick it up until that service is recreated, which this change does not do. The loop sleeps `MARKET_DATA_POLL_SECONDS` (60). It polls during the NSE cash session, 09:15–15:30 IST, after a 90-second publication delay, and it catches up after an outage by requesting from the last stored bar to now.

A daily bar is complete at 15:30 IST. Before the close plus the delay, yesterday's completed daily bar is the fresh one, or Friday's bar across a weekend. 2 October 2026 is a holiday, so the previous session is 1 October. Five-minute freshness during the session is the last 5-minute end that is already 90 seconds old. After the close, a 5-minute series is fresh when it reaches 15:15 IST. The provider has omitted the last 15 minutes before; those bars are not invented.

Bars whose end is still in the future are not stored. The feature endpoint builds from bars with `end <= as_of`, so an unfinished daily bar is not a completed feature.

## Authentication

An API key and secret only mean a Kite client can be constructed. `GET /api/v1/zerodha/status` stays `authenticated: false` until `GET /api/v1/zerodha/callback` exchanges a new `request_token`. That token is kept in the API process memory and is not written to logs, source, or the image. After a restart the memory is empty. `GET /api/v1/market/ingestion` then reports `authentication_required`. Recovery is a new login from `GET /api/v1/zerodha/connect`. Do not reuse a request token.

`GET /api/v1/market/ingestion` also reports the latest stored daily and 5-minute ends seen on the last cycle, per-symbol freshness, missing bars in the incremental window, the last error type, and whether a pass is running. `live_enabled` is false. The collector never submits an order.

## Paper guard

`core-worker` passes `require_fresh=True` unless `PAPER_REQUIRE_FRESH_CANDLES` is `false`. A new entry is skipped when that symbol's latest candle is behind the completed bar for the horizon. Intraday uses 5-minute bars. Swing and long-term use the daily bar. Existing tests call the paper cycle without that flag, so historical fixtures still fill. The worker is stopped and was not started to test this.

## Before paper execution

Finish a seed for symbols still marked `needs_seed` or left stale by the earlier timeout. Confirm `GET /api/v1/features/{symbol}` for daily and 5-minute data, with the worker still stopped. Recreate `core-api` only when you want the new loop to run. Start `core-worker` only after a separate approval. The portfolio was not reset.
