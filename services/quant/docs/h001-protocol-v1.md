# H001 protocol v1

Research specification only. H001 has not been trained, backtested, or scored. `DATA NOT READY` and `BLOCKED_PRECONDITION` are unchanged. `READY_TO_RUN` is **NO**. The live method is the approval table in [`h001-protocol-approval.md`](h001-protocol-approval.md): **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**. This file's early "unresolved" list and the 2025-07-01 split are historical. The specification is not implemented. `h001-implementation-readiness-audit.md` records that gap.

## Evidence checked on 2026-10-11

The NSE note [`h001-nse-announcement-audit.md`](h001-nse-announcement-audit.md) names three local paths and one digest. This checkout was checked once:

| Path | Result |
|---|---|
| `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` | absent |
| `datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json` | absent |
| `datasets/h001-nse-raw-20261010T140237Z` | absent |

SHA256 `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` is **unverified**. The note's counts (18,235 announcements, 3,690 results-like rows, 49/49 symbols, zero missing `available_at`) are prior-audit claims. They were not recomputed.

Market candles `nifty50_5m_20261005` and `nifty50_1d_20261005` remain `MARKET_DATA_READY` at `snapshots 2/nifty50`. `snapshots/holdout_after_20261005` was not opened.

## Frozen hypothesis

Taken from [`hypothesis-H001.md`](hypothesis-H001.md). Not changed.

- Information source: earnings and events, one source only.
- Universe: NIFTY 50 names with bars. TATAMOTORS stays excluded.
- Model, when a later task is authorized: one `sklearn.linear_model.LogisticRegression` configuration. No sweep, no boosting, no MlAgent.
- Economic gate, as later approved: 2 bp on the entry fill and 2 bp on the exit fill, `net = (P1 - P0) / P0 - 0.0002 - (P1 / P0) * 0.0002`. The cost code was not modified and has not been checked against that formula. The gate is not applied here.
- Timestamp rule: `period_end`, crawl time, RSS `retrieved_at`, and fixture clocks are not `available_at`. A row is usable only when `available_at` is at or before the prediction timestamp.
- Benchmarks, when a run exists: always-flat and always-long. The existing quant-agent baseline is the third comparison.

The economic claim in the hypothesis is that a newly public earnings or event surprise can change near-term returns. That claim is not a signal definition.

## Unresolved decisions

Historical as of the first draft. None of these alternatives was selected in this section. The approval table later selected rule B, H1, L-sign, four predictors, a smaller-class threshold of 50, and the 2024-06-30 split with an H1 purge. That selection is not an implementation.

- Event class: results-like announcements only, or every LODR announcement on the tape.
- Decision time: the first stored bar whose end is at or after `available_at`, or the next session open when `available_at` is after the cash close.
- Horizon: the next completed session close, or a fixed later session. The entry session's own close is not the label when `available_at` is still inside that session.
- Label: the sign of the forward close-to-close return, or whether that return exceeds a threshold declared before any fit. The 2 bp gate is the economic test, not the label.
- Minimum usable rows: a number must be written down before any fit. This protocol does not set that number, because the tape was not read.

The sentence that target, features, and horizon stay unfrozen applied only to this draft. The approval table is the later specification. It is not built.

## Data contract

From [`gate2-pit-events-spec.md`](gate2-pit-events-spec.md) and the NSE note.

- `available_at` is `exchdisstime` parsed as `Asia/Kolkata`. The vendor string is offset-naive. The raw string is kept as `exchdisstime_raw`. Tagging it as IST is the documented NSE-clock convention. It is not a second timestamp invented from period end or download time.
- Visibility: `available_at <=` prediction timestamp. After-close events wait until the next session. A non-trading day does not create a bar. Missing bars are not interpolated and are not an exit or a label.
- Same-symbol announcements stay separate rows. The duplicate key is `source` + `source_id`. At time `t`, a revision is the latest version with `available_at <= t`. An older version is not overwritten.
- The raw freeze, when present, is immutable. A derived table is a new versioned file. This checkout does not contain either file.

## Evaluation protocol

Specified before any model. Not executed.

- Event window: `available_at` from 2024-01-01 through 2025-12-31, timezone-aware.
- Chronological split in this draft: through 2025-06-30, then 2025-07-01 through 2025-12-31. That split is historical. The approved split trains on decision sessions on or before 2024-06-30 and validates after that date, through 2025-02-14, and purges a training row whose H1 window ends after 2024-06-30. Partial 2026 candles are not an event test set. The market holdout is not a test period.
- Leakage controls required before a later run: no feature timestamp after the decision; no use of the entry session close when the event is not yet available; no label from a revision with `available_at` after the decision; no open of `snapshots/holdout_after_20261005`.
- Metrics, when a run exists: Brier score and log loss with probabilities clipped to `[1e-6, 1-1e-6]`, plus the approved per-fill net. The acceptance gate is a strictly positive mean net over all eligible validation events, with a no-trade as zero, and a 95 percent symbol-bootstrap lower bound strictly above zero. Those scores are not implemented.
- `PASS`: leakage checks pass, the smaller label class has at least 50 eligible observations in each partition, and that financial gate passes. This draft does not compute that pass.
- `FAIL`: a completed run that misses that gate.
- `INCONCLUSIVE`: the tape or manifest is missing, the digest is unverified, a leakage check fails, or the usable count is below the predeclared minimum or was never computed.

Announcement-file presence, even if later confirmed, does not by itself meet the sample-size rule.

## Future command

Do not run this until a separate authorization exists and the three paths above are present with a verified digest.

```
python -m pytest packages/contracts/tests/test_export.py -q --tb=line
```

No H001 training or backtest command is authorized by this protocol.

## Readiness

H001 is **not** ready for a separately authorized experiment. The method is approved and not implemented. Eligible counts are unknown. The sentence that the announcement tape is absent described the first check in this file. Later sections record the files. The named directory `datasets/h001-nse-raw-20261010T140237Z` is still absent.

## Verification record, 2026-10-11

The earlier "absent" check in this file is unchanged. A later read of the same checkout found three files. None was renamed, rewritten, or extracted.

| File | Bytes | SHA256 |
|---|---:|---|
| `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` | 1625375 | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` |
| `datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json` | 501 | `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a` |
| `datasets/h001-nse-ann-2024-2025-v1.zip` | 4655549 | `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` |

The on-disk directory `datasets/h001-nse-raw-20261010T140237Z` is still absent. It was not recreated.

The manifest records `dataset_version` `nse-ann-2024-2025-v1`, `schema_version` `1.0`, `source` `nse_corporate_announcements`, `source_version` `h001-nse-raw-20261010T140237Z`, `row_count` 18235, `symbol_count` 49, `first_available_at` `2024-01-01T09:04:57+05:30`, `last_available_at` `2025-12-31T22:09:34+05:30`, and `available_at_field` `exchdisstime interpreted as Asia/Kolkata`. Those row, symbol, and timestamp fields match the parquet recomputation below. The manifest does not name the parquet or the zip, and it does not record their sizes or digests.

The manifest field `SHA256` is `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`. That is the raw/json digest in the NSE note, not a parquet digest. The same string is stored in the zip member `h001-nse-raw-20261010T140237Z/retrieval.json` as `sha256_of_named_files`. The note and that JSON do not state which names or which order produce the digest, so the raw/json bytes were not rehashed. The raw digest stays **unverified**. The parquet digest above is a different value. It was not compared with `b0f4760f…` as if the two hashes named the same object. The zip copies of the parquet and the manifest match the loose files byte for byte. That match is not a manifest entry.

`unzip -l` lists 495 members. The internal root `h001-nse-raw-20261010T140237Z/` contains 392 `corporate-announcements/*.raw` slices, 49 per-symbol `corporate-announcements/*.json` files, 49 auxiliary `financial-results/*.raw` files, and `audit_stats.json`, `fetch_log.json`, and `retrieval.json`. `HDFCLIFE.raw` and `SBILIFE.raw` are 2 bytes each. The parquet and the manifest are also members at the archive root. That listing matches the documented raw-freeze layout and also includes the auxiliary results files and the two derived files. The archive was not extracted, so this listing is not an on-disk recovery of the raw directory, and the published raw digest was not recomputed.

Parquet schema: `symbol`, `event_type`, `announced_at`, `published_at`, `available_at`, `source`, `source_id`, `period_end`, `has_xbrl`, `sm_isin`, `attachment_url`, `exchdisstime_raw`, `an_dt_raw`.

| Check | Result | Label |
|---|---|---|
| Rows | 18235 | verified |
| Unique symbols | 49, each with at least one row; TATAMOTORS absent | verified |
| Missing `available_at` | 0 | verified |
| Duplicate `source` + `source_id` | 0 | verified |
| `available_at` range | `2024-01-01T09:04:57+05:30` through `2025-12-31T22:09:34+05:30` | verified |
| `available_at` versus `exchdisstime_raw` | 18235 raw strings are offset-naive `DD-Mon-YYYY HH:MM:SS`. Tagging each as `Asia/Kolkata` reproduces `available_at` on every row. Raw values were not rewritten. | verified |
| `period_end` | null on all 18235 rows | verified |
| Results-like rows | audit claim 3690 | unverified |

The results-like claim stays unverified. The audit sentence is subjects matching `result`, `financial`, or `earnings`, or an XBRL flag. The parquet has `event_type` and `has_xbrl`. It does not contain the subject text, and it does not name the column, case rule, or flag field that produced 3690. `has_xbrl` is true on 3375 rows. That figure was not used as the results-like count.

A later stream read, without extracting the zip, opened only `retrieval.json`, `audit_stats.json`, and `fetch_log.json`. `retrieval.json` stores `sha256_of_named_files` and does not list the hashed filenames or their order. `fetch_log.json` has keys `calls`, `finished_at`, `started_at`, and `symbols`, and contains no digest, file list, or results-like rule. `audit_stats.json` stores `results_like_kept` 3690 and does not record the subject field, the match rule, or the XBRL flag field that produced it. The missing evidence for the raw digest is that filename list and that order. The 3690 figure stays an unverified prior-audit claim. No candidate ordering was hashed. The parquet, manifest, and zip digests above were not recomputed in this read.

## Extracted-tree audit, 2026-10-11

The path `datasets/h001-nse-raw-20261010T140237Z` is still absent. An extracted tree is at `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z`. The full note is [`h001-raw-recovery-audit.md`](h001-raw-recovery-audit.md).

493 extracted files match the zip members of the same relative path in size and SHA256. The only extra file is `.DS_Store`. The on-disk `retrieval.json`, `fetch_log.json`, and `audit_stats.json` still omit the hashed filenames and their order, so `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` stays unverified. No candidate order was hashed.

Announcement JSON and announcement `.raw` slices each contain 18,235 rows, one shared schema, and zero duplicate `seq_id` values. All 18,235 `seq_id` values match parquet `source_id`, with zero symbol mismatches and zero mismatches between `exchdisstime` tagged `Asia/Kolkata` and `available_at`. `desc` is present on every announcement row. `hasXbrl` is true on 3,375 rows. The note still does not name the subject field, match type, or case rule, so 3,690 stays unverified.

A search of this repository and of `git log --all` found the digest only as a written table cell in commit `2d687ff`. No generator for `sha256_of_named_files` or for `results_like_kept` is in the history. The raw digest stays unverified. Proposal P1 in [`h001-raw-recovery-audit.md`](h001-raw-recovery-audit.md) is one reading of the NSE sentence, counted after it was written down: 316 `desc` hits, 3,375 `hasXbrl` hits, 1 intersection, union 3,690. That equality is not approval of P1 and is not recovery of the original classifier. P1 is not frozen.

[`h001-next-decisions.md`](h001-next-decisions.md) records a wider search that still found no producer. The user approved `NEW_VERIFICATION_BASELINE` for integrity checks only. A recomputation on the extracted tree hashed 493 files to `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2`, which matches that specification. An independent run on 2026-10-11 matched it again, along with the parquet, manifest, and zip file digests. The named directory `datasets/h001-nse-raw-20261010T140237Z/` is still absent. The baseline is not `b0f4760f…`, and that historical procedure is still unrecovered. [`h001-event-classification-proposal.md`](h001-event-classification-proposal.md) is the design draft. [`h001-event-class-provisional.md`](h001-event-class-provisional.md) records the provisional class: three exact normalized `desc` values, contradiction check kept, `hasXbrl` not an inclusion rule. The identified sample is 251 rows in 2024Q1–2025Q1. 2025Q2–2025Q4 are uncovered. The 3,690 audit predicate is not this class. On 2026-10-12 the user approved the method in [`h001-protocol-approval.md`](h001-protocol-approval.md) as **PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED**. That approval does not count eligible labels.

`DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = **NO** stay. The method is approved and execution is not. H001 was not trained or backtested. Snapshots and `snapshots/holdout_after_20261005` were not opened. Nothing was committed.
