# Developer 3 gap register

Checkpoint 2 is recorded below the original Checkpoint 1 baseline. It stays in this folder on `developer-3`. The production stack was not queried, migrated, or started.

## Checkpoint 2

The collector status for a symbol is re-read after that timeframe's upsert. Daily and five-minute candles are read separately. `PUBLICATION_DELAY` is still 90 seconds, and `expected_completed_end` is unchanged.

`tests/test_market_collector.py::test_returned_status_matches_the_bar_just_persisted` failed first: the returned daily end was `2026-10-09T10:00:00+00:00` while the stored bar was `2026-10-12T10:00:00+00:00`. After the re-read, the same test passed. The returned daily end, five-minute end, and freshness match the bars persisted at the controlled clock `2026-10-13T05:00:00Z`.

`test_after_the_close_the_expected_five_minute_end_is_1515` passed. At 15:31:30 IST on 2026-10-13 the expected five-minute end is 15:15 IST, not 15:25 or 15:30.

`tests/test_entry_gate_postgres.py` passed on disposable PostgreSQL 16, bound only to `127.0.0.1:55434`, database `dev3_entry_gate`. Five qualifying entries were stored, then two `queue_entry` calls ran on independent connections. Exactly one more qualifying entry was stored. The final count was 6. The container was removed.

`tests/test_collector_isolation.py` passed against project `dev3-cp2-collector` using only `docker-compose.checkpoint2.yml`. Postgres was on `127.0.0.1:15432`, the probe on `127.0.0.1:18000`, with network `dev3-cp2-collector-net` and volume `dev3-cp2-collector-data`. The file has no `core-worker`. The scripted client does not call Zerodha. The probe persisted at least two five-minute bars through `run_incremental_once`. After `collector-api` stopped, the isolated candle count did not change. The project was removed with `down -v`.

This Compose run is scripted collector behavior. It does not prove live Zerodha connectivity or freshness of the production database. Production stored bars against `expected_completed_end` stay **NOT VERIFIED**. The running Core API was not rebuilt, so this ordering fix is not deployed.

## Checkpoint 3

`GET /api/v1/paper/daily-performance` returns `status: unavailable` and `reason: no_daily_equity_history`. It does not return realized P&L, Sharpe, drawdown, or a daily return. `GET /api/v1/performance` is still the latest backtest. `docs/dev3-snapshot-writer-design.md` describes one snapshot per IST date after the close and the 90-second delay. No job writes that row.

`GET /api/v1/worker/heartbeat` is unavailable until a beat is recorded, and again when that beat is older than the worker interval. The worker loop calls `publish_heartbeat` once per pass. Tests do not import `core_worker.__main__`. Core API was not restarted and `core-worker` was not started, so this route is not on the running process.

## Checkpoint 1

Recorded 2026-10-13. This checkpoint writes the register only. It does not change a cap, fix the collector, run a paper cycle, start `core-worker`, restart Core API, apply a migration, query production SQL, hash the holdout, or push.

## Baseline

| Item | Value |
| --- | --- |
| Branch | `dev3/checkpoint-1-gap-register`, created from `developer-3` |
| Commit | `eff7217` (`test: check the daily snapshot rule without a local snapshot`) |
| Worktree | Dedicated worktree. The `developer-3` checkout was left at the same commit. |
| Remote | This commit is local to the checkpoint branch. It is not pushed. |

`eff7217` is the parent of the register commit. Ancestors that matter for policy: `fd9a0de` (research backtests keep their own bound), `7604ea9` (paper notional and the six-entry gate), `144bc08` (paper policy still at ₹1,00,000).

## Access used

Permitted reads were existing HTTP APIs and `alembic current` against the running environment. No production SQL was run.

- `GET /health` returned `ok`.
- `GET /api/v1/system/status`: `PAPER`, `live_enabled` false, `zerodha_configured` false. That flag is the process environment check. It is not the in-memory login state.
- `GET /api/v1/zerodha/status`: configured, authenticated, `live_enabled` false.
- `GET /api/v1/paper/status`: `PAPER`, `live_enabled` false, running, session `c6c7f91fe84f4d48862c4a1b85646f3b`, starting cash `1000000`.
- `GET /api/v1/paper/sessions`: that session is active. Session `48951a4aa41c6dd3bc0e40bbdf2f548b98b2cc35d8d8fee894b9b5b59fa11b61` is closed with starting cash `100000`.
- `GET /api/v1/market/ingestion`: collector enabled, authenticated, `last_error` null, `credentials_rejected` false, `poll_skip_reason` `seed_active`, `last_success_at` `2026-10-13T07:28:56.376018+00:00` (12:58:56 IST), `latest_intraday_end` `2026-10-13T07:20:00+00:00` (12:50 IST), 50 symbol rows, 0 symbol errors, `symbols_fresh_intraday` 0, `symbols_stale` 50.
- `GET /api/v1/performance` returned 404. In source that route is the latest stored backtest, and 404 is `no_backtest`. It is not a daily paper P&L route.
- `alembic current`: `0007_entry_day_gates (head)`.
- Container state, read without starting anything: Core API running, Postgres running, `core-worker` exited 137 on image `sha256:5ea8292147331f73d32c1626526ffd4a24a8f6784299e0669ab192501eb863bc`. The API has no worker field, so this container state is not an API result.

Anything that needed production SQL, an API restart, a worker start, or an isolated Compose project is **NOT VERIFIED** or **BLOCKED** below.

## Tests already on this commit

This checkpoint did not re-run the suite and did not start a disposable database.

The paper lifecycle, entry window, one-shot clock, order cap, notional, and daily-entry tests live under `tests/`. They use SQLite. The six-entry race against real PostgreSQL is not one of those tests.

Quant unit tests were last run locally on this commit with paper execution on the path: 136 passed, none skipped. `services/quant/tests/unit/test_daily_rules.py` covers the snapshot-path guard with a temporary directory. It does not open the real snapshot or the holdout.

## Register

Status is `PASS`, `FAIL`, `BLOCKED`, or `NOT VERIFIED`. "Later checkpoint" means a later checkpoint may change it after review. This checkpoint does not.

| Gap | Status | Evidence | Owner | Later checkpoint |
| --- | --- | --- | --- | --- |
| Paper buy notional is ₹20,000. Fees sit on top. The code cap was not changed. | PASS | `execute.py` `MAX_NOTIONAL = Decimal("20000")`. `assess.py` default bound is `20000`. `7604ea9` introduced the paper cap. `fd9a0de` left paper callers on that default. | Developer 3 | No. Do not raise it. |
| Research backtests still use ₹1,00,000. | PASS | `backtest.py` `MAX_NOTIONAL = Decimal("100000")` is passed into `assess` as `max_notional`. `fd9a0de`. | Developer 3 | No. Do not fold it into the paper cap. |
| Older policy text still says ₹1,00,000 for the paper order. | FAIL | `docs/paper-execution-policy.md` still says the per-order cap remains ₹1,00,000. `144bc08` (2026-10-12) still had `MAX_NOTIONAL = Decimal("100000")` in `execute.py` and `assess.py`. `docs/architecture.md` and `docs/current-status.md` already say 20,000. | Developer 3 | Documentation only, after review. The code cap stays ₹20,000. |
| Six qualifying CNC buys per IST date. | PASS | `repository.py` `DAILY_ENTRY_LIMIT = 6`. Counted rows are BUY, not `REJECTED`, `policy_version` `cnc-limit-v1`, reason `entry`. Lock is `entry_day_gates` in the same transaction. Migration `0007_entry_day_gates`. Introduced in `7604ea9`. Live revision is `0007_entry_day_gates`. | Developer 3 | PostgreSQL concurrency only. Do not change the limit. |
| PostgreSQL concurrency of the six-entry gate. | PASS | `tests/test_entry_gate_postgres.py` on PostgreSQL 16 at `127.0.0.1:55434`, database `dev3_entry_gate`. Five qualifying rows, then two concurrent connections. Final count 6. | Developer 3 | No. Do not change the limit. |
| Collector host is Core API, not a collector service and not `core-worker`. | PASS | `docker-compose.yml` sets `MARKET_DATA_COLLECTOR=true` on `core-api`. `app.py` starts `_collector_loop` in that process. `core-worker` is a separate service whose command is `python -m core_worker`. | Developer 3 | No. |
| One poll succeeded while `core-worker` stayed exited. | PASS | Worker container was exited 137 before and during the read. Ingestion `last_success_at` was `2026-10-13T07:28:56Z`. The worker was not started. | Developer 3 | No. A repeated isolated poll is still Checkpoint 2. |
| Poll interval 60 seconds and publication delay 90 seconds. | PASS | Compose `MARKET_DATA_POLL_SECONDS=60`. `schedule.py` `PUBLICATION_DELAY` is 90 seconds. The loop sleeps after each pass. | Developer 3 | No. Do not change either number. |
| Returned ingestion status matches the bar just written. | PASS | After each upsert, `_one_symbol` re-reads that timeframe only. `test_returned_status_matches_the_bar_just_persisted` uses a controlled clock. The 12:58 IST production snapshot was taken before this change and is not a stored-bar proof. | Developer 3 | No. Do not deploy it in this checkpoint. |
| Persisted production candles versus `expected_completed_end`. | NOT VERIFIED | The controlled-clock test checks the scripted bars it writes. Production SQL was not run, and Core API was not rebuilt. | Developer 3 | Only with an approved production read. |
| Zerodha token is process memory and starts empty. | PASS | `app.py` sets `app.state.zerodha_access_token = None` at startup. The login callback writes the token onto that state. | Developer 3 | No code change required for the fact. |
| Live re-authentication after an API restart. | NOT VERIFIED | Core API was not restarted. The current process is authenticated. A restart would clear the token. | Developer 3 | Do not restart production to prove it. |
| Collection stops when the collector process is down. | PASS | Source: the loop lives in the API process. Isolated proof: after `collector-api` stopped in `dev3-cp2-collector`, the scripted candle count stayed unchanged. That proof is not live Zerodha and not the production database. | Developer 3 | No. |
| Snapshot-before-upsert race. | PASS | The new test failed on the pre-write end, then passed after the per-timeframe re-read in `collector.py`. | Developer 3 | No. The fix is not deployed. |
| Expected five-minute end after the cash close is 15:15 IST. | PASS | `schedule.py` is unchanged. `test_after_the_close_the_expected_five_minute_end_is_1515` expects 15:15 IST at 15:31:30 IST, and not 15:25 or 15:30. | Developer 3 | No. Do not change the rule. |
| Claim that the last bar has been stuck at 15:10 since 3 August. | NOT VERIFIED | No permitted historical read of stored bars was available. The 12:58 IST snapshot's latest end was 12:50 IST on 13 October, which does not test that claim. | Developer 3 | Only with an approved read. |
| Daily close versus five-minute close mismatch. | NOT VERIFIED | Not reproduced. Production SQL was not used. | Developer 3 | Only with an approved read. |
| Daily paper P&L and an end-of-day snapshot writer. | PASS | `GET /api/v1/paper/daily-performance` returns unavailable. `docs/dev3-snapshot-writer-design.md` is the writer design. No end-of-day row is written. `GET /api/v1/performance` remains the latest backtest. | Developer 3 | Do not deploy a writer without approval. |
| Worker heartbeat. | PASS | Branch tests cover a missing beat, a fresh beat, and a beat older than the interval. The running API was not rebuilt and `core-worker` was not started, so the live process does not serve this route yet. | Developer 3 | Deploy only with a later authorization. |
| Production revision. | PASS | `alembic current` reported `0007_entry_day_gates (head)`. | Developer 3 | No production migration in the next checkpoint. |
| Production paper session. | PASS | Paper status and session list, above. Mode `PAPER`, `live_enabled` false. | Developer 3 | No session write. |
| Intelligence live news. | BLOCKED | Compose sets `INTELLIGENCE_DATA_SOURCE=fixtures` and an empty LLM key. No credentialed live run was authorized. | Developer 3 | Checkpoint 4. Live news without credentials stays blocked. |
| Frontend and Intelligence contract in an isolated stack. | NOT VERIFIED | Contract files and the performance page exist. No isolated Compose run was started. | Developer 3 | Checkpoint 4. |
| H001 and the holdout. | BLOCKED | `services/quant/docs/daily-rules-result.md`: one of six pairs, `momentum_20` at horizon 5, mean excess about 9.8 bp, interval after delivery costs. That interval does not adjust for choosing the best of six. H001 stays blocked. The holdout was not opened or hashed. | Developer 3 | Checkpoint 5 audits the existing artifact. No new backtest and no holdout. |

## What the next review can authorize

Checkpoint 2 closed the ordering race in code, the 15:15 test, the disposable six-entry race, and the scripted Compose probe. It did not change ₹20,000, the six-entry limit, the 90-second delay, fees, or the production database, and it did not start the production worker.

Checkpoint 3 added the unavailable daily-performance route, the snapshot-writer design, and heartbeat code on this branch. It did not deploy the heartbeat, rebuild Core API, or start `core-worker`. The end-of-day writer is not implemented.

Checkpoint 4 may add contract tests for Intelligence and the frontend in an isolated Compose project. Live news without credentials stays blocked.
