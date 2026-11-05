# Momentum live: approve-then-place with Zerodha (plan)

Status (2026-11-05): **phases 1–3 built, then reviewed and fixed** (own cash and book, sale credit, lost replies, later-day runs, Mode Off stops a run, splits on holdings, price bands, Telegram alerts). Order placement exists but is switched off:** the server switch `MOMENTUM_LIVE_ENABLED` is not set, so Mode cannot be set to Live and Approve is refused. Written 2026-11-04.

- **Phase 1:** operator-only Settings page, Zerodha login through the site, read-only account view.
- **Phase 2:** the trial writes `live/proposal-<close>.json` once per month-end. Core's planner (`core_api/live_plan.py`) turns it into the orders shown on the Settings page; each dry run on the real account is logged once. Telegram sends one notice when the ranking is fixed and one at 08:45 IST on rebalance morning (Mode not Off).
- **Phase 3:** `core_api/live_exec.py` places an approved rebalance, tested only against a fake Zerodha (`tests/test_momentum_live_exec.py`).
  - **Approve** sends exactly the orders shown. The site sends a fingerprint of them, and a changed plan is refused with "reload".
  - Sells go first. Buys follow once the sells are done or 15 minutes have passed, sized to the cash Zerodha shows. Then one leftover round with the cash the fills freed.
  - Anything still open at 10:30 IST, or 60 minutes after Approve if that is later (never after 15:15), is cancelled.
  - The ledger is updated from the actual fills only.
  - **Skip** marks the month done with no orders. **Stop** cancels the strategy's open orders and sets Mode to Off.
  - A background step runs every 15 seconds. The run is saved after every order, so a restart continues it, and an order placed just before a crash is adopted rather than placed again.

## What it does

Once a month the system works out the orders for the owner's **real Zerodha account**, using the same 12-1 momentum rule as the paper trial. It places them only after the owner logs in to Zerodha and presses **Approve** on the site.

| When | What happens | Who |
|---|---|---|
| Month-end evening (about 19:30 IST) | The ranking is fixed from NSE's closing file, as in the paper trial today | System |
| Next morning, 08:45 IST | Telegram: "Rebalance ready. Log in to see the orders." | System |
| Any time from 09:15 | Log in to Zerodha through the site, on Zerodha's own page | **Owner** |
| Straight after | The site reads the real holdings and cash and shows the exact orders: sell X, buy Y, quantities, limit prices, estimated charges | System |
| | The owner presses **Approve** (or Skip) | **Owner** |
| Straight after Approve (from 09:15) | Sells are placed first. Buys follow once the sale money shows in the account | System |
| Until 10:30 | Fills are tracked. Unfilled orders are cancelled at 10:30 and reported | System |
| 10:35 | Telegram and the site show the report: filled, unfilled, money spent, charges | System |

The owner logs in once a month, on rebalance morning. In other months nothing needs doing.

**The paper trial keeps running unchanged.** It stays the clean experiment. The live book is separate and has its own record.

## What the owner sets (Settings page, operator sign-in required)

| Setting | Meaning | Default |
|---|---|---|
| **Money put into the strategy** | The money given to the strategy (₹). Its book (its own shares plus its own cash) then grows or shrinks with the market, like the paper trial. Raise it to add money; lower it to take money out at the next rebalance. Other money in the account is never used | ₹0, so nothing is bought until set |
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
- **The book is the strategy's own:** its ledger shares at the close, plus its own cash. That cash is the money put in, plus what its sales brought, minus what its buys cost, charges included. It is updated from the actual fills of each run.
- Each of the N stocks gets book value ÷ N, in whole shares.
- The leftover cash buys one more share at a time of the holding furthest below its share, as in the paper trial.
- Buys are limited to the smaller of the strategy's cash and the cash Zerodha shows.
- **A split or bonus on a holding** (the account's shares a multiple of the ledger's, and the price down in step) updates the ledger. More shares than that are taken to be bought by hand and left alone.

**Prices**
- The free Personal plan has no live prices, so orders are **limit orders priced from the last close** (NSE's free daily file): buys up to **3%** above it, sells down to **3%** below it. 3% replaced the first draft's 1.5% on 2026-11-05, after [momentum-gap-check.md](momentum-gap-check.md):
  - returns were about the same with either band;
  - at 3% far fewer orders miss, so the live book follows the paper trial closely.
- A limit is the worst price accepted, not the price paid. A buy limited at ₹1,030 fills at ₹1,004 if that is the market price.
- **No pre-open orders:** orders go in from 09:15, in the normal session. A stock outside NSE's 09:00–09:08 call auction can reject an order sent during it, and a rejected order is not retried. Approving soon after 09:15 keeps the prices close to the open the paper trial assumes.
- No re-pricing: the global-markets agent and a Yahoo re-price were considered and dropped (momentum-gap-check.md).
- An order still unfilled at 10:30 is cancelled and reported, never chased.
- **Checks before trading (added 2026-11-05).** On the morning of the trade, the planner reads Zerodha's instrument list for the day:
  - each limit is rounded to that stock's own price step (tick size);
  - a stock not trading in the EQ series that day (moved to trade-to-trade, for instance) is replaced by the next-ranked one, and such a holding is kept for the month;
  - a stock whose price is more than 30% from the decision close (a split or bonus) is left out the same way.

  Approve is refused without the instrument list, and opens only at 09:15, after the pre-open.
- **Before the first live run, the owner enables DDPI** in the Zerodha console. Without it, every automated sell from the demat account fails.
- **Daily price band:** a stock whose NSE band is narrower than 3% (2%) gets its limit at the band, because Zerodha rejects a price outside it. The trial reads NSE's band file each month-end.
- **Leftover round (phase 3):** Zerodha blocks cash at the limit price, so buys are sized to fit at 3% above the close and about 97% of the amount is invested at typical prices. Once the first buys fill below their limits, the freed cash buys more shares in a second round, so the book ends close to fully invested, as in the paper trial.
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

- **Gaps beyond 3% go unfilled.**
  - In 2016–2026, about 1 new buy in 20 opened more than 3% above the close, and about 1 sell in 25 opened more than 3% below it.
  - A missed buy's money stays as cash until the next month. A missed sell keeps the stock another month.
- **No live prices.** The site can't show the value of holdings during the day, only at the last close.
- **The account must not trade the same stocks by hand.** The ledger guard protects other holdings, but manual trades in the strategy's stocks make the reconciliation report differences.
- **Server down on rebalance morning.** Nothing is placed, and the health check alerts. Approving later that day, or the next day, still works: the proposal stays valid until the next month-end.
- **SEBI and NSE rules can change.** Static IP and the order-rate threshold are as of April 2026.
