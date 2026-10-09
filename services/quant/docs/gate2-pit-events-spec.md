# Gate 2 — PIT earnings/events acquisition spec

Documentation only. No ingestion, training, backtest, or H001 freeze in this task.

```
Market: MARKET_DATA_READY
Events: EVENT_DATA_BLOCKED
H001: BLOCKED_PRECONDITION
READY_TO_RUN: NO
```

H001 `target` / `features` / `horizon` stay **NOT FROZEN** until a dataset exists **and** the timestamp audit below passes.

## Coverage and universe

- Calendar: **2024-01-01 through 2025-12-31** (`available_at` in this window, timezone-aware).
- Universe: the **49** NIFTY50 names that have bars in `nifty50_5m_20261005` / `nifty50_1d_20261005`.
- **TATAMOTORS** is listed with zero bars and is **excluded**. Do not substitute another name.
- Deterministic symbol mapping: normalize incoming tickers to the same strings as the frozen snapshot manifests (strip, uppercase, NSE suffix removal as a documented table). Unmapped rows are **discarded**, not remapped by hand at train time.

Rejected inputs: contract fixtures, RSS `retrieved_at` (wall-clock), `period_end` as availability.

## Required fields

| Field | Rule |
|---|---|
| `symbol` | After mapping, one of the 49 |
| `event_type` | Explicit string (e.g. earnings, guidance) |
| `announced_at` / `published_at` | Timezone-aware |
| `available_at` | Timezone-aware; first time a backtest may observe the row |
| `source` | Non-empty |
| `source_id` | Non-empty; stable within `source` |
| event/value fields | Metric, value, unit, period as applicable |
| revision timestamp / version | Required if the source revises numbers |

Naive datetimes are untrusted. **`period_end` is never `available_at`.**

## Duplicates

Stable key: **`source` + `source_id`**.

Identical keys: keep one row (first in source order). Do not silently merge values.

## Revisions

Later revisions **must not overwrite** what was historically known. Store **versioned rows**. At prediction time `t`, keep the version with the latest `available_at` such that `available_at <= t`. Do not replace an earlier row in place.

## Discard, never fill

Discard (do not impute, midnight-fill, session-open-fill, or LLM-guess) if:

- `available_at` missing, naive, or untrusted
- `available_at` before `announced_at` / `published_at` when both exist
- symbol unmapped
- duplicate of an already-kept `source`+`source_id` (per duplicate rule)

On every **kept** row, H001 must enforce **`available_at <= prediction_time`** deterministically.

## Eventual dataset

Versioned, **immutable**, **gitignored** (under `datasets/`, e.g. `datasets/h001-pit-events-<dataset_version>.parquet` plus a sidecar `*.manifest.json` with SHA256). Do not commit the file. Do not mutate a published version; bump `dataset_version`.

## Pre-H001 audit (required before freeze)

Produce a small report (not alpha metrics):

- total rows in
- discarded rows (by reason)
- symbols covered vs 49
- first / last `available_at`
- duplicate counts
- revision counts

If the audit fails, H001 stays `BLOCKED_PRECONDITION`. Do not freeze. Do not train.

## Sequence after a real file exists

```
approved PIT data arrives
→ timestamp audit passes
→ freeze H001 fields
→ LogisticRegression
→ costed backtest
→ 2 bp gate
→ PASS/FAIL
```

No boosting. No MlAgent. One frozen spec, one run.
