# H001 protocol decision review

Supersession, 2026-10-12. This file is the review as written before approval. Its recommendations were not decisions on that day. The approval table in `h001-protocol-approval.md` later recorded those methodological choices as **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**. Do not read a recommendation below as if it were still open, and do not read it as if it had already been approved when this note was written.

What stays unresolved after that approval: completeness of the three-subject class, no include-list rows in 2025Q2–2025Q4, unknown eligible and smaller-class counts, validation adequacy, no H001 implementation, the symbol-bootstrap limit under common market shocks, the unverified historical digest, and actionability beyond the proxy clock. The 3,690-row coverage predicate, the 251 candidates, and eligible observations stay separate. Execution is not authorized.

Review only. Recommendations in this note are not decisions. No gate below was resolved in this review. The provisional event class in `h001-event-class-provisional.md` is unchanged. The hypothesis text was unchanged when this review was written.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. H001 is not authorized.

`h001-data-readiness.md` still says no historical earnings file is in the repository. That sentence is an earlier inventory. It is not the current file record. The readiness labels stay.

## Event clock, already constrained

`available_at` is `exchdisstime` parsed as `DD-Mon-YYYY HH:MM:SS` and tagged `Asia/Kolkata`. The vendor string has no offset. `period_end`, crawl time, and RSS `retrieved_at` are not substitutes. That parse was checked against the freeze. Actionability at that second was not shown. There is no BSE dissemination check. This review does not treat the clock as a tradable instant.

The hypothesis still says evaluation is blocked because point-in-time earnings have no trustworthy `available_at`. That sentence is older than the clock convention. The remaining clock limit is actionability, not a missing field. This note does not edit the hypothesis.

## 1. Decision time and entry

Options. A: the first stored 5-minute bar whose end is at or after `available_at`. B: the earliest research-calendar session whose 09:15 IST is strictly after `available_at`, with `P0` the open of the 09:15–09:20 bar only. A missing bar, or a later first bar that day, drops the event. No later bar is substituted.

Evidence. The session calendar is dates with a daily bar ending 15:30 IST in `nifty50_1d_20261005`. Missing 5-minute bars are not filled. The audit did not show that a trader could act at `exchdisstime`. Option A can enter the same session. The label section of the approval sheet still says `P0` is the open of the first stored 5-minute bar, which is looser than the 09:15–09:20 rule. The clock-rules paragraph is the stricter proposal.

Recommendation, not a decision. Choose B, including the 09:15–09:20 open and the drop rule.

Consequences. Intraday and after-close announcements both wait. Same-session reaction is unused. An announcement before 09:15 can use that day's open. Some events will be dropped when the opening bar is absent.

New data: no. Hypothesis: no. The frozen timestamp rule already requires `available_at` at or before the prediction time. B meets that rule. It does not rewrite the hypothesis.

## 2. Horizon

Options. H1: the 15:30 IST official close of the first calendar session strictly after the decision session. H5: the fifth such close. The decision session's own close is not `P1`. The 15:15 IST 5-minute bar is not the close. No horizon has been tested on outcomes.

Recommendation, not a decision. Choose H1.

Consequences. A Tuesday 09:15 entry uses Wednesday's 15:30 close, not Tuesday's close. H5 mixes later announcements into the label. For events disseminated in 2024Q1–2025Q1, both H1 and H5 finish before July 2025, so the horizon choice does not create validation events under the written July 2025 split.

New data: no. Hypothesis: the horizon field is **NOT FROZEN**. Choosing H1 fills that field. It does not change a frozen sentence.

## 3. Label

Options. L-sign: 1 when `(P1-P0)/P0 > 0`, else 0. L-threshold: 1 when the return exceeds a number written before any fit. A missing price leaves the label absent. No threshold number exists. The 2 bp gate is not the label.

Recommendation, not a decision. Choose L-sign. Do not invent a threshold.

Consequences. A zero return is class 0. The cost gate stays a separate economic test.

New data: no. Hypothesis: the target is **NOT FROZEN**. L-sign does not change a frozen sentence.

## 4. Features

Options. The written list is `hasXbrl` as 0/1, the IST minute of `available_at`, and the symbol's prior 1, 5, and 20 session returns from closes that ended before 09:15 on the decision day. A short history drops the row. `desc` is the sample filter, not a feature. The alternative is to cut one or more of those inputs. PDF text, line items, `period_end`, crawl time, `volume_imbalance`, Oil & Gas, and any price after the decision time stay out.

Evidence. On this freeze `hasXbrl` is false on every announcement through 17 July 2025. The provisional class has no include-list row after 2025Q1. Inside that sample the flag does not vary, so it cannot separate events. It remains a legal point-in-time field. It is not an inclusion rule.

Recommendation, not a decision. Keep the minute of day and the three prior returns. Drop `hasXbrl` from the model inputs for this class.

Consequences. `p` is smaller by one. The flag can be stored on the row and still not enter the regression. Adding it back would fit a constant.

New data: no. Hypothesis: features are **NOT FROZEN**.

## 5. Minimum sample

Options. At least `10 * p` labeled training clusters, with `p` equal to the model inputs plus the intercept. A cluster is one symbol on one decision session. The open choice is whether 10 applies to all training clusters or to the smaller class. Both classes must appear in each partition. Missing the bar later means `INCONCLUSIVE`, not a retune. `10` was not estimated from this tape.

Evidence. The approval sheet states that the all-cluster form can pass while the minority class is thin. The 251 include-list rows are not a cluster count, and this review does not compute one. `p` depends on the unapproved feature list.

Recommendation, not a decision. Apply `10 * p` to the smaller class in each partition. Use the same 10. Do not add a second constant.

Consequences. A thin class fails the bar instead of passing on the larger class. The run is then inconclusive. Repeated events in one symbol-session still count once. Correlation across days is still ignored.

New data: no. Hypothesis: no frozen sample-size sentence.

## 6. Date split

Options. The written split trains only when both the decision date and the horizon date are on or before 2025-06-30, embargoes a June decision whose horizon falls in July, and starts validation on 2025-07-01. The alternative is a cut inside the covered dissemination window, still with an embargo so a training label does not use a validation close.

Evidence. The provisional class has 251 include-list rows, all in 2024Q1–2025Q1, and none in 2025Q2–2025Q4. A validation window that starts on 2025-07-01 therefore has no primary event. Confirming the written split cannot produce a validation score. This conflict cannot be removed without changing the split or changing the class. This review does not change the class.

Recommendation, not a decision. Do not confirm the July 2025 validation start. Replace it, before any fit, with a cut inside the covered window. One such cut, not approved here: training only when both session dates are on or before 2024-12-31; rows whose horizon crosses into 2025 are in neither partition; validation decision dates run from 2025-01-01 through 2025-03-31. The documented 2025Q1 include-list subject is `financial result updates` only (49 rows before any clock or label drop).

Consequences. Validation is the early-2025 events, not the second half of 2025. The second half stays uncovered. The same symbol may still appear in both partitions. Overlapping horizons stay dependent rows.

New data: no. Hypothesis: no frozen split. This recommendation does change the split written in the approval sheet. It does not change the hypothesis.

## 7. Costs

Options. Leave the hypothesis sentence as written: positive validation net edge after 2 bp, without saying once or twice. Or adopt `net = (P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002` with zero slippage, which is 2 bp on entry notional and 2 bp on exit notional. Or write a different schedule, including one 2 bp round trip. Zerodha itemized delivery charges are a different schedule and are not this gate.

Evidence. `fee_on` charges `flat_bps` on each fill. `price_trade` calls it on the buy and on the sell with slippage zero. The hypothesis does not say once or twice. The documents do not choose. This ambiguity cannot be resolved from the existing text.

Recommendation, not a decision. Adopt the per-side formula as the gate arithmetic, and require a later explicit hypothesis edit that says 2 bp on each fill. This review does not make that edit.

Consequences. The charge is larger than one 2 bp round trip. Rejecting the formula leaves the gate existence frozen and the arithmetic unset, so the gate still cannot be applied.

New data: no. Hypothesis: yes, a later wording change is required if this formula is adopted. The existence of a 2 bp gate would stay. The arithmetic would be specified.

## 8. Probability cutoff

Options. Enter when `p` is strictly above the training positive rate, frozen from training labels before validation. Or enter when `p` is strictly above 0.5. No sweep.

Recommendation, not a decision. Use the training positive rate.

Consequences. The cutoff is the training base rate, not a claim that it is the best economic threshold. The constant-rate scoring baseline does not open a trade under this rule. Brier score and log loss do not use the cutoff.

New data: no. Hypothesis: no.

## 9. Scores and baselines

Options. The written scores are Brier score, mean `(p-y)^2`, and log loss with `p` clipped to `[1e-6, 1-1e-6]`. The scoring baseline is the constant training positive rate. Economic always-flat takes no trades. Always-long enters every validation event with `P0` and `P1`. The quant-agent baseline keeps its existing signals. The alternative is to reject or replace one of those definitions.

Evidence. The hypothesis already names always-flat, always-long, and the quant-agent baseline. It does not name Brier score or log loss.

Recommendation, not a decision. Keep this split.

Consequences. A better score is not a pass of the cost gate. The constant-rate object and the no-trade object stay different even when they make no trade.

New data: no. Hypothesis: the three economic baselines stay. Naming Brier score and log loss adds metrics the hypothesis did not list. It does not replace those baselines.

## 10. Bootstrap

Options. The written design is a 95 percent percentile interval, 1000 resamples, seed `20261011`, symbols drawn with replacement, rows of a symbol kept together, on validation Brier score, log loss, and the primary mean net. The alternative is a later time-block or two-way design. Nothing has been run.

Recommendation, not a decision. Keep the symbol bootstrap.

Consequences. Repeated events on one name stay together. A day on which many names move together is not a resample unit. The interval is not a market-day interval.

New data: no. Hypothesis: no.

## 11. Primary economic gate

Options. Mean `net` over every eligible validation event that has `P0` and `P1`, with a no-trade contributing zero, passing only if that mean is strictly positive and the leakage checks and sample minimum also pass. Trade-only mean, trade count, and the sum of `net` are diagnostics. The alternative is to make one of those diagnostics the gate.

Recommendation, not a decision. Keep the all-event mean, with no-trades as zero.

Consequences. The gate depends on the unapproved cost formula and cutoff. Many no-trades pull the mean toward zero. Under the written July 2025 split there are no validation events, so the mean is undefined until the split is replaced.

New data: no. Hypothesis: this specifies "positive validation net edge." It does not remove the 2 bp gate. The arithmetic still waits on item 7.

## Contradictions the documents do not resolve

The approval sheet calls the event class provisional and then says not to apply or count the rule until that paragraph is approved. The provisional note is the later decision. The leftover sentence is not a second class.

The label paragraph's "first stored 5-minute bar" and the clock rule's "09:15–09:20 bar only" are not the same entry. They stay unresolved until B is explicitly chosen with the stricter entry.

The written 2025-07-01 validation start and the provisional class cannot both be used. Validation would be empty. That is not fixed by confirming the split.

"After 2 bp" and the per-fill formula are not the same charge. Neither document selects one.

The hypothesis still says point-in-time events are unavailable. The later notes define `available_at` as tagged `exchdisstime` and leave actionability unverified. Those statements are not reconciled here, and the hypothesis is not edited.

`h001-data-readiness.md` still describes a checkout without the announcement file. Later notes record the file. Readiness is unchanged.

None of these recommendations is approved. Clock, entry, horizon, label, features, sample size, split, costs, cutoff, scores, bootstrap, and the primary gate remain open. Execution remains unauthorized.
