# Market data

Phase 1–2 ingestion is NSE-only. `FakeMarketDataProvider` comes from `packages/contracts`. `HistoricalReplayMarketDataProvider` reads stored ticks and candles through `CoreRepository` and returns nothing with an effective time after `as_of`.

`ZerodhaMarketDataProvider` is isolated here. Missing `ZERODHA_API_KEY` or `ZERODHA_ACCESS_TOKEN` makes the provider unavailable. It does not crash the API, and it does not rename contract order types.

## Later requirements

These are not implemented in Phase 1–2:

- Tick deduplication
- Reconnect handling
- Out-of-order tick handling
- Rate-limit handling for Zerodha historical and instrument-sync calls

Historical and instrument-sync API calls must be throttled before live use. This slice does not include throttling tests.
