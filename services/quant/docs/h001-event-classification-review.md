# H001 event-classification review

Review only. This note does not approve a classifier, does not replace `h001-event-classification-proposal.md`, and does not change the counts in `h001-coverage-audit.md` or `h001-coverage-anomaly.md`.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. H001 is not authorized.

`h001-data-readiness.md` still says no historical earnings file is in the repository. That sentence is an earlier inventory. Later notes record the local announcement freeze. The readiness labels stay because the event class, the protocol choices, and execution are still unapproved.

## Evidence

Announcement JSON has `desc`, `attchmntText`, `attchmntFile`, and `hasXbrl`. The Parquet file has `event_type` and `has_xbrl`, not `desc` or `attchmntText`. The coverage audit found `event_type` equal to `desc` on all 18,235 rows. The PDF body is not in the JSON.

`hasXbrl` is a boolean on every row. It is false through `2025-07-17T23:18:35+05:30` and true from `2025-07-18T10:05:43+05:30` on every later row. No day contains both. Before that instant the flag selects nothing. After it, the flag selects every announcement, including trading-window and other non-results subjects. It cannot define a results event in any quarter.

The audit predicate, `hasXbrl` true or `desc` matching `result|financial|earnings`, produced 3,690 qualifying rows. That predicate stays the coverage-audit rule. It is not the proposal below. Its 2025Q3–Q4 totals are mostly the flag after 18 July 2025. Its 2024 totals are mostly one `Financial Result Updates` row per symbol.

Normalized `desc` counts from the announcement JSON, using the proposal's normalization, are:

| Normalized `desc` | 2024Q1 | 2024Q2 | 2024Q3 | 2024Q4 | 2025Q1 | 2025Q2 | 2025Q3 | 2025Q4 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `financial result updates` | 49 | 49 | 49 | 49 | 49 | 0 | 0 | 0 | 245 |
| `consolidated result updates ifrs` | 1 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 4 |
| `publish audited results` | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 2 |
| `integrated filing financial` | 0 | 0 | 0 | 0 | 49 | 0 | 1 | 0 | 50 |
| `clarification financial results` | 0 | 1 | 4 | 1 | 0 | 2 | 0 | 0 | 8 |
| `reply to clarification financial results` | 0 | 1 | 4 | 0 | 1 | 0 | 1 | 0 | 7 |
| `outcome of board meeting` | 55 | 48 | 48 | 45 | 50 | 83 | 86 | 81 | 496 |
| `investor presentation` | 30 | 28 | 33 | 33 | 42 | 55 | 51 | 44 | 316 |
| `press release` | 206 | 199 | 185 | 158 | 138 | 137 | 122 | 108 | 1,253 |

On the three include-list subjects, attachment text was non-empty on all 251 rows, and none contained the contradiction phrases `trading window`, `divestment`, or `loss of share`. Those 251 rows all have `exchdisstime` in 2024Q1 through 2025Q1. Symbols with an include-list `desc` in 2025Q2, 2025Q3, or 2025Q4: 0.

A filename whose final segment contains `financialresult` or `financialresults` occurs on 8 to 16 non-include rows per quarter. In 2025Q2, 5 of those are `outcome of board meeting` and the others are dividend, record-date, or newspaper subjects. The filename does not mark one results row per symbol.

`attchmntText` containing `financial result` on `outcome of board meeting` is 18 rows in 2025Q2, 50 in 2025Q3, and 47 in 2025Q4. That is below one row per symbol in 2025Q2 and is not, by itself, proof that the row is the results print.

## Current proposal

`h001-event-classification-proposal.md` is still **PROPOSED — NOT APPROVED**. It includes a row only when normalized `desc` is exactly `financial result updates`, `consolidated result updates ifrs`, or `publish audited results`, and the contradiction check does not fire. `integrated filing financial` is always `REVIEW_REQUIRED`. `hasXbrl`, attachment text, and attachment filename never include a row. Board outcomes, press releases, investor presentations, and clarifications stay out of `INCLUDE` even when the summary mentions financial results. `REVIEW_REQUIRED` stays out of the primary sample until a later adjudication.

Applied to these records, that include list would admit 251 rows, all before 2025Q2, and none after. The contradiction check would remove none of them. This review measured those subject counts. It did not write `INCLUDE` or `EXCLUDE` onto the dataset.

## Inference

The only subject strings that name a periodic results disclosure and appear once per symbol are `financial result updates` for five quarters and `integrated filing financial` for 2025Q1. The second is a bundle, and the PDF is absent, so treating it as the results print is a guess. Board-meeting, press-release, and investor-presentation subjects are too broad to include automatically: they number in the hundreds each quarter, while the results subject, when it exists, numbers 49.

No field in the JSON distinguishes results announcements in all eight quarters. `desc` does so only while NSE used `Financial Result Updates`. `hasXbrl` does not do so in any quarter. Attachment text and filename can send a minority of other subjects to review. They do not restore a 49-symbol results set in 2025Q2, 2025Q3, or 2025Q4.

## False positives and false negatives

Supported counts only:

- Include-list rows with empty attachment text: 0. The known empty-text false-positive path did not occur.
- Include-list rows caught by the three contradiction phrases: 0. Other mislabeled include-list rows are possible. Their number is not known, because the PDF is absent.
- `integrated filing financial` left out of `INCLUDE`: 50 rows, 49 of them in 2025Q1. These are false negatives only if that bundle is the periodic results print. The JSON does not show that.
- Include-list rows in 2025Q2–2025Q4: 0, across 49 symbols that still have announcements. That is a coverage hole. It is not a counted list of missed results filings.
- Board-meeting summaries containing `financial result`: 18 in 2025Q2, 50 in 2025Q3, 47 in 2025Q4. These are review candidates, not confirmed missed results.

## Recommended rule

Status of this recommendation: **PROPOSED — NOT APPROVED**.

Keep one automatic class. Include a row only when normalized `desc` is exactly one of `financial result updates`, `consolidated result updates ifrs`, or `publish audited results`, and the existing contradiction check does not fire. Ignore `hasXbrl` for inclusion. Keep `integrated filing financial` in `REVIEW_REQUIRED`. Do not include `outcome of board meeting`, `investor presentation`, `press release`, or a keyword match on `desc`. Keep the audit predicate separate, and do not use its 3,690 count as this class.

Under that rule the primary sample has 251 announcement rows, all disseminated in 2024Q1 through 2025Q1. 2025Q2, 2025Q3, and 2025Q4 contribute no primary row. Those quarters stay uncovered. They are not filled from another subject.

## Unresolved

Whether the 50 integrated filings, or the board-meeting rows whose summaries mention financial results, are the missing results prints. That needs an authorized row-level review, or the PDF, which is not in the freeze.

Whether NSE retired `Financial Result Updates` after 2025Q1. The records show the subject count fall to zero. They do not include a taxonomy note.

Protocol items other than this class remain unresolved. Approving a class would still not authorize training or a backtest.

## Decisions required before the class can be frozen

1. Approve the three-subject include list, or write a different list. This note does not approve it.
2. Keep `integrated filing financial` as review-only, or move it into the include list with an explicit reason.
3. Accept that 2025Q2–2025Q4 have no primary row under this rule, or authorize a separate review of named subjects. Do not fill those quarters from `hasXbrl` or from every board-meeting row.
4. Confirm that the audit predicate and the 3,690 count stay out of the event class.
5. Leave H001 unauthorized until a later request. Readiness stays `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO.

Source announcement files, the Parquet file, the manifest, and the ZIP were not modified. Existing audit reports were not overwritten. Nothing was committed.
