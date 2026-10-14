# H001 frozen-data integrity audit, 2026-10-13

Integrity only. H001 was not built. No labels, features, fit, or backtest. No frozen file was rewritten. `snapshots/holdout_after_20261005` was not opened or listed.

Status is unchanged:

- `DATA NOT READY`
- `BLOCKED_PRECONDITION`
- `READY_TO_RUN = NO`

## Procedure

Each top-level artifact was hashed as its raw bytes with SHA-256. That digest is the file digest. It is not a composite.

The extracted freeze composite is the approved `NEW_VERIFICATION_BASELINE`. Regular files under `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/` whose relative POSIX path has no component starting with `.` were sorted by the UTF-8 bytes of that path. For each file the SHA-256 stream is the UTF-8 path, one `0x00`, the length as 8 unsigned big-endian bytes, then the raw file bytes. One digest covers that whole stream. It is not a concatenation of per-file hex digests.

`datasets/h001-nse-raw-20261010T140237Z/` was checked for existence and was not created.

## Measured files

| Path | Bytes | SHA-256 | Compared with 2026-10-11 |
|---|---:|---|---|
| `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` | 1,625,375 | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` | match |
| `datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json` | 501 | `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a` | match |
| `datasets/h001-nse-ann-2024-2025-v1.zip` | 4,655,549 | `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` | match |
| Extracted freeze, 493 files, 30,712,811 content bytes | composite | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` | match |

The first included freeze path is `audit_stats.json`. The last is `retrieval.json`. The named directory `datasets/h001-nse-raw-20261010T140237Z/` is absent. No discrepancy against the 2026-10-11 sizes or digests was found.

## Historical digest

`b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` remains `UNVERIFIED`.

The manifest field `SHA256` copies that string. This measurement does not reproduce it. The matching freeze digest `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` is the later baseline only. The original file list and byte order for the historical digest are still unrecovered.

## Parquet and manifest

The parquet file has 18,235 rows and 13 columns: `symbol`, `event_type`, `announced_at`, `published_at`, `available_at`, `source`, `source_id`, `period_end`, `has_xbrl`, `sm_isin`, `attachment_url`, `exchdisstime_raw`, `an_dt_raw`. The `symbol` column has 49 distinct values and no nulls. Arrow schema metadata is empty. File key-value metadata holds only the Arrow schema payload, not `dataset_version`, `schema_version`, or `source_version`.

The manifest says `dataset_version` `nse-ann-2024-2025-v1`, `row_count` 18235, `symbol_count` 49, `schema_version` `1.0`, and `source_version` `h001-nse-raw-20261010T140237Z`. Row count and symbol count agree with the parquet. The version strings live only in the manifest, so they are not independently stored inside the parquet.

That agreement is internal consistency of this freeze. It does not show that the event class is complete, that `exchdisstime` is an actionable public clock, or that the historical digest is the hash of these files.

## What the hashes establish

The parquet, the manifest, the zip, and the extracted 493-file freeze are the same bytes measured on 2026-10-11 under `NEW_VERIFICATION_BASELINE`.

## What stays unverified

The historical digest stays unverified. Point-in-time validity stays unverified. The event class stays provisional. 2025Q2–2025Q4 coverage stays open. The 2026-10-12 eligibility audit remains `INCONCLUSIVE` because the smaller training class has 34 rows against a bar of 50.

## Next data-readiness task

The next task is the event-class and coverage gap, not a fit. It is not authorized by this note. `READY_TO_RUN` stays NO.
