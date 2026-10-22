# Decision-engine audit

Generated 2026-10-22 17:24 IST from the read-only API of https://13-238-176-73.sslip.io, by `scripts/decision_audit.py`. Agent proposals (strategy `paper-fusion`) since 15 Oct 2026: 56 (48 BUY, 8 SELL). Manual and Strategy-lab proposals are left out.

Return = close of the k-th NSE session after the decision's session ÷ the proposal's entry price − 1. Every proposal gets one, including rejected and vetoed ones: that is the counterfactual. Proposals too recent to have k later sessions are left out of that column (n shows how many count).

## 1. BUY proposals by outcome path

A proposal that failed two risk checks appears under both.

| | Proposals | Mean 1-session return (n) | Up after 1 | Mean 5-session return (n) | Up after 5 |
|---|---:|---:|---:|---:|---:|
| **All agent BUYs** | 48 | -0.38% (48) | 38% | n/a (0) | n/a |
| Risk approved | 20 | +0.65% (20) | 70% | n/a (0) | n/a |
| Risk rejected (any reason) | 28 | -1.11% (28) | 14% | n/a (0) | n/a |
| approved and filled | 18 | +0.37% (18) | 67% | n/a (0) | n/a |
| rejected: max_open_positions | 16 | -1.84% (16) | 0% | n/a (0) | n/a |
| rejected: daily_entry_cap | 7 | +0.19% (7) | 43% | n/a (0) | n/a |
| vetoed by the manager | 5 | -0.59% (5) | 20% | n/a (0) | n/a |
| approved, not filled | 2 | +3.14% (2) | 100% | n/a (0) | n/a |
| reduced (manager or risk) | 2 | -0.18% (2) | 50% | n/a (0) | n/a |

SELL proposals (exits): 8, mean 1-session return of the stock -0.51% (a negative number means the exit avoided a fall).

## 2. By supporting agent

An agent supports a BUY when its signal in the fused set is at least +0.05.

| | Proposals | Mean 1-session return (n) | Up after 1 | Mean 5-session return (n) | Up after 5 |
|---|---:|---:|---:|---:|---:|
| mean_reversion | 1 | +10.01% (1) | 100% | n/a (0) | n/a |
| momentum | 41 | -0.36% (41) | 39% | n/a (0) | n/a |
| news | 16 | -0.11% (16) | 38% | n/a (0) | n/a |
| regime | 41 | -0.36% (41) | 39% | n/a (0) | n/a |
| technical | 40 | -0.62% (40) | 38% | n/a (0) | n/a |
| volume | 21 | -0.55% (21) | 43% | n/a (0) | n/a |

## 3. Decision threshold

BUY proposals whose stored fused signal is at least the bar. The decision engine only proposes from a lower bar, so 0.25 shows what a looser bar would let through among proposals that exist; nothing below the engine's own bar can be judged here.

| Fused signal ≥ | Proposals | Mean 1-session return (n) | Up after 1 | Mean 5-session return (n) | Up after 5 |
|---|---:|---:|---:|---:|---:|
| 0.25 | 39 | -0.66% (39) | 33% | n/a (0) | n/a |
| 0.35 (live) | 22 | -1.47% (22) | 14% | n/a (0) | n/a |
| 0.45 | 5 | -0.25% (5) | 40% | n/a (0) | n/a |

## 4. Answer to the mentor's question

- After one session, the BUYs risk approved moved +0.65% on average and the ones it rejected -1.11%: the approved group did better, so on this sample the filters kept the better trades.
- 23 of the 28 rejected BUYs failed only capacity limits (max_open_positions, daily_entry_cap, exposure_cap, per_stock_cap, sector_concentration, notional_cap): those checks say the book was full, not that the trade was bad, so their returns mostly reflect which day the proposals came on.
- The portfolio manager vetoed 5 BUYs; after one session they were up 20% of the time (mean -0.59%).
- No proposal is five sessions old yet, so the 5-session columns are empty; rerun with --refresh once they are.
- Across all 48 agent BUY proposals, the stock was up after one session 38% of the time (mean -0.38%). That is the quality of what the agents and the fusion step proposed, before any filter.
- Raising the BUY bar from 0.35 to 0.45 would keep 5 of 22 proposals; their mean 1-session return is -0.25% against -1.47%.
- Caveat: this covers days, not months, and a few dozen proposals in one market regime. Nothing here was tested for statistical significance, and with samples this small differences of this size can easily be chance; proposals made on the same day move together, so they are not independent either. Read it as a first look that says where to measure next, not as a verdict.

## Context: agent scorecard (live, last 10 days)

| Agent | Horizon | Directional samples | Hit rate | In fusion |
|---|---|---:|---:|---|
| earnings | SWING | 109 | 35% | no |
| fundamental | SWING | 53 | 49% | no |
| mean_reversion | INTRADAY | 7540 | 47% | yes |
| mean_reversion | SWING | 201 | 45% | yes |
| momentum | INTRADAY | 11655 | 51% | yes |
| momentum | SWING | 250 | 59% | yes |
| news | SWING | 111 | 40% | yes |
| regime | INTRADAY | 11400 | 53% | yes |
| regime | SWING | 200 | 54% | yes |
| technical | INTRADAY | 11390 | 51% | yes |
| technical | SWING | 239 | 56% | yes |
| valuation | SWING | 52 | 40% | no |
| volume | INTRADAY | 2559 | 48% | yes |
| volume | SWING | 75 | 49% | yes |

## Every proposal

| Decision bar (IST) | Symbol | Side | Fused | Supporting agents | Manager | Risk | Failed checks | Filled | 1-session | 5-session |
|---|---|---|---:|---|---|---|---|---|---:|---:|
| 15 Oct 11:45 | WIPRO | BUY | +0.27 | momentum, regime, technical | - | REJECTED | daily_entry_cap | no | +6.11% | n/a |
| 15 Oct 11:45 | ULTRACEMCO | BUY | +0.27 | momentum, regime, technical, volume | - | REJECTED | daily_entry_cap | no | +0.81% | n/a |
| 15 Oct 11:45 | TECHM | BUY | +0.23 | mean_reversion, momentum, regime | - | APPROVED | - | yes | +10.01% | n/a |
| 15 Oct 11:45 | ONGC | BUY | +0.29 | momentum, regime, technical, volume | - | APPROVED | - | yes | -1.33% | n/a |
| 15 Oct 11:45 | JSWSTEEL | BUY | +0.25 | momentum, regime, technical | - | APPROVED | - | yes | +1.23% | n/a |
| 15 Oct 11:45 | HDFCLIFE | BUY | +0.27 | momentum, regime, technical, volume | - | APPROVED | - | yes | +0.12% | n/a |
| 15 Oct 11:45 | GRASIM | BUY | +0.29 | momentum, regime, technical, volume | - | APPROVED | - | yes | +0.81% | n/a |
| 15 Oct 11:45 | BAJAJFINSV | BUY | +0.37 | momentum, regime, technical, volume | - | APPROVED | - | yes | +0.05% | n/a |
| 15 Oct 15:30 | TCS | BUY | +0.29 | momentum, news, regime, technical, volume | - | APPROVED | - | no | +4.66% | n/a |
| 15 Oct 15:30 | KOTAKBANK | BUY | +0.35 | momentum, news, regime, technical, volume | - | APPROVED | - | yes | +0.31% | n/a |
| 15 Oct 15:30 | HDFCLIFE | BUY | +0.22 | momentum, regime, technical | - | APPROVED | - | yes | +0.55% | n/a |
| 15 Oct 15:30 | HCLTECH | BUY | +0.27 | momentum, news, regime, technical, volume | - | APPROVED | - | no | +1.61% | n/a |
| 15 Oct 15:30 | DRREDDY | BUY | +0.23 | momentum, regime, technical | - | APPROVED | - | yes | +0.92% | n/a |
| 15 Oct 15:30 | AXISBANK | BUY | +0.26 | momentum, regime, technical, volume | - | APPROVED | - | yes | +0.33% | n/a |
| 16 Oct 15:30 | DRREDDY | BUY | +0.22 | momentum, regime, technical | - | APPROVED | - | yes | +0.99% | n/a |
| 16 Oct 15:30 | HDFCLIFE | BUY | +0.28 | momentum, news, regime, technical, volume | - | APPROVED | - | yes | -1.36% | n/a |
| 16 Oct 15:30 | WIPRO | BUY | +0.23 | momentum, regime, technical, volume | - | REJECTED | max_open_positions | no | -1.49% | n/a |
| 16 Oct 15:30 | TECHM | BUY | +0.40 | momentum, news, regime, technical, volume | - | REJECTED | max_open_positions | no | -0.06% | n/a |
| 16 Oct 15:30 | TCS | BUY | +0.34 | momentum, news, regime, technical, volume | - | REJECTED | max_open_positions | no | -0.26% | n/a |
| 16 Oct 15:30 | INFY | BUY | +0.25 | momentum, news, regime, technical, volume | - | REJECTED | max_open_positions | no | -2.80% | n/a |
| 16 Oct 15:30 | HCLTECH | BUY | +0.26 | momentum, news, regime, technical, volume | - | APPROVED | - | yes | +0.65% | n/a |
| 16 Oct 15:30 | BHARTIARTL | BUY | +0.21 | momentum, news, regime, technical, volume | - | APPROVED | - | yes | -1.20% | n/a |
| 19 Oct 10:30 | ULTRACEMCO | BUY | +0.42 | momentum, regime, technical, volume | - | REJECTED | max_open_positions | no | -3.06% | n/a |
| 19 Oct 10:30 | POWERGRID | BUY | +0.24 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -0.26% | n/a |
| 19 Oct 10:30 | MARUTI | BUY | +0.36 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -3.61% | n/a |
| 19 Oct 10:30 | LT | BUY | +0.36 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -1.19% | n/a |
| 19 Oct 10:30 | HINDALCO | BUY | +0.31 | momentum, regime, technical, volume | - | REJECTED | max_open_positions | no | -2.23% | n/a |
| 19 Oct 10:30 | HEROMOTOCO | BUY | +0.37 | momentum, regime, technical, volume | - | APPROVED | - | yes | -2.54% | n/a |
| 19 Oct 10:35 | TITAN | BUY | +0.36 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -2.21% | n/a |
| 19 Oct 10:35 | TATASTEEL | BUY | +0.29 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -1.87% | n/a |
| 19 Oct 10:35 | RELIANCE | BUY | +0.36 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -1.10% | n/a |
| 19 Oct 10:35 | MARUTI | BUY | +0.36 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -3.56% | n/a |
| 19 Oct 10:35 | LT | BUY | +0.36 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -1.14% | n/a |
| 19 Oct 10:35 | HDFCLIFE | SELL | -0.31 | momentum, technical | - | APPROVED | - | yes | -1.34% | n/a |
| 19 Oct 10:35 | EICHERMOT | BUY | +0.24 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -3.26% | n/a |
| 19 Oct 10:35 | CIPLA | BUY | +0.27 | momentum, regime, technical | - | REJECTED | max_open_positions | no | -1.34% | n/a |
| 19 Oct 10:40 | KOTAKBANK | SELL | -0.54 | momentum, regime, technical | - | APPROVED | - | yes | -1.22% | n/a |
| 19 Oct 10:40 | BAJAJFINSV | SELL | -0.50 | momentum, regime, technical, volume | - | APPROVED | - | yes | -1.42% | n/a |
| 19 Oct 10:45 | BHARTIARTL | SELL | -0.22 | regime, technical | - | APPROVED | - | yes | -0.29% | n/a |
| 19 Oct 10:50 | ONGC | SELL | -0.21 | momentum, regime | - | APPROVED | - | yes | +0.43% | n/a |
| 19 Oct 10:50 | HDFCLIFE | SELL | -0.35 | momentum, regime, technical | - | APPROVED | - | yes | -1.06% | n/a |
| 19 Oct 10:50 | DRREDDY | SELL | -0.21 | momentum, regime | - | APPROVED | - | yes | +0.87% | n/a |
| 19 Oct 10:55 | TATASTEEL | BUY | +0.36 | momentum, regime, technical | - | REJECTED | daily_entry_cap | no | -1.82% | n/a |
| 19 Oct 10:55 | LT | BUY | +0.37 | momentum, regime, technical, volume | - | REJECTED | daily_entry_cap | no | -1.06% | n/a |
| 19 Oct 10:55 | HINDALCO | BUY | +0.36 | momentum, regime, technical | - | REJECTED | daily_entry_cap | no | -1.81% | n/a |
| 19 Oct 10:55 | HCLTECH | BUY | +0.27 | momentum, regime, technical | - | REJECTED | daily_entry_cap | no | +2.51% | n/a |
| 19 Oct 10:55 | EICHERMOT | BUY | +0.37 | momentum, regime, technical, volume | - | REJECTED | daily_entry_cap | no | -3.43% | n/a |
| 19 Oct 10:55 | BPCL | BUY | +0.36 | momentum, regime, technical | - | APPROVED | - | yes | -2.47% | n/a |
| 19 Oct 15:30 | JSWSTEEL | BUY | +0.56 | news | REDUCE | APPROVED | - | yes | -0.66% | n/a |
| 19 Oct 15:30 | BEL | BUY | +0.42 | news | VETO | REJECTED | portfolio_manager | no | -1.11% | n/a |
| 19 Oct 15:30 | ADANIENT | BUY | +0.64 | news | VETO | REJECTED | portfolio_manager | no | -2.23% | n/a |
| 19 Oct 15:30 | TITAN | BUY | +0.42 | news | VETO | REJECTED | portfolio_manager | no | -0.95% | n/a |
| 19 Oct 15:30 | TCS | BUY | +0.64 | news | VETO | REJECTED | portfolio_manager | no | +2.76% | n/a |
| 19 Oct 15:30 | NESTLEIND | BUY | +0.70 | news | VETO | REJECTED | portfolio_manager | no | -1.41% | n/a |
| 19 Oct 15:30 | ICICIBANK | BUY | +0.72 | news | REDUCE | APPROVED | - | yes | +0.29% | n/a |
| 21 Oct 12:35 | GRASIM | SELL | -0.79 | momentum, technical | - | APPROVED | - | yes | -0.07% | n/a |
