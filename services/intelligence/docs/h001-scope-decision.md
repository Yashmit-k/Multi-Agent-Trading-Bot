# H001 scope (Intelligence overlay)

**Controlling protocol:** [`services/quant/docs/h001-protocol-approval.md`](../../quant/docs/h001-protocol-approval.md) (recorded 2026-10-12). This Intelligence file does **not** replace that record and does **not** modify the protocol.

Dev1 records the written decision (2026-10-13):

- **Approved research scope is A** — announcement-timing event study on the three approved subjects.
- **Scope B is not required** under that protocol. EPS, revenue, consensus, and restatements are excluded.
- Sponsor/data: **neither** paid fundamentals subscription nor NSE XBRL instance download. No Prowess/CMIE/FMP/I/B/E/S purchase. No Prowess or XBRL adapter.
- Scope B remains a separate, **unapproved** data project.
- Intelligence keeps `FundamentalDataPoint` on **fixtures** until a source is explicitly approved.

`exchdisstime` tagged `Asia/Kolkata` is accepted **only as a proxy clock**, not as proof of first public availability.

| Flag | Value |
|---|---|
| `DATA_PREP_READY` | **NO** |
| `READY_TO_RUN` | **NO** |
| Gate 2 DATA READY | **withdrawn** |
| Eligibility | **INCONCLUSIVE** (training minority 34 &lt; 50) |
| Protocol rows | `USER APPROVED — NOT AUTHORIZED TO EXECUTE` |

Do not train, generate H001 labels, backtest, execute H001, or access the holdout. Scope A approval is **not** execution authorization.
