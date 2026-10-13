# Developer 3 gap register — Checkpoint 1

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
| PostgreSQL concurrency of the six-entry gate. | NOT VERIFIED | SQLite coverage exists in the daily-entry tests. No disposable PostgreSQL race was run. Production SQL was not used. | Developer 3 | Checkpoint 2, isolated database only. |
| Collector host is Core API, not a collector service and not `core-worker`. | PASS | `docker-compose.yml` sets `MARKET_DATA_COLLECTOR=true` on `core-api`. `app.py` starts `_collector_loop` in that process. `core-worker` is a separate service whose command is `python -m core_worker`. | Developer 3 | No. |
| One poll succeeded while `core-worker` stayed exited. | PASS | Worker container was exited 137 before and during the read. Ingestion `last_success_at` was `2026-10-13T07:28:56Z`. The worker was not started. | Developer 3 | No. A repeated isolated poll is still Checkpoint 2. |
| Poll interval 60 seconds and publication delay 90 seconds. | PASS | Compose `MARKET_DATA_POLL_SECONDS=60`. `schedule.py` `PUBLICATION_DELAY` is 90 seconds. The loop sleeps after each pass. | Developer 3 | No. Do not change either number. |
| Ingestion "fresh" count is not proof of the stored bar. | PASS | `collector.py` `_one_symbol` records `latest_candle` before `upsert_candles`. The snapshot can describe the previous bar. The 12:58 IST read reported 0 fresh and 50 stale with latest end 12:50 IST. That is the snapshot, not a stored-bar proof. | Developer 3 | Checkpoint 2 fixes the ordering. It does not treat this snapshot as the proof. |
| Persisted candles versus `expected_completed_end`. | NOT VERIFIED | Proving the stored bar needs a database read. Production SQL was not run. | Developer 3 | Checkpoint 2, on an isolated database or a later approved read. |
| Zerodha token is process memory and starts empty. | PASS | `app.py` sets `app.state.zerodha_access_token = None` at startup. The login callback writes the token onto that state. | Developer 3 | No code change required for the fact. |
| Live re-authentication after an API restart. | NOT VERIFIED | Core API was not restarted. The current process is authenticated. A restart would clear the token. | Developer 3 | Do not restart production to prove it. |
| Collection stops when Core API is down. | PASS | The loop lives in the API process. There is no second collector process to keep polling. | Developer 3 | Checkpoint 2 documents the same fact in the isolated project. |
| Snapshot-before-upsert race. | FAIL | `collector.py` `_one_symbol` publishes freshness from the candle read that happens before `upsert_candles`. | Developer 3 | Checkpoint 2: failing regression, then the smallest ordering fix. |
| Expected five-minute end after the cash close is 15:15 IST. | PASS | `schedule.py`: after the session is ready, the expected intraday end is close minus the 15-minute grace. 15:25 and 15:30 are not expected ends. | Developer 3 | Close-of-session tests in Checkpoint 2. Do not change the rule. |
| Claim that the last bar has been stuck at 15:10 since 3 August. | NOT VERIFIED | No permitted historical read of stored bars was available. The 12:58 IST snapshot's latest end was 12:50 IST on 13 October, which does not test that claim. | Developer 3 | Only with an approved read. |
| Daily close versus five-minute close mismatch. | NOT VERIFIED | Not reproduced. Production SQL was not used. | Developer 3 | Only with an approved read. |
| Daily paper P&L and an end-of-day snapshot writer. | FAIL | `portfolio_snapshots` exists. No production writer was found. `GET /api/v1/performance` serves the latest backtest and returned 404 `no_backtest`. The frontend performance page calls that route. It is not session daily P&L. | Developer 3 | Checkpoint 3 is design and a read-only contract. Do not deploy a writer. |
| Worker heartbeat. | FAIL | Core API routes do not expose a worker heartbeat. Live status must stay unavailable until a later authorized deploy. The exited container is operational state, not an API heartbeat. | Developer 3 | Checkpoint 3, branch only. Do not deploy. |
| Production revision. | PASS | `alembic current` reported `0007_entry_day_gates (head)`. | Developer 3 | No production migration in the next checkpoint. |
| Production paper session. | PASS | Paper status and session list, above. Mode `PAPER`, `live_enabled` false. | Developer 3 | No session write. |
| Intelligence live news. | BLOCKED | Compose sets `INTELLIGENCE_DATA_SOURCE=fixtures` and an empty LLM key. No credentialed live run was authorized. | Developer 3 | Checkpoint 4. Live news without credentials stays blocked. |
| Frontend and Intelligence contract in an isolated stack. | NOT VERIFIED | Contract files and the performance page exist. No isolated Compose run was started. | Developer 3 | Checkpoint 4. |
| H001 and the holdout. | BLOCKED | `services/quant/docs/daily-rules-result.md`: one of six pairs, `momentum_20` at horizon 5, mean excess about 9.8 bp, interval after delivery costs. That interval does not adjust for choosing the best of six. H001 stays blocked. The holdout was not opened or hashed. | Developer 3 | Checkpoint 5 audits the existing artifact. No new backtest and no holdout. |

## What the next review can authorize

Checkpoint 2 may add a failing regression for the snapshot-before-upsert race, the smallest ordering fix, close-of-session tests, a disposable PostgreSQL concurrency test for the six-entry gate, and an isolated Compose project that polls more than once while its own paper worker stays stopped. That project must not join this network or this database.

Checkpoint 2 may not change ₹20,000, the six-entry limit, the 90-second delay, fees, or the production database. It may not start the production worker.

Documentation does not close the collector race, the missing heartbeat, or the missing daily snapshot writer.
