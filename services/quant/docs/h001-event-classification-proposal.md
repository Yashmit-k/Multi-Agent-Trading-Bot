# H001 event-classification proposal

Status: **PROPOSED — NOT APPROVED**. Writing it down does not approve it. It has not been applied to the announcement rows. No class count, distribution, or sample size is reported here.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay. Do not count records under this rule until it is reviewed and approved in a separate step.

## 1. Research objective

H001 asks whether eligible earnings-related corporate announcements for the covered NIFTY 50 names contain predictive information that can be judged with the written validation protocol and the 2 bp gate. The source is earnings and events, one source only. The population is not every LODR filing on the tape. The stored claim of 3,690 results-like rows is not the definition of that population.

## 2. Proposed event class

An eligible event is a corporate announcement whose job is to disclose the company's own periodic financial results or the financial statements that go with that disclosure. Periodic means quarterly, half-yearly, or annual. A filing that mentions finance, a filing that carries an XBRL flag, and a filing that discusses results without being the results disclosure are outside this class until a later review says otherwise.

## 3. Field inventory

Announcement JSON and announcement `.raw` slices share one schema. These fields are present on the rows inspected as examples:

| Field | Role in this proposal |
|---|---|
| `desc` | NSE subject category. This is the only field that can **include** a row. |
| `attchmntText` | Short exchange summary. It can send a row to review. It cannot include a row by itself. |
| `attchmntFile` | URL of the attachment. The final path segment can send a row to review. It cannot include a row by itself. |
| `hasXbrl` | Boolean. Recorded as a supporting attribute. It is not a definition of earnings, and it cannot include a row. |
| `symbol` | Issuer. Not part of the event class. |
| `seq_id` | Announcement id. Identity for duplicates. Not part of the class test. |
| `exchdisstime` | Dissemination clock. Used only in a later stage. |

One results example: `desc` `Financial Result Updates`, `hasXbrl` false, `attchmntText` stating that the company submitted financial results for a period ended. One non-results example: `desc` `Updates`, attachment text about a divestment. One XBRL example that is not results: `desc` `Trading Window`, `hasXbrl` true, text about a trading-window closure.

The parquet does not have `desc` or `attchmntText`. It has `event_type`, `attachment_url`, and `has_xbrl`. This proposal is defined on the announcement JSON and `.raw` fields. Using `event_type` as if it were `desc` is provisional until that equality is checked. That check is not part of this note. The financial-results files use a different schema and are not announcement rows.

## 4. Inclusion

Normalize text before any compare:

- Missing or non-text becomes empty.
- Casefold.
- Replace every character that is not a letter or digit with a space.
- Collapse repeated spaces and strip the ends.

`INCLUDE` only when normalized `desc` is exactly one of:

- `financial result updates`
- `consolidated result updates ifrs`
- `publish audited results`

and the contradiction check below does not fire.

`integrated filing financial` is not on this list. That NSE category is a bundled financial filing. The name does not say the document is only the periodic results print, and the PDF body is not in the JSON. It is `REVIEW_REQUIRED` in every case.

`hasXbrl` never includes a row. `attchmntText` and `attchmntFile` never include a row by themselves. Matching is exact on the normalized `desc` string. It is not a substring search.

## 5. Exclusion

`EXCLUDE` when `desc` is non-empty, its normalized form is not in the include list, and none of the review triggers in the next section fire.

That covers filings whose category is something else, including a true `hasXbrl` on a non-results category such as a trading-window notice. The XBRL flag stays on the row as an attribute. It does not move the row into the event class.

## 6. Ambiguity and missing text

Apply the first matching outcome:

1. `desc` empty: `REVIEW_REQUIRED`.
2. Normalized `desc` is `integrated filing financial`: `REVIEW_REQUIRED`.
3. Normalized `desc` is on the include list, and normalized `attchmntText` is non-empty and contains `trading window`, `divestment`, or `loss of share`, and does not contain `financial result`: `REVIEW_REQUIRED`. The same review outcome applies when the text contains both `financial result` and one of those three phrases.
4. Normalized `desc` is on the include list and step 3 did not fire: `INCLUDE`.
5. Normalized `desc` is `updates`, `general updates`, `press release`, `press release revised`, `outcome of board meeting`, `investor presentation`, `clarification financial results`, or `reply to clarification financial results`, and normalized `attchmntText` contains `financial result`: `REVIEW_REQUIRED`.
6. Normalized `desc` is not on the include list, and the final path segment of `attchmntFile`, after the same normalization, contains `financialresult` or `financialresults`: `REVIEW_REQUIRED`. A filename is not the PDF body. It cannot include a row.
7. Otherwise: `EXCLUDE`.

An include-list `desc` with empty attachment text stays `INCLUDE`. There is no PDF text to contradict it. That is a known limit, not a second guess.

A clarification, a board-meeting outcome, a press release, or a generic update is not `INCLUDE`, even when the words "financial results" appear. Those rows wait for a later adjudication.

`REVIEW_REQUIRED` rows are out of the primary sample until that adjudication is separately authorized. They are not relabeled by this note.

Duplicate and repeated disclosures stay separate rows. The later key is `source` + `source_id` (`seq_id` on the raw row). This rule does not merge them and does not drop a second disclosure.

## 7. Expected false positives

A row stays in the primary class when `desc` is one of the three include strings and the attachment summary is empty or does not contradict it. A mislabeled `desc` with empty text would be kept. The contradiction phrases catch only `trading window`, `divestment`, and `loss of share`. Other wrong attachments can still pass. `integrated filing financial` is not in the primary class, so a bundled filing is not counted as the earnings print. Keyword search on `desc` is not used. `hasXbrl` is not used, so a trading-window or governance XBRL filing is not included on that flag.

## 8. Expected false negatives

A genuine results print filed as `integrated filing financial` is not in the primary class. It waits in `REVIEW_REQUIRED` because the JSON cannot show that the bundle is only the results. Board outcomes, press releases, and generic updates are also outside `INCLUDE` even when they mention results. Company-specific wording that never uses the three include strings is missed. The PDF at `attchmntFile` is not in the dataset, so a results disclosure that exists only inside that file cannot be recovered. Empty attachment text cannot be used to discover those misses.

## 9. Dataset limitations

The vendor clock has no offset. `old_new` does not identify revisions. TATAMOTORS has no bars. `HDFCLIFE` and `SBILIFE` financial-results bodies are empty arrays; their announcements are a different feed. There is no BSE clock cross-check and no restated line-item panel. None of those limits change the event class. They belong to later stages.

## 10. How this differs from P1

P1 included a row when `desc` contained `result`, `financial`, or `earnings`, or when `hasXbrl` was true. This proposal does not. Exact normalized `desc` categories include a row. `hasXbrl` never includes a row. Keyword hits in attachment text only request review.

## 11. Why 3,690 is not the design target

The include list is the set of subject categories that name a periodic results disclosure. It was not chosen by searching for a rule that totals 3,690. The historical `results_like_kept` value stays an unverified prior claim. P1's union of 3,690 stays an unapproved coincidence. This note does not report a count under the new rule.

## 12. Approval still required

Do not apply this rule, and do not count `INCLUDE`, `EXCLUDE`, or `REVIEW_REQUIRED`, until a separate review approves the list. Approval of the checksum baseline below is not approval of this classifier.

## 13. Stages that stay separate

1. Event class: this proposal.
2. Point-in-time eligibility: `exchdisstime` tagged `Asia/Kolkata`, and a decision time that is still unresolved.
3. Symbol and bars: NIFTY 50 names with bars, TATAMOTORS excluded, missing bars not filled.
4. Label and window: horizon and label are still unresolved.

A row can be `INCLUDE` and still be unusable in a later backtest because the clock, the symbol, or the future bar fails. Those failures do not change the event class.
