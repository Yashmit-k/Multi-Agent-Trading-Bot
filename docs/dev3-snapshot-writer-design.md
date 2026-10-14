# End-of-day snapshot writer — design for approval

This document does not add a job, a route, or a migration. Nothing in Checkpoint 3 writes an end-of-day row.

## Why the current rows are not a daily book

`portfolio_snapshots` already stores a `PortfolioSnapshot` when a paper fill is recorded. The snapshot id is the execution id. That is a point in time after one fill, not one row per IST cash date.

When a position quantity reaches zero, the position row is removed. Summing `realized_pnl` on the positions that remain omits closed trades. `GET /api/v1/paper/daily-performance` therefore stays `unavailable` until an approved writer has stored a daily series. It does not invent Sharpe, drawdown, or a daily return.

`GET /api/v1/performance` stays the latest backtest. The performance page reads that route.

## Proposed writer, after approval

One snapshot per IST cash date for the active paper session.

Write it only after the cash close is ready: session close plus the existing 90-second publication delay. The collector does not write it. The per-fill snapshot in the paper cycle stays as it is.

Use the existing `PortfolioSnapshot` fields: timestamp, cash, equity, market value, exposures, realized P&L, unrealized P&L, total P&L, and drawdown. Realized P&L has to come from the fill ledger for that session, including positions that have already been closed. The figure is labeled Realized P&L. Days with no fills and no prior snapshot are left absent. They are not filled with a copied equity.

The writer is a later approved job. It is not scheduled in this checkpoint, and it is not applied to the production database.
