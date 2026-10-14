# H001 decision package

Status: **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. On 2026-10-12 the user approved the recommendations below. The live record is the approval table in `h001-protocol-approval.md`. Where this note still says a choice is awaiting approval, that sentence is historical and the table controls.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. No labels, features, or model were built. Holdout was not opened. Approval does not authorize a fit.

The incoming review text stopped while defining `p`. Item G below uses the definition already written in `h001-protocol-approval.md`: `p` is the number of model inputs plus the intercept. Items H through M are the remaining open rows on that sheet. They are included so the package covers every methodological blocker still listed there.

## Preserved provisional choices

These choices are now user-approved and are not authorization to execute.

Split. Training decision sessions are on or before 2024-06-30: 102 events, 98 symbol-session clusters. Validation decision sessions are after 2024-06-30, through 2025-02-14: 149 events, 147 clusters. Those counts are historical and pre-eligibility. They are not labeled samples. They do not show whether the smaller-class rule passes or fails. A training row whose H1 window ends after 2024-06-30 is purged.

Costs. `net = (P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`. That is 2 bp on the entry notional and 2 bp on the exit notional, about 4 bp round-trip when the price does not change. The hypothesis cost cell now says this. The cost code was not modified and has not been verified against the formula.

## A. Research scope

Options. Scope A tests whether the occurrence and timing of a results-announcement event contain predictive information. Scope B tests the surprise in first-publication EPS or revenue against expectations, using point-in-time fundamentals.

Evidence. The provisional class is three `desc` subjects. It has no EPS, revenue, consensus, or restatement field. The classification review and the recovery audit record that PDF bodies and line-item restatements are absent. The hypothesis rationale mentions surprises. The frozen source line says earnings and events, one source. No surprise series exists in the freeze.

Recommendation. Scope A.

Why. Scope B cannot be computed from the records that exist. Inventing expectations would break the point-in-time rule.

Downside. Scope A does not test whether the market was surprised. A results print that was already anticipated is still an event.

Consequences. The 251-row class is the population. Eligibility, the split, and the acceptance test stay event-level. Statistical power is the power of that event sample, not of an earnings-surprise panel.

Depends on. Nothing else. Scope B would be a separate data-readiness project and is not authorized.

## B. Event clock

Options. Use `available_at`, defined as `exchdisstime` tagged `Asia/Kolkata`, as an explicit proxy. Or stay blocked until a source proves when the filing became public and when a strategy could act.

Evidence. The vendor string is offset-naive `DD-Mon-YYYY HH:MM:SS`. Tagging it as `Asia/Kolkata` reproduces the parquet `available_at` on the audited rows. That is a parse. It does not prove first public access, immutability, or that a trader could act at that second. There is no BSE dissemination check. The hypothesis still says a trustworthy `available_at` is unavailable. That sentence is older than the parse and was not edited.

Recommendation. Use `available_at` as a documented proxy clock for protocol design. Do not treat it as proof of public access or of actionability. Execution stays blocked until the other gates are approved.

Why. A later decision time can avoid pretending the dissemination second is the trade time. Rejecting the proxy leaves no clock in the file.

Downside. The proxy can be early or late relative to real access. That error is unmeasured.

Consequences. Every later timestamp is measured from this proxy. The acceptance test inherits that error. Readiness does not flip to ready.

Depends on. Decision time. The proxy is usable only together with a decision time that is strictly after it.

## C. Decision time and entry

Options. Rule B: the earliest research-calendar session whose 09:15 IST is strictly after `available_at`, with `P0` the open of that 09:15–09:20 bar. A missing bar drops the event. Rule A: the first stored 5-minute bar whose end is at or after `available_at`.

Evidence. The feasibility counts used rule B and are not an approval of it. Under B, an announcement before 09:15 can use that day’s open. An announcement at 09:15, or any time after 09:15 including after 15:30, waits for a later session. There is no same-session entry. The feasibility check found a 09:15–09:20 bar for every include-list row. That check is not a label.

Recommendation. Rule B, including the drop rule.

Why. Actionability at `exchdisstime` is unproved. Rule A can enter the same session, including on a bar that ends while the announcement is still new.

Downside. Same-session reaction is unused. The pre-eligibility cluster counts are tied to this clock. Approving A would make those counts the wrong split.

Consequences. `P0` is defined. Events with no opening bar leave the sample and must be counted as drops, not filled. The 2024-06-30 split stays meaningful only if B is the decision clock.

Depends on. The proxy clock in B. The split counts.

## D. Horizon

Options. H1: the 15:30 IST close of the first calendar session strictly after the decision session. H5: the fifth such close. The decision session’s own close is not `P1`. The 15:15 IST 5-minute bar is not the close. Sessions are dates with a daily bar ending 15:30 IST in `nifty50_1d_20261005`.

Recommendation. H1 is the only primary horizon. H5 is excluded from the primary test. It may be reported later as exploratory only if a separate request says so. It is not part of this recommendation’s acceptance test.

Why. The provisional sample is a few hundred events. One horizon spends that sample once. H5 mixes later news into the label.

Downside. H1 does not measure a week-long drift. From a Tuesday open, `P1` is Wednesday’s close, so the decision day is inside the hold.

Consequences. A training row whose H1 session falls after 2024-06-30 must be embargoed from both partitions. That embargo is not yet applied. The feasibility counts did not drop those rows. Labeled counts will be smaller than 102 and 149 if any training horizon crosses the cut. Power falls if that embargo is large. No label was built, so the number of crossings is unknown.

Depends on. Rule B, because the decision session defines “the next session.”

## E. Label

Options. L-sign: `y = 1` when `(P1 - P0) / P0 > 0`, otherwise `0`. A missing price leaves the label absent. L-threshold needs a number written before any fit. No number exists. The 2 bp gate is not the label.

Recommendation. L-sign.

Why. A threshold chosen now would be arbitrary. Tying it to 2 bp would mix the label with the cost gate.

Downside. A zero return is class 0. The label ignores costs, so a small positive return can still lose money after the per-fill charge.

Consequences. Class balance is unknown until labels exist. The smaller-class sample rule cannot be checked before that. Missing prices are exclusions, reported as drops, not imputed.

Depends on. Rule B for `P0` and H1 for `P1`.

## F. Features and eligibility

Options. The written candidate list is `hasXbrl`, the IST minute of `available_at`, and prior 1-, 5-, and 20-session returns. The alternative is that list without `hasXbrl`. Exclusions already recorded: attachment and PDF text, future prices, `period_end`, crawl time, `volume_imbalance`, and holdout.

Evidence. Inside the provisional class, `hasXbrl` does not vary: it is false on every announcement through 17 July 2025, and the class has no later row. The feasibility note found 27 events with fewer than 21 prior daily sessions, all with decision dates on or before 2024-03-31. That is not a feature table.

Recommendation. Four inputs only: IST minute of `available_at`, and the symbol’s own prior 1-, 5-, and 20-session returns, using daily closes that ended before 09:15 on the decision session. `desc` stays the filter, not a feature. Keep the exclusions above, including `hasXbrl`.

Why. Four inputs plus an intercept is small relative to about 100 training clusters. A constant flag does not belong in the regression.

Downside. The 20-session return drops the 27 short-history events. Early 2024 is thinner. No other pre-event state is in the model.

Eligibility. A row enters the labeled sample only when `P0`, `P1`, and all four inputs exist. A short history is a drop, counted in a drop table, not filled from another symbol. The 27 events are expected drops if this list is approved. They are not dropped yet, because features were not built.

Consequences. At the preserved split, those 27 sit on the training side. Training clusters would fall from 98 by at most 27. Validation clusters are unchanged by that particular gap. Power on the training side falls. The acceptance test uses only rows that survive.

Depends on. Rule B, because “before the decision session” uses that clock.

## G. Model complexity and `10 * p`

Options. One logistic regression, already frozen, with no sweep. The sample bar is `10 * p` labeled clusters. The open choice is all training clusters, or the smaller class. `p` is the number of model inputs plus the intercept. `10` was not estimated from this tape. Missing the bar later means `INCONCLUSIVE`, not a change of class or features.

Recommendation. Use the four inputs in item F. Then `p = 5` and the proposed threshold is `10 * p = 50`. Check that threshold against the eligible observations in the smaller label class in each partition, not against all clusters. Both classes must still appear in each partition. This smaller-class interpretation is **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. It is not evidence that the count of 50 is met.

Why. The all-cluster form can pass while one label class is thin. With one logistic regression, that is the failure the rule was meant to catch. Applying the same 10 to the smaller class does not add a second constant.

Downside. The run is more likely to be inconclusive. Correlation across days of the same symbol is still ignored. The pre-eligibility totals are 98 training clusters and 147 validation clusters. Both are numerically greater than 50. They are not counts of the smaller label class.

Consequences. The requirement remains unresolved. It has not passed and it has not failed. Actual smaller-class counts are unknown because labels have not been generated. Do not estimate them. If a later authorized run finds either partition’s smaller class below 50, that run is inconclusive and the acceptance test is not applied.

Depends on. The feature list, which sets `p`, and the label, which sets the class counts.

## H. Probability cutoff

Options. Enter when predicted probability is strictly above the training positive rate, frozen from training labels before validation. Or enter when it is strictly above 0.5. No sweep.

Recommendation. Use the training positive rate.

Why. With an unknown base rate, 0.5 can trade almost every event or almost none. The training rate is fixed before validation and is not tuned on the validation outcome.

Downside. It is not claimed to be the best economic threshold. The constant-rate score baseline does not open a trade under this rule.

Consequences. Many no-trades pull the primary mean toward zero. The cutoff does not enter Brier score or log loss.

Depends on. The label, because the training rate is a label frequency.

## I. Scores and baselines

Options. Brier score is the mean of `(p - y)^2`. Log loss uses `p` clipped to `[1e-6, 1 - 1e-6]`. The scoring baseline is the constant training positive rate. Economic always-flat takes no trades. Always-long enters every validation event with `P0` and `P1`. The quant-agent baseline keeps its existing signals. The hypothesis already names those three economic baselines and does not name Brier score or log loss.

Recommendation. Keep these definitions available for a later report. Whether each baseline is diagnostic only, or is part of acceptance, is unresolved. Do not assign that role here.

Why. A probability score and a trading result answer different questions. The hypothesis names always-flat, always-long, and the quant-agent baseline, and it does not say whether beating them is required for a pass.

Downside. Naming Brier score and log loss adds metrics the hypothesis did not list. Leaving their role open means a later reader can mistake a diagnostic for a gate.

Consequences. No baseline is an acceptance hurdle until you say so. The constant-rate object, always-flat, always-long, and the quant-agent baseline stay defined and unresolved in role.

Depends on. The label and the model. Not on the cutoff. The acceptance role also depends on item L.

## J. Bootstrap

Options. The written design is a 95 percent percentile interval, 1000 resamples, seed `20261011`, symbols drawn with replacement, rows of a symbol kept together, on validation Brier score, log loss, and the primary mean net. The alternative is a later time-block design. Nothing has been run.

Recommendation. Keep the symbol bootstrap.

Why. Several events can share a name. Keeping those rows together matches the cluster idea better than drawing rows independently. A time-block design is not specified.

Downside. A day on which many names move together is not a resample unit. The interval is not a market-day interval.

Consequences. A positive observed mean net is not a demonstration that the true expected return is positive. The existing protocol does not say whether the 95 percent interval is part of acceptance. These choices stay unresolved, and this note does not pick one:

- The lower confidence bound must be above zero.
- The strategy must beat a named baseline.
- The interval is diagnostic only, and acceptance uses the observed mean alone.

Depends on. The primary gate and the scores. Not on new data. The acceptance role also depends on item L.

## K. Primary gate

Options. Mean `net` over every eligible validation event that has `P0` and `P1`, with a no-trade as zero, passing only if that mean is strictly positive. Or use the trade-only mean, the trade count, or the sum of `net` as the gate. Those three are written as diagnostics.

Recommendation. Keep the all-eligible-event mean, with a no-trade as zero. This denominator is **USER APPROVED — NOT AUTHORIZED TO EXECUTE**, with the per-fill formula `net = (P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`. The lower 95 percent bound must also be strictly above zero. That bound is not proof of a live-tradable edge.

Why. A rule that skips most events should not be judged only on the trades it keeps. The hypothesis cost cell now states the per-fill charge. The cost code was not checked against it.

Downside. Many no-trades shrink the observed mean toward zero. A strictly positive observed mean is still not proof that the true expected return is positive.

Consequences. The mean is undefined until labels, `P0`, and `P1` exist. The 149 validation events are not that denominator. Whether a confidence bound or a baseline comparison is also required is item J, and it is unresolved.

Depends on. The provisional cost formula, the cutoff, rule B, H1, and L-sign.

## L. Acceptance and validation viability

Options. One proposed line is: leakage checks pass, the smaller-class count is at least 50, and the observed mean net is strictly positive. Separately, and not chosen here: require the lower confidence bound to exceed zero; require a win against a named baseline; or treat the interval and the baselines as diagnostic only. Otherwise a later run is inconclusive or a fail, and the class and features are not retuned.

Recommendation. Leave the three-part line as a proposal only. Do not add the interval or a baseline hurdle to it. Validation viability is not established. The 149 events and 147 clusters show only that a nonempty pre-eligibility validation set exists under rule B. They do not show a labeled smaller class, and they do not pass or fail the threshold of 50.

Why. The feasibility report already separated event counts from labeled examples. Treating 147 clusters as a smaller-class result would skip the labels. A positive observed mean would still not show that the true expected return is positive.

Downside. H001 can remain inconclusive after a later authorized run even if some trades make money.

Consequences. No acceptance claim is available now. Readiness stays `READY_TO_RUN = NO`.

Depends on. Items C through K.

## M. Uncovered quarters

The provisional class has no identified event in 2025Q2, 2025Q3, or 2025Q4. That is a coverage limit. It is not proof that no earnings results were announced. Do not fill those quarters from `hasXbrl`, board-meeting outcomes, press releases, or investor presentations.

Recommendation. Report the limit beside any later result. Do not extend the validation window into those quarters under this class.

Why. The 2024-06-30 split already ends at the last include-list decision session, 2025-02-14. Extending it would add empty time, not events.

Downside. The second half of 2025 is untested. A subject change at NSE can look like a dead strategy.

Consequences. The acceptance test does not speak about 2025Q2–2025Q4.

Depends on. The provisional class, which this package does not change.

## Cost wording

The hypothesis cost cell now states 2 bp on the entry fill and 2 bp on the exit fill, with the formula above. The cost implementation was not modified and has not been verified against that sentence.

## Approval record

The methodological choices in this note are **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. The status line for the protocol is **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**.

The smaller-class threshold of 50 is approved as a rule and is unresolved as a result. It is not passed and it is not failed. Eligible class counts are unknown. Whether the symbol-cluster bootstrap supports inference under common market shocks is an interpretation blocker, not a silent change of method. The 251 include-list rows are not confirmed eligible. 2025Q2–2025Q4 stay uncovered. Execution is not authorized.

`DATA NOT READY`  
`BLOCKED_PRECONDITION`  
`READY_TO_RUN = NO`
