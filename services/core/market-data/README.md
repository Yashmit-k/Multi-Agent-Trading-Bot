# Market data

Phase 1–2 ingestion is NSE-only. `FakeMarketDataProvider` comes from `packages/contracts`. `HistoricalReplayMarketDataProvider` reads stored ticks and candles through `CoreRepository` and returns nothing with an effective time after `as_of`.

`ZerodhaMarketDataProvider` is isolated here. Missing `ZERODHA_API_KEY` and `ZERODHA_API_SECRET` leaves the login routes unconfigured. The access token from `generate_session` stays in the API process. `LIVE` stays off, and this adapter does not place orders.

Historical day and 5-minute downloads run for symbols already in the repository. Instrument tokens come from `instruments("NSE")` and are stored on those rows. Requests are paced at three per second and split into the Kite window for each interval.

## Later requirements

These are still not implemented:

- Tick deduplication
- Reconnect handling
- Out-of-order tick handling
- Websocket streaming
