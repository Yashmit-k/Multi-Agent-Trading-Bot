# H001 data readiness

H001 has not been run. This note does not train a model, freeze a target, freeze features, freeze a horizon, or run an H001 backtest.

**Decision: DATA NOT READY**

## 1. Objective

Determine whether this repository can build historical earnings and events with an `available_at` that is the time the information was actually public. That property is required before any H001 label or model.

## 2. Candidate data sources

Only sources already in the repository were inspected. Nothing was downloaded.

| Source | What it is |
|---|---|
| `packages/contracts/src/contracts/fixtures.py` | Hand-written EPS rows and news headlines for fixture symbols |
| Intelligence news fixtures | The same fixture articles, with `published_at` and `retrieved_at` |
| `services/intelligence/src/intelligence_agents/fundamentals/csv_loader.py` | A CSV loader that can store `available_at` |

No NSE or vendor point-in-time feed is wired. No NIFTY50 historical earnings file is in the tree.

## 3. Available fields

Fixture fundamentals have `symbol`, `metric`, `value`, `period`, `announced_at`, `available_at`, `source` (`fixture-filings`), and `source_id`. One example is RELIANCE EPS 48.25 for `FY2024`, announced `2024-04-20T10:00:00Z`, available `2024-04-20T12:00:00Z`. `metadata.fixture` is true.

News fixtures have `published_at` and `retrieved_at` (five minutes after publication in the fixture builder). They do not carry an earnings `available_at`.

The CSV loader reads `symbol`, `metric`, `value`, `period`, `announced_at`, `available_at`, and `source_id`. Its module comment says this path is never used in `BACKTEST`.

## 4. Timestamp semantics

These clocks are not interchangeable.

| Field | What it means here |
|---|---|
| `period` / period end | The accounting period label on a fixture row, such as `FY2024`. Not a publication time. |
| `announced_at` | A hand-written fixture timestamp. |
| `published_at` | A hand-written fixture headline time. |
| `retrieved_at` | Fixture publication plus five minutes. It is not a historical market clock. |
| `available_at` | On fixtures, announced time plus two hours, also hand-written. |

`available_at` must be the time a backtest is allowed to see the row because the information was public. The fixture offset does not establish that rule for a production source.

## 5. Point-in-time availability analysis

The contract rejects `available_at` before `announced_at`, and stores can hide rows with `available_at` after `as_of`. That is a filter. It does not create a historical public timestamp.

Fixture `available_at` values are authored next to `announced_at`. `metadata.fixture` is true. They are not evidence of when the market learned an earnings number.

RSS or retrieval time is not used as `available_at`. `period` is not used as `available_at`.

## 6. Coverage analysis

Fixtures cover a handful of demonstration symbols and a few periods around 2024. They do not cover the 49 symbols that have bars in `nifty50_5m_20261005` and `nifty50_1d_20261005` from 2024-01-01 through 2025-12-31. `TATAMOTORS` has zero bars and is not given a substitute name.

## 7. Historical revision analysis

Fixture rows are single versions. Nothing in the repo stores a later revision without overwriting the earlier public value. There is no as-of reconstruction of revised earnings.

## 8. Example records

RELIANCE fixture EPS: period `FY2024`, announced `2024-04-20T10:00:00Z`, available `2024-04-20T12:00:00Z`, source `fixture-filings`, `metadata.fixture` true.

RELIANCE fixture headline `news-reliance-20240603`: `published_at` `2024-06-03T04:00:00Z`, `retrieved_at` five minutes later, `metadata.fixture` true.

## 9. Problems and limitations

- The only `available_at` values in code are fixture clocks.
- News fixtures have publication and retrieval times, not an earnings availability time.
- The CSV loader can persist `available_at` and is explicitly not the backtest path. No historical CSV is present.
- No source here supports revisions that stay point-in-time.
- License, API cost, and vendor retention cannot be assessed because no vendor feed is connected.

## 10. Final decision

**DATA NOT READY**

## 11. Exact blocker

There is no historical earnings or events file in this repository whose `available_at` can be trusted as the time the information was actually public.

## 12. Recommended next step

Obtain a versioned, gitignored historical file. Then audit its timestamps. H001 stays blocked until that audit passes.

```text
data source
  -> historical file
  -> timestamp audit
  -> point-in-time availability verified
  -> DATA READY
  -> freeze target, features, and horizon
  -> dataset
  -> baseline
  -> chronological evaluation
  -> 2 bp cost-aware backtest
```

Do not invent `available_at` from `period`, retrieval time, or the fixture two-hour offset. Do not train, label, or freeze H001 before DATA READY.
