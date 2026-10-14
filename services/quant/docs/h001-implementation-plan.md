# H001 implementation plan

Planning only. Status stays **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**. `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO are unchanged. This note does not authorize labels, features, a fit, or a backtest.

Source of truth: `h001-protocol-approval.md`, approval table. Where an earlier paragraph in that file still lists an open option, the table controls. Known gaps: `h001-implementation-readiness-audit.md`.

The request that produced this plan ended during feature construction. Components after the short-history exclusion are taken from that approval table so the plan can be reviewed as one document.

## What exists, and what must stay unused

There is no H001 module. Do not turn these neighbors into the experiment:

| Existing code | Why it is not H001 |
|---|---|
| `quant_agents.direction.fit._fit_probabilities` | Fits isotonic regression on validation labels. That uses validation outcomes. |
| `quant_agents.research.rebound.price_trade` and `core_paper.costs.fee_on` | Rupee fees quantized to paise for a different study. Not the approved return identity. |
| `quant_agents.research.delivery_costs` | Itemized delivery charges. A different schedule. |
| `quant_agents.calendar.static_nse` | Weekday and holiday list. Not the research calendar. |
| `quant_agents.ml` and MlAgent | Unloaded. No boosting. Not this model. |
| `core_market_data.replay.open_snapshot` | Refuses `holdout_after_20261005` and windows starting on or after 2026-10-06. Useful refusal. Not an event pipeline. |

Research candles, when a later run is authorized, are `snapshots 2/nifty50/5m/candles.jsonl` (`nifty50_5m_20261005`) and `snapshots 2/nifty50/1d/candles.jsonl` (`nifty50_1d_20261005`). Five-minute bars are UTC. The 09:15–09:20 IST bar starts at `03:45:00Z` and ends at `03:50:00Z`. A daily bar that ends at `10:00:00Z` is the 15:30 IST close. `snapshots/holdout_after_20261005` is never opened, listed, or used. TATAMOTORS has no bars and stays out.

Announcement rows, when a later run is authorized, come from the frozen parquet `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet`. The stable id is `seq_id` with source `nse_corporate_announcements`. `available_at` in that file is the ISO form of `exchdisstime` tagged `Asia/Kolkata`. The implementation re-parses `exchdisstime` and checks the two agree. A mismatch is an exclusion, not a silent choice of one clock.

## Proposed paths

New package, not imported by the paper runner, the quant vote path, or MlAgent:

```
services/quant/src/quant_agents/research/h001/events.py
services/quant/src/quant_agents/research/h001/calendar.py
services/quant/src/quant_agents/research/h001/labels.py
services/quant/src/quant_agents/research/h001/features.py
services/quant/src/quant_agents/research/h001/split.py
services/quant/src/quant_agents/research/h001/net.py
services/quant/src/quant_agents/research/h001/model.py
services/quant/src/quant_agents/research/h001/scores.py
services/quant/tests/unit/test_h001_events.py
services/quant/tests/unit/test_h001_calendar.py
services/quant/tests/unit/test_h001_labels.py
services/quant/tests/unit/test_h001_features.py
services/quant/tests/unit/test_h001_split.py
services/quant/tests/unit/test_h001_net.py
services/quant/tests/unit/test_h001_scores.py
```

`research/__init__.py` stays a docstring. Importing `quant_agents.research` must not load announcements or fit a model. There is no console script until a separate execution authorization exists. Unit tests use synthetic rows and synthetic bars only.

## Component A — Input and event eligibility

`events.py` applies the approved class. It does not broaden it.

Normalization, from `h001-event-class-provisional.md`: missing or non-text `desc` becomes empty; casefold; every character that is not a letter or digit becomes a space; collapse spaces; strip.

Include only an exact normalized `desc` of `financial result updates`, `consolidated result updates ifrs`, or `publish audited results`.

Contradiction check: if attachment text is non-empty and contains `trading window`, `divestment`, or `loss of share`, exclude the row. The check is case-insensitive on the summary text already stored on the row. It does not open a PDF.

`hasXbrl` never includes a row. `integrated filing financial`, board outcomes, press releases, investor presentations, and filename-only matches stay out. Scope B (EPS or revenue surprise) is out.

Clock: parse `exchdisstime` with `%d-%b-%Y %H:%M:%S`, attach `Asia/Kolkata`, and do not convert it to another zone before the comparison. Store both the raw string and the aware timestamp. This is a proxy. It is not proof of first public access or of actionability.

Every row that fails a check is kept in an exclusion log with `seq_id`, symbol, and one reason. Reasons are an enum, including `desc_not_in_class`, `contradiction`, `unparsed_clock`, `clock_mismatch`, `symbol_excluded`, `before_window`, `after_window`, `missing_entry_bar`, `missing_horizon_close`, `short_history`, `missing_daily_history`, `nonpositive_price`, `purged_embargo`. A candidate that passes the class and the clock is not yet an eligible experiment row. Eligible means class, clock, rule B entry, H1 prices, and a complete symbol history on the required prior research-calendar sessions are all present. `short_history` and `missing_daily_history` are different exclusions, defined in Component D. The 251 include-list count and the 3,690 coverage predicate are not eligibility totals. The class remains provisional as a completeness limit: 2025Q2–2025Q4 have no include-list row, which is not proof that no results were announced.

Distinct `seq_id` values stay separate. `old_new` is null, so no row is dropped as a revision. Several rows may share a symbol and a decision session. They stay in the score as dependent rows.

## Component B — Decision calendar and entry

`calendar.py` implements rule B. The research calendar is the union of dates with a daily bar ending at 15:30 IST in `nifty50_1d_20261005`, at `snapshots 2/nifty50/1d/candles.jsonl`. A date qualifies when at least one symbol other than TATAMOTORS has such a bar. This is a snapshot-derived research calendar. It is not a guarantee that the official NSE calendar is complete. If every included symbol is missing a date, that date is absent from the union. Do not use `services/quant/src/quant_agents/calendar/static_nse.py` to fill missing dates. A missing 5-minute bar does not add or remove a date. The holdout is not part of the calendar.

The decision session `D` is the earliest such date whose 09:15:00 IST is strictly after `available_at`.

- An event at 09:14:59 IST on a session date can use that date.
- An event at 09:15:00 IST, or any later time that day including after 15:30, waits for a later session.
- A weekend or a date with no daily bar is not a session. The search moves to the next date that is.

`P0` is the `open` of the event symbol's own 5-minute bar that starts at 09:15:00 IST on `D` and ends at 09:20:00 IST. If that bar is absent, or the symbol's first stored bar that day starts later, the event is excluded. A later bar is not the open. The decision timestamp is 09:15:00 IST on `D`. The open is known then. That bar's high, low, and close are not features and are not `P0`.

`P0` and `P1` are the event symbol's prices. The calendar date can exist because another symbol has a daily bar. If this symbol's designated bar is missing, this event is still excluded. That exclusion is `missing_entry_bar` or `missing_horizon_close`. It does not remove the date from the union.

Tests, all on synthetic calendars, and not implemented by this note: 09:14:59 uses that session; 09:15:00 and 09:15:01 wait; 15:30 and later the same day wait; Saturday and Sunday are skipped; a date with no daily bar is skipped; a present calendar date with no 09:15 bar is an exclusion; a 09:20 or 09:25 bar is not a substitute; two events with the same clock stay two rows; a naive timestamp is rejected; a UTC instant equal to 09:15 IST is treated as 09:15 IST, not as a local wall time. A date with a 15:30 IST daily bar for only one non-TATAMOTORS symbol qualifies as a session. A date missing across all included symbols is absent from the calendar union. `static_nse.py` is not consulted to fill that date.

## Component C — H1 and the label

`labels.py` sets `P1` to the event symbol's official daily close on the first research session strictly after `D`. That close is the 1-day bar that ends at 15:30 IST. It is not the 15:15 IST 5-minute bar and not the close of `D`.

`return_gross = (P1 - P0) / P0` with `Decimal`. `y = 1` only when `return_gross > 0`. Zero and negative map to 0. If `P0` or `P1` is missing, non-numeric, or not strictly positive, there is no label and no imputed price. H5 is not computed as a second primary label. A helper may exist only behind a test that asserts the pipeline's primary label is H1.

Tests: positive return labels 1; negative and exact zero label 0; missing `P0`, missing `P1`, and a next session with no daily close exclude the row; a Tuesday decision uses Wednesday's daily close when Wednesday is the next session, and Friday's decision uses the next session date rather than Saturday.

## Component D — Features

Four predictors, plus the intercept inside the estimator. `p = 5`.

1. IST minutes from midnight of `available_at`, as an integer. No bins fit from outcomes.
2. Prior 1-session return.
3. Prior 5-session return.
4. Prior 20-session return.

For decision session `D`, return `k` is the symbol's own close on the last completed research-calendar session before `D`, divided by its own close `k` research-calendar sessions before that, minus 1. For the 20-session lookback, if the symbol has no daily bar on any of those 20 calendar sessions, exclude the event with `missing_daily_history`. Do not skip the missing date and do not reach further back to substitute an older close. The same exclusion applies when the symbol is missing the last completed session before `D`.

`short_history` is a separate reason. Use it when the research calendar itself contains fewer than 21 sessions before `D` because the tape starts too recently. A missing symbol-specific bar inside an otherwise available calendar window is `missing_daily_history`, not `short_history`. Do not impute, do not borrow another symbol, and do not use the decision session's close or any later close.

Normalized `desc` is the filter, not a feature. Excluded from `X`: `hasXbrl`, attachment and PDF text, future prices, `period_end`, crawl time, `volume_imbalance`, Oil & Gas, and anything from the holdout.

Tests, planned only and not implemented by this note: the minute of 15:53:23 IST is `15 * 60 + 53`; a complete symbol history over the required lookback passes this history check, subject to the other eligibility rules, and does not read the decision-day close; a zero or negative close excludes the row; a column list assertion fails if a forbidden name is added. A missing bar on any of the 20 prior research-calendar sessions excludes the event with `missing_daily_history` and does not use an older close. Fewer than 21 prior calendar sessions at the start of the tape produces `short_history`.

## Component E — Split, purge, and the sample rule

`split.py` assigns partitions only after a row is eligible.

- Training: decision session on or before 2024-06-30, then drop the row if its H1 session date is after 2024-06-30. A purged row is in neither partition.
- Validation: decision session after 2024-06-30 and on or before 2025-02-14.

The historical counts 102/98 and 149/147 are pre-eligibility. They are not acceptance numbers. If an eligible decision session falls after 2025-02-14, the run stops and reports it. It does not extend the approved window and does not fill 2025Q2–2025Q4.

`p = 5` because there are four predictors and an intercept. The bar is 50 eligible rows in the smaller label class, in training and again in validation. Both classes must appear in each partition. The bar is not the total event count and not the cluster count. The earlier paragraph in the approval file that counted all clusters is superseded by the table. Missing the bar yields `INCONCLUSIVE`. The class and the features are not retuned.

Validation labels are not read when choosing features, the cutoff, or the fit. The purge is applied before the fit.

Tests: a decision on 2024-06-28 whose next session is 2024-07-01 is purged; a decision on 2024-06-28 whose next session is 2024-06-28's next date on or before 2024-06-30 stays in training; 2024-07-01 is validation; 2025-02-15 is refused; a partition with a minority class of 49 is inconclusive.

## Component F — Model, cutoff, and net

`model.py` fits one `sklearn.linear_model.LogisticRegression` with `fit_intercept=True`, `random_state=0`, and a fixed `max_iter` large enough for the default solver to converge. No `C` search, no class weight, no scaler, no isotonic step, no boosting. Scaling was not approved. Adding it would be a new decision.

The cutoff is the training positive prevalence, frozen from training labels only. A trade is taken when the predicted probability is strictly greater than that rate. `p > 0.5` is not used. There is no sweep.

`net.py` implements the identity directly. It does not call `price_trade` or `fee_on`.

`gross = (P1 - P0) / P0`

`net = gross - Decimal("0.0002") - (P1 / P0) * Decimal("0.0002")`

Unchanged prices are 4 bp against the trade, not 2 bp. The mean that enters the gate uses every eligible validation row that has `P0` and `P1`. A row that does not clear the cutoff contributes 0. The trade-only mean, the trade count, and the sum of `net` are diagnostics.

Tests: unchanged prices give `-0.0004`; a +1 percent gross gives `0.01 - 0.0002 - 1.01 * 0.0002`; a probability equal to the training rate does not trade; a no-trade changes the all-event mean and not the trade-only diagnostic.

## Component G — Scores, baselines, and bootstrap

`scores.py` reports diagnostics. They do not replace the gate.

- Brier score: mean of `(p - y)^2` on validation rows.
- Log loss: mean of `-(y log p + (1 - y) log(1 - p))` after clipping `p` to `[1e-6, 1 - 1e-6]`. The clip is the metric, not a model parameter.
- Scoring baseline: the constant training positive rate, for Brier score and log loss only.
- Always-flat: no trades, so every validation contribution to economic `net` is 0.
- Always-long: enters every validation row that has `P0` and `P1`. Diagnostic only. Not a pass rule.
- Quant-agent comparison: not wired. Report `not_applicable` unless a later decision names an existing signal that is known at 09:15 IST on `D` and does not use `P1`. Do not invent that alignment in this implementation.

Bootstrap, when a later run is authorized: resample symbols with replacement, keep all of a drawn symbol's validation rows together, 1000 resamples, seed `20261011`, percentile interval at 2.5 and 97.5. Apply it to validation Brier score, validation log loss, and the primary mean `net`. Do not substitute a day block or a two-way resample. The interval does not capture a shock shared across symbols on one day. That limit is reported beside the interval. It is not a reason to change the method.

The primary gate passes only when the observed mean validation `net` is strictly positive and the bootstrap lower bound is strictly above zero, and the leakage checks and the smaller-class bar also pass. A pass would not be a live-tradable edge. This plan does not run the bootstrap.

Tests: a known two-point sample matches hand-computed Brier score and clipped log loss; the seed reproduces the same resample indices on a fixture symbol list; an interval that contains zero fails the gate even if the mean is positive.

## Order of work, after a later authorization to implement

Implementation of code and synthetic tests is a separate request from execution on the frozen tape.

1. Events, calendar, labels, features, split, and `net`, with synthetic tests. No parquet read in those tests.
2. Model and scores, still on synthetic arrays, asserting that validation labels are not an argument to the cutoff or the fit.
3. A reviewer checks that `direction/fit.py` and `price_trade` are not on the import path.
4. Only a further authorization may point the package at the frozen parquet and the two research candle files, write an eligibility exclusion log, and evaluate the smaller class. If either minority class is below 50, stop at `INCONCLUSIVE`.
5. A fit and the gate are a third authorization. They are not implied by steps 1–3.

## Still unresolved after this plan

Class completeness, empty 2025Q2–2025Q4, eligible and smaller-class counts, validation adequacy, the unverified historical digest `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`, actionability beyond the proxy, and the symbol-bootstrap common-shock limit. `NEW_VERIFICATION_BASELINE` is an integrity checksum only. The 3,690-row predicate, the 251 candidates, and eligible observations stay three different counts.

`PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED`

`DATA NOT READY`

`BLOCKED_PRECONDITION`

`READY_TO_RUN = NO`
