# Data readiness (2026-10)

Do **not** start H001. This is not an alpha result.

```
H001: BLOCKED_PRECONDITION
Market: MARKET_DATA_READY
Events: EVENT_DATA_BLOCKED
READY_TO_RUN: NO
```

Gate 1 done: **move/rename only** (`snapshots 2/snapshots 2/nifty50` → `snapshots 2/nifty50`). Not extraction. Not regeneration. Manifests reverified at the expected path. Candle files not overwritten.

```
Data exists and covers TRAIN/VALIDATION.
Snapshot content is not missing.
Expected path is now correct.
```

## Market data

Code `snapshots_root()` in `services/core/market-data/src/core_market_data/replay.py` expects `snapshots 2/nifty50` (space required). That path **is a directory** after the move/rename. Nested source path no longer contains `nifty50`.

Holdout path `snapshots/holdout_after_20261005`: **not read, not listed, not traversed.** Existence check only: absent.

### 5m

| Field | Value |
|---|---|
| Expected path | `snapshots 2/nifty50/5m/` |
| Actual path (this machine) | `snapshots 2/nifty50/5m/` |
| snapshot_id | `nifty50_5m_20261005` |
| SHA256 (`candle_sha256`) | `0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b` |
| Timeframe | 5m |
| Symbols in manifest | 50 names; **TATAMOTORS count 0**; **49** with bars |
| Coverage | first_bar `2024-01-01T03:45:00+00:00`; last_bar `2026-10-05T09:45:00+00:00` |
| Train 2024-01-01–2025-06-30 | covered (manifest) |
| Validation 2025-07-01–2025-12-31 | covered (manifest) |
| `candles.jsonl` exists | yes |
| size > 0 | yes (517606507 bytes) |
| opened read-only | yes (one byte, then close; **not scanned**) |
| Manifest | readable; snapshot_id matches `nifty50_5m_20261005` |
| Status | **MARKET_DATA_READY** |

### 1D

| Field | Value |
|---|---|
| Expected path | `snapshots 2/nifty50/1D/` |
| Actual path (this machine) | `snapshots 2/nifty50/1D/` |
| snapshot_id | `nifty50_1d_20261005` |
| SHA256 (`candle_sha256`) | `0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d` |
| Timeframe | 1d |
| Symbols | 50 listed; TATAMOTORS count 0; 49 with bars (~685 each) |
| Coverage | first_bar `2024-01-01T03:45:00+00:00`; last_bar `2026-10-05T10:00:00+00:00` |
| Train / validation | covered (manifest) |
| `candles.jsonl` exists | yes |
| size > 0 | yes (7019418 bytes) |
| opened read-only | yes (one byte, then close; **not scanned**) |
| Manifest | readable; snapshot_id matches `nifty50_1d_20261005` |
| Status | **MARKET_DATA_READY** |

Combined zip/root `snapshots 2/nifty50/manifest.json` id `35f78b61…` (created 2026-10-03) is **not** the research snapshot ID. Use the 5m/1D IDs above.

Do not add or remove symbols. TATAMOTORS stays listed with zero bars (`EXCLUDED` in quant direction inventory).

No interpolation. No new snapshot. No unzip. Move/rename only.

## Event/earnings data

| Field | Value |
|---|---|
| Source | Contract fixtures (`all_fundamentals` / `all_articles`); intelligence SQLite/CSV **schema** only |
| Coverage | 5 fixture symbols (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`); not 49-name 2024–2025 history |
| Fields in schema | `available_at`, `announced_at` on fundamentals; `published_at`, `retrieved_at` on news |
| Point-in-time safety | Fixtures are not research history. RSS `retrieved_at` is wall-clock — rejected. |
| Status | **NO_HISTORICAL_DATA** |
| Event status | **EVENT_DATA_BLOCKED** |

`period_end` is **never** accepted as availability time. **`available_at <= prediction_time` must be enforceable on every row.** Records without a trustworthy availability timestamp are **discarded**, not filled. Fixtures are **NO_HISTORICAL_DATA** and are not used. There is still no in-repo PIT NIFTY50 event file to acquire from; Gate 2 remains blocked.

## H001

```
H001: BLOCKED_PRECONDITION
Market: MARKET_DATA_READY
Events: EVENT_DATA_BLOCKED
READY_TO_RUN: NO
```

`BLOCKED_PRECONDITION` and `DATA NOT READY` name this same research-data blocker. H001 has not been run, so this is not a pass, not a cleared 2 bp gate, and not an alpha result. No LogisticRegression. No MlAgent.

## Required next action

1. Gate 1 **done** (move/rename + manifest reverify).
2. **Still required:** acquire historical NIFTY50 earnings/events for **2024-01-01 through 2025-12-31**, 49 names with bars (TATAMOTORS excluded from bars). Required fields:
   - `symbol`
   - `event_type`
   - `announced/published_at`
   - `available_at`
   - `source`
   - `source_id`
   - event/value fields
   - revision timestamp/version if applicable

   `period_end` is never availability. No RSS wall-clock. No fixtures. No guessed midnight/open.

Do not freeze H001 target/features/horizon and do not train until events are point-in-time ready. Then freeze remaining fields **before** training and **before** seeing validation, then run LogisticRegression once with the costed backtest and 2 bp gate.

## Safety

| Item | Yes/No |
|---|---|
| Holdout not read | Yes |
| Holdout not listed | Yes |
| Holdout not traversed | Yes |
| Frozen snapshots not modified | Yes |
| No unzip into expected path | Yes |
| No H001 training | Yes |
| No H001 validation | Yes |
| No live trading | Yes |
| No broker orders | Yes |
| No model training | Yes |
| No synthetic timestamps | Yes |
| No future information used | Yes |
