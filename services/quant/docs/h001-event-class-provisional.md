# H001 provisional event class

Status: **PROVISIONAL**. Recorded from an explicit decision on 2026-10-11. This is a research-design rule. It is not approval to train, label, or backtest. It does not change `DATA NOT READY`, `BLOCKED_PRECONDITION`, or `READY_TO_RUN` = NO.

The design draft remains `h001-event-classification-proposal.md`. The measurements remain in `h001-event-classification-review.md`. Those files, `h001-coverage-audit.md`, and `h001-coverage-anomaly.md` are unchanged by this decision.

## Rule

Normalize `desc` as in the proposal: missing or non-text becomes empty; casefold; replace every non-letter and non-digit with a space; collapse spaces and strip.

Include a row only when that normalized `desc` is exactly one of:

- `financial result updates`
- `consolidated result updates ifrs`
- `publish audited results`

Exclude the row from the automatic class when the existing contradiction check fires: non-empty attachment text contains `trading window`, `divestment`, or `loss of share`.

`hasXbrl` is not an inclusion criterion.

`integrated filing financial`, board-meeting outcomes, press releases, investor presentations, and filename-only matches stay outside the automatic class. They can be reviewed only under a later, separate authorization. They are not included by this decision.

## Rationale

These three subjects are the only `desc` values that name a periodic results disclosure and, for `financial result updates`, appear once per symbol across 2024Q1–2025Q1. `hasXbrl` is false on every row through 17 July 2025 and true on every row from 18 July 2025, so it cannot separate results from other filings. Broader subjects number in the hundreds per quarter and are not the results print by name.

## Sample and coverage

The review counted 251 rows whose normalized `desc` is on this include list. All of them have `exchdisstime` in 2024Q1 through 2025Q1. None of those 251 rows had empty attachment text, and none fired the contradiction check. This decision does not reclassify the tape and does not write labels.

2025Q2, 2025Q3, and 2025Q4 have no row on the include list. That means those quarters are uncovered by this definition. It is not proof that no earnings results were announced. The JSON has no PDF body, and other subjects were not promoted into the class.

## What stays separate

The coverage-audit predicate is `hasXbrl` true or `desc` matching `result|financial|earnings`. That predicate produced 3,690 rows. It is not this event class. The 3,690 figure is not the provisional sample.

## Still unresolved

These gates are not decided by this note. Each remains a proposal in `h001-protocol-approval.md`.

| Gate | Current proposal | Still open |
|---|---|---|
| Clock and entry | Decision time B: the earliest research-calendar session whose 09:15 IST is strictly after `available_at`. Entry is the open of that 09:15–09:20 bar only. | B or A. A missing opening bar drops the event. |
| Horizon | H1, the 15:30 IST close of the next calendar session after the decision session. | H1 or H5. |
| Target | L-sign: 1 when `(P1-P0)/P0 > 0`, else 0. | L-sign, or a numeric threshold written before any fit. |
| Features | `hasXbrl` as a covariate, IST minute of `available_at`, and the symbol's prior 1, 5, and 20 session returns. `desc` is the filter, not a feature. | Approve or cut the list. |
| Sample size | At least `10 * p` labeled training clusters, `p` including the intercept. A cluster is one symbol on one decision session. | All clusters, or the smaller class. |
| Date split | Training only when both the decision date and the horizon date are on or before 2025-06-30. Validation decisions start 2025-07-01. | Confirm or replace. Under this class, 2025Q2–2025Q4 have no primary row, so a validation window that starts in July 2025 has no include-list events until the split is reconsidered. |
| Cost | `net = (P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002`, zero slippage. | The hypothesis still says only "after 2 bp". The per-side formula is not approved. |
| Validation | Brier score and log loss clipped to `[1e-6, 1-1e-6]`. Cutoff `p` above the training positive rate. Primary gate: mean net over all eligible validation events, with a no-trade as zero. Bootstrap: 95 percent, 1000 resamples, seed `20261011`, by symbol. | Each of those choices. |

Overlaps, duplicate `seq_id` handling, and the scoring-baseline split are also still proposals. Execution of H001 is not authorized.
