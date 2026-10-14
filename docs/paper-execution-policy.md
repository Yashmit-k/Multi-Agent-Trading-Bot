# Paper execution policy

This is a preliminary execution control for paper trading. It is not evidence that a strategy is profitable. Fills are OHLC simulations, not broker executions. A five-minute bar does not show queue priority, volume at the limit, or the path inside the bar.

`live_enabled` stays false. The worker is not started by this change. Migration `0006_paper_execution` is not applied to the running database.

## Cash

The previous paper cycle did not reserve cash. It checked cash when the proposal was sized and again at fill time, and it left an unaffordable buy `OPEN`. Two open buys could therefore be sized against the same cash.

A new CNC buy now writes a `HELD` cash reservation in the same transaction as the order. The reserved amount is the limit notional plus a ceiling estimate of the versioned delivery charges. Available cash is economic cash minus held reservations for that session. A fill converts the reservation into the actual debit and releases the excess by leaving only `applied_debit` on a `CONVERTED` row. Expiry, rejection, and cancellation move a `HELD` row to `RELEASED` once. A second transition does not release it again.

Snapshot cash remains the cash after fills. Available cash is the figure used for a new order.

## Reference price and limit

At the decision timestamp, the reference price is the close of the latest completed daily candle whose end is at or before that timestamp. The candle end, candle id, rule `latest_completed_daily_close_v1`, and the price are stored on the order and are not recomputed later.

`limit = floor_to_tick(reference * (1 + 25/10000))`. The floor never raises the 25 bp cap. A 0.5% gap above the reference is above that limit. The order can fill only when a later eligible bar meets the limit rule.

If the daily close or the next verified session cannot be established, the order is stored `REJECTED` with `reference_price_unavailable` or `calendar_unverified`. It is not left as a market order.

## Entry window

Times are Asia/Kolkata. Storage stays UTC.

The ordinary entry window is 09:20 inclusive to 10:30 exclusive for five-minute bar starts. The 09:15–09:20 bar is excluded. The last eligible bar starts at 10:25 and ends at 10:30. A bar can be used only when it has ended, it starts strictly after the order's activation time, and it belongs to the assigned session.

Assignment rule: if the order is created on a verified session and at least one eligible bar start is strictly after the activation time, that session is the entry window. Otherwise the order is assigned to the next verified session. An order created exactly at 10:30 has no remaining bar in that window and rolls forward. It does not become executable in the window that just ended. After assignment, the window does not roll again.

## Fills, expiry, and data gaps

For a buy limit `L` on a completed eligible five-minute bar:

- open below `L` fills at the open
- open equal to `L` fills at `L`
- open above `L` fills at `L` only when low is strictly below `L`
- a low that only touches `L` does not fill
- no bar fills above `L`

Evaluated bar ids are stored in `order_bar_checks`. A repeated pass cannot fill the same order again.

When the window has ended and a required bar is missing, the order becomes `EXPIRED_NO_DATA`. When every required bar is present and none qualifies, the order becomes `EXPIRED` with reason `limit_not_reached`. An uncertain or uncovered charge schedule does not invent a fill. A fill that already happened is left in place.

## CNC, charges, and same-day reclassification

New equity buys and sells record `product_type=CNC`. The engine does not create `MIS` orders and does not apply intraday leverage. A sell cannot exceed the shares still held after other open sells.

The charge schedule is `zerodha-equity-ri-2026-10-12`, read on 2026-10-12, effective from that date until replaced:

- https://zerodha.com/charges/
- https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/how-is-the-securities-transaction-tax-stt-calculated
- https://support.zerodha.com/category/trading-and-markets/charts-and-orders/order/articles/what-does-cnc-mis-and-nrml-mean
- https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/brokerage-charged-for-partial-delivery

Delivery brokerage is zero. Delivery STT is 0.1% on both sides, rounded to the nearest rupee, half up. Intraday brokerage is 0.03% or ₹20 per executed order, whichever is lower. Intraday STT is 0.025% on the sell side, using the average of the buy and sell prices, rounded to the nearest rupee. NSE equity transaction charge is 0.00307%. SEBI is ₹10 per crore. Stamp duty is 0.015% on a delivery buy and 0.003% on an intraday buy. GST is 18% on brokerage, SEBI charges, and transaction charges. IPFT is ₹0.01 per crore plus GST. A schedule without a version, effective date, access date, and source URL is refused. The flat 2 bp research schedule is not a substitute.

Zerodha states that a same-day CNC buy and sell is charged as intraday, and that if any part of a buy order is squared off the whole buy order attracts intraday brokerage. This engine applies that whole-order brokerage. STT and stamp follow the squared quantity and the quantity that remains for delivery. The difference from the originally booked buy cost is applied once. A retry finds the existing fill and the `reclass` ledger row and does not apply the delta again.

DP is ₹15.34 per scrip per trading day, as published (₹3.5 CDSL + ₹9.5 Zerodha + ₹2.34 GST). The published line says this is charged when stocks are sold, irrespective of quantity. It does not say whether a same-day CNC square-off, which never leaves the trading account for demat, is exempt. This engine therefore records one charge on the first sell of a scrip on that trading day and does not treat that choice as exact depository accounting. The female-holder discount is not applied. The accumulator key is the paper-session id plus the trading date, exchange, and symbol. The trading date is not the paper-session id. The instrument model has no ISIN.

The paper per-order notional cap is ₹20,000. `MAX_NOTIONAL` in `services/core/paper-execution/src/core_paper/execute.py` and the default bound in `services/core/risk-engine/src/core_risk/assess.py` are `Decimal("20000")`. Fees sit on top of that notional. Quantity is floored at the limit, then reduced until limit notional plus the ceiling fee estimate fits both the cap and unreserved cash.

Research backtests are a separate bound. `services/core/paper-execution/src/core_paper/backtest.py` sets `MAX_NOTIONAL = Decimal("100000")` and passes that value into `assess` as `max_notional`. That figure is not the paper-order cap.

`7604ea9` introduced the paper cap of ₹20,000. `fd9a0de` kept the research backtest on ₹1,00,000. `144bc08` still had `Decimal("100000")` in `execute.py` and `assess.py`. This paragraph replaces that older paper-cap sentence. The caps themselves were not changed here.

## Calendar

Ordinary sessions use the existing weekday and holiday list through 2026-12-31. Saturday 18 May 2024 is included as a special live capital-market session. The primary normal market was 09:15–10:00 IST, so the entry window is 09:20–10:00 rather than 09:20–10:30. The later disaster-recovery segment is not treated as an extension of an expired primary window. Source read on 2026-10-12: the NSE circular copy at `https://fileserver.enrichmoney.in/Content/UploadedFiles/d5iUWAst01M8tx2hzeGjmrp2_20240516100248100.pdf`.

Saturday mock drills, including 25 July 2026, 29 August 2026, and 10 October 2026, are not cash sessions. NSE's holiday page says Muhurat trading on 8 November 2026 will have timings notified later. That date has no invented window. A date past 2026-12-31 raises `CalendarUnverified` instead of guessing the next session.

## Legacy KOTAKBANK order

The open KOTAKBANK buy uses `fill_at=next_open` and has no policy version, reference price, limit, entry window, or charge version. Settlement skips any open order that is not `cnc-limit-v1` or `cnc-sell-v1`. The row is not rewritten to look like a new policy order.

An operator can cancel or replace it later. This implementation does not call that operation on the running system.

Cancel:

`POST /api/v1/paper/sessions/{session_id}/orders/{order_id}/cancel`

```json
{"operator_id": "<operator>", "reason": "<why>", "expected_status": "OPEN"}
```

The service records the audit time itself. The expected status must match. The reservation, if any, is released once. A conflicting status leaves the order unchanged. The audit action is `paper_order_cancel`.

Replace:

`POST /api/v1/paper/sessions/{session_id}/orders/{order_id}/replace`

```json
{
  "operator_id": "<operator>",
  "reason": "<why>",
  "expected_status": "OPEN",
  "decision_at": "<timestamp strictly after the original decision_end>"
}
```

The replacement is a new order. Its reference price is the daily close available at `decision_at`, not the original October 12 close. The original order is cancelled only after the replacement is accepted. The audit action is `paper_order_replace`.

## Migration

`0006_paper_execution` adds `cash_reservations`, `charge_ledger`, `dp_charges`, and `order_bar_checks`. Existing order payloads are unchanged, so a legacy market order does not become policy-compliant. Downgrade drops those four tables. Reservation amounts, ledger rows, DP keys, and evaluated bar keys cannot be reconstructed. Order, fill, position, and snapshot payloads remain.
