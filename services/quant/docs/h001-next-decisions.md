# H001 next decisions

Preparation only. H001 was not trained or backtested. `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. Methodological choices approved on 2026-10-12 are **USER APPROVED — NOT AUTHORIZED TO EXECUTE**. The record is `h001-protocol-approval.md`. This note does not authorize a fit.

Checked on 2026-10-11 from branch `main` at `ad7557ff9332f943660b058bff401c71983bdd3d`. The extracted tree is `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/`. `datasets/h001-nse-raw-20261010T140237Z/` is absent.

## 1. Historical digest

**Conclusion B. The historical digest cannot be reproduced.**

Recorded value: `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`.

Searched, and not found as a generator:

- This repository, including `retrieval.json`, `fetch_log.json`, `audit_stats.json`, and the NSE, protocol, readiness, and recovery notes.
- `git log --all -S` for that digest and for `sha256_of_named_files`. The digest appears only as a table cell in commit `2d687ff`.
- Sibling folders under `/Users/yashmitkotekar/Coding` (`DataScience`, `abc`, `pbl`), filenames only, depth 2. No H001 producer script.
- The local agent transcript for this project. It quotes the field name. It does not contain the hashing code.

Missing evidence: which files were included, the path spelling, the sort order, and whether the hash covered file bytes, names plus bytes, or something else. Empty financial-results bodies and auxiliary files cannot be included or excluded without that list. No file order was tried.

The parquet digest `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494`, the manifest digest `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a`, and the zip digest `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` are different objects.

## 2. Checksum baseline

The user approved `NEW_VERIFICATION_BASELINE` as an integrity baseline only. A recomputation matched it: 493 files, digest `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2`. An independent run on 2026-10-11 hashed the same extracted tree again, 30,712,811 content bytes, and matched that digest, plus the parquet, manifest, and zip file digests recorded in the recovery audit. `datasets/h001-nse-raw-20261010T140237Z/` is still absent. The baseline is not the historical digest and it does not prove provenance. The historical procedure remains unrecovered, so `b0f4760f…` stays unverified.

- Root: the extracted directory above.
- Files: every regular file whose relative path has no component starting with `.` (this drops `.DS_Store`).
- Order: lexicographic by the UTF-8 bytes of the relative POSIX path.
- Bytes, for each file: UTF-8 path, one `0x00`, the file length as 8 big-endian bytes, then the raw file bytes.
- Algorithm: SHA-256 of that stream.
- Count: 493 files, from `audit_stats.json` through `retrieval.json`.
- Digest: `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2`.

Use this digest for later tamper checks of this tree. It does not replace `b0f4760f…`. The source files were not modified. The event rule in [`h001-event-classification-proposal.md`](h001-event-classification-proposal.md) is `PROPOSED — NOT APPROVED`. Primary inclusion is the exact normalized `desc` values `financial result updates`, `consolidated result updates ifrs`, and `publish audited results`. `integrated filing financial` is `REVIEW_REQUIRED` only. The rule was not counted and was not aimed at 3,690.

## 3. Historical results-like count

**Unverified.** No classifier was found in the same search. `audit_stats.json` stores `results_like_kept` 3690 and no predicate. The 5,844 financial-results rows stay out of the announcement count.

Proposal P1 remains unapproved. It was declared before it was counted: announcement `desc.casefold()` contains `result`, `financial`, or `earnings`, or `hasXbrl` is true. Result: 316 text hits, 3,375 XBRL hits, 1 intersection, union 3,690. Matching the stored number is not evidence that P1 is the original rule.

## 4. Event-class options

No option is selected.

| Option | Eligible events | Evidence | Assumption | Reproduction | Error check | Fit for H001 |
|---|---|---|---|---|---|---|
| 1. Recover the original classifier | Whatever that code kept | The stored count exists. The code does not. | None until the producer is found. | Rerun that code on the freeze. | Compare with 3,690 and inspect disagreements. | Appropriate only if the code is the one that wrote `audit_stats.json`. |
| 2. Approve P1 | Announcement rows whose `desc` hits those three substrings, or `hasXbrl` is true | The sentence in the NSE note, plus the counted union | `desc` is the subject, match is case-insensitive substring, XBRL means `hasXbrl`, and the join is OR | The count in `h001-raw-recovery-audit.md` | Hand-check the six `desc` labels and a sample of `hasXbrl` rows that are not results | A research definition only after approval. The 3,690 match is not a reason to approve it. |
| 3. Write a different rule | To be stated before any count | Not written | Everything in the new text | A script fixed before the count | A labeled sample of included and excluded `desc` values | Possible. It must be written before anyone sees whether it looks profitable. |

False positives for P1 include XBRL filings that are not earnings. False negatives include earnings wording that lives only in `attchmntText`. Those errors are not measured.

## 5. Protocol decision table

The approval table in `h001-protocol-approval.md` controls where this table disagrees. Status **USER APPROVED — NOT AUTHORIZED TO EXECUTE** is not permission to run.

| Item | Documented proposal | Status | Recommended proposal | Why | Approval before training |
|---|---|---|---|---|---|
| 1. Event class | Earnings results disclosures, not every LODR row | PROVISIONAL | The adopted rule is in `h001-event-class-provisional.md`. | The objective is in the hypothesis. This row is not a second rule. | Recorded. Not an execution approval. |
| 2. Classification rule | Three exact `desc` strings include a row. Integrated filings, board outcomes, press releases, investor presentations, and filename-only matches stay out. `hasXbrl` never includes a row. | PROVISIONAL | Use that rule for research design. Do not add subjects from this note. | 2025Q2–2025Q4 have no include-list row. The PDF is absent. | Recorded. Not an execution approval. |
| 3. Decision time | Rule B. 09:15–09:20 open strictly after `available_at`. A missing bar drops the event. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | See the approval table. Do not recalculate the feasibility counts. | The proxy clock is not proof of actionability. | Approved. Not an execution approval. |
| 4. Horizon | H1. Next session's 15:30 IST close. H5 is not primary. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | See the approval table. | A training H1 window that ends after 2024-06-30 is purged. | Approved. Not an execution approval. |
| 5. Label | L-sign. Missing price means no label. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | See the approval table. | The 2 bp gate is not the label. | Approved. Not an execution approval. |
| 6. Features | IST minute and prior 1-, 5-, and 20-session returns. `hasXbrl` is not a predictor. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | See the approval table. | Short history is an exclusion, not a filled value. | Approved. Not an execution approval. |
| 7. Periods | Decision sessions on or before 2024-06-30 train, after the H1 purge. Later sessions through 2025-02-14 validate. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | 102/98 and 149/147 are pre-eligibility history. | 2025Q2–2025Q4 have no include-list row. Cluster counts do not pass or fail the smaller-class rule. | Approved. Not an execution approval. |
| 8. Minimum sample | `p = 5`. Threshold 50 on the smaller label class. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | The rule is approved. The result is unknown. | Labels were not built. This is not a power guarantee. | Approved as the rule. Not evidence it is met. |
| 9. Duplicates | Key is `source` + `source_id`. Zero duplicate `seq_id` in this freeze. | PROVISIONAL | Keep one row per `seq_id`. | That key is documented and the count of extras is zero. | Confirm |
| 10. Overlapping windows | Not written | UNRESOLVED | For a later label study, overlapping labels may exist and must be reported as dependent. Do not add a one-position trading rule here. | Overlap handling changes the sample. | Yes |
| 11. Revisions | Latest row with `available_at` <= t. `old_new` is null on all 18,235 rows. | PROVISIONAL | Do not drop rows for an unseen revision chain. State that restatements are not identified. | There is no chain key. | Confirm |
| 12. Missing symbols and bars | TATAMOTORS excluded. Missing bars are not interpolated. | FROZEN for those two sentences | Keep both. A label that needs a missing future bar is absent, not filled. | Already the data contract. | Confirm |
| 13. Costs | 2 bp on entry notional and 2 bp on exit notional. `net = (P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002`. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | The hypothesis cost cell now says this. Do not apply it from this row. | Cost code was not modified and was not verified. | Approved. Not an execution approval. |
| 14. Baselines | Brier score and clipped log loss are diagnostics. Always-flat is no trade. Always-long is diagnostic, not a pass rule. Quant-agent comparison only if a valid aligned signal exists. | USER APPROVED — NOT AUTHORIZED TO EXECUTE | See the approval table. | No quant-agent comparison is claimed. | Approved. Not an execution approval. |
| 15. Leakage and reproducibility | No feature after the decision. No entry-session close while the event is unavailable. No later revision as a label. No holdout open. Digest unverified means INCONCLUSIVE. | PROVISIONAL | Keep these controls. Add the approved checksum once one exists. | Written in the protocol. The historical digest is still missing. | Confirm |
| 16. Ready | Not met | UNRESOLVED | Method is approved. Eligible counts, implementation match, and bootstrap inference are not. | File presence is not readiness. | Do not mark ready. |
| 17. Authorization | A separate authorization is required | USER APPROVED — NOT AUTHORIZED TO EXECUTE as a refusal to run | Do not train from this note. | Protocol approval is not execution approval. | A later explicit request |

Also frozen, and not reopened: earnings and events as the only source; NIFTY 50 names with bars; one logistic regression; no sweep; no boosting; no MlAgent.

## 6. Point-in-time blockers

| Limitation | Class | Proposal, not implemented |
|---|---|---|
| 18,235 ids match across JSON, raw slices, and parquet | Verified structure | None |
| `exchdisstime` tagged `Asia/Kolkata` matches `available_at` | Verified transform | None. The vendor string has no offset. |
| NSE coverage beyond this pull | Unverified. Hard blocker for a claim of complete history. | Do not re-download in this task. |
| No BSE `DissemDT` check | Unverified. Hard blocker for a second-source clock. | Leave as a documented limit unless a later task fetches BSE. |
| Actionability at `exchdisstime` | Unverified. Hard blocker for "tradable at that second." | A later protocol can wait until the next session open. That choice is item 3. |
| `old_new` null | Verified fact. Revision chains are unidentified. | Item 11. Do not invent links. |
| TATAMOTORS absent | Known coverage limit | Keep the exclusion. |
| `HDFCLIFE.raw` and `SBILIFE.raw` are `[]` | Known limit of the auxiliary results feed. Announcements for those names exist. | Do not fill the results feed from announcements. |
| No line-item restatement panel | Hard blocker for an EPS-revision model | H001, if run later, uses announcement rows, not restated fundamentals. |

## 7. Still required

- The producer file list and byte order if the historical digest `b0f4760f…` must still be reproduced. `NEW_VERIFICATION_BASELINE` is already approved as a different checksum.
- The draft rule is now the provisional class in `h001-event-class-provisional.md`. Option 2, approving P1, was not chosen. The 3,690 audit predicate stays separate.
- Confirmation of the 2024–2025 split.
- A decision time, a horizon, a label, a feature list, a minimum sample, and the scoring-rule formula. Proposals are in `h001-protocol-approval.md`. They are not approved.
- A separate authorization to train or backtest.

## 8. Later readiness review

- [x] `NEW_VERIFICATION_BASELINE` approved as a different checksum and recomputed. The historical digest `b0f4760f…` stays unverified.
- [x] Event rule recorded as provisional in `h001-event-class-provisional.md`. Three exact `desc` strings include a row. Integrated filings and the other named subjects stay out. This is not an execution approval.
- [ ] Decision time, horizon, label, features, and minimum sample written before any fit.
- [ ] Duplicate, overlap, and revision rules confirmed.
- [ ] 2 bp gate unchanged.
- [ ] Holdout still unopened.
- [ ] `READY_TO_RUN` still NO until the authorization in item 17.
