# H001 integrity procedure investigation

Date: 2026-10-14. Authorization B remains recorded (`h001-authorization-b-grant.md`). This note does not authorize a fit. Eligibility counts were not computed. The holdout was not accessed.

## Question

What procedure produced the approved historical digest

`b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`

and can it be reproduced on the freeze in this checkout?

## Sources checked

| Source | Result |
|---|---|
| `git log --all -S b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` | Docs only. First appearance: commit `2d687ff` (2026-10-10, `h001 data readiness md`). Later copies in protocol, NSE note, recovery audits. |
| `git log --all -S sha256_of_named_files` | Same documentation trail. No Python/shell generator. |
| Repository `*.py` / `*.sh` / `*.ps1` | No symbol `sha256_of_named_files`. No script that builds the aggregate raw/json digest. |
| `datasets/h001-nse-raw-20261010T140237Z/retrieval.json` | Keys: `dataset_id`, `results_url`, `retrieval_finished_utc`, `retrieval_method`, `retrieval_timestamp_utc`, `sha256_of_named_files`, `source`, `source_coverage`, `source_url`, `ui`, `universe_snapshot`, `window`. The digest string is stored. There is no file list, path convention, sort order, encoding, or separator. |
| `fetch_log.json`, `audit_stats.json` | No hash procedure. Freeze root also has `corporate-announcements/` and `financial-results/` directories; the note does not say whether those were in the named set. |
| Parquet manifest | Field `SHA256` copies the **same** historical string. It is not a parquet-bytes digest. |
| `h001-raw-recovery-audit.md`, `h001-next-decisions.md`, `h001-protocol-v1.md` | Prior searches (repo, git, sibling folders on another machine, transcripts) already concluded the producer is missing. This checkout repeats that result. |
| Agent transcripts (this project) | No `sha256_of_named_files` generator. |
| Nearby folders (`SEM 7/flexiproj`, `flexi`, `pbl`, `honorsproj`, Desktop `flexi3`) | No extra producer script found in this pass. |

No original command, script, or filename order was recovered. Candidate hash orders were **not** tried.

## What the three digests actually cover

| Digest | Object | This checkout | Status |
|---|---|---|---|
| `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` | Claimed SHA-256 of “named raw/json files” in freeze `h001-nse-raw-20261010T140237Z`. Procedure unknown. | String present in protocol, NSE note, parquet manifest, `retrieval.json`. Bytes that produce it: unknown. | **UNVERIFIED**. Not recovered. |
| `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` | `NEW_VERIFICATION_BASELINE`: 493 regular files under the freeze root, excluding hidden path components, ordered by UTF-8 POSIX relative path; for each file, path + NUL + 8-byte big-endian length + file bytes; SHA-256 of that stream. | Recomputed 2026-10-14 on `datasets/h001-nse-raw-20261010T140237Z/` (named path present). Match. Nested extract path absent. | **Verified tamper-check of that tree**. Not the historical digest. |
| `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` | SHA-256 of parquet **file bytes** `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet`. | File present (1,625,375 bytes). Match. | **Verified for that file only**. |

Related objects, still not `b0f4760f…`: parquet-sidecar manifest bytes `d0a481cb…`, zip `271dd1ce…`.

The parquet manifest copying `b0f4760f…` into field `SHA256` does not mean the parquet hashes to that value. The parquet hashes to `8ae800ef…`.

## Candle snapshots

Required (protocol / implementation plan / data-readiness-2026-10):

| Snapshot | Path | Expected `candle_sha256` | Size on the machine that recorded MARKET_DATA_READY | This checkout |
|---|---|---|---|---|
| `nifty50_5m_20261005` | `snapshots 2/nifty50/5m/candles.jsonl` + `manifest.json` | `0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b` | 517,606,507 bytes | **absent** |
| `nifty50_1d_20261005` | `snapshots 2/nifty50/1D/candles.jsonl` + `manifest.json` | `0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d` | 7,019,418 bytes | **absent** |

`.gitignore` excludes `snapshots/` and `snapshots 2/`. Git never stored these files. No `snapshots 2.zip` / `snapshots.zip` is in the repo or in scanned sibling project folders.

Provenance of the expected hashes: `services/quant/docs/data-readiness-2026-10.md`, written when those paths existed on **that** machine after a move/rename (`snapshots 2/snapshots 2/nifty50` → `snapshots 2/nifty50`). This Windows checkout does not contain that tree.

Not restored. Not substituted from `snapshots/nifty50`. Holdout not listed or opened.

Most likely recovery: copy the gitignored `snapshots 2/nifty50/{5m,1D}/` tree from the machine or backup that produced the 2026-10 data-readiness note, then verify `snapshot_id` and `candle_sha256` against the table above. Do not regenerate prices.

## Decision on running the eligibility audit

**Not safe to execute.** Two independent blockers remain:

1. Historical digest procedure not recovered; `b0f4760f…` stays UNVERIFIED. `NEW_VERIFICATION_BASELINE` was not substituted.
2. Approved candle files are missing.

A supervisor decision request is in `h001-supervisor-decision-request-verification-basis.md`. Do not switch verification bases without that decision. Do not run eligibility until candles are restored **and** the integrity basis is either historically verified or explicitly replaced in writing.
