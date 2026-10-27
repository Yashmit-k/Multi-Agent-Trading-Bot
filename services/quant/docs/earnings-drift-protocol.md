# Earnings drift (post-announcement drift): pre-registered protocol

Status: **PRE-REGISTERED 2026-10-27, before any return around a result announcement was computed.** The only work done beforehand was counting the events: 2,192 stock-quarters, 2013-04 to 2025-02, 48 stocks.

Question: after a NIFTY 50 company's quarterly results get a strongly positive market reaction, does the stock keep outperforming for the next weeks by more than the cost of a delivery round trip?

## Data

- **Announcement times:** NSE `corporates-financial-results`, frozen 2026-10-10 under `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/financial-results/` (gitignored).
  - Use rows with `period = Quarterly`.
  - An event is one (symbol, `toDate`) pair. Its time is the **earliest** `exchdisstime` across its standalone and consolidated filings, read as IST.
  - Only the timestamp is used, never the reported figures (they are a later vendor extract).
- **Prices:** `datasets/research/dip_history/daily_2015_2026.jsonl`, daily bars 2015-01-01 to 2026-10-05, split and bonus adjusted. 48 of the 49 current members have both.

## Event timing (no look-ahead)

- **Day 0** is the session on which the market can first react:
  - the announcement session itself if the result came out before 15:30 IST on a trading day;
  - otherwise the next trading session.
- **Reaction (the surprise proxy):** the stock's return from the close of day −1 to the close of day +1, minus the equal-weight average return of the other universe stocks over the same days.
- **Entry:** the open of day +2, plus 5 bp slippage. The reaction is fully known at the day +1 close.
- **Exit:** the close of day +1+H, less 5 bp slippage.
- **Skips:**
  - an event whose window from day −1 to the exit contains an open more than 20% from the previous close (a corporate action);
  - an event without the full window in the price data.

## Rules (fixed here; nothing is tuned)

| Rule | Buy when the reaction is | Hold H |
|---|---|---|
| `pos2_h20` | ≥ +2% | 20 sessions |
| `pos4_h20` | ≥ +4% | 20 sessions |
| `pos2_h40` | ≥ +2% | 40 sessions |
| `pos4_h40` | ≥ +4% | 40 sessions |

## Measures

- **Excess return of a trade:** the stock's return from entry to exit minus the equal-weight universe return over the same days (open of day +2 to close of exit day).
- **Net excess:** excess minus the round-trip cost: Zerodha delivery charges on ₹20,000 (`mentor_strategies.delivery_charges`) plus 10 bp of slippage.
- Per rule and period:
  - trades;
  - mean and median net excess;
  - win rate against the universe;
  - the 10th-percentile bootstrap of the mean net excess, resampling whole calendar quarters (2,000 draws), because events in a results season overlap;
  - the mean raw net return (not market-adjusted) as well.
- **Descriptive only:** the mean excess return over 20 sessions by reaction quintile. This is the drift curve, and it covers negative reactions too.

## Periods (by day 0)

| Period | Dates | Use |
|---|---|---|
| Train | 2015-03-01 to 2019-12-31 | gate |
| Validate | 2020-01-01 to 2022-12-31 | gate |
| Test | 2023-01-01 to 2025-02-28 | gate |

## Gate

A rule **works** only if both hold:
1. Its mean net excess is above zero in **each** of the three periods.
2. The pooled 10th-percentile quarter-block bootstrap of the mean net excess is above zero.

Four rules are tested, so the report also states whether the best rule would survive a Bonferroni-style check: the pooled 2.5th percentile above zero.

If a rule works, the next step is a separate forward paper test with announcements pulled live from NSE. Nothing changes in the live system from this study alone.

## Output

- `services/quant/docs/results/earnings-drift-result.json`;
- `services/quant/docs/earnings-drift-result.md`.

Run:

```
python -m quant_agents.research.earnings_drift
```

## Amendment A (2026-10-27): clean test on results published after the extract

Written after the first result (one rule, `pos4_h40`, passed the gate) and **before any return on the new events was computed.**

- **Rule scored:** `pos4_h40` only, unchanged: reaction ≥ +4%, entry at the open of day +2, hold 40 sessions, the same costs and the same equal-weight universe benchmark. The other three rules are reported for information only.
- **Events:**
  - NSE `corporate-announcements` from 2025-03-01 to 2026-10-27, fetched 2026-10-27, one call per symbol. Raw responses are kept under `datasets/research/earnings_drift/` (gitignored).
  - The old results endpoint stops in January 2025, when SEBI moved results into integrated filings.
- **Which announcement is the result:** for each symbol and quarter end Q, take announcements dated 7 to 75 days after Q with category "Outcome of Board Meeting", "Financial Result Updates" or "Integrated Filing- Financial". The event time is:
  - the earliest of those whose text mentions "result";
  - if none mentions it, the earliest "Outcome of Board Meeting" in the window.
- **Extraction check, before scoring:** the same rule is applied to the 2024 announcements already in the H001 extract and compared with the results endpoint's times. The rule is used only if it matches the same session for at least 90% of 2024 events.
- **Prices:** the same daily file, ending 2026-10-05. Only events whose 40-session exit falls inside it are scored, so day 0 runs to about August 2026.
- **Gate for the clean test:** mean net excess > 0 **and** the 10th-percentile quarter-block bootstrap > 0. With so few trades the bootstrap may be wide, and that is reported as it is.

### Amendment A.1 (2026-10-27): the extraction check, as run

Written before any return on the new events was computed.

**The same-session check failed: 115 of 180 events (64%) matched.** The reason is timing, not wrong events: in the mismatches, the announcement is **earlier** than the results endpoint's time, usually by up to a day. Axis Bank's Q3 results, for example, were announced on the evening of 23 Jan 2024, and the endpoint's time is the next morning, apparently a later filing.

So the check is replaced by what it was meant to test:
- **Does the rule find the same result event, at or before the endpoint's time?**
- Result: **180 of 180** (100%) have a rule event between 3 days before and 6 hours after the endpoint's time, and **none** of the rule's events is later.
- The rule's 8 extra 2024 events are also genuine results filings ("has submitted to the Exchange, the financial results…").

Consequences:
- The rule is used for the clean test.
- **The original study's day 0 was sometimes a day late.** That cannot leak the future, since every time used was at or after the real disclosure. It can blur the reaction, so the clean test, using the earlier and more accurate times, is not an exact replica of the original timing.
