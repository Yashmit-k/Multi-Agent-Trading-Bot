# H001 candle restore — copy from the data-readiness machine

This checkout still has **no** `snapshots 2/` tree and no `snapshots 2.zip`. Those files are gitignored and cannot be recovered from Git. This environment cannot reach the original data-readiness machine. Do not regenerate candles. Do not copy `snapshots/nifty50`. Do not copy or open `snapshots/holdout_after_20261005`.

Source of the expected IDs and hashes: `services/quant/docs/data-readiness-2026-10.md` (the machine that recorded `MARKET_DATA_READY` after the move `snapshots 2/snapshots 2/nifty50` → `snapshots 2/nifty50`).

## Copy these four files

On the original machine, copy **byte-for-byte** into this repo root. Create the destination directories if needed. Do not overwrite any other snapshot tree.

| Snapshot ID | Source on original machine | Destination in this checkout | Expected size (reference) | Expected `candle_sha256` |
|---|---|---|---:|---|
| `nifty50_5m_20261005` | `snapshots 2/nifty50/5m/candles.jsonl` | `snapshots 2/nifty50/5m/candles.jsonl` | 517,606,507 | `0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b` |
| (manifest) | `snapshots 2/nifty50/5m/manifest.json` | `snapshots 2/nifty50/5m/manifest.json` | (small JSON) | `snapshot_id` must be `nifty50_5m_20261005`; `candle_sha256` must match the 5m hash |
| `nifty50_1d_20261005` | `snapshots 2/nifty50/1D/candles.jsonl` | `snapshots 2/nifty50/1D/candles.jsonl` | 7,019,418 | `0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d` |
| (manifest) | `snapshots 2/nifty50/1D/manifest.json` | `snapshots 2/nifty50/1D/manifest.json` | (small JSON) | `snapshot_id` must be `nifty50_1d_20261005`; `candle_sha256` must match the 1d hash |

If the original machine stored daily files under `1d` (lowercase) instead of `1D`, copy **from** that folder **to** `snapshots 2/nifty50/1D/` here. Quant research daily code expects the `1D` parent name.

Optional extra (not required for H001 P0/P1): do **not** copy `snapshots 2/nifty50/candles.jsonl` (short combined file; not the research dataset).

## After copy (on this machine)

1. Confirm `manifest.json` `snapshot_id` values.
2. SHA-256 the two `candles.jsonl` files and compare to the hashes above. Stop if either differs.
3. Confirm TATAMOTORS remains listed with zero bars; do not fill.

Until these files exist **and** the integrity-basis decision is recorded, the eligibility audit stays blocked.
