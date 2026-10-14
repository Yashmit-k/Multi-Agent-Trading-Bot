# Trading system integration audit

Read-only check on 2026-10-12. ML is excluded. No container was restarted, no signal or order was submitted, and the database was not queried.

The paper path is implemented and covered by unit and in-memory tests. It is not fully integrated as a live loop on the current source. Quant and intelligence containers are still running earlier images. The dashboard was not opened in a browser in this audit.

## Runtime versus source

Compose defines postgres, redis, core-api, core-worker, intelligence, quant, and frontend. Postgres and core-api have health checks. Quant and intelligence wait for core-api to be healthy.

| Service | Latest image | Container image | Match |
|---|---|---|---|
| core-api | `752d8cc20e91` (2026-10-11 21:02 UTC) | same | yes |
| core-worker | `c7d10627b691` (same build time) | same | yes |
| frontend | `ee11c860857b` (2026-10-11 21:02 UTC) | same | yes |
| quant | `39d45402582e` (2026-10-12 04:30 UTC) | `1f26ff040a92` (created 2026-10-11 21:08 UTC) | no |
| intelligence | `da922954f582` (2026-10-11 21:52 UTC) | `f384ed9e5d66` (created 2026-10-11 21:08 UTC) | no |

This session: `GET /health` on ports 8000, 8102, and 8101 returned 200. Intelligence reported `llm_mode=fixture`, `sink_reachable=true`, and a last run at 2026-10-12 06:38 UTC. That is the older intelligence image. Authenticated status, signal lists, and order lists were not requested.

Documented earlier, and not re-run here: `tests/test_phase4.py`, `tests/test_dev3.py`, and `tests/test_backtest.py` were recorded as 31 passed on 2026-10-12. Frontend unit tests were recorded as 12 passed. Those results do not prove the images that are running now.

## Connections

| Connection | Status | Evidence |
|---|---|---|
| Live market source to collector | NOT VERIFIED | `services/core/market-data` has a Zerodha client. `.env.example` leaves the keys empty. Zerodha status was not called. |
| Collector to stored candles | PARTIALLY VERIFIED | Snapshot load and candle schema exist. A live collector was not observed. |
| Candle store to market-data provider | PARTIALLY VERIFIED | `HistoricalReplayMarketDataProvider` reads `snapshots 2/nifty50`. Not replayed in this audit. |
| Provider to Feature Engine | PARTIALLY VERIFIED | `build_feature_set` keeps bars with `end <= as_of` and omits missing values. Unit coverage exists. Not replayed here. |
| Feature Engine to five Quant agents | PARTIALLY VERIFIED | `paper.py` lists `technical`, `momentum`, `mean_reversion`, `volume`, and `regime`. Agents read `FeatureView`. Tests exist. The running quant image is older than `quant:latest`. |
| Point-in-time and missing history | PARTIALLY VERIFIED | Feature engine and agent code omit or skip missing inputs. Not demonstrated on the running stack in this audit. |
| Quant output to signal contract | VERIFIED | Agents build `AgentSignal`. Contract tests and paper tests cover the schema. This is code and test evidence, not a new runtime post. |
| Quant worker to Core ingestion | PARTIALLY VERIFIED | `service.py` posts through `CoreSignalSink` after core health. Running quant health is ok. Current source is not the running image. No new signal was submitted. |
| Fixtures to intelligence agents | PARTIALLY VERIFIED | Compose sets `INTELLIGENCE_DATA_SOURCE=fixtures`. Running health shows fixture LLM mode and a completed cycle. Valuation outside five symbols is a known skip in current source; that skip is not proven on the older running image. |
| RSS to NewsAgent | BLOCKED | RSS code exists and is off unless configured. Compose stays on fixtures. No feed was fetched. |
| CSV to FundamentalAgent | BLOCKED | CSV loader exists. Compose does not set `csv-live`. |
| Intelligence to Core ingestion | PARTIALLY VERIFIED | HTTP sink and internal signal route exist. Running intelligence reports the sink reachable. Current source is not the running image. |
| Ingestion validation and dedupe | VERIFIED | `ingest_signal` validates and treats an existing `signal_id` as a duplicate. Covered by ingestion tests, not by a new insert. |
| Accepted signals to storage | PARTIALLY VERIFIED | Insert path is in `ingest_signal`. Persistence in the running database was not queried. |
| Store to fusion | PARTIALLY VERIFIED | `fuse` reads stored signals. Paper-cycle tests use an in-memory repository. |
| Fusion to decision | PARTIALLY VERIFIED | `run_paper_cycle` fuses, then builds a proposal. Same in-memory tests. |
| Decision to risk | VERIFIED | `assess` accepts `PAPER` only and records reason-coded failures. `tests/test_phase4.py` covers non-paper, cash, notional, and shorts. Not re-run in this audit. |
| Risk result to downstream | VERIFIED | The paper cycle queues an order only after approval. Rejection tests exist. Not re-run here. |
| Approved decision to paper order | PARTIALLY VERIFIED | `cycle.py` queues `fill_at=next_open`. No order was created in this audit. |
| Order to fill | PARTIALLY VERIFIED | Fill uses the next stored open, default 2 bp, and stop-first if stop and target share a bar. Covered by `tests/test_dev3.py` and `tests/test_backtest.py`. Not re-run here. |
| Fill to order state, positions, cash, P&L | PARTIALLY VERIFIED | Repository updates are in the paper cycle. Running portfolio state was not read. |
| Restart and duplicate protection | PARTIALLY VERIFIED | Duplicate `signal_id` and stored proposal identity are in source. Restart recovery was not exercised. |
| API read endpoints | PARTIALLY VERIFIED | Routes exist for signals, orders, positions, portfolio, and paper status. This audit called only `/health`. |
| API to dashboard | NOT VERIFIED | Frontend pages exist. No browser session was run. |
| Dashboard matches positions and P&L | NOT VERIFIED | No browser session. |
| Snapshots to replay provider | PARTIALLY VERIFIED | `open_snapshot` maps the two permitted snapshot ids and refuses the holdout id. Not executed. |
| Replay to features and backtest | PARTIALLY VERIFIED | Backtest uses the same fill helper as paper. Research reports exist from earlier runs. Not executed here. |
| Backtest to reports | PARTIALLY VERIFIED | Reports under `datasets/research` and `docs` exist from earlier work. Not regenerated. |

`VERIFIED` in this table means the code and existing tests show the behavior. It does not mean this audit posted a signal or watched a fill.

## Blockers and unverified areas

- Quant and intelligence processes are not running the latest images.
- RSS and CSV are implemented and not the Compose data source.
- A live Zerodha collector was not shown to be configured.
- Dashboard behavior was not opened in a browser.
- Running orders, positions, and cash were not read, because that would use the API beyond the health check or touch the database.

## Next steps for paper mode

1. Leave Postgres volumes and Compose environment as they are.
2. When approved, recreate only `quant` and `intelligence` from the current images. Do not use a volume reset.
3. Repeat read-only health checks. Do not post signals by hand.
4. Open the dashboard and compare it with read-only API state.
5. Keep fixtures as the intelligence source until a real news archive exists.

## Later live-trading work

- Broker credentials and a verified collector.
- `live_enabled` stays false in the API responses today.
- Risk still rejects modes other than `PAPER`.
- RSS or CSV, if used, need an explicit configuration and a point-in-time archive.
- ML and H001 are separate and are not part of this integration.

ML was not trained or wired in this audit. H001 was not run. `snapshots/holdout_after_20261005` was not opened. Paper state and running configuration were not changed. The only file written is this report.
