# Backend contract request (Developer 2 → Core)

The premium dashboard is implemented against a typed daily P&L interface. These Core routes were inspected and **do not** provide a paper daily series:

Existing: `GET /api/v1/system/status`, `paper/status`, `portfolio`, `positions`, `orders`, `trades`, `market/overview`, `zerodha/status`, `risk/status`.  
`GET /api/v1/performance` is the **latest backtest**, not paper-session P&L. It is not used as session win rate.

## Missing (please publish read-only)

1. `GET /api/v1/paper/sessions` — list actual paper sessions (id, status active/closed, starting cash, date bounds). Do not invent history from a single order.
2. `GET /api/v1/paper/sessions/{session_id}/daily-pnl` rows:
   - `session_id`
   - `calendar_date_ist` (`YYYY-MM-DD` IST civil key, not a JS timestamp)
   - `snapshot_as_of`
   - `complete` (documented meaning, not “HTTP 200”)
   - `pnl_basis` (`net_equity` | `realized_only`)
   - `net_pnl_inr`
   - `start_of_day_equity_inr`
   - realized P&L, unrealized change, fees (fees already in equity — do not double-count)
   - `has_activity`
   - trading-calendar state (open / closed / holiday / special session)
   - source update timestamp
3. Preferred `net_pnl_inr = EOD equity − previous EOD equity − net external cash flows`.
4. `trading_date_ist` or an authoritative clock on system/market status (not the browser clock).
5. Exchange calendar for cash-market holidays and special sessions.
6. Documented closed-trade pairing if win rate is to be shown. Sample size required.
7. Worker status, if it should appear. Until then the UI shows `Worker status unavailable`.

Do not send tokens or credentials to the frontend.
