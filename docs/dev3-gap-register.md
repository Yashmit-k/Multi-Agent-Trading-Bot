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

## Checkpoint 4

Project `dev3-cp4-intel` used only `docker-compose.checkpoint4.yml`. Intelligence listened on `127.0.0.1:18101` with fixture news, an empty LLM key, and no `NEWS_RSS_URLS`. `GET /health` reported `llm_mode` `fixture`. `GET /news/RELIANCE` returned articles that validate as `NewsArticle` from `fixture-wire`. The project was removed with `down -v`. That is fixture news, not a live provider.

The frontend news page still shows the global list as unavailable and points at per-symbol Core news. The performance page is labelled Backtest results and still calls `GET /api/v1/performance`. The dashboard calls `GET /api/v1/portfolio` for the active session. When that response has no snapshot, `total_pnl` and `gross_exposure` are null and the dashboard shows a missing-data cell and an empty equity graph. A closed session's position and snapshot stay on that session id. Live news without credentials stays **BLOCKED**. Daily equity history is still absent, so Checkpoint 4 is **PARTIAL**.

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
| Daily paper P&L and an end-of-day snapshot writer. | PARTIAL | `GET /api/v1/paper/daily-performance` returns unavailable. With no snapshot, `GET /api/v1/portfolio` leaves `total_pnl` null. The dashboard does not draw a zero P&L. `docs/dev3-snapshot-writer-design.md` is still design only. | Developer 3 | Do not deploy a writer without approval. |
| Worker heartbeat. | PASS | Branch tests cover a missing beat, a fresh beat, and a beat older than the interval. The running API was not rebuilt and `core-worker` was not started, so the live process does not serve this route yet. | Developer 3 | Deploy only with a later authorization. |
| Production revision. | PASS | `alembic current` reported `0007_entry_day_gates (head)`. | Developer 3 | No production migration in the next checkpoint. |
| Production paper session. | PASS | Paper status and session list, above. Mode `PAPER`, `live_enabled` false. | Developer 3 | No session write. |
| Intelligence live news. | BLOCKED | The isolated project kept `INTELLIGENCE_DATA_SOURCE=fixtures`, an empty LLM key, and no `NEWS_RSS_URLS`. No credentialed live run was authorized. | Developer 3 | Live news without credentials stays blocked. |
| Frontend and Intelligence contract in an isolated stack. | PARTIAL | Fixture news passed on `127.0.0.1:18101`. The dashboard uses `GET /api/v1/portfolio`. `/performance` is labelled backtest results from `GET /api/v1/performance`. Live news remains blocked. | Developer 3 | No live-news claim until a provider is verified. |
| H001 and the holdout. | BLOCKED | `docs/dev3-daily-rules-audit.md`: one of six pairs, `momentum_20` at horizon 5, mean excess about 9.8 bp. That interval is per pair and does not adjust for choosing the best of six. H001 stays blocked. The holdout was not opened or hashed. | Developer 3 | No new backtest and no holdout. |

## What the next review can authorize

Checkpoint 2 closed the ordering race in code, the 15:15 test, the disposable six-entry race, and the scripted Compose probe. It did not change ₹20,000, the six-entry limit, the 90-second delay, fees, or the production database, and it did not start the production worker.

Checkpoint 3 added the unavailable daily-performance route, the snapshot-writer design, and heartbeat code on this branch. It did not deploy the heartbeat, rebuild Core API, or start `core-worker`. The end-of-day writer is not implemented.

Checkpoint 4 checked fixture Intelligence news and the page contracts. The closure is **PARTIAL**: fixture routes pass, and live news plus daily equity history stay blocked.

Checkpoint 5 audited the existing daily-rule result in `docs/dev3-daily-rules-audit.md` and wrote `docs/dev3-demo-runbook.md`. H001 stays blocked. No new backtest was run and the holdout was not opened.

## Post-deployment verification, 2026-10-14

This section supersedes the stale sentences below. It does not delete them. It does not claim that every symbol and timeframe is complete, or that the collector has run continuously.

Verified while writing this note, without restarting services:

- `GET /health` returned `{"status":"ok"}`.
- `multi-agent-trading-bot-core-worker-1` was exited, code 137, finished `2026-10-14T06:27:40.772517625Z`, restart policy `no`, image `sha256:5ea8292147331f73d32c1626526ffd4a24a8f6784299e0669ab192501eb863bc`. It was not started.

Previously observed on 2026-10-14 after the Core API recreate from `24bed9f44de1c991d182daf39e1ac25aac6a579e`, and not re-read for authentication or candle ends while writing this note:

- The running API image was `sha256:b0e1e4ea8937ca6a2d1223b1680ea0295cc2f1c0aeed48f02b86e37040a1b201`. System status was `PAPER` and `live_enabled` false.
- After the browser login, `GET /api/v1/zerodha/status` was `configured` true, `authenticated` true, `live_enabled` false. Ingestion `last_error` was null. `authentication_required` had cleared.
- The login callback queued the existing historical seed. Logs reported `seed_finished status=completed symbols=50 failed=0`.
- `last_success_at` moved through `2026-10-14T07:51:14Z`, `2026-10-14T07:54:34Z`, and `2026-10-14T07:55:54Z`. The latest reported five-minute end moved from `2026-10-14T07:45:00Z` (13:15 IST) to `2026-10-14T07:50:00Z` (13:20 IST). The poll at 13:25:54 IST was before the 13:25 bar was 90 seconds old, so 13:20 IST was the completed bar at that read. `poll_skip_reason` still said `seed_active` after `seed_status` was `completed`. A later `last_success_at` still advanced.
- Orders were one cancelled `KOTAKBANK` buy created `2026-10-12T10:00:00Z`. Trades were zero. That order count was not re-read for this note.
- `GET /api/v1/paper/daily-performance` was `{"status":"unavailable","reason":"no_daily_equity_history"}`. `alembic current`, using `main`'s scripts, was `0007_entry_day_gates (head)`.

The worker had been found running on that old image at `2026-10-14T06:05:43Z`. `docker compose stop core-worker` stopped only that service. Stdout for the 30 minutes before the stop was empty, which is not proof that no cycle ran.

Superseded claims:

- "The collector re-read is not deployed" and "Core API was not rebuilt" in the collector and heartbeat rows. The API image above is the `24bed9f` image. The running worker image is still the older one, and it is stopped, so a live heartbeat from that worker was not observed.
- "Live re-authentication after an API restart" as `NOT VERIFIED`. The recreate cleared the in-memory token. A later browser login left `authenticated` true. That observation is the one timestamped above, not a new login during this documentation edit.
- "Older policy text still says ₹1,00,000 for the paper order." `docs/paper-execution-policy.md` now states the paper cap as ₹20,000 and the research backtest cap as ₹1,00,000. `execute.py` and `assess.py` remain `Decimal("20000")`. `backtest.py` remains `Decimal("100000")`. No cap was changed.

Still blocked, and not started here: the end-of-day snapshot writer, live news, H001 execution, and the holdout. `DATA_PREP_READY` and `READY_TO_RUN` stay NO.

### Dev2 handoff

Recommendation only. No file under `apps/frontend` was edited.

On `developer-2` at `cffb6ef`, `apps/frontend/src/lib/load-real-dashboard.ts` reads `GET /api/v1/paper/status` and then sets `session_id` to the literal `current-paper`. The Core response field is `session_id` from `_paper_body` in `services/core/api/src/core_api/app.py`. Unscoped `GET /api/v1/positions` is already the active session. The synthetic id does not select that session.

Please derive the dashboard session id from `session_id` on `GET /api/v1/paper/status`. Keep the active-session reads, the loading and error states, and the demo path behind `?demo=1`. Add a regression test that the real-mode session id equals the API value and is not `current-paper`. Run the frontend tests and the TypeScript check, then check the dashboard in the browser and report the files changed. Do not mix demo fixtures into the real account response.
