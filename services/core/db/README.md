# core-db

This package owns PostgreSQL persistence for the core platform.

Other services call `CoreRepository`. They do not import SQLAlchemy models. Timescale hypertables, if added later, stay in this package.

Phase 1–2 ingestion is NSE-only. `instruments.instrument_id` is the internal identity. `exchange`, `symbol`, `trading_symbol`, and `instrument_token` are attributes.

## Migrations

Alembic revisions are a shared contract. Review them with the same pull-request gate as `packages/contracts`.

```bash
alembic -c services/core/db/alembic.ini upgrade head
```

## Seed

`seeds/universe_membership_seed.csv` columns are `symbol,universe,effective_from,effective_to`. An empty `effective_to` means the membership is still current. The loader creates `NSE:{symbol}` instrument ids.
