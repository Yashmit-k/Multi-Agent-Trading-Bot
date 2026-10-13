# H001 Authorization B eligibility audit

Protocol: `H001-2026-10-12` (`h001-protocol-approval.md`).  
Authorization: `h001-authorization-b-grant.md` (`granted_by=user`, `granted_on=2026-10-14`, scope `H001_ELIGIBILITY_AUDIT`).  
Gate: `authorization_b_status` = `AUTHORIZATION_B_PRESENT`.  
Alternative integrity basis: recorded 2026-10-14 (`h001-supervisor-decision-request-verification-basis.md`).  
Holdout accessed: **no**. Model fitted or backtested: **no**.

## Result (2026-10-14) — eligibility-only audit complete

**`AUDIT_COMPLETE_INCONCLUSIVE`.** Training minority class is **34** (bar 50). Validation minority is **70** (pass). The threshold was not lowered. The event class was not widened. This is **not** `DATA_READY`. Execution remains unauthorized. Historical digest `b0f4760f…` remains **UNVERIFIED**. Integrity basis used: recorded alternative (`adda9d82…` + parquet `8ae800ef…`).

Working decision 2026-10-14 (`h001-protocol-amendment-request-minority-sample.md`): **accept inconclusive; do not fit; do not retune.** No 2023 harvest. Protocol text unchanged. Baseline JSON unchanged.

Machine-readable copy: `h001-eligibility-audit-result.json`.

Command:

```
PYTHONPATH=packages/contracts/src;services/quant/src python services/quant/scripts/run_h001_eligibility_audit.py
```

Loader paths (exact; `snapshots/nifty50` and holdout not used):

- `snapshots 2/nifty50/5m/candles.jsonl` (517,606,507 bytes)
- `snapshots 2/nifty50/5m/manifest.json` (`snapshot_id` `nifty50_5m_20261005`)
- `snapshots 2/nifty50/1D/candles.jsonl` (7,019,418 bytes)
- `snapshots 2/nifty50/1D/manifest.json` (`snapshot_id` `nifty50_1d_20261005`)
- Freeze JSON: `datasets/h001-nse-raw-20261010T140237Z/corporate-announcements/*.json`

| Check | Value |
|---|---|
| 5m file SHA-256 | `0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b` match |
| 5m manifest `candle_sha256` | same, match |
| 1d file SHA-256 | `0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d` match |
| 1d manifest `candle_sha256` | same, match |
| Configured root | `snapshots 2/nifty50` |
| Daily 15:30 close bars loaded | 33,565 |
| 09:15–09:20 entry bars loaded | 33,463 |
| Holdout accessed | no |
| Model fitted | no |

| Stage | Count |
|---|---:|
| Input records / unique `seq_id` | 18,235 |
| In approved three-`desc` class | 251 |
| `desc_not_in_class` | 17,984 |
| With P0 (09:15–09:20 open) | 251 |
| Missing P0 | 0 |
| With H1 label (next-session 15:30 close) | 251 |
| Missing P1 | 0 |
| Short history (features) | 27 |
| With features | 224 |
| Purged (H1 after 2024-06-30) | 0 |
| Decision after 2025-02-14 | 0 |
| Eligible labelled train | 75 |
| Eligible labelled validation | 149 |

| Split | n | positive | negative | minority | vs 50 |
|---|---:|---:|---:|---:|---|
| Train (decision ≤ 2024-06-30) | 75 | 34 | 41 | **34** | INCONCLUSIVE |
| Validation (after cutoff through 2025-02-14) | 149 | 70 | 79 | 70 | SATISFIED |

The previously reported training minority of 34 is **confirmed** by this authorized recount. It still fails the approved bar.

Executed at `2026-10-13T20:15:20+00:00`. Protocol `H001-2026-10-12`. `execution_authorized = false`.

## Authorization B

The required statement matched `REQUIRED_AUTHORIZATION_B_STATEMENT` exactly. The grantor identity recorded is `user`, the same role used for the 2026-10-12 protocol approval. No legal name was supplied in the instruction; none was invented. This grant does not authorize fitting or backtesting.

## Approved inputs

| Object | Expected path | Present |
|---|---|---|
| Named freeze | `datasets/h001-nse-raw-20261010T140237Z/` | yes |
| Nested extract | `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/` | no |
| Parquet | `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` | yes |
| Daily candles | `snapshots 2/nifty50/1D/candles.jsonl` (`nifty50_1d_20261005`) | yes |
| Five-minute candles | `snapshots 2/nifty50/5m/candles.jsonl` (`nifty50_5m_20261005`) | yes |
| Holdout | `snapshots/holdout_after_20261005` | not used, not listed, not joined |

Hashing used the named freeze root (the nested extract is absent on this machine).

## Historical digest (required)

Expected (full string from `h001-protocol-approval.md`, not reconstructed):

`b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`

Procedure: SHA-256 of named raw/json files, per the NSE freeze note. `retrieval.json` still does not list filenames, path spelling, or byte order (`retrieval_describes_hash_procedure = false`).

Actual freeze bytes were **not** shown to produce that digest. Status **UNVERIFIED**.

## Supplementary checks (not substitutes)

These were computed after Authorization B was accepted. They do **not** verify `b0f4760f…`.

| Check | Result |
|---|---|
| `NEW_VERIFICATION_BASELINE` procedure on the named freeze (regular files, no hidden path component, POSIX path + NUL + 8-byte big-endian length + file bytes, SHA-256) | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` — **matches** the approved tree tamper-check |
| Parquet file SHA-256 | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` — **matches** the recorded parquet digest |
| Candle manifests / `snapshot_id` | **missing**; `snapshots 2/nifty50` is absent |

`NEW_VERIFICATION_BASELINE` is not treated as the historical digest.

## Eligibility stages

Not run. No input-record count, exclusion histogram, train/validation split, or minority-class count from this authorization.

`run_frozen_eligibility_audit(..., historical_digest_verified=False)` raises `IntegrityVerificationFailed` by design.

## Why this stops

The task requires verifying the actual input against the exact approved historical digest before eligibility counts. That verification cannot be completed: the hashing procedure for `b0f4760f…` is not in the project record, and the measurable tree digest is a different approved checksum. Candle files at the approved research path are also missing, so a later eligibility join would be unreliable even after a digest decision.

## Follow-up, 2026-10-14 (finalize attempt)

Checked only the approved `snapshots 2/nifty50/{5m,1D}` paths. All **absent**. No `snapshots 2.zip`. Copy list: `h001-candle-restore-instructions.md`.

Checked for a written supervisor reply to `h001-supervisor-decision-request-verification-basis.md`. **None.** The request file still contains only the unanswered template. This task is **not** treated as approval. `b0f4760f…` stays **UNVERIFIED**. The alternative basis was **not** adopted.

Eligibility still **not safe to execute**. Two external blockers remain: (1) missing approved candles, (2) missing written verification-basis decision.

## Follow-up investigation, 2026-10-14

See `h001-integrity-procedure-investigation.md`. The original `b0f4760f…` procedure was **not recovered**. Candidate hash orders were not tried. `NEW_VERIFICATION_BASELINE` still matches and is still not substituted. Approved candles remain **absent** (gitignored; not in this checkout; no zip backup found in scanned sibling folders).

The eligibility audit is **not safe to execute**. Supervisor wording for an optional new verification basis is in `h001-supervisor-decision-request-verification-basis.md`. That request is not an approval.

## Recommended next action

1. Supervisor: recover the original file list and byte order that produce `b0f4760f…`, **or** answer the written decision request. Do not silently substitute hashes.
2. Restore `snapshots 2/nifty50` research candles (`nifty50_5m_20261005`, `nifty50_1d_20261005`) from the MARKET_DATA_READY backup and verify `candle_sha256`. Do not use the short `snapshots/nifty50` tape or the holdout.
3. Only then re-run eligibility-only under Authorization B. Do not fit a model.

`DATA NOT READY`. `BLOCKED_PRECONDITION`. `READY_TO_RUN = NO`.
