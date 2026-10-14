# H001 chronological split feasibility

Feasibility only. No label, feature value, score, or model was produced. The provisional event class is unchanged. The hypothesis text and the cost configuration are unchanged.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. H001 is not authorized.

Holdout `snapshots/holdout_after_20261005` was not opened. Session dates and opening-bar presence came from the research files `snapshots 2/nifty50/1d/candles.jsonl` and `snapshots 2/nifty50/5m/candles.jsonl`. Prices were not read.

## What was counted

The 251 rows are announcement rows whose normalized `desc` is `financial result updates` (245), `consolidated result updates ifrs` (4), or `publish audited results` (2), and whose attachment text does not fire the contradiction check. That check fired on none of them. These are event counts, not labeled examples.

`available_at` is `exchdisstime` tagged `Asia/Kolkata`. The first is `2024-01-11T15:53:23+05:30`. The last is `2025-02-13T18:46:44+05:30`. Forty-nine symbols appear. `TATAMOTORS` is absent.

A symbol-session cluster below uses the unapproved decision-time proposal B: the decision session is the earliest research-calendar date whose 09:15 IST is strictly after `available_at`. The calendar is the 685 dates from 2024-01-01 through 2026-10-05 that have a daily bar ending 15:30 IST. This is not an approval of B. Under that clock the 251 rows fall on 245 clusters. Six rows share a symbol and a decision session with another include-list row. Decision sessions run from 2024-01-12 through 2025-02-14.

A labeled example would also need `P0`, `P1`, and a class. Those were not built. Event counts are therefore an upper bound on usable labeled rows.

## Sample rule, without labels

`10 * p` on the smaller class cannot be evaluated until labels exist. The smaller class is unknown. Two necessary checks use cluster totals only:

- If features are the IST minute plus three prior returns, `p` is 5 including the intercept, and `10 * p` is 50.
- If `hasXbrl` is also an input, `p` is 6 and `10 * p` is 60.

If a partition has fewer clusters than that number, the smaller class also has fewer, so the rule fails. If a partition has more clusters, the rule can still fail. Neither case produces a label count.

## Candidate boundaries

The boundary is the decision-session date. Training is on or before that date. Validation is after it. Opening-bar misses are zero on both sides of every cut.

| Boundary | Train events | Validation events | Train symbols | Validation symbols | Train clusters | Validation clusters |
|---|---:|---:|---:|---:|---:|---:|
| 2024-03-31 | 50 | 201 | 49 | 49 | 49 | 196 |
| 2024-06-30 | 102 | 149 | 49 | 49 | 98 | 147 |
| 2024-09-30 | 153 | 98 | 49 | 49 | 147 | 98 |
| 2024-12-31 | 202 | 49 | 49 | 49 | 196 | 49 |
| 2025-03-31 | 251 | 0 | 49 | 0 | 245 | 0 |
| 2025-06-30 | 251 | 0 | 49 | 0 | 245 | 0 |

The written approval-sheet split, validation decisions from 2025-07-01, matches the last two rows. Validation is empty. That split cannot support a chronological test of this class.

## Constraints that can shrink the sample

These are availability checks, not labels.

Every include-list row has a decision session, a 09:15–09:20 bar for that symbol on that session, a daily bar for that symbol on that session, and a later calendar session. None of those gaps removes a row.

The unapproved 20-session return needs 21 daily sessions on that symbol strictly before the decision session. Twenty-seven events have fewer than 21. All 27 have decision dates on or before 2024-03-31. They sit in training for every boundary at or after that date. If that feature is kept, those 27 events drop. At the 2024-06-30 boundary, training clusters would fall from 98 by at most 27, and would still be at least 71. Validation is unchanged. This is not a feature value.

## Earliest split that can be tested

The earliest boundary at which both sides are nonempty and both have at least 60 clusters is **2024-06-30**. Training has 102 events, 49 symbols, and 98 clusters. Validation has 149 events, 49 symbols, and 147 clusters, with decision dates from 2024-07-01 through 2025-02-14.

That is the earliest plausible validation period in this tape. It is not a decision. The smaller-class rule is still unevaluable. A 2024-09-30 boundary also clears the cluster-total check, with 98 validation clusters. A 2024-12-31 boundary does not: validation has 49 clusters, which is already below 50 and below 60.

## What a new split would change

The frozen hypothesis does not name a split date. Target, features, and horizon are **NOT FROZEN**. Replacing 2025-06-30 / 2025-07-01 does not rewrite the earnings claim, the one logistic regression, or the existence of a 2 bp gate.

It does change the split written in `h001-protocol-approval.md`. That change needs an explicit approval before any fit. Choosing 2024-06-30 would test the claim on a validation window that ends in February 2025, not on the second half of 2025. The second half stays uncovered by this class. Approving that cut is a protocol amendment, not a result.

## 2 bp per fill and 2 bp round-trip

The hypothesis says “after 2 bp” and does not say once or twice. This note does not edit that sentence.

Per fill, as implemented by charging `flat_bps` on the buy and again on the sell with zero slippage:

`net = (P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`

That is 2 bp of entry notional plus 2 bp of exit notional.

A 2 bp round-trip subtracts 2 bp once:

`net = (P1 - P0) / P0 - 0.0002`

If `P1 = P0`, the per-fill result is −4 bp and the round-trip result is −2 bp. If the gross return is 1 percent, the per-fill result is 0.9598 percent and the round-trip result is 0.98 percent. No market price was used. The two formulas are not interchangeable, and neither is approved.
