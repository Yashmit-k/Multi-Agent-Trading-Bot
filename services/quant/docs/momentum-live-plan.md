# Momentum live: approve-then-place with Zerodha (plan)

Status: **PLAN, not built.** Written 2026-11-04. Nothing here places an order until the owner switches it on.

## What it does

Once a month the system works out the orders for the owner's **real Zerodha account**, using the same 12-1 momentum rule as the paper trial. It places them only after the owner logs in to Zerodha and presses **Approve** on the site.

| When | What happens | Who |
|---|---|---|
| Month-end evening (about 19:30 IST) | The ranking is fixed from NSE's closing file, as in the paper trial today | System |
| Next morning, 08:45 IST | Telegram: "Rebalance ready. Log in to see the orders." | System |
| Any time 09:00–10:30 | Log in to Zerodha through the site, on Zerodha's own page | **Owner** |
| Straight after | The site reads the real holdings and cash and shows the exact orders: sell X, buy Y, quantities, limit prices, estimated charges | System |
| | The owner presses **Approve** (or Skip) | **Owner** |
| 09:00–09:08 (pre-open), or straight after Approve | Sells are placed first. Buys follow once the sale money shows in the account | System |
| Until 10:30 | Fills are tracked. Unfilled orders are cancelled at 10:30 and reported | System |
| 10:35 | Telegram and the site show the report: filled, unfilled, money spent, charges | System |

The owner logs in once a month, on rebalance morning. In other months nothing needs doing.

**The paper trial keeps running unchanged.** It stays the clean experiment. The live book is separate and has its own record.

## What the owner sets (Settings page, operator sign-in required)

| Setting | Meaning | Default |
|---|---|---|
| **Amount for the strategy** | The most of the account the strategy may use (₹). It never spends beyond this, even if the account holds more cash | ₹0, so nothing is bought until set |
| **Number of stocks** | How many of the top-ranked stocks to hold (10, 15, 20…). Changed by hand only; takes effect at the next rebalance | 10 |
| **Mode** | **Off**: nothing is computed. **Dry run**: orders are computed and shown but never sent. **Live**: orders are sent after Approve | Off |
| **Largest single order** | Any order above this value is refused, as a guard against a bug | ₹25,000 |

All changes are logged with the time. A change made after a proposal is ready applies from the next month.

## Rules for the orders

**Which holdings it manages**
- The strategy keeps its own ledger of the shares it bought.
- **It only ever sells shares in its ledger.** Any other shares in the account are never touched.
- Before every rebalance the ledger is checked against Zerodha's holdings. If a stock in the ledger has fewer shares in Zerodha (sold by hand, say), the smaller number is used and the difference is reported.

**How much to hold of each**
- Book value = value of the ledger holdings + the strategy's cash, capped at the amount set.
- Each of the N stocks gets book value ÷ N, in whole shares.
- The leftover cash buys one more share at a time of the holding furthest below its share, as in the paper trial.
- It reuses the paper trial's own code for this, so the two books follow exactly the same rule.

**Prices**
- The free Personal plan has no live prices, so orders are **limit orders priced from the last close** (NSE's free daily file): buys up to 1.5% above it, sells down to 1.5% below it.
- A limit is the worst price accepted, not the price paid. A buy limited at ₹1,015 fills at ₹1,004 if that is the market price.
- **Pre-open:** where possible, orders go in during NSE's pre-open session (09:00–09:08), so they fill at the opening price if it is inside the band. That matches the paper trial's "bought at the open". The dry run checks which stocks take part in the pre-open auction.
- **One retry:** an unfilled buy may be re-priced once from Yahoo Finance's price, which is unofficial and possibly delayed, so it is a hint only. The re-price is never above a hard cap of 3% over the close.
- A stock beyond the cap is cancelled at 10:30 and reported, never chased.
- Market orders are not used.

**Order of events**
- All sells first.
- Buys start once Zerodha's funds API shows the sale money as available.
- If the money is short, buys are scaled down; nothing is bought on margin.

**Safety guards (all must pass, or nothing is sent)**
1. Mode is Live, **and** the owner pressed Approve in the last 30 minutes, **and** `MOMENTUM_LIVE_ENABLED=true` on the server. This server switch is off by default and only the owner sets it.
2. Every order is CNC (delivery) on NSE, in a stock from that month's ranking or the ledger.
3. No single order is above the "largest single order" setting. Total buys stay within the amount set.
4. One rebalance per month. A second Approve for the same month is refused.
5. Each order carries a tag such as `mom2612`. After a restart or a retry, the order book is read first, so nothing is placed twice.
6. At most one order per second, far below the 10 orders per second at which SEBI treats it as an algorithm needing registration.
7. A **Stop** button on the site cancels all open orders from the strategy and switches Mode to Off.

Every proposal, approval, order, fill, cancellation and setting change is written to an append-only log on the server.

## How it is built

The system has three parts:
- **momentum-trial:** the service that already runs the paper trial every evening.
- **core-api:** the server program that already handles the Zerodha login. It gets new endpoints in this plan.
- **website:** the frontend.

Only core-api talks to Zerodha.

1. **Zerodha login through the site** (core-api and website)
   - Today's login callback only works through an SSH tunnel. It moves to a public page, `https://13-238-176-73.sslip.io/zerodha/callback`.
   - The callback needs the operator to be signed in to the site.
   - The access token is kept as it is today, in the database, and expires at Zerodha's daily cut-off.
   - The market-data collector is switched off (`MARKET_DATA_COLLECTOR=false`). The Personal plan has no quotes, and the collector is not used any more.
2. **Account reading** (core-api, read-only): holdings (including shares bought yesterday and not yet settled), today's positions, available cash and the order book. These show on the site once logged in. **Phase 1 stops here: no order code at all.**
3. **Proposal** (momentum-trial):
   - After the month-end decision is recorded, it writes `proposal-<month>.json` with the target stocks, last closes and the rule's targets.
   - It never talks to Zerodha.
4. **Planner** (core-api):
   - It combines the proposal with the live account, the ledger and the settings into an exact order list.
   - It is a pure function, unit-tested against cases such as a manual sale, a stock locked at upper circuit, money short, a held stock dropping out, or N changed.
5. **Placer** (core-api):
   - It places orders, polls the order book, cancels at 10:30 and updates the ledger from actual fills.
   - It uses the Kite client the code already has.
   - Tests run against a fake Kite that can reject, part-fill or fail midway.
6. **Telegram**: the same bot and `.env` keys the health check already uses.
7. **Website**: a "Live" section on the Momentum page (status, proposal, Approve / Skip / Stop, last report) and the Settings page above.
   - Only the signed-in operator sees the buttons.
   - The settings replace the old NIFTY 50 risk limits, as asked; their code stays in git.
8. **Before January:** add the 2027 NSE holidays to the trading calendar. Live trading must know them.

## Rollout

| Phase | What | Real orders? | Earliest |
|---|---|---|---|
| 1 | Login through the site, read-only account view, settings page | No | mid-Nov 2026 |
| 2 | Proposals and dry runs. The 1 Dec rebalance is shown as a dry run next to the paper trial's own trades | No | 1 Dec 2026 |
| 3 | Order placement built and tested against the fake Kite only | No | Dec 2026 |
| 4 | **The owner** sets Mode to Live, a small amount, and the server switch, then approves the first real rebalance | **Yes, by the owner** | 1 Jan 2027 at the earliest |

Each phase is committed and deployed only with the owner's approval. Claude will not set Mode to Live, set the server switch, or press Approve.

## What only the owner can do

1. Create a **Personal (free)** app at developers.kite.trade:
   - Redirect URL: `https://13-238-176-73.sslip.io/zerodha/callback`.
   - **Static IP: `13.238.176.73`.** It can be changed at most once a week.
2. Put `ZERODHA_API_KEY` and `ZERODHA_API_SECRET` in the server's `.env`. Claude does not read `.env`.
3. Set `OPERATOR_PASSWORD` to a strong password if it is not one already. It guards Approve.
4. Log in on rebalance morning and approve.
5. Choose the amount and when to go live. These are investment decisions. A SEBI-registered adviser can help; Claude cannot advise on them.

## Known limits

- **Gaps beyond 1.5% go unfilled.**
  - Momentum stocks often open sharply higher, so some months a buy will be missed. That money stays as cash until the next month.
  - The result will differ from the paper trial, which buys at the open whatever the price.
  - The band can be widened in Settings later.
- **No live prices.** The site can't show the value of holdings during the day, only at the last close.
- **The account must not trade the same stocks by hand.** The ledger guard protects other holdings, but manual trades in the strategy's stocks make the reconciliation report differences.
- **Server down on rebalance morning.** Nothing is placed, and the health check alerts. Approving later that day, or the next day, still works: the proposal stays valid until the next month-end.
- **SEBI and NSE rules can change.** Static IP and the order-rate threshold are as of April 2026.
