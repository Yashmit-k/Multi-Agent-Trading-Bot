# Paper sessions

A paper session is one cash account. Orders, fills, positions, proposals, risk decisions, and portfolio snapshots belong to exactly one session. The market-data collector does not read or write sessions.

The configured initial cash stays `PAPER_STARTING_CASH`. The code default, used only when the variable is unset, is `1000000`. `.env.example` has the same value. Compose does not set the variable; Core API and `core-worker` load `.env`. The current `.env` value, and the value in both of those containers, is `100000`. A new session copies the process value at the moment it is opened. The smallest change that makes that copy ₹10,00,000 is to set `PAPER_STARTING_CASH=1000000` in `.env` and recreate Core API before `POST /api/v1/paper/sessions`. Editing `.env` does not change an already running process, and it does not rewrite a session that is already stored.

## Records

`paper_sessions` stores `session_id`, `status` (`active` or `closed`), `created_at`, `closed_at`, `starting_cash`, and `peak_equity`.

`session_id` is also stored on `trade_proposals`, `risk_decisions`, `orders`, `executions`, `positions`, and `portfolio_snapshots`. Position identity is `session_id` plus instrument, so two sessions can each hold the same symbol.

Proposal ids for a session include that session id. The same symbol, horizon, and candle can therefore produce a new decision in a later session. Inside one session the proposal id is still unique, so the same signal does not create a second order.

Cash for a session starts at that session's `starting_cash` and then follows only that session's fills. A fill updates only that session's position and snapshot. Peak equity for drawdown is stored on the session, not on the process-wide paper flag.

There is at most one active session. Closing a session records `closed_at` and leaves every order, fill, position, and snapshot in place. A closed session is not reopened, so its positions do not become the live book again.

## Legacy rows

Rows written before sessions have a null `session_id`. They are not part of any new session. Accounting for the active session ignores them.

`alembic` revision `0005_paper_sessions` is the non-destructive mapping. It adds the table and columns, rebuilds `positions` so each row can carry a session, and assigns every null-session row to one deterministic id:

`sha256("paper-session:legacy:v1")`

That assignment updates the existing rows. It does not delete them and it does not copy them onto a session opened later. Starting cash is the latest unassigned snapshot cash with every unassigned fill undone: a buy adds `price × quantity + fees`, and a sell subtracts `price × quantity − fees`. Slippage stays inside the stored fill price and is not added a second time. The migration activates that session only when a snapshot exists, its timestamp covers every fill, every fill has a matching order, quantities and fees agree, and snapshot cash, equity, exposure, and P&L agree with the stored positions. The current KOTAKBANK book meets those checks and reconstructs to `100000`. Those figures are the stored book, not inputs baked into the migration.

If the rows do not prove that reconstruction, the legacy session is stored closed with `starting_cash` null. The reason is written to `audit_logs` under audit id `sha256("paper-session:legacy:assessment:v1")`. An uncertain book is not activated.

`runtime_flags.paper.peak_equity` is the running maximum of equities passed to `note_peak_equity`. It is copied onto the legacy session only when it is positive, at least the latest snapshot equity, and reproduces that snapshot's drawdown. When the flag is missing or disagrees, and the snapshot drawdown is 0, `peak_equity` is initialized to that snapshot equity and the audit says the historical peak is incomplete. A positive drawdown without a matching flag leaves `peak_equity` empty for the same reason. The runtime flag row itself is not updated. Later peak updates go to the active session row.

`alembic downgrade` drops the session table and columns. It does not restore `positions.instrument_id` as the primary key. A failed migration is restored from the pre-migration backup, not by downgrading.

Startup does not create a session and does not run this assignment. `core-worker` does not create one either. With no active session, the paper cycle returns without placing an order.

Until the revision has been applied, the default portfolio, order, position, and trade reads see only an active session. Null-session rows remain available at `GET /api/v1/paper/unassigned`.

## APIs

`live_enabled` on these responses is false.

- `GET /api/v1/paper/sessions` lists sessions.
- `POST /api/v1/paper/sessions` opens one session with the configured starting cash. A second active session returns 409. This does not start `core-worker` and does not create an order.
- `GET /api/v1/paper/sessions/{session_id}` returns that session's decisions, orders, trades, positions, and latest snapshot.
- `POST /api/v1/paper/sessions/{session_id}/close` closes it.
- `POST /api/v1/paper/sessions/{session_id}/activate` confirms the session that is already active. A closed session stays closed.
- `GET /api/v1/paper/status` includes `session_id`, `session_status`, and `session_starting_cash`. `starting_cash` remains the configured default.
- `GET /api/v1/portfolio`, `/orders`, `/positions`, `/trades`, and `/decisions` accept `session_id`. Without it they use the active session.

## Opening a new session later

Do this only under a separate instruction. Keep `core-worker` stopped. Do not use `docker compose down` or delete volumes.

1. Stop Core API as well. That pauses the collector while the schema changes. The new process selects columns that do not exist until the revision runs.
2. Take a restorable backup of the Postgres data, record its size and checksum, and prove a restore into a disposable database contains the KOTAKBANK order, fill, quantity 1, and snapshot cash `99581.6500`. Rollback is that restore.
3. Set `PAPER_STARTING_CASH=1000000` in `.env` before the new Core API process starts.
4. Build the Core API and `core-worker` images. Do not start the worker.
5. Apply `alembic upgrade 0005_paper_sessions` once while Core API is stopped.
6. Read the legacy session. It should be the only active session, with starting cash `100000`, the KOTAKBANK quantity still 1, and a peak that was either copied from `runtime_flags.paper` or marked incomplete in `audit_logs`.
7. Start only the new Core API. Confirm health, `live_enabled` false, and `GET /api/v1/paper/status` shows configured `starting_cash` `1000000` plus the legacy session id.
8. `POST /api/v1/paper/sessions/{legacy_id}/close`, then `POST /api/v1/paper/sessions`. The new session's cash is `1000000`. It has no positions and no open orders. The legacy session still shows KOTAKBANK.
9. Leave `core-worker` stopped until a later instruction. Opening a session does not place orders.
