# H001 Authorization B eligibility audit — prepared, not executed

Status: Authorization B eligibility audit **completed**. Result **`AUDIT_COMPLETE_INCONCLUSIVE`**: training minority **34** < 50; validation minority 70. Working decision: **accept inconclusive; do not fit.** Historical digest `b0f4760f…` remains **UNVERIFIED**. Alternative basis used. Not `DATA_READY`. See `h001-authorization-b-audit.md`.

The previously reported training minority count of 34 is **UNVERIFIED** until an authorized recount. Historical digest `b0f4760f…` remains **UNVERIFIED**. Presence of raw freeze files or passing synthetic tests is not `DATA_READY`.

## What exists now

`quant_agents.research.h001` classifies caller-supplied rows, applies Rule B, builds H1 labels and the four approved predictors plus intercept, splits at 2024-06-30 / 2025-02-14 with H1 purge, and checks the minority bar of 50. Modules still open no files.

This preparation adds:

- `authorization.py`: fail-closed Authorization B gate. Absent, malformed, or wrong wording stays `AUTHORIZATION_PENDING`. Holdout paths are refused even if a token is present. Named freeze paths are not read.
- `eligibility.py`: deterministic staged eligibility audit on **in-memory** rows and bars. Synthetic origin cannot report production `DATA_READY`. The frozen-tape entry point requires Authorization B and still does not execute on this checkout.

## Status meanings (kept separate)

| Status | Meaning |
|---|---|
| `AUTHORIZATION_PENDING` | Written Authorization B is absent. |
| `AUDIT_COMPLETE_INCONCLUSIVE` | An authorized freeze audit finished and at least one split missed the 50-observation minority bar. |
| `DATA_READY` | Authorized freeze audit: minority ≥ 50 in **both** train and validation. Not execution authorization. |
| `SYNTHETIC_FIXTURE_NOT_PRODUCTION` | Synthetic audit only. Never production `DATA_READY`. |
| Execution authorization | Separate from B. Required before any fit or backtest. |

An authorized audit that confirmed 34 training minority observations would remain `AUDIT_COMPLETE_INCONCLUSIVE`. The threshold is not lowered. The event class is not widened.

## Exact Authorization B wording required

The authorized quant/research supervisor must issue **this statement verbatim**, plus grantor name and date, as `AuthorizationB.statement`:

```
AUTHORIZATION B GRANTED: run the H001 eligibility-only audit on the frozen Scope A announcement tape identified in services/quant/docs/h001-protocol-approval.md (protocol dated 2026-10-12). Do not access snapshots/holdout_after_20261005. Do not fit, backtest, optimize, or evaluate an H001 model. Do not change the approved event class, features, split, minority threshold, or label definitions.
```

Anything else, including a paraphrase, remains `AUTHORIZATION_PENDING`.

After that grant, a follow-up may supply freeze rows **in memory** to the audit. This package still must not open the holdout. Integrity stays `UNVERIFIED` until the approved digest is checked against the actual input bytes. Model fit remains unauthorized.

## Audit report fields (generated only after B on freeze rows)

- Protocol version/id (`H001-2026-10-12`) and protocol status
- Snapshot identifiers and integrity-verification status (`UNVERIFIED` unless the exact approved digest is verified against those bytes)
- Input records and unique event identifiers
- Counts after classification, P0 entry, H1 label, features, and split
- Exclusion counts by `ExclusionReason`
- Eligible labelled train/validation counts, positive/negative, minority vs 50
- Readiness decision and reason
- `execution_authorized = false`
- Reproducibility metadata and UTC execution timestamp

Raw event text is not written into the report.

## Not done

- Frozen parquet / announcement JSON were not read.
- `snapshots/holdout_after_20261005` was not accessed.
- No real labels or eligibility counts.
- No model fit or backtest.
- Protocol, event class, features, split, and minority bar are unchanged.
