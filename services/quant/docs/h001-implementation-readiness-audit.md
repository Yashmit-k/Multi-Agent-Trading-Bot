# H001 implementation and data-readiness audit

Audit only. The approval table in `h001-protocol-approval.md` is the methodological source of truth. Status: **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. This audit did not run H001, build labels or features, or open the holdout.

`services/quant/docs/current-status.md` is absent. The status file that exists is `docs/current-status.md`.

## 1. Static implementation alignment

No module implements the approved H001 experiment. Searches of Python sources found no event-class filter, no rule B entry, no H1 label, no four-predictor matrix, no training-prevalence cutoff for announcements, no symbol-cluster bootstrap, and no all-event mean-net gate. The items below are therefore **NOT IMPLEMENTED** unless a neighboring function is named. Neighboring functions are not H001.

| Requirement | Class | Where inspected |
|---|---|---|
| `available_at` = `exchdisstime` tagged `Asia/Kolkata`, as a proxy only | NOT IMPLEMENTED as code. Documented as a parse in `h001-protocol-v1.md` and the approval sheet. | No loader applies this clock to a decision. |
| Rule B, 09:15–09:20 open, at-or-after 09:15 waits, missing bar drops | NOT IMPLEMENTED | No function selects that bar. `rebound.py` `lookahead_audit` checks a different 09:15–15:00 signal window (around lines 671–697). |
| H1 next-session 15:30 close; H5 not primary | NOT IMPLEMENTED | No H001 horizon function. |
| L-sign; missing price means no label | NOT IMPLEMENTED | No label function. |
| Four predictors; history before the decision session; short history excluded | NOT IMPLEMENTED | `direction/fit.py` builds a different feature set through `build_feature_set`. |
| `hasXbrl`, PDF text, `period_end`, crawl time, `volume_imbalance`, holdout excluded from the model | NOT IMPLEMENTED as an H001 exclusion list | Holdout refusal exists in market-data replay for snapshots, not as an H001 feature gate. |
| `p = 5`, threshold 50 on the smaller label class | NOT IMPLEMENTED | No sample-size check. |
| Training-prevalence cutoff; validation labels do not tune it | NOT IMPLEMENTED | See the mismatch note on `direction/fit.py` below. |
| Per-fill normalized `net` | NOT IMPLEMENTED as that identity | `fee_on` and `price_trade` are related and are not this gate. |
| Mean `net` over all eligible validation events, no-trade = 0 | NOT IMPLEMENTED | |
| Split at 2024-06-30 and H1 purge | NOT IMPLEMENTED | Counts exist only in the feasibility note. |
| Brier score and log loss clipped to `[1e-6, 1-1e-6]` | NOT IMPLEMENTED for H001 | The same clip appears in other studies. |
| Always-flat, always-long, training-prevalence baseline | NOT IMPLEMENTED for H001 | Direction code scores a training-rate log loss for OHLCV. |
| Quant-agent baseline on the same events | NOT APPLICABLE until a causally aligned signal is wired. None is. | Quant agents do not consume this event class. |
| Symbol bootstrap, 95 percent, 1000 resamples, seed `20261011`, lower bound above zero | NOT IMPLEMENTED | No bootstrap of that design. |

### Neighboring code that must not be treated as alignment

`fee_on` in `services/core/paper-execution/src/core_paper/costs.py` (lines 35–37) charges `abs(notional) * flat_bps / 10000` once per call. `CostSchedule.research` (lines 23–24) stores that bps figure and a slippage figure.

`price_trade` in `services/quant/src/quant_agents/research/rebound.py` (lines 370–421) calls `CostSchedule.research(cost_bps, 0)`, then `fee_on` on the buy notional and again on the sell notional, and quantizes each fee to paise. `return_pct` is `net_pnl / entry_notional * 100`. That is a rupee path for a different study. It is not the approved identity `net = (P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002`. Paise rounding means the two are not the same number. Class: **CANNOT VERIFY WITHOUT EXECUTION** if someone later claims `price_trade(..., 2)` is the H001 gate. For this audit it is **NOT IMPLEMENTED** as H001.

`_fit_probabilities` in `services/quant/src/quant_agents/direction/fit.py` (lines 151–161) fits `LogisticRegression` and then fits `IsotonicRegression` on validation labels. That uses validation outcomes to change probabilities. The file header says it is not wired into MlAgent. It is the closed OHLCV direction study. Class for H001: **MISMATCH FOUND** if reused. It is not an H001 implementation.

`_metrics` in the same file (line 166) and `_score` in `direction/review.py` (line 410) clip probabilities to `[1e-6, 1-1e-6]` and score Brier and log loss against a training rate. The clip matches the approved metric. The surrounding model, features, and validation fit do not. Class: the clip constant is **ALIGNED — STATICALLY VERIFIED** only as a numeric literal in another study. The H001 scoring path is **NOT IMPLEMENTED**.

## 2. Confirmed mismatches

The hypothesis opening still says historical events have no trustworthy `available_at` (`hypothesis-H001.md`, lines 7 and 39). The approval table accepts tagged `exchdisstime` as a proxy and says actionability is not proved. Those sentences disagree. The cost cell was updated; this availability sentence was not.

`h001-protocol-v1.md` line 3 still says the document does not select a target, a feature set, or a horizon. Line 79 still says the label fields are not frozen and the announcement tape is not in this checkout. Later paragraphs in that file point at the approval. The early sentences are stale.

`h001-protocol-decision-review.md` and `h001-event-classification-review.md` still speak as if the method is awaiting approval. They are earlier reviews. The approval table is later.

`alpha-research-report.md` still says target, features, and horizon are not frozen, and that point-in-time events are missing. That report was not updated when the method was approved.

`direction/fit.py` must not be called an H001 fit. Its validation-label calibrator contradicts the approved rule that validation outcomes do not select or adjust the threshold.

## 3. Missing implementation

Everything required to run the approved protocol is missing: event selection, rule B, H1, L-sign, the four predictors, the smaller-class count, the training-prevalence cutoff, the purged split, the per-fill normalized return, the all-event mean, and the symbol bootstrap with seed `20261011`. There is no command that executes H001.

The symbol-only bootstrap cannot be calculated by the current code. Its limitation is already approved: it does not resample a common market day. That limitation is not a reason to substitute another method.

## 4. Data-readiness blockers

From the existing reports, not from a new file scan:

The three-subject class remains the approved rule and is still not a confirmed eligible sample. `h001-event-class-provisional.md` and the approval table both say the 251 include-list rows are candidates. 2025Q2–2025Q4 have no include-list row. That is a coverage limit, not proof that no results were announced.

The 3,690 figure is the coverage predicate `hasXbrl` or a keyword on `desc`. It is not the 251-row class and not an eligible labeled count. Eligible counts, smaller-class counts, and whether validation is large enough are unknown. The `10 * p = 50` rule is approved and unevaluated.

The historical digest `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` stays unverified. `NEW_VERIFICATION_BASELINE` is a different checksum.

The proxy clock’s actionability limit is stated on the approval sheet. It is not stated consistently in the hypothesis opening or in `alpha-research-report.md`.

## 5. Needs a later authorization

Building the eligibility table, labels, features, the purged split counts, the smaller-class counts, and any bootstrap. Checking whether `price_trade` at 2 bp matches the approved formula after paise rounding. Deciding whether a quant-agent signal is causally aligned. Replacing the bootstrap if it cannot support the intended inference. None of that is done here.

## 6. Remediation order

1. Leave execution unauthorized. Do not point H001 at `direction/fit.py`.
2. If a later task is authorized, add a separate H001 path for rule B, H1, L-sign, the four predictors, the purge, and the training-only cutoff.
3. Implement the approved `net` identity explicitly. Do not assume `price_trade` is that identity.
4. Add the symbol bootstrap as specified, and report the common-shock limit. Do not swap the method silently.
5. Only then, under a separate authorization, count eligible rows and the smaller class. If either partition is below 50, stop at inconclusive.
6. Reconcile the stale “not frozen” and “no trustworthy `available_at`” sentences only as documentation, without flipping readiness.

Hard blockers: no H001 implementation, unknown eligible and smaller-class counts, unverified historical digest, and no proof the event class is complete. Disclosed limits that do not by themselves forbid a later preliminary run, once implementation exists and a run is separately authorized: the proxy clock, the empty 2025Q2–2025Q4 window, and symbol-only resampling.

This audit does not declare H001 ready.

`PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED`

`DATA NOT READY`

`BLOCKED_PRECONDITION`

`READY_TO_RUN = NO`
