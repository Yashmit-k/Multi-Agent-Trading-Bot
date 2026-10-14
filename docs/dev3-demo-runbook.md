# Paper demo runbook

This runbook describes the paper demo as it stands on `developer-3`. It does not start `core-worker`, place an order, run a paper cycle, or open the holdout.

## What a reader can say

The trading mode is `PAPER` and `live_enabled` is false.

The dashboard reads the active paper session from `GET /api/v1/portfolio`, plus system status, the market overview, stocks, signals, positions, and risk status. It does not read `GET /api/v1/performance`. If the active session has no snapshot, portfolio `total_pnl` is null and the dashboard shows that daily equity history is unavailable. It does not draw a zero profit or an equity graph.

`/performance` is labelled Backtest results. It calls `GET /api/v1/performance`, which is the latest stored backtest. Those figures are not paper-account P&L. When no backtest is stored, the page says there are no backtests.

`GET /api/v1/paper/daily-performance` returns `status: unavailable` and `reason: no_daily_equity_history`. There is no end-of-day snapshot writer in production. The design is in `docs/dev3-snapshot-writer-design.md` and is not implemented.

The global news page is unavailable. Per-symbol news is `GET /api/v1/stocks/{symbol}/news`. Isolated Intelligence can serve fixture articles. Live news is blocked until a provider is configured and verified. Fixture articles are not live news.

A closed paper session stays on its own session id. The dashboard's default portfolio and positions calls are the active session.

## What this demo does not show

It does not show a worker heartbeat on the running API. Heartbeat code is on this branch and is not deployed.

It does not show live Zerodha polling as proof of stored-bar freshness. The collector ordering fix is on this branch and is not deployed.

It does not show an H001 result. H001 stays blocked. The daily-rule audit is in `docs/dev3-daily-rules-audit.md`. One of six pairs passed its own interval, and that interval does not adjust for selecting the best of six.

Paper buys stay capped at ₹20,000, with fees on top, and at six qualifying CNC entries per IST date.
