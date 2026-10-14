# H001 protocol approval

Status: **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**. On 2026-10-12 the user approved the methodological choices in `h001-decision-package.md`. Each approved choice is **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. H001 stays `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO. This note does not authorize labels, features, training, or a backtest.

`available_at` is `exchdisstime` parsed and tagged `Asia/Kolkata`. That is a documented proxy clock for this experiment. It does not establish when a filing first became public, when a live strategy could act, or that the timestamp is immutable. Those points were not independently verified.

No event count, feature matrix, score, or backtest was computed for this note.

## Approved facts, left as they are

- Research source: earnings and events, one source.
- Universe: NIFTY 50 names with bars. TATAMOTORS stays excluded.
- Model, when authorized: one logistic regression. No sweep, no boosting, no MlAgent.
- Cost gate: 2 bp on the entry fill and 2 bp on the exit fill, `net = (P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`. The hypothesis wording now says this. The cost code was not changed and was not checked against the formula. The gate is not a label.
- Baselines, when a run exists: always-flat, always-long, and the existing quant-agent baseline.
- Integrity baseline `NEW_VERIFICATION_BASELINE`: 493 files, SHA-256 `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2`. This is not the historical digest.
- Historical digest `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`: unverified.
- `available_at` is `exchdisstime` tagged `Asia/Kolkata`. Missing bars are not interpolated.

## 1. Event class

Status: **PROVISIONAL**. On 2026-10-11 the three-subject rule was adopted for research design only. The record is `h001-event-class-provisional.md`. It does not authorize a fit. The 3,690-row audit predicate is not this class. The identified include-list sample is 251 rows, all in 2024Q1–2025Q1. 2025Q2–2025Q4 are uncovered under this definition, which is not proof that no results were announced.

Primary `INCLUDE` is an exact normalized `desc` of `financial result updates`, `consolidated result updates ifrs`, or `publish audited results`, unless the attachment summary contradicts it. `integrated filing financial` stays `REVIEW_REQUIRED` because that category is a bundle and the PDF is not in the JSON. `hasXbrl`, attachment text, and the filename cannot include a row.

Specificity: the three strings name a results disclosure. They do not admit every filing that contains the word "financial".

False positives that remain: a wrong `desc` with empty attachment text still enters, because the PDF is absent and the contradiction list only covers trading window, divestment, and loss of share.

False negatives: a real results print filed as an integrated filing, a board outcome, or a press release is not in the primary sample. A disclosure that exists only in the PDF cannot be recovered.

`REVIEW_REQUIRED` stays out of the primary sample until a later adjudication you authorize. Do not apply the rule, and do not count it, until you approve this paragraph.

## 2. Decision time

Both options are open. Recommendation: **next trading-session open after `available_at`**.

| Option | What it uses | Reliability | Intraday versus overnight | Missing bar |
|---|---|---|---|---|
| A. First stored 5-minute bar whose end is at or after `available_at` | The next bar already in the research tape | The clock is parsed. Actionability at that second is not shown. A bar that ends during the session can sit before a trader could act. | An announcement during the session can enter the same session. An announcement after the cash close waits for a later bar, which may be the next day. | If that bar is one of the missing 5-minute steps, the event has no decision time. It is dropped, not filled. |
| B. Next session open | The open of the next cash session after `available_at`. The price is the open of the first stored 5-minute bar of that session (09:15 IST). | Matches the existing rule that after-close events wait. It does not claim the print was tradable at `exchdisstime`. | Intraday and overnight announcements both wait for the next 09:15. Same-session information is not used. | If that opening bar is missing, the event is dropped. |

Option B is the recommendation because the audit did not show that the strategy could trade at the dissemination second, and option A can use a bar that ends while the announcement is still fresh. Option A remains available if you want the earlier time. Neither is frozen.

### Clock rules for option B

These rules are part of the proposal. They are not approved.

The session calendar is the set of dates that have a daily bar ending at 15:30 IST in the research daily snapshot `nifty50_1d_20261005`, using symbols that have bars. A missing 5-minute bar does not add or remove a date. The holdout snapshot is not part of this calendar.

All clocks below are `Asia/Kolkata`.

The decision session is the earliest calendar date D such that 09:15:00 on D is strictly after `available_at`. An announcement before 09:15 uses that day's open. An announcement at or after 09:15, including at or after the 15:30 close, uses a later date. There is no same-session entry.

`P0` is the open of the 5-minute bar that starts at 09:15:00 on D and ends at 09:20:00. If that bar is absent, or the first stored bar that day starts later, the event is dropped. A later bar is not treated as the open.

The decision timestamp is 09:15:00 on D. A feature is usable only when its own end is at or before that instant. The open price is known then. That bar's high, low, and close are not.

## 3. Horizon

No horizon was tested. Two alternatives, both measured in completed sessions after the decision session. The decision session's own close is not the horizon.

| Id | Horizon | Why it is meaningful | Tradeoff |
|---|---|---|---|
| H1 | The 15:30 close of the first calendar session strictly after the decision session | Near-term. The decision session's own close is not `P1`. From a Tuesday open, `P1` is Wednesday's official close. | Holds through the decision day and the next day. It is not "open to that same day's close." |
| H5 | The close of the fifth completed session strictly after the decision session | About one trading week. | Mixes later news into the label. |

Recommendation: pre-register **H1** if you approve option B as the decision time. H5 is the only other horizon on this list. Do not add horizons after seeing results.

The close is the official daily bar close for that session (15:30 IST). It is not the 15:15 IST 5-minute bar.

## 4. Label

The label is not the 2 bp gate.

Let `P0` be the open of the decision session's first stored 5-minute bar. Let `P1` be the daily close of the horizon session. The return is `(P1 - P0) / P0`. If either price is missing, the label is absent. It is not filled.

| Label | Definition |
|---|---|
| L-sign, recommended | 1 when the return is strictly positive. 0 when the return is zero or negative. |
| L-threshold | 1 when the return is strictly greater than a threshold written down before any fit. 0 otherwise. |

No threshold number is proposed. Choosing one now would be arbitrary, and tying it to 2 bp would mix the label with the cost gate. L-threshold stays unavailable until you write the number first.

## 5. Features

Candidates only. The list is not frozen. A feature may be used only if its time is at or before the decision time.

| Candidate | Source | Usable when | Leakage if misused |
|---|---|---|---|
| `hasXbrl` | Announcement row, known at `available_at`, which is before 09:15 on D | Binary 0/1 covariate. It is not the class and it is not target-encoded. | Treating it as the event definition |
| Minute of day of `available_at` | The parsed IST clock | Numeric minutes from midnight. No bins fit from outcomes. | None from later prices |
| Prior 1, 5, and 20 session returns | The symbol's own daily closes with bar end before 09:15 on D. Return k is `close[t] / close[t-k] - 1`, where t is the last completed session before D. | The symbol has at least k+1 such closes. Otherwise the row is dropped. Prices are not filled from another name or from a missing day. | Using the decision session's close or any later close |

Normalized `desc` is the sample filter, not a model input. On an `INCLUDE`-only sample it does not vary, so it cannot be a feature. No text encoding is used.

Excluded, because availability is not established or the field is absent:

- PDF body and any text read from `attchmntFile`
- Financial-results line items, EPS, and restatements
- `period_end`, crawl time, and RSS `retrieved_at`
- `volume_imbalance` and Oil & Gas
- Any price after the decision time, including the horizon close (that is the label)
- The market holdout

## 6. Minimum sample

No announcement count is computed here, so no numeric minimum in row units is set.

Method, to be applied only after you approve the class and the feature list, and only in a later authorized pass:

- The sample is primary `INCLUDE` rows with a present label. `REVIEW_REQUIRED` is out.
- Repeated `seq_id` values stay separate. They are not collapsed.
- Dependence: several announcements can share a symbol and a session. The minimum is judged on clusters, not on raw rows. A cluster is one symbol on one decision session.
- Let `p` be the number of model inputs plus the intercept. Let `r` be 10. The training partition must contain at least `r * p` labeled clusters, and both classes must appear in training and in validation.
- If that bar is missed, the later run is `INCONCLUSIVE`. The class rule and the features are not changed to clear it.

`r = 10` is **PROVISIONAL**. It is a heuristic events-per-variable convention for one logistic regression, not a proof that the fit is adequate. It was not estimated from this tape. Repeated announcements in one symbol-session count as one cluster, so correlation inside the cluster is ignored by the count. Correlation across sessions of the same symbol is also ignored. The bar is on all training clusters, not on the smaller class, so a thin minority class can still pass. No second number is added. Approval still required: say whether 10 applies to all clusters or to the smaller class.

## 7. Scores and the economic gate

Probabilities come from the one logistic regression. No score is calculated here.

Brier score, mean over the validation rows of `(p - y)^2`.

Log loss, mean over the validation rows of `-(y log p + (1 - y) log(1 - p))`, with `p` clipped to `[1e-6, 1 - 1e-6]` before the log. The clip is part of the metric, not a model parameter.

The constant-probability baseline predicts the training positive rate, computed on training labels only, and is used only for Brier score and log loss. It is not the economic always-flat baseline. Economic always-flat takes no trades, so its net contribution on every validation event is zero. Always-long enters every validation event that has `P0` and `P1`. The quant-agent baseline keeps its existing signals. No score was calculated.

### Cutoff

Status: **PROPOSED — NOT APPROVED**. The primary economic rule is `p > training positive rate`, with that rate frozen from training labels before validation. It is a baseline-relative cutoff. It is not claimed to be the economically best threshold. `p > 0.5` is the alternative, not the default. There is no threshold sweep. Brier score and log loss do not use this cutoff.

Under the primary rule, the constant-rate probability equals the cutoff, so `p > rate` is false and that probabilistic baseline does not open a trade. That is the same economic result as always-flat, by construction, and it is still a different object from the scoring baseline.

### Cost formula

Status: **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. Recorded on 2026-10-12. This is not an executed calculation. The hypothesis cost cell now states the same formula. The cost code was not modified and has not been verified against it.

`fee_on` in `costs.py` applies `flat_bps` to each fill notional. `price_trade` in `rebound.py` calls it on the buy and again on the sell, with `CostSchedule.research(cost_bps, 0)`, so slippage is zero.

The approved convention is 2 bp per fill: 2 bp of entry notional and 2 bp of exit notional. At unchanged prices that is about 4 bp round-trip, not one 2 bp round trip.

`gross = (P1 - P0) / P0`

`net = gross - 0.0002 - (P1 / P0) * 0.0002`

The hypothesis cost cell now states 2 bp on the entry fill and 2 bp on the exit fill. Zerodha itemized delivery charges are a different schedule and are not this gate. No return was calculated. Implementation review is still outstanding.

### What the gate reports

On the validation partition, for every eligible event that has `P0` and `P1`:

- Primary acceptance measure: the mean of `net` across all those events. An event that does not meet the cutoff contributes zero. The gate passes only when this mean is strictly positive, and the leakage checks and the sample minimum also pass.
- Diagnostic, not the gate: the mean of `net` across executed trades only, the number of executed trades, and the sum of `net` across executed trades.

Probabilistic scores do not decide this gate.

### Bootstrap

Status: **PROPOSED — NOT APPROVED**. Not run.

- 95 percent percentile interval, from the 2.5 and 97.5 percentiles of the resampled statistic.
- 1000 resamples.
- Seed `20261011`.
- Resample symbols with replacement. All rows of a drawn symbol stay together.
- Intervals for validation Brier score, validation log loss, and the primary mean `net`.

Symbol resampling keeps repeated events on one name together. It does not rebuild a day on which many names move together, and it does not block time. A time-block or two-way resample would be a later design choice, not part of this proposal.

## 8. Window and leakage

Event clock: `available_at` from `2024-01-01T00:00:00+05:30` through `2025-12-31T23:59:59+05:30`.

The earlier written split, training through 2025-06-30 and validation from 2025-07-01, is historical. Under the provisional event class it has no validation events. It is not the current proposal.

Status: **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. Recorded on 2026-10-12 from `h001-split-feasibility.md`, and approved with rule B and H1. The feasibility counts were not recalculated. They remain pre-eligibility history, not labeled sample totals.

- Training: decision session date on or before 2024-06-30. The historical pre-eligibility count is 102 events and 98 symbol-session clusters. Those figures are not eligible labeled totals.
- Validation: decision session date after 2024-06-30, through the last identified provisional-class decision session on 2025-02-14. The historical pre-eligibility count is 149 events and 147 symbol-session clusters. Validation begins in July 2024. Those figures are not eligible labeled totals.
- Purge: a training row whose H1 outcome window ends after 2024-06-30 is in neither partition. A training decision date alone does not prevent that leakage. Validation outcomes must not influence training, feature selection, threshold selection, or model fitting.
- The `10 * p` smaller-class check is approved as a rule and is not evaluated. Labels were not built. The cluster counts do not pass or fail it.

2025Q2–2025Q4 remain uncovered by the provisional class. This split does not fill them. The same symbol can still have one event in training and another in validation. The price path does not cross the cut. The firm effect can. Overlapping horizons on one symbol stay in the score as separate rows and are treated as dependent. They are not dropped and they are not a portfolio rule.
- A label that needs a 2026 session is absent. Partial 2026 candles are not the event test. The market holdout is not a partition.

Duplicates: this freeze has no duplicate `seq_id`. Different `seq_id` values for the same symbol stay as separate events. Revisions are not identified because `old_new` is null, so no row is dropped as a restatement. Overlapping labels are kept for the score and are reported as dependent. This note does not add a one-position portfolio rule.

Missing symbol: TATAMOTORS is excluded. Missing entry bar or missing horizon close: the label is absent.

## 9. Limitations that stay open

This is one NSE pull. There is no BSE `DissemDT` check. Actionability at `exchdisstime` is unverified. Revision chains are unidentified. TATAMOTORS is absent. `HDFCLIFE.raw` and `SBILIFE.raw` are empty arrays. There is no line-item restatement history. PDF bodies are absent. The historical digest is unverified. None of these are cleared by approving the proposals above.

## 10. Approval table

The table is the record of the 2026-10-12 approval. Where an earlier paragraph still lists an open option, this table controls. Approval does not authorize a fit. Execution stays unauthorized.

| Decision | Approved value | Status | Limitation | Approval |
|---|---|---|---|---|
| 1. Event class | Three exact `desc` strings. Integrated filing, board outcomes, press releases, investor presentations, and filename-only matches stay out. `hasXbrl` cannot include a row. Scope A only. Scope B is a separate data project. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | 251 include-list rows are not confirmed eligible. 2025Q2–2025Q4 are uncovered. That is not proof that no results were announced. Completeness is unresolved. | Approved as the class rule. Not an execution approval. |
| 2. Decision time | Rule B. Earliest session whose 09:15 IST is strictly after `available_at`. `P0` is that 09:15–09:20 open. At or after 09:15 waits. A missing bar drops the event. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | Same-session reaction is unused. Proxy clock is not proof of actionability. Feasibility counts were not recalculated. | Approved. Not an execution approval. |
| 3. Horizon | H1. Next session's 15:30 IST close after the decision session. H5 is not a primary result. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | H1 is not the decision day's close. Training rows whose H1 window ends after 2024-06-30 are purged. | Approved. Not an execution approval. |
| 4. Label | L-sign. 1 if `(P1-P0)/P0 > 0`, else 0. Missing price means no label. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | No nonzero threshold. No imputation. | Approved. Not an execution approval. |
| 5. Features | IST minute of `available_at` and prior 1-, 5-, and 20-session returns. `hasXbrl` is not a predictor. Short history is a counted exclusion. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | The 27 short-history events are a feasibility note, not a feature table. | Approved. Not an execution approval. |
| 6. Minimum sample | `p = 5`. Threshold 50 on the smaller label class in each partition. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | Heuristic, not a power guarantee. Class counts are unknown. The rule has not passed or failed. | Approved as the rule. Not evidence it is met. |
| 7. Boundaries | Train on decision sessions on or before 2024-06-30, after the H1 purge. Validate after 2024-06-30 through 2025-02-14. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | 102/98 and 149/147 are pre-eligibility history, not labeled totals. 2025Q2–2025Q4 stay empty. | Approved. Not an execution approval. |
| 8. Overlaps and duplicates | Distinct `seq_id` values stay separate. Overlaps stay in the score. No revision is dropped. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | Rows are dependent. `old_new` is null. | Approved. Not an execution approval. |
| 9. Scores and baselines | Brier score and log loss clipped to `[1e-6, 1-1e-6]` are probability diagnostics. Always-flat is no trade. Always-long is diagnostic, not a pass rule. Training-prevalence baseline is the score baseline. Quant-agent comparison only if a valid causally aligned signal exists. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | No quant-agent comparison is claimed. Scores do not replace the financial gate. | Approved. Not an execution approval. |
| 10. Cost formula | `net = (P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002`. 2 bp per fill. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | Hypothesis wording updated. Cost code not modified and not verified. | Approved. Not an execution approval. |
| 11. Probability cutoff | `p` strictly above the training positive prevalence. No validation tuning. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | Not claimed to be the best economic threshold. No sweep. | Approved. Not an execution approval. |
| 12. Primary gate | Mean `net` over all eligible validation events. A no-trade is zero. Observed mean must be strictly positive, and the lower 95 percent bound must be strictly above zero. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | A pass would not prove a live-tradable edge. Symbol bootstrap may miss common market shocks. | Approved. Not an execution approval. |
| 13. Bootstrap | Symbol clusters, 95 percent percentile interval, 1000 resamples, seed `20261011`. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | Not a market-day interval. Do not replace this method without a new decision. Not run. | Approved. Not an execution approval. |
| 14. Ready | Not met. | UNRESOLVED | Method is approved. Eligible counts, class completeness, implementation match, bootstrap inference, and the historical digest are not. | Do not mark ready. |
| 15. Fit and backtest | A later request is required. | UNRESOLVED | This approval is not that request. | Authorize separately. |
