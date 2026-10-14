# H001 raw recovery audit

Read-only check of the extracted NSE freeze. No model was trained, no backtest was run, and no source file was modified. `snapshots/holdout_after_20261005` was not opened.

The path named by the NSE note, `datasets/h001-nse-raw-20261010T140237Z`, is absent. The extracted tree is `datasets/h001-nse-raw-20261010T140237Z` under `datasets/h001-nse-ann-2024-2025-v1/`. This audit reads that nested directory. It does not move it.

## How this was read

A Python 3 process used `pathlib`, `hashlib.sha256`, `zipfile`, `json`, and `pyarrow.parquet`. It hashed files in place, compared those hashes with zip members read into memory, loaded the per-symbol announcement JSON and the `.raw` slices, and compared `seq_id` with the parquet `source_id`. It wrote `datasets/research/h001_raw_recovery_audit/summary.json` and `file_hashes.jsonl`. Those two files are derived notes. The zip, the parquet, the manifest, and the extracted tree were not rewritten.

## Inventory

| Item | Result |
|---|---|
| Named path `datasets/h001-nse-raw-20261010T140237Z` | absent |
| Extracted root | `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z` |
| Files in that root | 494 |
| Bytes in that root | 30,721,007 |
| Bytes excluding `.DS_Store` | 30,712,811 |
| Empty files (0 bytes) | 0 |
| Duplicate relative paths | 0 |
| Duplicate basenames | 0 |

Counts by directory and extension:

| Directory | Extension | Files |
|---|---|---:|
| root | `.json` | 3 |
| root | `.DS_Store` | 1 |
| `corporate-announcements` | `.json` | 49 |
| `corporate-announcements` | `.raw` | 392 |
| `financial-results` | `.raw` | 49 |

`retrieval.json`, `fetch_log.json`, and `audit_stats.json` are present in the extracted root.

`financial-results/HDFCLIFE.raw` and `financial-results/SBILIFE.raw` are 2 bytes and contain `[]`. They are empty arrays, not missing files.

The parent folder `datasets/h001-nse-ann-2024-2025-v1/` also holds copies of the parquet and the manifest. Both copies match the loose files in `datasets/`:

| File | Bytes | SHA256 | Matches loose file |
|---|---:|---|---|
| parquet | 1625375 | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` | yes |
| manifest | 501 | `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a` | yes |

The zip file digest remains `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` (4,655,549 bytes). That digest is the archive, not the raw/json digest below.

## Zip comparison

The zip contains 493 members under `h001-nse-raw-20261010T140237Z/`. All 493 match the extracted files of the same relative path in size and SHA256. Nothing in the zip is missing on disk. The only extracted file the zip does not contain is `.DS_Store` (8,196 bytes, SHA256 `31a6f3e03fa564d6cd8c6c21dd8ed303c0db4ab7e1d96350d4efcc97f52dcd79`).

## Raw digest

Published digest: `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`.

`retrieval.json` stores that string as `sha256_of_named_files`. It does not list filenames, a relative-path convention, a byte encoding, or an order. `fetch_log.json` has keys `calls`, `finished_at`, `started_at`, and `symbols`, and no digest procedure. `audit_stats.json` does not describe a hash. The NSE note calls it "SHA256 of named raw/json files" and stops there. The manifest copies the same string and does not name the inputs.

The procedure is not documented. The digest was not recomputed. No candidate file order was hashed. Status: **unverified**. The missing evidence is the filename list and the order of the bytes that were hashed.

Individual SHA256 values for the extracted files are in the manifest at the end of this note and in `datasets/research/h001_raw_recovery_audit/file_hashes.jsonl`.

## Results-like rows

Prior-audit claim: 3,690. `audit_stats.json` stores `results_like_kept` 3690 and does not store the predicate.

Announcement JSON and announcement `.raw` slices share one schema. Every row has the same 20 keys: `an_dt`, `attFileSize`, `attchmntFile`, `attchmntText`, `bflag`, `csvName`, `desc`, `difference`, `dt`, `exchdisstime`, `fileSize`, `hasXbrl`, `old_new`, `orgid`, `seq_id`, `smIndustry`, `sm_isin`, `sm_name`, `sort_date`, `symbol`. `desc` is a non-empty string on all 18,235 rows. `hasXbrl` is a boolean, true on 3,375 rows and false on 14,860. `old_new` is null on all 18,235 rows.

The NSE note's sentence is subjects matching `result`, `financial`, or `earnings`, or an XBRL flag. It does not name the field, the match type, or the case rule. `desc` and `attchmntText` are both text. `hasXbrl` is a boolean flag, and the financial-results files have a separate `xbrl` field. Binding the sentence to one of those fields would be a new rule. The 3,375 `hasXbrl = true` count was not used as the 3,690 count.

Because that rule is not established, these counts were not computed:

1. Rows matching a subject-text condition.
2. Rows matching an XBRL condition other than the observed `hasXbrl` boolean tally above.
3. Rows matching either condition.
4. A deduplicated results-like total.

Duplicate `seq_id` values inside the announcement JSON: 0. Duplicate `seq_id` values inside the `.raw` slices: 0. `seq_id` sets of the JSON files and the `.raw` slices are equal (18,235 ids). Unmatched announcements between those two stores: 0.

Status of 3,690: **unverified prior-audit claim**.

Financial-results files are a different schema (`audited`, `broadCastDate`, `exchdisstime`, `filingDate`, `fromDate`, `toDate`, `oldNewFlag`, `reInd`, `resultDescription`, `seqNumber`, `xbrl`, and the other keys listed in `summary.json`). They contain 5,844 rows, which matches the stored `financial_results_rows_in` figure. That equality was recomputed by counting rows. The stored in-window figure of 453 was not recomputed. These rows are not announcement rows and were not matched to the parquet.

## Raw data against the parquet

The documented announcement key is `nse_corporate_announcements` plus `seq_id`. The parquet column `source` is `nse_corporate_announcements` on every row, and `source_id` is the `seq_id` string.

| Check | Result | Label |
|---|---|---|
| Announcement JSON rows | 18235 | verified |
| Announcement `.raw` rows | 18235 | verified |
| Parquet rows | 18235 | verified |
| `seq_id` matched to `source_id` | 18235 | verified |
| JSON ids absent from the parquet | 0 | verified |
| Parquet ids absent from the JSON | 0 | verified |
| Duplicate `seq_id` | 0 | verified |
| Duplicate parquet `source` + `source_id` | 0 | verified |
| Symbol mismatches on matched ids | 0 | verified |
| `exchdisstime` string versus `exchdisstime_raw` | 0 mismatches | verified |
| Parsed `exchdisstime` as `Asia/Kolkata` versus `available_at` | 0 mismatches | verified |
| `hasXbrl` versus parquet `has_xbrl` | 0 mismatches | verified |
| Unique symbols | 49, same set as `audit_stats.json` `symbols_covered_list`; TATAMOTORS absent | verified |

The raw announcement rows and the parquet rows are the same 18,235 identifiers, with the same symbol and the same dissemination clock. Financial-results rows are outside that comparison.

## Point-in-time

On the 18,235 announcement rows:

- Missing `exchdisstime`: 0.
- Unparseable `exchdisstime` (expected `DD-Mon-YYYY HH:MM:SS`): 0.
- Parsed instants outside 2024-01-01 00:00 through 2025-12-31 23:59:59 `Asia/Kolkata`: 0.
- Duplicate `seq_id`: 0, so the freeze does not contain two bodies for one announcement id.
- `old_new` is null on every row. The files do not identify a revision chain, so a later revision of the same filing cannot be separated from a different `seq_id`. The prior claim of 69 `/revis/i` rows was not recomputed, because the note does not name which text field the pattern uses.
- Raw timestamp strings were left as stored. `period_end` remains null in the parquet. Crawl time was not written into `available_at`.

## Limitations

The published raw digest is unverified until a record states the hashed filenames and their order. A separate integrity baseline is approved below and is not this digest. The 3,690 results-like count is unverified until the original classifier is recovered. Event class, decision time, horizon, label, features, and minimum sample size stay unfrozen. `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay.

## Readiness follow-up, 2026-10-11

Repository at the start of this follow-up: branch `main`, HEAD `ad7557ff9332f943660b058bff401c71983bdd3d`. Uncommitted work already present was left in place and was not staged. The named directory `datasets/h001-nse-raw-20261010T140237Z` is absent. This follow-up reads `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/`.

### Raw checksum

Searched with `git log --all -S` for the digest and for `sha256_of_named_files`, and with `git grep` for `hasXbrl` and `results_like` in Python, Markdown, and shell. The digest string appears in history only as the table cell in commit `2d687ff` (`services/quant/docs/h001-data-readiness.md`, later kept as the NSE announcement note). No commit contains `sha256_of_named_files` or `results_like`. No script in this checkout builds the aggregate digest.

`retrieval.json`, `fetch_log.json`, and `audit_stats.json` still omit the filename list, path convention, and byte order. The digest was not recomputed. Status remains **unverified**. A match between extracted files and zip members does not verify this aggregate digest.

Independent digests, unchanged:

| Object | SHA256 |
|---|---|
| Raw/json claim | `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` |
| Parquet | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` |
| Manifest | `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a` |
| ZIP | `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` |

Missing evidence: the exact file list and the order in which their bytes were hashed.

### Results-like count

No classifier implementation is in this repository. The stored `results_like_kept` value 3690 stays an **unverified prior-audit claim**.

Proposal P1 is not that claim and is not approved. It is one reading of the NSE sentence, declared before the count below was computed: announcement JSON rows only; a row is included when `desc.casefold()` contains `result`, `financial`, or `earnings`, or when `hasXbrl` is true. Financial-results rows are excluded. No other rule was tried.

| P1 piece | Rows |
|---|---:|
| Announcement rows examined | 18235 |
| `desc` substring hit | 316 |
| `hasXbrl` true | 3375 |
| Intersection | 1 |
| Union | 3690 |

The six `desc` values in the text hit are `Financial Result Updates` (245), `Integrated Filing- Financial` (50), `Clarification - Financial Results` (8), `Reply to Clarification- Financial results` (7), `Consolidated Result Updates - IFRS` (4), and `Publish Audited Results` (2).

The union equals the stored claim. That equality does not recover the original rule: the generator is absent, and other rules were not searched for. P1 is not frozen. `hasXbrl` true alone remains 3,375 and is not the results-like count.

### Point-in-time limitations

| Topic | What this checkout supports |
|---|---|
| Structural consistency | Verified earlier in this note: 18,235 announcement rows, 49 symbols, every `seq_id` matches parquet `source_id`. |
| Timestamp transform | Verified: every `exchdisstime` parses, and tagging it `Asia/Kolkata` reproduces `available_at`. The vendor string has no offset. |
| Source completeness | Unverified. This is one NSE pull. BSE `DissemDT` was not cross-checked. NSE can change historical JSON later. |
| Actionable availability | Unverified. A parsed dissemination clock is not proof that a strategy could have traded on that row at that instant. |
| Revisions | `old_new` is null on all 18,235 rows. Revision chains are not identified. The prior 69 `/revis/i` count was not recomputed. |
| Coverage | TATAMOTORS is absent. `HDFCLIFE.raw` and `SBILIFE.raw` in financial-results are `[]`. Announcements for those two names are present. Line-item restatement history is not in this freeze. |

The NSE note's heading `DATA READY` applies to announcement-level `exchdisstime` only. It already says training `READY_TO_RUN` is NO. This follow-up does not change that note.

### Protocol-freeze checklist

Taken from `h001-protocol-v1.md` and `hypothesis-H001.md`. Nothing below is newly chosen.

| Decision | Documented value | State | Still required before training |
|---|---|---|---|
| Information source | Earnings and events, one source | Frozen in the hypothesis | Keep this source. Do not add another. |
| Universe | NIFTY 50 names with bars; TATAMOTORS excluded | Frozen | Keep the exclusion. |
| Model | One `LogisticRegression`, no sweep, no boosting, no MlAgent | Frozen for a later authorized run | Do not fit it in this task. |
| Cost gate | Positive validation net edge after 2 bp | Frozen and not applied | Keep the gate. It is not a label. |
| `available_at` | `exchdisstime` as `Asia/Kolkata`; `period_end` and crawl time forbidden | Frozen as the clock convention | A decision that this clock is trustworthy enough to trade on is still open. |
| Event class | Results-like only, or every LODR row | Unresolved | Approve a written classifier, or approve all rows. P1 is not that approval. |
| Decision time | First bar whose end is at or after `available_at`, or next session open after the cash close | Unresolved | Pick one. After-close events wait. |
| Horizon | Next completed session close, or a later fixed session | Unresolved | Write the session rule. Entry-session close is not the label while `available_at` is inside that session. |
| Label | Sign of forward close-to-close return, or a threshold declared before the fit | Unresolved | Declare the label before any fit. |
| Features | None listed | Unresolved | List fields and the time each one may be used. |
| Periods | Events 2024-01-01 through 2025-12-31; split through 2025-06-30, then through 2025-12-31 | Provisional in the protocol | Confirm or replace the split before the fit. Partial 2026 candles and the market holdout are not the event test. |
| Minimum sample | No number | Unresolved | Write the minimum before the fit. |
| Revisions and overlap | Key is `source` + `source_id`; at time t keep the latest row with `available_at` <= t | Provisional, and chains are not in the data | Define how unidentified revisions and overlapping windows are handled. |
| Baselines | Always-flat, always-long, existing quant-agent baseline | Frozen for a later run | Name the proper scoring rule. |
| Acceptance | Leakage pass, sample minimum met, validation net edge after 2 bp positive | Written, not executed | Authorize the run separately. |
| Leave `BLOCKED_PRECONDITION` | Not met | Unresolved | Verified raw digest, frozen event class, decision time, horizon, label, features, and minimum sample, then a separate authorization. |

## Approved integrity baseline, 2026-10-11

The user approved `NEW_VERIFICATION_BASELINE` as an integrity check of the extracted tree only. It does not reproduce `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`.

Recomputed from `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/` with no source file changed. Regular files whose relative POSIX path has no component starting with `.` were sorted by the UTF-8 bytes of that path. For each file the SHA-256 stream is the UTF-8 path, one `0x00`, the length as 8 unsigned big-endian bytes, then the raw bytes.

| Item | Result |
|---|---|
| Files | 493 |
| Digest | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` |
| Match to the approved specification | yes |

Parquet `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494`, manifest `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a`, and zip `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` stay separate.

## Independent integrity audit, 2026-10-11

A later run hashed the local files again and did not modify them. `datasets/h001-nse-raw-20261010T140237Z/` is still absent and was not created. The readable freeze is `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/`.

Included files are regular files under that root whose relative POSIX path has no component starting with `.`. The only excluded file is `.DS_Store` (8,196 bytes). It is macOS metadata, it is not a zip member, and the approved baseline already excludes hidden path components. No symlink was present.

Path spelling is the relative POSIX path. Order is lexicographic by the UTF-8 bytes of that path. For each included file the hashed sequence is the UTF-8 path, one `0x00`, the file length as 8 unsigned big-endian bytes, then the raw file bytes. SHA-256 covers that whole stream. This is not a list of per-file digests concatenated as text.

| Object | Files | Content bytes | SHA-256 |
|---|---:|---:|---|
| Included freeze | 493 | 30,712,811 | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` |
| Parquet file bytes | 1 | 1,625,375 | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` |
| Manifest file bytes | 1 | 501 | `d0a481cbaf87ceae8679d0918f5001af76793ed5ec9b08c3a5f89876c2b9ec7a` |
| ZIP file bytes | 1 | 4,655,549 | `271dd1ce85a1a1c326a87a2c870f567148bed604914c993fd6eb5f1ff157f83c` |

The first included path is `audit_stats.json`. The last is `retrieval.json`. These four digests match the measurements already recorded above. The freeze digest is a verified recomputation of `NEW_VERIFICATION_BASELINE`. It is not a reproduction of `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`. The original file list and byte order for that historical digest were not recovered, so it stays unverified. No error was raised. `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay.

## File hashes

Relative path, bytes, and SHA256 for every file under the extracted root. The `.DS_Store` row is the macOS file the zip does not contain.

| Relative path | Bytes | SHA256 |
|---|---:|---|
| `.DS_Store` | 8196 | `31a6f3e03fa564d6cd8c6c21dd8ed303c0db4ab7e1d96350d4efcc97f52dcd79` |
| `audit_stats.json` | 1979 | `43fb92ba08dfc3fba0bf5d083e2f3785aa030475680134bf973744eb3d529126` |
| `corporate-announcements/ADANIENT.json` | 248649 | `d7c892d06648e8a94fcb422e03191dc60c3f0b5bb0d35f97e432032559be04a9` |
| `corporate-announcements/ADANIENT_01-01-2024_31-03-2024.raw` | 29614 | `026bf75a5556b2a845be9e8ac281c08da5fe72e918832b79d45e5255b1b173f0` |
| `corporate-announcements/ADANIENT_01-01-2025_31-03-2025.raw` | 20096 | `16186bf0bd898132dbbb22bd736563d3eac8ac70d51abd31b8682eccfec063a9` |
| `corporate-announcements/ADANIENT_01-04-2024_30-06-2024.raw` | 23770 | `cd0f2b5d56d6a953a27225dd10be21def8916799746cfe2c7e3f5b0264979b1b` |
| `corporate-announcements/ADANIENT_01-04-2025_30-06-2025.raw` | 28231 | `29c4de7d6d9f4a3d4b93b811f7d673ac9c8d7a34e006e4e022d10ed40b810dc3` |
| `corporate-announcements/ADANIENT_01-07-2024_30-09-2024.raw` | 23742 | `4f09f22aeb6e2f2389fe9d084e3969c1c6cdec5714e618b935686b9d931d0fbf` |
| `corporate-announcements/ADANIENT_01-07-2025_30-09-2025.raw` | 24792 | `f70b2c6ef6614129ba38066e7d6f7d3ded8253f28e427be2b862b9f5a735898f` |
| `corporate-announcements/ADANIENT_01-10-2024_31-12-2024.raw` | 33962 | `d862cf3ad24a40a0034ee097befd1bcbbc65e7a99d37e0575dddbbde6abd620d` |
| `corporate-announcements/ADANIENT_01-10-2025_31-12-2025.raw` | 51130 | `bbe072c9fa52b8e2f627e9070a0c6843b4524996f5f264ff17d21ffbf4d7e343` |
| `corporate-announcements/ADANIPORTS.json` | 222466 | `f8579ec43f6980ad76826583824801860ae1e9f8514f28c71ba1cf785f7ae763` |
| `corporate-announcements/ADANIPORTS_01-01-2024_31-03-2024.raw` | 36161 | `00eec6d1fdb7d9d733b8f5b40adf9b1a148faf2babcdfe4fc395ea42f348ca5b` |
| `corporate-announcements/ADANIPORTS_01-01-2025_31-03-2025.raw` | 14806 | `f8540a3c1e701552e6389ee07ee7f8171da559bc3d0b79fcd9638c401b51e921` |
| `corporate-announcements/ADANIPORTS_01-04-2024_30-06-2024.raw` | 28507 | `2df62ef250092ae86b52b3520bc16f08b66f7feb9d71ed9a1e0cd92678d70cf6` |
| `corporate-announcements/ADANIPORTS_01-04-2025_30-06-2025.raw` | 37881 | `723bfebf46ffee584cea72935873c3b26ee08cdccbb40be54cc089203b044e4e` |
| `corporate-announcements/ADANIPORTS_01-07-2024_30-09-2024.raw` | 22551 | `8c66dfbd23cb68a9e34cbd41bf15be943da58f2891e5e25952ec50de646e664e` |
| `corporate-announcements/ADANIPORTS_01-07-2025_30-09-2025.raw` | 24140 | `771a7f45477e4cd9cd96156e48dbf0b0ce5d7e430fc4fdc4d29b1e0abdd6cee2` |
| `corporate-announcements/ADANIPORTS_01-10-2024_31-12-2024.raw` | 26691 | `a6c169d0d7f5dc6fe693d6550b94eb0d79a6ecae23d42fbacafb74b51df16664` |
| `corporate-announcements/ADANIPORTS_01-10-2025_31-12-2025.raw` | 19857 | `f2f29402e529d1b5ab15468fc8801db4bad3c3df57547dedee6ce8851da6c511` |
| `corporate-announcements/APOLLOHOSP.json` | 164463 | `dfc4a3c9201e0c7904d7236a815b21c4b14bfc07273b07d59d6c131de3eba914` |
| `corporate-announcements/APOLLOHOSP_01-01-2024_31-03-2024.raw` | 23544 | `72a7a2560f6abd22076412d1ce88d4889a535bf7490c6c5a5e861062e47105a9` |
| `corporate-announcements/APOLLOHOSP_01-01-2025_31-03-2025.raw` | 13352 | `9cf3391b298b6f1e1b577766c1bf04f58c34997f7fe1498550623a8cc92d7c10` |
| `corporate-announcements/APOLLOHOSP_01-04-2024_30-06-2024.raw` | 26135 | `49d2d2120fc2198a0e302a0e642bd0ceda9262f4f4ced3a5f93e9bd34d8b404d` |
| `corporate-announcements/APOLLOHOSP_01-04-2025_30-06-2025.raw` | 21254 | `8aab4d89682d2e6fbc05f605483f8b847c52d7945e1be39386b21f2d8a7788d7` |
| `corporate-announcements/APOLLOHOSP_01-07-2024_30-09-2024.raw` | 30069 | `703ef3970122c18ea5462c68fd67eb9f5e0467e2d23ebc08067a572808f18154` |
| `corporate-announcements/APOLLOHOSP_01-07-2025_30-09-2025.raw` | 18544 | `b35df25e35c8f15dfb87a6319759efd24d1cb6a7b02187daec1bbcdc2df5b4f7` |
| `corporate-announcements/APOLLOHOSP_01-10-2024_31-12-2024.raw` | 13648 | `0b945d8d695142bd760995b8a13b5b187196ccf820c30be74b4e8d980735c7ce` |
| `corporate-announcements/APOLLOHOSP_01-10-2025_31-12-2025.raw` | 8885 | `e1663090152f0e29928d819fc3d82f67174f87af709891c06c7e66e78ad8f3a8` |
| `corporate-announcements/ASIANPAINT.json` | 272033 | `1da74c488b63b2b977f367c06eb71f9c094f32dff7cafa01d1a9731c97e23137` |
| `corporate-announcements/ASIANPAINT_01-01-2024_31-03-2024.raw` | 43292 | `c5566560917dda853c98fc462a9e9ed8c3ff06adbb306b294f488262a1975939` |
| `corporate-announcements/ASIANPAINT_01-01-2025_31-03-2025.raw` | 21817 | `16368ccb1ee9b730dcc21da1f522f7f005c8d2d552bea5df6342c3f1683fa9e6` |
| `corporate-announcements/ASIANPAINT_01-04-2024_30-06-2024.raw` | 49871 | `fb29f8699c7d398cf80e962defc276be79645efa94521854132584311d54f84e` |
| `corporate-announcements/ASIANPAINT_01-04-2025_30-06-2025.raw` | 32338 | `39b79cf63f93a0cf1d2d61f342bbc7048f0b666ae076018341a115a4a5e977b5` |
| `corporate-announcements/ASIANPAINT_01-07-2024_30-09-2024.raw` | 34120 | `574d241fd2c59d4867a8e89940cf25bf9392268c261ab3f2a962398c5d41fc96` |
| `corporate-announcements/ASIANPAINT_01-07-2025_30-09-2025.raw` | 16565 | `fa4701c83a0d67ce8cbbc528558447e04db0eb5640e79f5d114363bf21ae1c41` |
| `corporate-announcements/ASIANPAINT_01-10-2024_31-12-2024.raw` | 41200 | `46c0de2ede2c28f12291fa63d8659b547c073aeab9286ead3039145fb7616247` |
| `corporate-announcements/ASIANPAINT_01-10-2025_31-12-2025.raw` | 20398 | `122d4abc6833c88d3da7d5a5de1e9dbec219d938c7613657f41fcb3a5dcb6484` |
| `corporate-announcements/AXISBANK.json` | 313964 | `cfe669ae44ab4c9ba1e56410886c6964e0e8c4fec4438b275e7eb051017d15d5` |
| `corporate-announcements/AXISBANK_01-01-2024_31-03-2024.raw` | 41889 | `21981a73fdce794cf5ebd91509516697be09f431a8f8ba1057de6a48b4497061` |
| `corporate-announcements/AXISBANK_01-01-2025_31-03-2025.raw` | 25252 | `b6237aad7f4436df869d353081845c9692a5794fc35e4444d5e02263e8353c58` |
| `corporate-announcements/AXISBANK_01-04-2024_30-06-2024.raw` | 55296 | `5686ad40ac36e1fdcf73726dc40a69dccbf5fd84cb739080f9d1f413ddacf18d` |
| `corporate-announcements/AXISBANK_01-04-2025_30-06-2025.raw` | 34481 | `927beaf06f66399db733e227ac7bb60523d50ad7d06f41f947909d3b9161085c` |
| `corporate-announcements/AXISBANK_01-07-2024_30-09-2024.raw` | 38068 | `34dbe4292b73fa15ccaa7580b756e98fb42a34156ac3737339eea7675e1aa7b3` |
| `corporate-announcements/AXISBANK_01-07-2025_30-09-2025.raw` | 33803 | `4c58267548dbb29043aca9aa07f01031a99d91a0574afcbce73579449a78d5a5` |
| `corporate-announcements/AXISBANK_01-10-2024_31-12-2024.raw` | 34354 | `2e088a4a2726eed6d06052a0fd1fd5b224550dc480d274d61fce9a53bd565951` |
| `corporate-announcements/AXISBANK_01-10-2025_31-12-2025.raw` | 32429 | `1637afc619ce23995fff71592241839f61e666d7b6738a7e6eab123bec94d84b` |
| `corporate-announcements/BAJAJ-AUTO.json` | 205328 | `6ac36d58e78c76f377aa47217cc13e405d8427f01c317113f98294fc5cf68ea0` |
| `corporate-announcements/BAJAJ-AUTO_01-01-2024_31-03-2024.raw` | 30741 | `08b418914072da85e2d36573365525504c41be59b3ef3c56f2a20eb5ffbca579` |
| `corporate-announcements/BAJAJ-AUTO_01-01-2025_31-03-2025.raw` | 22869 | `4247ae0a13ebbc872d24817b9e95f8ed4ca3e68a1cc48bda7cd54d23145ccab3` |
| `corporate-announcements/BAJAJ-AUTO_01-04-2024_30-06-2024.raw` | 28103 | `7fa32bc708e37b3c5d36709f0445b95ac027d79a1d62f1bd8367bc74552acdd0` |
| `corporate-announcements/BAJAJ-AUTO_01-04-2025_30-06-2025.raw` | 28369 | `27bc696dc9587808f001298bfd51fdc75fa073c7772ab77994af485adc01d35c` |
| `corporate-announcements/BAJAJ-AUTO_01-07-2024_30-09-2024.raw` | 24039 | `ccb94e185fb30b87c7a6aaed506e148b1d3274f56ad82b186e23fe55ccf3a166` |
| `corporate-announcements/BAJAJ-AUTO_01-07-2025_30-09-2025.raw` | 26393 | `3e12b059b2832634e4fb3b1f23571eb2df723fc2f0d7caf17fa2330e5406aa16` |
| `corporate-announcements/BAJAJ-AUTO_01-10-2024_31-12-2024.raw` | 10813 | `1290052dbcd82d798589ee477a4af7e1532bfce17e5190f01ae20422c8d8c956` |
| `corporate-announcements/BAJAJ-AUTO_01-10-2025_31-12-2025.raw` | 22809 | `bb737d5fcf74e8d7ba081aed92a5a3fc85ff4e59331d83c939d52f9306ff0f75` |
| `corporate-announcements/BAJAJFINSV.json` | 129481 | `48b74e4fe1cc264592117bca3aafcfe9f4e4d7d2e4accae405e0e708085e6601` |
| `corporate-announcements/BAJAJFINSV_01-01-2024_31-03-2024.raw` | 13386 | `9f35b88e3b987f82cc87038af8dec8aa85dffe534bebee5df0d44b709fad67e9` |
| `corporate-announcements/BAJAJFINSV_01-01-2025_31-03-2025.raw` | 15445 | `bb6052349b707f0f096083faf9d876a0dc1f311a5042c3115392225a6b413e79` |
| `corporate-announcements/BAJAJFINSV_01-04-2024_30-06-2024.raw` | 17952 | `582ae15697dc4737150f5713fa6f947fba16dc70d277ce7b2f16212f306eb343` |
| `corporate-announcements/BAJAJFINSV_01-04-2025_30-06-2025.raw` | 19221 | `1f50ea34977775011c430ed1c967ed3b709cf1f1ad970218849f3695bb1cfe45` |
| `corporate-announcements/BAJAJFINSV_01-07-2024_30-09-2024.raw` | 10656 | `a6b68f51753b5584dedb31d57c8c521f06801708b57b92135e1a45003e8ea02f` |
| `corporate-announcements/BAJAJFINSV_01-07-2025_30-09-2025.raw` | 20814 | `434b400494c42a5350de27a6313cbe77dd5c1a8ba24b94166fabacd38eaf4074` |
| `corporate-announcements/BAJAJFINSV_01-10-2024_31-12-2024.raw` | 11207 | `3d910cd6c2ec0e67477f15d5a0f258b75a5a6364699d25b22153250c3fef2424` |
| `corporate-announcements/BAJAJFINSV_01-10-2025_31-12-2025.raw` | 13488 | `3e7ff7bff4841a7630de37d83c18946232259e4397e5ef2ca5381ea5bfeda3b1` |
| `corporate-announcements/BAJFINANCE.json` | 204350 | `980fc311ef46e878ff0261c312c1438f06dc68e1eb688fa073631b5197462495` |
| `corporate-announcements/BAJFINANCE_01-01-2024_31-03-2024.raw` | 27718 | `c4a460825ceae786e12b2ce261a466999beef3c305188aefca99d69f0920821f` |
| `corporate-announcements/BAJFINANCE_01-01-2025_31-03-2025.raw` | 23310 | `0d56bd88e402d6e8d55ea3d2d71815fe5cb571db6a69138472b0a913b0232945` |
| `corporate-announcements/BAJFINANCE_01-04-2024_30-06-2024.raw` | 30786 | `e0ed1483bbf66d742d04f5867b0cf2e717b30614da60b51200af87cf02b10b6d` |
| `corporate-announcements/BAJFINANCE_01-04-2025_30-06-2025.raw` | 30829 | `80f5aa25e20bba6b796a1424a539676166cd407ebee7944c238686d54f1cbc27` |
| `corporate-announcements/BAJFINANCE_01-07-2024_30-09-2024.raw` | 20034 | `5733afa02817a67128a5b35a1be73289b7a17e7855db14c9ba000030ccc6cb6e` |
| `corporate-announcements/BAJFINANCE_01-07-2025_30-09-2025.raw` | 27017 | `41f90157fef83e2633b1ca6b217a4eb3868d2afa004cb7157916a180954d5c52` |
| `corporate-announcements/BAJFINANCE_01-10-2024_31-12-2024.raw` | 17169 | `2e0713cf81ce89217213479059b16f4b43bc439077a77521434acc0b3e7930dc` |
| `corporate-announcements/BAJFINANCE_01-10-2025_31-12-2025.raw` | 16135 | `49b5de3f37c27fc9c1014336024e20206800107672ecafb612fd37acf16d48d6` |
| `corporate-announcements/BEL.json` | 128498 | `b0b6a0fc435265b46248d92b056da61b9bbab9026f141438b345bbcaf483531a` |
| `corporate-announcements/BEL_01-01-2024_31-03-2024.raw` | 14450 | `93e2db5dce827c6a0a6a70b6a8d85094428c29f3ad913a51d921a89877b34090` |
| `corporate-announcements/BEL_01-01-2025_31-03-2025.raw` | 18754 | `ea4874b8711e3800c14371e4f5311d773bc8529d468376dcc5068ccb5d9fe2cd` |
| `corporate-announcements/BEL_01-04-2024_30-06-2024.raw` | 11899 | `28453a4181edcedf4cdaf51ce4086cedb2a383bf763602ba155c19684d2da581` |
| `corporate-announcements/BEL_01-04-2025_30-06-2025.raw` | 17310 | `6c99bc47dce92c60be688a3ceddd3c9ca18f69f1e07b2b42d5c15672523b9f96` |
| `corporate-announcements/BEL_01-07-2024_30-09-2024.raw` | 16671 | `c4f9699a2906092c942e8095cf177446d29fd3ea1ceb79a310906c2d561d405d` |
| `corporate-announcements/BEL_01-07-2025_30-09-2025.raw` | 20507 | `8a435f3bb6c77554c40c9494328382d1105e2fb436e2ad42900d0a5cfa73fa89` |
| `corporate-announcements/BEL_01-10-2024_31-12-2024.raw` | 10923 | `cc84465c03c13d6a000369f985034e69e5d46f3016a7a3e8889dbde79b47c6ac` |
| `corporate-announcements/BEL_01-10-2025_31-12-2025.raw` | 10832 | `6ccf00610500c75f46e3e38abc718b3cbaae68963d968850a12a4d5895761de7` |
| `corporate-announcements/BHARTIARTL.json` | 503664 | `ebdc83b8f0b415682c76bdca994db1e7d9b71c2ba7afee7f3aa4e570ab75a8d1` |
| `corporate-announcements/BHARTIARTL_01-01-2024_31-03-2024.raw` | 95020 | `d2140cfcd451332987fdf5caf45cf42bc828d068431a85b03f142d158a0a1f84` |
| `corporate-announcements/BHARTIARTL_01-01-2025_31-03-2025.raw` | 48447 | `f36abb321f25f1ab1ead1275a61834a62873e5d4b3bfc17af39de1d65c05c209` |
| `corporate-announcements/BHARTIARTL_01-04-2024_30-06-2024.raw` | 90249 | `7d00f199ce511844778c42886308fe70dc326fc6978ba40a6c58cf6326c71490` |
| `corporate-announcements/BHARTIARTL_01-04-2025_30-06-2025.raw` | 31152 | `f05cedd60d765b14dc09568c19bd19bd0e7606e0cc397f55acb283106def0010` |
| `corporate-announcements/BHARTIARTL_01-07-2024_30-09-2024.raw` | 81942 | `76571afb2922fde52af525b0e4d4f8454d055a65ca0d0970fb1478a82acb4104` |
| `corporate-announcements/BHARTIARTL_01-07-2025_30-09-2025.raw` | 31659 | `be783d4692f705e77b16f5b47eb724502a554b5ad6b17388c282d061f7536176` |
| `corporate-announcements/BHARTIARTL_01-10-2024_31-12-2024.raw` | 62441 | `dc8cb3ba857b2a6bb11a381f3a4f2f79b381c7c0417855f9f889e7dbb788de5f` |
| `corporate-announcements/BHARTIARTL_01-10-2025_31-12-2025.raw` | 36162 | `318432fa4a49c83be62f25da86b61742ce281bc146252dab0501bd2eabf351c4` |
| `corporate-announcements/BPCL.json` | 202442 | `721f6a3e79444fab8443975ae5d54a38f56ffff21ad6b523fc41851b4592b6e1` |
| `corporate-announcements/BPCL_01-01-2024_31-03-2024.raw` | 23938 | `7f1ad37ff3fd9ce882e5ce4bc42b24e5a9d2feabda477ab1a693875a98d0d129` |
| `corporate-announcements/BPCL_01-01-2025_31-03-2025.raw` | 18203 | `23c9b52159ee970ba27fe1c82dc113dbcf751bfef5fde4fa0548c2b5a2637cac` |
| `corporate-announcements/BPCL_01-04-2024_30-06-2024.raw` | 32806 | `f241309e2e412ca827efe2cde612d5b35311353c6d412b8ffbddff4b6019c7f1` |
| `corporate-announcements/BPCL_01-04-2025_30-06-2025.raw` | 16939 | `2492f5b31280eb3e0677f446ffbc84b0c46310844233ee20bb4adf84f8c4de05` |
| `corporate-announcements/BPCL_01-07-2024_30-09-2024.raw` | 39446 | `cadee821c3d7b62f3b631d81ce0f6a25d3495da0d3af9f66002e37a0f1f5579e` |
| `corporate-announcements/BPCL_01-07-2025_30-09-2025.raw` | 19960 | `c190cc38c8d843be66ea5bb06f5a629ea6bd77633bf64d4ded8fecc4fe6459d3` |
| `corporate-announcements/BPCL_01-10-2024_31-12-2024.raw` | 24518 | `3724b095ea6da89a51adc711282a0db499ff3d59f9f583d379f1a576addcf3a7` |
| `corporate-announcements/BPCL_01-10-2025_31-12-2025.raw` | 15400 | `555991c5fe95a113ddeda6d6fabb5aa60c18e3eea30adf5c4754fc1b0a62ee27` |
| `corporate-announcements/BRITANNIA.json` | 159376 | `1ad6880dddcb383de8835a7ceeddf621597f07b10e4cc1f2920610b2c8800b3a` |
| `corporate-announcements/BRITANNIA_01-01-2024_31-03-2024.raw` | 12638 | `05fde1756cc236c8a0414b569584f3c1c0e32b9dba9dbd96a3b9f18e90db8e8b` |
| `corporate-announcements/BRITANNIA_01-01-2025_31-03-2025.raw` | 16033 | `8e57a09d513409e433680a8fdd08fb6e6b098c243d62744ef2e681897341de12` |
| `corporate-announcements/BRITANNIA_01-04-2024_30-06-2024.raw` | 18537 | `a137b54bd4053d49d38431f50f901e2d9d4951e2cab8474d3c872473653b3ef8` |
| `corporate-announcements/BRITANNIA_01-04-2025_30-06-2025.raw` | 19040 | `9c38ea359e22f974e4a7f175c478262a572590137c0f79972ee414cd882c16e2` |
| `corporate-announcements/BRITANNIA_01-07-2024_30-09-2024.raw` | 22533 | `52ead444b1fef6bff9f34415e52e3144cb9f442852cbe7161a2cd761b09a2d52` |
| `corporate-announcements/BRITANNIA_01-07-2025_30-09-2025.raw` | 23884 | `44bd15848611392f3cdc0fed365d0e139fb8d36749222864baa1b01b578948e2` |
| `corporate-announcements/BRITANNIA_01-10-2024_31-12-2024.raw` | 14822 | `690f8aff8a530f21491bccbde41c29227079169915d747046b4fe2792717cbfb` |
| `corporate-announcements/BRITANNIA_01-10-2025_31-12-2025.raw` | 24017 | `9dc3c35c8112726ed3883d71d2ddd699c0438b21f8ec29e6ece8689dd7191684` |
| `corporate-announcements/CIPLA.json` | 184377 | `09f33827d547f7125c6f479b4a4fc6d35b781939a43f82d2d5ab27d7eee4b7c0` |
| `corporate-announcements/CIPLA_01-01-2024_31-03-2024.raw` | 27574 | `d0d08fa08a9cc3e3d669cf2b3f5b0fcf189271d928d23b880cd8e9a94d990cfd` |
| `corporate-announcements/CIPLA_01-01-2025_31-03-2025.raw` | 15277 | `c01764fd34c295e7f04c31cb2006995cc0b73bbfd3c9084e035934d3e731617b` |
| `corporate-announcements/CIPLA_01-04-2024_30-06-2024.raw` | 31459 | `fc787e4e4028fc7d24e71437de7c34be80573f5a8af9ef1b40aa7c51442a8980` |
| `corporate-announcements/CIPLA_01-04-2025_30-06-2025.raw` | 25681 | `1ff7fdd236d5b9a3877597f91ecfbfd8c4d78931455fdac8aa6fd54ff7261ada` |
| `corporate-announcements/CIPLA_01-07-2024_30-09-2024.raw` | 25031 | `cedcb34b28b66db7c3bd193adad08590c1938901ad1092768eb4737f2fac025a` |
| `corporate-announcements/CIPLA_01-07-2025_30-09-2025.raw` | 19178 | `6bb5d4c7086d5aad7c1663f5f8e5a9f4497e58a0bd896a97b7eae99413510bf5` |
| `corporate-announcements/CIPLA_01-10-2024_31-12-2024.raw` | 14748 | `7652b95b7f29699abe4b0c258dc345cbc08273628aaa970a33811867bef43ea0` |
| `corporate-announcements/CIPLA_01-10-2025_31-12-2025.raw` | 14717 | `dfff9b94012c3f2ead7f267bd8f8d1d940be590966d59e631ae73c9ab7f3db34` |
| `corporate-announcements/COALINDIA.json` | 209788 | `8f2abaf074728ddc1ad705a4cca354eff5c9d1ebe4ac741306e81969b0426145` |
| `corporate-announcements/COALINDIA_01-01-2024_31-03-2024.raw` | 23015 | `f6b6816497e7b90061f0a54bbe0000798e1ebafcfc735ecdf51650a2a2721f0d` |
| `corporate-announcements/COALINDIA_01-01-2025_31-03-2025.raw` | 26813 | `6dfdcbd8eb7a7de0d2aeafa09a401688d252f14078cb4d293707813862c5b684` |
| `corporate-announcements/COALINDIA_01-04-2024_30-06-2024.raw` | 16617 | `53a49a94f29a9652772a6620e80493e799dcbf7e8351fd5ccf99df6513f11501` |
| `corporate-announcements/COALINDIA_01-04-2025_30-06-2025.raw` | 28585 | `533178d9557b3158e2d07f6d6914a3a843dee6cb54f2aa303676d09ccb0ecfe7` |
| `corporate-announcements/COALINDIA_01-07-2024_30-09-2024.raw` | 23594 | `2a0fa9db9a693cfc367e99902d34e830d1a96ed757c2d6863957d95d352c698b` |
| `corporate-announcements/COALINDIA_01-07-2025_30-09-2025.raw` | 35162 | `d279aab96186747d141c54133fb29edb3c5ddaede65ae578f49edbd85fc2f3c7` |
| `corporate-announcements/COALINDIA_01-10-2024_31-12-2024.raw` | 16026 | `11060930b815f5690d7f73a25e1c5f1891fc849c48c04dd05daafb79fef51324` |
| `corporate-announcements/COALINDIA_01-10-2025_31-12-2025.raw` | 28424 | `3281be58947e44625bfe1e09dfb2b0ac31aa6a3e3c06cc88b6d5550d2fae3f4f` |
| `corporate-announcements/DRREDDY.json` | 276243 | `6df9559e39b872ed4b73e2a30aaef9c8eb8d910d48cde9d04aa37da4f5327674` |
| `corporate-announcements/DRREDDY_01-01-2024_31-03-2024.raw` | 38499 | `101caa3f27e310233625913b6736ecd15ab5475a3593d3a73bbf26541a187570` |
| `corporate-announcements/DRREDDY_01-01-2025_31-03-2025.raw` | 21903 | `24e9cebdc906bb6bd452a6261099814a3ba8b44eeaa34b00358fb6f3f8d599e1` |
| `corporate-announcements/DRREDDY_01-04-2024_30-06-2024.raw` | 53939 | `00f279ac51ca4d3e54f7c14b892305a165c01bd44842d920c8b066be022c9c29` |
| `corporate-announcements/DRREDDY_01-04-2025_30-06-2025.raw` | 26389 | `9033a5968e184b649a493e4ac59e19cd973f89c40d62c847cca0cf776e4921bf` |
| `corporate-announcements/DRREDDY_01-07-2024_30-09-2024.raw` | 37565 | `769c3696959ddec0c4e589f3f78b7cdbfd51729d1fbb0f0c64b9007ffe51e8cf` |
| `corporate-announcements/DRREDDY_01-07-2025_30-09-2025.raw` | 28820 | `c3adc95f6d7838e35469fef1c6b20c3e2d953f2838858c11839ef38d257bbfad` |
| `corporate-announcements/DRREDDY_01-10-2024_31-12-2024.raw` | 30128 | `451da3b3fc55941a1cf91dd738d7c4a052f4b9b9db3de89af8d76e69ea6276f1` |
| `corporate-announcements/DRREDDY_01-10-2025_31-12-2025.raw` | 24008 | `8ccb2163beb840d2c77fccc26a73b928c7525c2654184a8d59a97d9928f08d21` |
| `corporate-announcements/EICHERMOT.json` | 256038 | `bc108b5ec4640db70cf5248a7c5b973e970b1c7fe3ae84f277673500b95a1553` |
| `corporate-announcements/EICHERMOT_01-01-2024_31-03-2024.raw` | 28174 | `a4fe57fed74cccbe5113530969d53f32c569f9114b0692cef804f629f5cca155` |
| `corporate-announcements/EICHERMOT_01-01-2025_31-03-2025.raw` | 29149 | `88f9dacb509f6bcccbc082945ab59e164a84f536a130751eaba545652d014d06` |
| `corporate-announcements/EICHERMOT_01-04-2024_30-06-2024.raw` | 40419 | `90a22d9a0cf50c3b66d33ccaa18a51a2dbffba551d7bee2509ee3ca050892d34` |
| `corporate-announcements/EICHERMOT_01-04-2025_30-06-2025.raw` | 22051 | `67bbc034d1faf4ce0775f831d1044d1bed7d473c78393bef2944f3e20265f42e` |
| `corporate-announcements/EICHERMOT_01-07-2024_30-09-2024.raw` | 40243 | `277cca5eec9a88619ec024c4bd39321094ec1defc6bb736930f200a5edf444c0` |
| `corporate-announcements/EICHERMOT_01-07-2025_30-09-2025.raw` | 31140 | `004057ac5bec24ede78bd0ab9e7596cd967775209eb693a0edb6fa644234feb2` |
| `corporate-announcements/EICHERMOT_01-10-2024_31-12-2024.raw` | 30542 | `e9f7995ae31e162100cfb6974d15683a13d2717299d392774ef199d27ac53e9e` |
| `corporate-announcements/EICHERMOT_01-10-2025_31-12-2025.raw` | 20528 | `43c6f66a089b095ea37c121319cd505f50ae054d914872cc75fd403a482a3fef` |
| `corporate-announcements/GRASIM.json` | 362915 | `78ba3cd0cd1481e7e6bad3c761a8714f40e0eef0f0c1c8864f5c0b60e9c16bdc` |
| `corporate-announcements/GRASIM_01-01-2024_31-03-2024.raw` | 66265 | `748f9c4b80dbb3fe647ffc7173c28651453bc74afcf23a6a293589bfc62fa8bc` |
| `corporate-announcements/GRASIM_01-01-2025_31-03-2025.raw` | 22189 | `cfb5d968fe9c39901838d603aee401d84b84a281cab16cdfa887c281ab56c88a` |
| `corporate-announcements/GRASIM_01-04-2024_30-06-2024.raw` | 65403 | `f693a5c26b6303403c25dfee799e6b945c90599f3c59f13b73ef1d8294ee682e` |
| `corporate-announcements/GRASIM_01-04-2025_30-06-2025.raw` | 25105 | `c8adc383652b3a63345b689d741795ef7561b2dee0369f8dae358051ab162c43` |
| `corporate-announcements/GRASIM_01-07-2024_30-09-2024.raw` | 58118 | `a0e4f7bf8bb7d1762d67f84ebff29d99e05f5b4703181370695158f309bbe8e7` |
| `corporate-announcements/GRASIM_01-07-2025_30-09-2025.raw` | 26931 | `0a6530ee2b02add64696d7f4b8908b860e73af7f01d99b70cb4ee4e2606b43d0` |
| `corporate-announcements/GRASIM_01-10-2024_31-12-2024.raw` | 55970 | `96cf508a40239372975d69d17bb3b083a15dfee00da24ee790e213519adc819e` |
| `corporate-announcements/GRASIM_01-10-2025_31-12-2025.raw` | 22462 | `e77e9c324ead6fb6a08196d858718d014d440e9df59d2fd2fb5c55b28f13b043` |
| `corporate-announcements/HCLTECH.json` | 286565 | `dfc1c85a0fff75c186b2a1655e548d78eec372a647df6c261425b40c83dbd19c` |
| `corporate-announcements/HCLTECH_01-01-2024_31-03-2024.raw` | 27542 | `9d69f06e236dfe4aedfbd74ad8133cdab63f50719633fab88448091a8ca48721` |
| `corporate-announcements/HCLTECH_01-01-2025_31-03-2025.raw` | 27989 | `f37c4560975aacda27ee459912d51466f2c8787b09c8cd7a99ba5f80fe8145c1` |
| `corporate-announcements/HCLTECH_01-04-2024_30-06-2024.raw` | 31391 | `9962569919f25487ef1b4911c3afa71563fdfd375a76bd278d397a03ebecbc4a` |
| `corporate-announcements/HCLTECH_01-04-2025_30-06-2025.raw` | 44248 | `be72cd1926ea6dbe00119a26359d6a3d34ca3d842f109073627396c92c863848` |
| `corporate-announcements/HCLTECH_01-07-2024_30-09-2024.raw` | 37109 | `5690221209fc8e11338de35c3edae39a3c9c553424fd8bc7414af31be19c0f62` |
| `corporate-announcements/HCLTECH_01-07-2025_30-09-2025.raw` | 35341 | `cb7f468c4860d2aa82074dd115ccf53ecf67e25253092a8b0927479d201bdfc0` |
| `corporate-announcements/HCLTECH_01-10-2024_31-12-2024.raw` | 29650 | `58877175fbfa70509359554db10202962d6a308d672445ad649132a20badc490` |
| `corporate-announcements/HCLTECH_01-10-2025_31-12-2025.raw` | 37583 | `8e488f13762b6b89c5fe88a64972e486a0818acae04de085018848cb538e682a` |
| `corporate-announcements/HDFCBANK.json` | 261660 | `387ca1581ed0da9fc43745d2b38afdcb44024062c5071e182457a877db721378` |
| `corporate-announcements/HDFCBANK_01-01-2024_31-03-2024.raw` | 43840 | `06235e71fb4a75fee97a1766bd4fbb520730f2dd5d2e42f790dd045f89ece955` |
| `corporate-announcements/HDFCBANK_01-01-2025_31-03-2025.raw` | 18318 | `d509f85af4f9cca4c190357cac32288ab1767ba082f28fc2195db5a463b43eec` |
| `corporate-announcements/HDFCBANK_01-04-2024_30-06-2024.raw` | 45229 | `ccfb5d0fb928008d87a7330767cb11da76d7b1a94e6dd8151d90113327714f0b` |
| `corporate-announcements/HDFCBANK_01-04-2025_30-06-2025.raw` | 21870 | `94bbc06ee335b92017fbcdcc409f466a60dc31a6526a0454b84974cca0bc70d8` |
| `corporate-announcements/HDFCBANK_01-07-2024_30-09-2024.raw` | 40523 | `72b05a1ce37c3ed4ac48b3abf83f961fe5fc2eb9ef83af8d21f43a30d1fe87ca` |
| `corporate-announcements/HDFCBANK_01-07-2025_30-09-2025.raw` | 26999 | `8be935702d83ea6ff7c6e86e7e6b7ff1e25613c63311338b3a16d6589d020212` |
| `corporate-announcements/HDFCBANK_01-10-2024_31-12-2024.raw` | 30716 | `6708f42179b1838e37cdb006fbccb01b383af4880008561eae4b7f761c0e1a81` |
| `corporate-announcements/HDFCBANK_01-10-2025_31-12-2025.raw` | 19053 | `b5040f8562ee8c4a9210a92a43939502f549b6ce86b9e8a8a8f79ff6430c28f7` |
| `corporate-announcements/HDFCLIFE.json` | 165035 | `f36d301f5237d9093fd16ad6d5aaba753e3621eb192c52d312a01c49555229ab` |
| `corporate-announcements/HDFCLIFE_01-01-2024_31-03-2024.raw` | 22100 | `7faceaba2450f4b86c13b4c5a7a10c46998ead6d4aac41198fd02caba22e1624` |
| `corporate-announcements/HDFCLIFE_01-01-2025_31-03-2025.raw` | 18173 | `23dff19e703311f25404c4d33b1fb1a55fd5616f7afa26444ed75089359ecc7b` |
| `corporate-announcements/HDFCLIFE_01-04-2024_30-06-2024.raw` | 28335 | `4893ad7cdbf08d73ce84f665f5600e9156aca00b464b60c5faed8fff60489fb0` |
| `corporate-announcements/HDFCLIFE_01-04-2025_30-06-2025.raw` | 14042 | `1397cf907fb80266878d21df83713c39e9f01ef3111a640c0b5dd653631b8c93` |
| `corporate-announcements/HDFCLIFE_01-07-2024_30-09-2024.raw` | 31195 | `0579ac3c6d9400fc30bd3d54f2c9c2762886f6ba46bb679690ee18ccc0830350` |
| `corporate-announcements/HDFCLIFE_01-07-2025_30-09-2025.raw` | 11587 | `3dc17c993186a43ead2405cc9e24767d7079dabdef31c1df86f7f754440c1452` |
| `corporate-announcements/HDFCLIFE_01-10-2024_31-12-2024.raw` | 18538 | `fb4d61b66939fc4c00a014a434fec9b595275019d9abb88c915a4542d07d6bce` |
| `corporate-announcements/HDFCLIFE_01-10-2025_31-12-2025.raw` | 11753 | `1fcc5062b3120bf157a942fba25dd4393eac7725ac923e0c7efcd84701049689` |
| `corporate-announcements/HEROMOTOCO.json` | 278825 | `cf51b600b57550e9bfbad802d70a8edad208bfe6575c87d551f7a8caf3e130e1` |
| `corporate-announcements/HEROMOTOCO_01-01-2024_31-03-2024.raw` | 34176 | `7d67af9526f3295e222b413e32778cc2cb414b81735df8bfb27d886e20baff17` |
| `corporate-announcements/HEROMOTOCO_01-01-2025_31-03-2025.raw` | 30486 | `24d1eb530248469233fe3872fbabbff022eb3f80614f6ccbfbaee139d6477b1f` |
| `corporate-announcements/HEROMOTOCO_01-04-2024_30-06-2024.raw` | 40139 | `2e9cb71dfa8cd7ade9933a66a939776f8ba21f8952a8cbe35405d90059622c68` |
| `corporate-announcements/HEROMOTOCO_01-04-2025_30-06-2025.raw` | 31761 | `ef2195d8ce728ab16d1016f3d2eb4c2ba094824071114e803848687d017fa5e7` |
| `corporate-announcements/HEROMOTOCO_01-07-2024_30-09-2024.raw` | 37474 | `b012fba75df4b07e55a88f1ee8540712ebc636dd87b005253f67ba37b5020dde` |
| `corporate-announcements/HEROMOTOCO_01-07-2025_30-09-2025.raw` | 30926 | `ba1b50d5d96fc759429fdc448d1c0d881ce144c4b1a7696873ace334a2d71124` |
| `corporate-announcements/HEROMOTOCO_01-10-2024_31-12-2024.raw` | 30424 | `8e0d010a76681e528debc7d05246aa17317e5a5134309717a12f7c409e2d5412` |
| `corporate-announcements/HEROMOTOCO_01-10-2025_31-12-2025.raw` | 29647 | `09637d2ca0c386e85d556ac9cfc0965174832b8a282153abafacb72bc2472e24` |
| `corporate-announcements/HINDALCO.json` | 263456 | `5ce2ee675692eac42533db2c6716ef9364f4cdf43f8d12dd1310b57de9cc7cc8` |
| `corporate-announcements/HINDALCO_01-01-2024_31-03-2024.raw` | 38365 | `cc5a54fe188c3e49ce52aacab1f495a203049bb3c0f97696f94f050d49361aa8` |
| `corporate-announcements/HINDALCO_01-01-2025_31-03-2025.raw` | 21873 | `b6a0ad086833677935aec8bbeae1992786d06eb6d79ce1a444994ecc564b99cc` |
| `corporate-announcements/HINDALCO_01-04-2024_30-06-2024.raw` | 33860 | `7581b223d39c1857bcecf91b54c66c1335c2c4c499cc9c877c9481296d36b0df` |
| `corporate-announcements/HINDALCO_01-04-2025_30-06-2025.raw` | 20861 | `a1f1e282e9792d72cec6f75f6dfe0128861ce95ac74bded0f94906fc7592145e` |
| `corporate-announcements/HINDALCO_01-07-2024_30-09-2024.raw` | 47934 | `a94009b640667823bd124d178fe8288b781752c56d37014bfa718d69f6ebb73b` |
| `corporate-announcements/HINDALCO_01-07-2025_30-09-2025.raw` | 24869 | `ae7ed15244205cc32e94f110cba8de206d556eca77af4a5a3b294a2d4b030714` |
| `corporate-announcements/HINDALCO_01-10-2024_31-12-2024.raw` | 35259 | `a8d46395d31f33f5acf5cde51779c6c574855125fd86b28abe77176a52d6baaa` |
| `corporate-announcements/HINDALCO_01-10-2025_31-12-2025.raw` | 25763 | `8e9b49af01d634e3da09d0db6b5d7e53eadef646f085a086b3dbd7f6e1e8b379` |
| `corporate-announcements/HINDUNILVR.json` | 239536 | `ef97ba7d862e82f0b2737b1c180ae20890888994a668f434e54c895331a03ede` |
| `corporate-announcements/HINDUNILVR_01-01-2024_31-03-2024.raw` | 34434 | `2c890ca3e6c1bab20bac9194b298af1b13fbaf262d5c4e9f667414baf425a3a5` |
| `corporate-announcements/HINDUNILVR_01-01-2025_31-03-2025.raw` | 17015 | `b8a17d2161f047fca6f523375a7f08b6f7a735235ce5b16a35dc4efd4b67af1a` |
| `corporate-announcements/HINDUNILVR_01-04-2024_30-06-2024.raw` | 37812 | `ed888873298a3c71a9c5e3fa957e0d6d598b0137e8421ed320ba783dc7a057bb` |
| `corporate-announcements/HINDUNILVR_01-04-2025_30-06-2025.raw` | 20373 | `75af57b20e8f5f0e0ab65e05b13a9e287a47d7889380e0cba60bee687a789d7c` |
| `corporate-announcements/HINDUNILVR_01-07-2024_30-09-2024.raw` | 30621 | `1db1bb3997f439a2aae638b7f929b1429f7237f8991c1c32c493ae5f9c05bb25` |
| `corporate-announcements/HINDUNILVR_01-07-2025_30-09-2025.raw` | 25315 | `0c1886b5f16b38852eb57b9c854bd3412f0d928d17e71c3006ee2cb48f45044c` |
| `corporate-announcements/HINDUNILVR_01-10-2024_31-12-2024.raw` | 35878 | `507632e55676bc9b8c48655f7f44900164ef755be4f5b8144ad9e997dfeab567` |
| `corporate-announcements/HINDUNILVR_01-10-2025_31-12-2025.raw` | 24816 | `4d35785a709fdf99fbfb01c6c5740c669a0165eebc87fb3233e72ec234404b2d` |
| `corporate-announcements/ICICIBANK.json` | 567050 | `2d7ce30cdb90ff5ccdfb6a7e1be04002a10349f4a919afeabf8dae7ad80e0349` |
| `corporate-announcements/ICICIBANK_01-01-2024_31-03-2024.raw` | 100735 | `32e50731bf5f608da142d1086efd3459b557743c15cf79d226a5c032f1016a76` |
| `corporate-announcements/ICICIBANK_01-01-2025_31-03-2025.raw` | 45405 | `5c788c089e0fe603f7e12a00242a8de82077b3d07a2cef5ee768ddf17a16cdd5` |
| `corporate-announcements/ICICIBANK_01-04-2024_30-06-2024.raw` | 93952 | `cdf3139f3c6c9051f34b443deceb4bb44e1db42ab35977d364a2104a655f4d10` |
| `corporate-announcements/ICICIBANK_01-04-2025_30-06-2025.raw` | 39242 | `9ba6292ecc57da500045cfdf45d985cd0897e5bca5535be13ab37e87c3c7bd09` |
| `corporate-announcements/ICICIBANK_01-07-2024_30-09-2024.raw` | 92471 | `9d0efb18118f0419bd9415dbdcd849a4bddbfdf526aee4156e0cc523732e140a` |
| `corporate-announcements/ICICIBANK_01-07-2025_30-09-2025.raw` | 37710 | `733eb2fc3dcb284ff6bc6b2844d471f25435e28d121bb1f8f42bae3a33f42f4c` |
| `corporate-announcements/ICICIBANK_01-10-2024_31-12-2024.raw` | 87141 | `73fd382d127ab30533c7d221cff2bd029ee9d535a0d6f0703dae786e9378efce` |
| `corporate-announcements/ICICIBANK_01-10-2025_31-12-2025.raw` | 38442 | `9c797275c4c1264c1ee34114f288588512a4106c30c33b6afb92cd9102d68c26` |
| `corporate-announcements/INDUSINDBK.json` | 334651 | `b05929e205ab830820193ee92a37bcc4bb139072204a8e07670e2893f99aa8f4` |
| `corporate-announcements/INDUSINDBK_01-01-2024_31-03-2024.raw` | 56923 | `d61eaf46c57ca7a37574e138d1054c2d42f489e0dbc0a4049beeebede188d391` |
| `corporate-announcements/INDUSINDBK_01-01-2025_31-03-2025.raw` | 29285 | `7d31b75aed6c50bb132eb3707f0a694dee9313da5d8c61d7ab8cb8a68ca603a4` |
| `corporate-announcements/INDUSINDBK_01-04-2024_30-06-2024.raw` | 50846 | `81fa60bcaefa4ef900a8ba7b3fe7c48a78f3c4440ab7757b4cb7baa51e3dfffd` |
| `corporate-announcements/INDUSINDBK_01-04-2025_30-06-2025.raw` | 32250 | `a8d7040a948c69c0ec8fb878fdafbe445d017d293df25a084e3c58e7a2f0f757` |
| `corporate-announcements/INDUSINDBK_01-07-2024_30-09-2024.raw` | 53488 | `88bd6b84c2a8776c3470131299f7bee5108027e4631df3f9e04ca6b1f1c9ef67` |
| `corporate-announcements/INDUSINDBK_01-07-2025_30-09-2025.raw` | 36859 | `7f62cca2c382e2c2944343087703f6bcc1a46c7e61c395733c3dd8b6e33eea16` |
| `corporate-announcements/INDUSINDBK_01-10-2024_31-12-2024.raw` | 32885 | `24c83a3a68633bf04e46ed19e6449f212ccf572fd0e2c75a5e73dbafd639c3b4` |
| `corporate-announcements/INDUSINDBK_01-10-2025_31-12-2025.raw` | 23323 | `3c2aae6a2bfaf77322379c573feabd63199e859b80815696125ef272d3d2241b` |
| `corporate-announcements/INFY.json` | 371463 | `7ed82091ea86655a58f077a3a0bb00720372f1a049aee0fd0451f6fb90d4c79d` |
| `corporate-announcements/INFY_01-01-2024_31-03-2024.raw` | 44088 | `421586299a07565cf92fd5bc619862722450bc461b1a6065243eda619411b532` |
| `corporate-announcements/INFY_01-01-2025_31-03-2025.raw` | 33743 | `eea9efe69cd9cca5c48ba36eba95b261836199fb30c7b2a8406cc6e3f6dbae27` |
| `corporate-announcements/INFY_01-04-2024_30-06-2024.raw` | 61487 | `7f1b3c1c246fafc0c08ac16a9ea201de01adde0d47f65a2a0a92402279e3e3f6` |
| `corporate-announcements/INFY_01-04-2025_30-06-2025.raw` | 64777 | `4f9de9b065e30d573ec3a0cefd432e54a64cb85832ef12e6f0c57fe054ba1887` |
| `corporate-announcements/INFY_01-07-2024_30-09-2024.raw` | 39660 | `40cd4b52317dbe60bdd7c06a3ee29ead4ecebb66a9f5fe50353b64df9bf5a762` |
| `corporate-announcements/INFY_01-07-2025_30-09-2025.raw` | 34110 | `d18ec261595649ac632983cc51c67d5a5ed76aa9507ddb0427c3ebc29c2a872b` |
| `corporate-announcements/INFY_01-10-2024_31-12-2024.raw` | 37686 | `43fcceb1ea22b59af70438f1e7048d46ba41243e76dcae321d2616d266fac15d` |
| `corporate-announcements/INFY_01-10-2025_31-12-2025.raw` | 34760 | `a7feb38542152f0bf1ac6ec991f46e52431a886a2b9c8df2daa9c30596e1cd86` |
| `corporate-announcements/ITC.json` | 190040 | `b2abadea27ea234e7de189e322ca96810b29b5b3d96f4fcd9d96b4f47be36cbb` |
| `corporate-announcements/ITC_01-01-2024_31-03-2024.raw` | 30303 | `8c9b4b832774f8a65020c587d278526c1dc5a1888009f96ec937e08cbbe2b8a4` |
| `corporate-announcements/ITC_01-01-2025_31-03-2025.raw` | 16135 | `c309420d4c70906a94922cf3c5a485b9e760eb4ec81fa40a363441236342b07d` |
| `corporate-announcements/ITC_01-04-2024_30-06-2024.raw` | 25362 | `3b7bb93ebaa991c5fef05db57b475137750b168c007810a5881e6f9d531f02b4` |
| `corporate-announcements/ITC_01-04-2025_30-06-2025.raw` | 17566 | `3a0bbf5e3b6e5c7df603ad2516dbd04bcc8d45f10b294744ad091a860203a3d9` |
| `corporate-announcements/ITC_01-07-2024_30-09-2024.raw` | 33210 | `f323f79787d537e1f9961bb8bd672f9c911d75d059e8d03bf47ce4ddc0cbb236` |
| `corporate-announcements/ITC_01-07-2025_30-09-2025.raw` | 13718 | `3eaf041bbbd3f8a70de42fb5fd361ae4bd80fa37642104f56b8143e797e1f412` |
| `corporate-announcements/ITC_01-10-2024_31-12-2024.raw` | 28205 | `4268c6f6188a0b8433d5952a271c6aa4f56d1957478d9b95554f7f79ef9ff935` |
| `corporate-announcements/ITC_01-10-2025_31-12-2025.raw` | 14029 | `cccfad0651b4556a54685d035a0a1f30f6f87cfcb62760aad6c8f28ebd8dc655` |
| `corporate-announcements/JSWSTEEL.json` | 207640 | `f10f1b8b4be9a746665908105d05515b5dff143aabf8e559f1cea8daf7163a5e` |
| `corporate-announcements/JSWSTEEL_01-01-2024_31-03-2024.raw` | 21284 | `6c1de7766ffbdb27066611df673db890dab1cbddfd0c4dc11e606f4097fd48a6` |
| `corporate-announcements/JSWSTEEL_01-01-2025_31-03-2025.raw` | 25651 | `f6a9976100822384c1b9a902a317c0d10e051e8e1565a1f4140547021f4e09bc` |
| `corporate-announcements/JSWSTEEL_01-04-2024_30-06-2024.raw` | 22019 | `824c08ef8116d03a3335de3545744c4a3aaa2a86ccb0c58ec1221ce85b71da48` |
| `corporate-announcements/JSWSTEEL_01-04-2025_30-06-2025.raw` | 22870 | `dc626f80912f0be488695110e57a7fe4932154c6bcb3b8dd1492f39549096348` |
| `corporate-announcements/JSWSTEEL_01-07-2024_30-09-2024.raw` | 25098 | `15d0666aaa39d61142ace19b24494e55f16e84eb3455ca9e9ba2bf9a5033f4bd` |
| `corporate-announcements/JSWSTEEL_01-07-2025_30-09-2025.raw` | 27299 | `e222107a98e5408668b096569e06710f0a41924c05977de10807ccc4bedda4cb` |
| `corporate-announcements/JSWSTEEL_01-10-2024_31-12-2024.raw` | 29709 | `0d8e2169e534924b1f604f45c55169861380fbb9dedfb47a8d6b373eea1d27bc` |
| `corporate-announcements/JSWSTEEL_01-10-2025_31-12-2025.raw` | 22238 | `85baf0fa1e3694fc9790326969f0736e02e8674441490f784052d60d9ff3e63e` |
| `corporate-announcements/KOTAKBANK.json` | 255523 | `ed20e6e91d836b0ed6fdb6802752b75b426ab0f02fe50533cf4dbf453e92ee07` |
| `corporate-announcements/KOTAKBANK_01-01-2024_31-03-2024.raw` | 44330 | `1bfccd09d5484ee6f046e92d94e2736ed8d66602fc05a44f006c974c81d7bb34` |
| `corporate-announcements/KOTAKBANK_01-01-2025_31-03-2025.raw` | 27078 | `8ff392127c888d88e2d8cbf7fbc39f23b8f27abcc65c5dfac1af5280023cf184` |
| `corporate-announcements/KOTAKBANK_01-04-2024_30-06-2024.raw` | 33506 | `82ee2881a1612724088ae50d76a14f8d3fe92c486dda60531511a147c551b6fe` |
| `corporate-announcements/KOTAKBANK_01-04-2025_30-06-2025.raw` | 23767 | `f77e68ae0db838b2bcf2c41bf5977affd948bd234b2d1d07c7824be2a77e80f7` |
| `corporate-announcements/KOTAKBANK_01-07-2024_30-09-2024.raw` | 32578 | `917fd95126be1fe3896a1893c057821a756425ef5a72926146aa85e8888d3c5b` |
| `corporate-announcements/KOTAKBANK_01-07-2025_30-09-2025.raw` | 29478 | `abfcf2853f43cce2140ab0d6e1243ab61d5b800290d7940b104ba4fdcd55590a` |
| `corporate-announcements/KOTAKBANK_01-10-2024_31-12-2024.raw` | 19795 | `bbbe19102007948af1147bfb9be1ebe22db4ae401195901033654c164b1c1db1` |
| `corporate-announcements/KOTAKBANK_01-10-2025_31-12-2025.raw` | 31399 | `4b04ca68763abd763b12aca2558c7734c7ed48e99bed49697fca8251a9778341` |
| `corporate-announcements/LT.json` | 256966 | `585ae688f46a586a976a23366f0b5b268548ef3a5d850be9735751e0d083cd1e` |
| `corporate-announcements/LT_01-01-2024_31-03-2024.raw` | 41215 | `c5111be05cbad83475ecca09d2f3b65157417e02a526e83ef770c0850cf4d217` |
| `corporate-announcements/LT_01-01-2025_31-03-2025.raw` | 27130 | `130acfc3cc9675e7f0f5f0accb8a77f41fbc00c4dcfc4c33cf37b1abeb768284` |
| `corporate-announcements/LT_01-04-2024_30-06-2024.raw` | 38620 | `1f17974c436eabc0f7c5218b49d855e8544ebb7ea703ab643e5de1553bfb2703` |
| `corporate-announcements/LT_01-04-2025_30-06-2025.raw` | 27901 | `530aff61ce5241aac0c48e2c9fe0c35f506307f04f3733a9d0e7b061e16ebd3d` |
| `corporate-announcements/LT_01-07-2024_30-09-2024.raw` | 34164 | `7fd3d7f71d71f63bf84dea299f1c12a8712767494adb1235196d693932fa1124` |
| `corporate-announcements/LT_01-07-2025_30-09-2025.raw` | 24930 | `c62ed113dd83b9e360d04be26ab1768a3e1ac810c1eb8310ff36a71d257210ab` |
| `corporate-announcements/LT_01-10-2024_31-12-2024.raw` | 23997 | `9987896553fef71a82d0a7552a4a89094e419accb32a6adc3dae896891aad81c` |
| `corporate-announcements/LT_01-10-2025_31-12-2025.raw` | 24537 | `91ab8de3acaa6cc2b935451db8ca0aac8154b2ff9a2a75cb56750c0701756838` |
| `corporate-announcements/M&M.json` | 480404 | `d18ad359dd0abfa32627c9a71b6b2d2cdcfa8ed1279deeedb70f00d7e2c46425` |
| `corporate-announcements/M&M_01-01-2024_31-03-2024.raw` | 60552 | `e3492617d2a6a011cf6d79afbee3af4b7ac3bfb444ddfb46647932576ecef7a0` |
| `corporate-announcements/M&M_01-01-2025_31-03-2025.raw` | 37006 | `b915cf299d0d421165a8fd6991d9a23aa765fd5e9d7842c93dc0f619b6f8b205` |
| `corporate-announcements/M&M_01-04-2024_30-06-2024.raw` | 72200 | `1976fa2c639a652898d693b813cf249ea55fee700143d3351ec3c624d31248a8` |
| `corporate-announcements/M&M_01-04-2025_30-06-2025.raw` | 57662 | `6401481fc0cc928425f47c8bec5fce3ca60d8718c1c0c831d44ea3f568c7c2a2` |
| `corporate-announcements/M&M_01-07-2024_30-09-2024.raw` | 70181 | `0058e81af73e9405ffec6e3bd2392d823b03c693d3ab24de48a08cdd26d765e6` |
| `corporate-announcements/M&M_01-07-2025_30-09-2025.raw` | 55677 | `bc613a0520188f56d5f2fa6b474a9b81ff9cb59001683688fa87a909066d8fa9` |
| `corporate-announcements/M&M_01-10-2024_31-12-2024.raw` | 51664 | `eeae3a510b290405b1816315778570a7ad6966624117d4a7da9dd5e505b2dcd3` |
| `corporate-announcements/M&M_01-10-2025_31-12-2025.raw` | 49510 | `7e2d5251b41328d0e00f8f4e7242df64526b1a39dff5e0859fbac686df011ba8` |
| `corporate-announcements/MARUTI.json` | 251110 | `034e49a47d6d33e134737d458a4afbb0da5ddd9c68422b6c33c4f52ddea52160` |
| `corporate-announcements/MARUTI_01-01-2024_31-03-2024.raw` | 38191 | `13f44557a746d3ddfc08c964d37b72018f3cf23cbdc2792f8657ab55ea9efce8` |
| `corporate-announcements/MARUTI_01-01-2025_31-03-2025.raw` | 28421 | `61b586085b0b574a8b4f229d4a809d781ba85f4f4ccce2003ad7ae85a2e5ec00` |
| `corporate-announcements/MARUTI_01-04-2024_30-06-2024.raw` | 23988 | `154e25ea72b7609908f3ce7903f39ffbe2b572d9c2766db402b88851e33f94ad` |
| `corporate-announcements/MARUTI_01-04-2025_30-06-2025.raw` | 29946 | `dfe526fc7802ccef5c1d8fff5f27604684c392f0a9e967dbdf38897d9584a902` |
| `corporate-announcements/MARUTI_01-07-2024_30-09-2024.raw` | 31360 | `f0c526253e944dfae3ab86105b833040c33f802994b085cd6bcf0053b9d5f97c` |
| `corporate-announcements/MARUTI_01-07-2025_30-09-2025.raw` | 36690 | `deb5a4d49fa5608438ae2a0f8b765da885626c5d0500d5faf579d602a1ed583a` |
| `corporate-announcements/MARUTI_01-10-2024_31-12-2024.raw` | 22418 | `6c42a478c98afbf31f9a91871207de384b368a033d83eec9053b52b3b7c96fed` |
| `corporate-announcements/MARUTI_01-10-2025_31-12-2025.raw` | 26664 | `d5d7a71e704ec89d9580906ba994556dacc115584e7fa78febfd6ea320126dbb` |
| `corporate-announcements/NESTLEIND.json` | 195143 | `012e65533a0741bfb6cf638f6be483c9c2f5e7ff0780c466f5cada3c43c73295` |
| `corporate-announcements/NESTLEIND_01-01-2024_31-03-2024.raw` | 19853 | `6a244e040549fb711e31db09b3e0863dae7a4ea61d25610c5a2439c8d0ba1d0a` |
| `corporate-announcements/NESTLEIND_01-01-2025_31-03-2025.raw` | 17238 | `c7fcf4616aef28b381adcdf22d20513dc9f2435deac28298bae6dc3f0c61639b` |
| `corporate-announcements/NESTLEIND_01-04-2024_30-06-2024.raw` | 41869 | `715b51723a741875d6a8fd4f58b2ac3cf3d3042a7ea69ff1ac0106adffd55892` |
| `corporate-announcements/NESTLEIND_01-04-2025_30-06-2025.raw` | 23555 | `ed9488fdc70bd861b38987a346cbea7895ac3ad36796d030cf4a0d62bbc5f144` |
| `corporate-announcements/NESTLEIND_01-07-2024_30-09-2024.raw` | 14736 | `69b0d78a8bc545dbae3c2d8efea548125c2988811e80c0915e77a307fed1f887` |
| `corporate-announcements/NESTLEIND_01-07-2025_30-09-2025.raw` | 29730 | `d80f238bc261e0c489489342b4309da8dcaf0d5322fa69c321ca1ee30c6d5d79` |
| `corporate-announcements/NESTLEIND_01-10-2024_31-12-2024.raw` | 15232 | `a53a41de3f2d27ae711b135ad7086d2d1bc17c967ee1dd4438d9d5af7ba87175` |
| `corporate-announcements/NESTLEIND_01-10-2025_31-12-2025.raw` | 22778 | `4c81c44c1845cf2d22816ebf4eeda5050641daaacf9239a060e8734c3e720c7c` |
| `corporate-announcements/NTPC.json` | 238054 | `25eb5ef66d315f74085620ad7188a5df191285201115c252e7d2caf782133baa` |
| `corporate-announcements/NTPC_01-01-2024_31-03-2024.raw` | 25329 | `d8b05c5299a11fbf1d799429726ac3c0a5fa1560c541ae477709b9598630dd38` |
| `corporate-announcements/NTPC_01-01-2025_31-03-2025.raw` | 28296 | `36a5f510cef9aa8f7525a010312613e0e0347323f2390ece3afc6befbf10b14a` |
| `corporate-announcements/NTPC_01-04-2024_30-06-2024.raw` | 26585 | `123771af6bca3b6d03391b733677e762304954696f0acb88a2f5336d3d68709c` |
| `corporate-announcements/NTPC_01-04-2025_30-06-2025.raw` | 31114 | `3952135288cba49495b55cd32760f364e36cbf4d019fd8f1549d019e1fc3f0b7` |
| `corporate-announcements/NTPC_01-07-2024_30-09-2024.raw` | 26563 | `95bdb1d8902f13b34a9083f4eecd44fa77be73176aa57ed2154710eb6e2aadb2` |
| `corporate-announcements/NTPC_01-07-2025_30-09-2025.raw` | 37706 | `d9165160cf0184b0624b6187648a35e9a5143bf7e7d38c0d68c9c92b757d01d7` |
| `corporate-announcements/NTPC_01-10-2024_31-12-2024.raw` | 21226 | `5f132ce10ee3ea8a88a306152ccea30684db03f14eb21d52c1ced9bfa46d77d7` |
| `corporate-announcements/NTPC_01-10-2025_31-12-2025.raw` | 27883 | `3e5d0dd07066da8b4202d26bacbc44a6daeb1989c69a92bff845a6e275f366de` |
| `corporate-announcements/ONGC.json` | 197908 | `4be513f6d77ecdbef460e82555a80cc163ac00ee97f1abb3656f4a0aa748dcc3` |
| `corporate-announcements/ONGC_01-01-2024_31-03-2024.raw` | 30193 | `b013e80a941fabef3cd7ac4ab1a4bad99e6cb06e4e386bd034cc6b38259c03d0` |
| `corporate-announcements/ONGC_01-01-2025_31-03-2025.raw` | 32979 | `022ef921c4c43b8a04da0fd61e9b185139ba8ef96ae304baedac2cb346e83446` |
| `corporate-announcements/ONGC_01-04-2024_30-06-2024.raw` | 15286 | `73a41d96da85a039bbe0d0fa426782c23a9469b73a2f4be7caf853a8fae3a37f` |
| `corporate-announcements/ONGC_01-04-2025_30-06-2025.raw` | 16892 | `4873d4764cad16f7a545129c9617f033a023d0c2ea714a7538a47af49c53cc42` |
| `corporate-announcements/ONGC_01-07-2024_30-09-2024.raw` | 31256 | `c9133ef86d24f2292051eaa516100a22881331d6da3be60c2d85c1338ac80459` |
| `corporate-announcements/ONGC_01-07-2025_30-09-2025.raw` | 25241 | `e535ea323c3ca950d11ed962b872367c43a39d6c2a2b7a0a97ec35c4c71a7665` |
| `corporate-announcements/ONGC_01-10-2024_31-12-2024.raw` | 15149 | `d28276bff358c1c04687e63cf554eedc6f69ae6d626e98ebb534ecb205ed812f` |
| `corporate-announcements/ONGC_01-10-2025_31-12-2025.raw` | 20360 | `6fb3e578aad0c3691e0f4191892f0cf2255dcb31ae4c5b6621bda0cee2ff4717` |
| `corporate-announcements/POWERGRID.json` | 219458 | `57ca89a944772c3d9909c9858a3bc2bba796a840a30276ef48d29a2f60c974c6` |
| `corporate-announcements/POWERGRID_01-01-2024_31-03-2024.raw` | 23280 | `0dcd3c30cc248f3e3669da12788c2e59c1a28b7298dbf8d02e023a89bd24a67b` |
| `corporate-announcements/POWERGRID_01-01-2025_31-03-2025.raw` | 28104 | `9550ac5bc22347fdadb82c12a2d798c8089863dfc4da92f8b429398c720b6455` |
| `corporate-announcements/POWERGRID_01-04-2024_30-06-2024.raw` | 24632 | `80b77ec2e1f7fe3bdf02f327ab40bd57e0a258b45c2a6c38d1b49fdba3a82e5e` |
| `corporate-announcements/POWERGRID_01-04-2025_30-06-2025.raw` | 24098 | `8eced181d3840e020862e1beb2dcfee19c6142b6c58e72cfa467eed4feb04471` |
| `corporate-announcements/POWERGRID_01-07-2024_30-09-2024.raw` | 29408 | `5ec0703b3a5f6c4eb8846fc6395ef89c749cbf625e747db669ba6b8350d610b4` |
| `corporate-announcements/POWERGRID_01-07-2025_30-09-2025.raw` | 26413 | `ea59e04063d8c0dc09b89fcff0ed0e8ba97340958dd097d393576f84cde9171c` |
| `corporate-announcements/POWERGRID_01-10-2024_31-12-2024.raw` | 32213 | `79433fe291ea786a0d24653f1318d932e4ea045ead4522e613526147e97d76e3` |
| `corporate-announcements/POWERGRID_01-10-2025_31-12-2025.raw` | 19558 | `e99b67013d44379b94bb460aa6d0f43738a5012495232716caaa05a4e3a46071` |
| `corporate-announcements/RELIANCE.json` | 517056 | `7a6f92157decbecd874100b8711f7668dd4ab22588293149980139dcbcdabd46` |
| `corporate-announcements/RELIANCE_01-01-2024_31-03-2024.raw` | 89603 | `760be7b6f41b9332daa4d6dc02ebb05a88822c780c9ba99dcc42fa9cc961c0ce` |
| `corporate-announcements/RELIANCE_01-01-2025_31-03-2025.raw` | 26155 | `b13b118cb49effb51e0b4727768668f6c8069c84f827e502443997a06a5b3fd0` |
| `corporate-announcements/RELIANCE_01-04-2024_30-06-2024.raw` | 92178 | `415826b088d8a7b850443f4296186c507dca17989a0af6e2f6bcb48cbd795d8b` |
| `corporate-announcements/RELIANCE_01-04-2025_30-06-2025.raw` | 34818 | `58f3979e236bf979868c00454b07aa5847c69b629aeea51d5c77691232941144` |
| `corporate-announcements/RELIANCE_01-07-2024_30-09-2024.raw` | 105585 | `803cd83f6b1c53d0fc96431670f056ab678b6a05512edaa18a26b8e22dd6e595` |
| `corporate-announcements/RELIANCE_01-07-2025_30-09-2025.raw` | 35432 | `dd740480bd4978dac0e858e606e1c058453059e000fea098eba8f9e2231f72a0` |
| `corporate-announcements/RELIANCE_01-10-2024_31-12-2024.raw` | 84083 | `40d91d4c20a3f601bdc208abb40761bb02e27ae8729ea203831c9038891ead80` |
| `corporate-announcements/RELIANCE_01-10-2025_31-12-2025.raw` | 26770 | `b3c9604a5a73226d5dff7ccea7190d115931416af1ad922ef8fba2836fe7b6ce` |
| `corporate-announcements/SBILIFE.json` | 159950 | `323b0bf80065f04a60a38c6f5365103deb37476731864326318c7ecf1d45116c` |
| `corporate-announcements/SBILIFE_01-01-2024_31-03-2024.raw` | 20123 | `f1b560d20c5b4a93cbc1799c5e797f99627f0ef0ba16323dabcc82da00426076` |
| `corporate-announcements/SBILIFE_01-01-2025_31-03-2025.raw` | 27210 | `4139f98b14265cbb1a6f8b96acd38484dad85c8c99fefb278d17ac9f5392d931` |
| `corporate-announcements/SBILIFE_01-04-2024_30-06-2024.raw` | 16510 | `4ba78478185d03fefb12ad3ab64c70a25fba3241c573f7a232864354036a90b1` |
| `corporate-announcements/SBILIFE_01-04-2025_30-06-2025.raw` | 9029 | `a622259c34d5d06ca73b09b505f201a73cbc1f1a2ab0aa6e320ed2dab2d86156` |
| `corporate-announcements/SBILIFE_01-07-2024_30-09-2024.raw` | 33009 | `4dd360cbaec4144357376a297bac547b8a6aa125534061bb19bfe27ae618c504` |
| `corporate-announcements/SBILIFE_01-07-2025_30-09-2025.raw` | 16398 | `5b5691b58f396e162b761eec63ad0a8f5cec99f47e83feb9ed3ea66b9a63266a` |
| `corporate-announcements/SBILIFE_01-10-2024_31-12-2024.raw` | 15734 | `0046fc214120c439772bd58cdffc041b20c7c9bf392df750bb88952b791b2588` |
| `corporate-announcements/SBILIFE_01-10-2025_31-12-2025.raw` | 13105 | `92d4d55922e84f886631a3e5892ab3ee21d1e89397f205c91729b32ae6a8458b` |
| `corporate-announcements/SBIN.json` | 327789 | `086ea1da34b450df172e181cc684f98f2676bf344dafd02586a912ef3474a7a6` |
| `corporate-announcements/SBIN_01-01-2024_31-03-2024.raw` | 48623 | `12335ecf820a8437e330ee010bcefebf0caee3739d47cd1d49a62aa666cc65c4` |
| `corporate-announcements/SBIN_01-01-2025_31-03-2025.raw` | 29706 | `47d80b4bcabcabbcbac782ec2db9d82172f08fa46da31ced0670923a207d2aed` |
| `corporate-announcements/SBIN_01-04-2024_30-06-2024.raw` | 46380 | `0b429ef22f0e496c3b5d831e15b731c8171850bc1e9b3db3180a880415d205be` |
| `corporate-announcements/SBIN_01-04-2025_30-06-2025.raw` | 44182 | `a93bc89b8e61fac25ca0093248d3f05f24c6a63d4822e0c3e2f3a67432accbb3` |
| `corporate-announcements/SBIN_01-07-2024_30-09-2024.raw` | 44899 | `3b0ade80e138426054e9614cc3773942308a4aa0d2a802f7277dbd52e754b65c` |
| `corporate-announcements/SBIN_01-07-2025_30-09-2025.raw` | 31613 | `6b27792b7da05bbcd4b37fd9153ef910a7df22add1f8136c65af17f1a3bf22e9` |
| `corporate-announcements/SBIN_01-10-2024_31-12-2024.raw` | 34224 | `c915dd08e564651657c75765fa9ea8f1a3ad21321d75ec6af6b84a1b5b1dc667` |
| `corporate-announcements/SBIN_01-10-2025_31-12-2025.raw` | 29050 | `ef7a7318e221c1a12ce4d2f284d54dd203ccf1c01400e9d9c78a82d593b12b58` |
| `corporate-announcements/SHRIRAMFIN.json` | 630673 | `b301f756093d7e3d1532beeedf2ded0bc0f7182c4132724f6272cb15c077a68f` |
| `corporate-announcements/SHRIRAMFIN_01-01-2024_31-03-2024.raw` | 100882 | `42fe719a9af423744c12b09a5efffd9d7f6fa1f4acb6d225728f1038a33274ab` |
| `corporate-announcements/SHRIRAMFIN_01-01-2025_31-03-2025.raw` | 60000 | `e138286bcc870fb3e1a7a827b559dde3f1a08bbe9ff80d08507b2a816929abbd` |
| `corporate-announcements/SHRIRAMFIN_01-04-2024_30-06-2024.raw` | 100765 | `185145a0bc40cd55f665806a6cde9876e3a1a775528a2ec868dd3659f4a4a252` |
| `corporate-announcements/SHRIRAMFIN_01-04-2025_30-06-2025.raw` | 65601 | `f091016d9c1ad05c492e99111d66bd3331f414805c354f1905e606e12245fc79` |
| `corporate-announcements/SHRIRAMFIN_01-07-2024_30-09-2024.raw` | 83238 | `47f353f2e6c6eddf860a06b67b3c1b0ce5f46634aecdae49bdee6e28ad2162ec` |
| `corporate-announcements/SHRIRAMFIN_01-07-2025_30-09-2025.raw` | 61298 | `6ec9e99c541cb60e2b97d8d3f2fbe6a542b7f0ecc7413e03461d9f5a6fbadc97` |
| `corporate-announcements/SHRIRAMFIN_01-10-2024_31-12-2024.raw` | 62097 | `4be15d70e1d8bed8d1efc722efa554df78bd4c5f6de52d923d187d97d1181b14` |
| `corporate-announcements/SHRIRAMFIN_01-10-2025_31-12-2025.raw` | 61240 | `63ffc0433d6a7f80b5c202a184d90b925ce1c611483f23019ff90251ee6c4d7f` |
| `corporate-announcements/SUNPHARMA.json` | 218758 | `d17e0ed951ea47230f0ba4022963dba2ad2d59c1be727e1a9df7b2ef0ea21ac2` |
| `corporate-announcements/SUNPHARMA_01-01-2024_31-03-2024.raw` | 30453 | `f7c17cce1b47a57b36c3435d92a19fed9b1b904e2dc88c0e6ccd7809cd2a605c` |
| `corporate-announcements/SUNPHARMA_01-01-2025_31-03-2025.raw` | 19149 | `a27088ca55b03a6d6cca53f648287659c01f659a2cdcc24c588e0e74d02bbfe2` |
| `corporate-announcements/SUNPHARMA_01-04-2024_30-06-2024.raw` | 35557 | `872ad69f848d96e0db457609fbfd53731f973726413cf25f59ec8a400f7a96aa` |
| `corporate-announcements/SUNPHARMA_01-04-2025_30-06-2025.raw` | 19038 | `9d5318a8509adee7813ab4a7c70bb55f0177dbe98ef10ad3673f505b4e888987` |
| `corporate-announcements/SUNPHARMA_01-07-2024_30-09-2024.raw` | 40287 | `f44d5ae2a6ca6cf4b31743e136c94afb0eb99978ebf49f1a14f8aff4b8c959ba` |
| `corporate-announcements/SUNPHARMA_01-07-2025_30-09-2025.raw` | 19555 | `70f4994b58efee54ac3aef8f91125b3275e2c40ecbd8c75ac0891e4efda6626e` |
| `corporate-announcements/SUNPHARMA_01-10-2024_31-12-2024.raw` | 26582 | `60db62051c9aab46931871827b052384deb721423f01789c6a35a157e189788a` |
| `corporate-announcements/SUNPHARMA_01-10-2025_31-12-2025.raw` | 16625 | `6885beca55ae80b8f6a1c5eaa4ec5c5c9bdf55ae2997123d063e58d61e39145b` |
| `corporate-announcements/TATACONSUM.json` | 218623 | `f3fac63c54bd54b3e3615747619afa226b59a57b9474c459c93c5aa684c0f80c` |
| `corporate-announcements/TATACONSUM_01-01-2024_31-03-2024.raw` | 24111 | `4abc2baf85219387b97bfa349d8ad7150b470d70d12343b9105a6cdef0b551c0` |
| `corporate-announcements/TATACONSUM_01-01-2025_31-03-2025.raw` | 18026 | `09982ca77411ff586112ef44655b593042e471dc5a916bbaa5081e298008f973` |
| `corporate-announcements/TATACONSUM_01-04-2024_30-06-2024.raw` | 34737 | `09126840971f5769cf44d164657d25849f7603bb2d4c0b1a9edf053ca6d67dd0` |
| `corporate-announcements/TATACONSUM_01-04-2025_30-06-2025.raw` | 26318 | `39f80cdbda1665e3b8b0ffdb4f2c575e048ba9ad5ad41aa5490c169059ab6d32` |
| `corporate-announcements/TATACONSUM_01-07-2024_30-09-2024.raw` | 38714 | `42d9dd672b18ab823958d5826b44eb961b539ec5aaf76791f75703c78c6aac8a` |
| `corporate-announcements/TATACONSUM_01-07-2025_30-09-2025.raw` | 15696 | `e723305b3f67e1024bea19e1ec5767d5da32a342eec422b9e84ce1f5ff68e47e` |
| `corporate-announcements/TATACONSUM_01-10-2024_31-12-2024.raw` | 32384 | `9399a2b667d45ea1b6815d3d82c1c36b52367602edee8e5d6f8ca3e08954038e` |
| `corporate-announcements/TATACONSUM_01-10-2025_31-12-2025.raw` | 16445 | `9e1bdb39d42a6368baaec8eaad93bbd7bdd52f4c0c95db59d803f42eac674a84` |
| `corporate-announcements/TATASTEEL.json` | 403193 | `96228821d1354ee74fffae5e940697c287a1dc6a7c495da298bda2c94e465ccc` |
| `corporate-announcements/TATASTEEL_01-01-2024_31-03-2024.raw` | 73110 | `eda965a183b970100519d15dc655ce38809c42a6c8103a5c51e35241268d636d` |
| `corporate-announcements/TATASTEEL_01-01-2025_31-03-2025.raw` | 19928 | `bf7be8a481cc63972b72c2989637732f2e27aaa985eb9a975839daff1cd39759` |
| `corporate-announcements/TATASTEEL_01-04-2024_30-06-2024.raw` | 72174 | `e495d2c8fa93df855ce6ec98b4148ced6b1748cfe7c0947b69468ae736ed1c58` |
| `corporate-announcements/TATASTEEL_01-04-2025_30-06-2025.raw` | 33083 | `d70f21c3f2b1bb51e9eddf5d61869b34cf4bba38927d02ce2832775d18efc6b7` |
| `corporate-announcements/TATASTEEL_01-07-2024_30-09-2024.raw` | 76493 | `3346f79b31e1202640e73370b8b7811321a97b55982230b08ab8dd421b26f9f3` |
| `corporate-announcements/TATASTEEL_01-07-2025_30-09-2025.raw` | 28137 | `88cacfaa5587739ab1123794b4b189ef6497f8dd022cefe13b683f0cbea3e02c` |
| `corporate-announcements/TATASTEEL_01-10-2024_31-12-2024.raw` | 48279 | `31f6cabf54a707ce700883bc5664f27c9620e4ae093bedb02d656fa9c40152e2` |
| `corporate-announcements/TATASTEEL_01-10-2025_31-12-2025.raw` | 28717 | `51ff67dd3fa196f271a540ccba9ee242a9747ffb02be9a5778c8c1157beeb543` |
| `corporate-announcements/TCS.json` | 287602 | `df12948eefeb4c2b320611016c8f28e18d63aa33e9f234a9c8d7b5dedd2324c6` |
| `corporate-announcements/TCS_01-01-2024_31-03-2024.raw` | 29314 | `2e2d192f37963be765593b18f2b9279c2e709fb71f48223f07f1fe7f23b7f3f1` |
| `corporate-announcements/TCS_01-01-2025_31-03-2025.raw` | 27981 | `464a66471dce004ad00fbfb64528a733aca3cc1166d6f3c2bd5167099171377b` |
| `corporate-announcements/TCS_01-04-2024_30-06-2024.raw` | 40082 | `5e78c2a9cbb5b0d9ad0839c0bf2a5d695817029f80456a3fd8efd361c3c03dd3` |
| `corporate-announcements/TCS_01-04-2025_30-06-2025.raw` | 37305 | `cb89f3c4a0c6001754d1c1ddfef3d8c36e30c9a1e88f2a5ff3b8f7206e85156a` |
| `corporate-announcements/TCS_01-07-2024_30-09-2024.raw` | 32263 | `34d2d44f38cf3bc8eaf48218978c8c4292b82266afd1e5799eec2f364ef65340` |
| `corporate-announcements/TCS_01-07-2025_30-09-2025.raw` | 30672 | `562c726973c1511ff1012bb517066381409621dc66b8ac0ff6bb3e2e41ecaff1` |
| `corporate-announcements/TCS_01-10-2024_31-12-2024.raw` | 33067 | `85cb6b84b41966f3bf8b88d77e581f44f53f5b367a415ae2f2d3ceb982c083fd` |
| `corporate-announcements/TCS_01-10-2025_31-12-2025.raw` | 41446 | `b21291fc721dba0692bd33d5890cedf9092c2b09ed344f062ef87d5eb6885338` |
| `corporate-announcements/TECHM.json` | 200839 | `5ae84c89acdb928214a2e7e3e40fa80a7ec17852f640901de9f3ed4db8140fd1` |
| `corporate-announcements/TECHM_01-01-2024_31-03-2024.raw` | 18030 | `1945057b105a8ab4671a72956c4e5cbf75b8c1c56a7af60d5840882c527e7a74` |
| `corporate-announcements/TECHM_01-01-2025_31-03-2025.raw` | 14854 | `20d934e03eb85b312ffd700c4ab5bae93deabf6fdaad418e5e09aaab1f0dcaf1` |
| `corporate-announcements/TECHM_01-04-2024_30-06-2024.raw` | 29622 | `011b104521d4e69e5f1d9cbee780db9255515cf2440a29b9db3179eb134b4a0d` |
| `corporate-announcements/TECHM_01-04-2025_30-06-2025.raw` | 26687 | `42afa74ec442d44dad2d875a25ed2ee93fc62719ca3452c87eb47ef8560c00b7` |
| `corporate-announcements/TECHM_01-07-2024_30-09-2024.raw` | 24686 | `78b90b992f3892ccde548fd02423d15ca7e24420c0741df13a23a69d4b2b4d82` |
| `corporate-announcements/TECHM_01-07-2025_30-09-2025.raw` | 27586 | `802e29cba7e9851c940ff5d89e9aa2f3e0c091184960a9d2a6368daf680e1ced` |
| `corporate-announcements/TECHM_01-10-2024_31-12-2024.raw` | 22999 | `c68f5153e0b96674278296ef1c4bbf18168a694b24601a643517f74c793f36b8` |
| `corporate-announcements/TECHM_01-10-2025_31-12-2025.raw` | 25263 | `953cd579fc8be4aa85cff07c67ece934745ee172e4a3cb82450f6d190931bd6b` |
| `corporate-announcements/TITAN.json` | 214198 | `c123463819220ffae3d054d24228e8e75923916aee3fad8b44e91ce33231d0bf` |
| `corporate-announcements/TITAN_01-01-2024_31-03-2024.raw` | 29749 | `dafcdf5ca6a492585b1edcbfae05ea50bd84b3818d218e45c9eebf3108e4d47b` |
| `corporate-announcements/TITAN_01-01-2025_31-03-2025.raw` | 14005 | `46b7ecc7b5acf4786c5d2264889eb2f39089db32651f5066148e859c7183ed7f` |
| `corporate-announcements/TITAN_01-04-2024_30-06-2024.raw` | 36519 | `2f538e3485b1729dca54db2cc5888e19ff5481d73284e687ade1bff6cc245bda` |
| `corporate-announcements/TITAN_01-04-2025_30-06-2025.raw` | 22828 | `fdc7adf4dc3dea6322b0826f07e18553782d1c291223ebeee7266e418c55f44d` |
| `corporate-announcements/TITAN_01-07-2024_30-09-2024.raw` | 32650 | `794e090a4f1e9444daa109374e46ed50d5536b67cd6e1c7f6da2f1255e65e8ba` |
| `corporate-announcements/TITAN_01-07-2025_30-09-2025.raw` | 24950 | `ddff24bbc083173901883434f7ad93e9c3e7baa1a8851dd772e41d22e154232d` |
| `corporate-announcements/TITAN_01-10-2024_31-12-2024.raw` | 23422 | `5972925aa549f0f9ed7214a0cec1e6f9f0254e4845d8efa5c77df241900269a7` |
| `corporate-announcements/TITAN_01-10-2025_31-12-2025.raw` | 18043 | `6d61ff2b23473d906b20363734cc9fe027cea75886b401d6ef261f295c4de5a4` |
| `corporate-announcements/TRENT.json` | 249222 | `ad6ae153b8d8d5dad0848cce69c81916c41c5fb34c8bfe958d5ecd8eeda8c018` |
| `corporate-announcements/TRENT_01-01-2024_31-03-2024.raw` | 15829 | `6302cc25464a239860ea9821549b4520c6badbd68564f28d9e3dfec900bb247a` |
| `corporate-announcements/TRENT_01-01-2025_31-03-2025.raw` | 21780 | `29b030e1a886c9de7dfd9e281cab661f8c9ca1c18eee4815d943c2970effdbc0` |
| `corporate-announcements/TRENT_01-04-2024_30-06-2024.raw` | 52110 | `d0e83ad62d240214adf66ad8aec948d00ff8d79dfdea6c1baf24296a83f58611` |
| `corporate-announcements/TRENT_01-04-2025_30-06-2025.raw` | 21672 | `899454213467840964b939f6230c70203873f4cf50896bcfe02d29ac75008af2` |
| `corporate-announcements/TRENT_01-07-2024_30-09-2024.raw` | 47451 | `ec3640f00c07d7b2de67bdc3919e52c89a0ae0f5b5251592dfc5afe891c78503` |
| `corporate-announcements/TRENT_01-07-2025_30-09-2025.raw` | 20823 | `76049fa62c617390a127c73daa340c27a6c81890dc028ebb71bc198e3b40fbf3` |
| `corporate-announcements/TRENT_01-10-2024_31-12-2024.raw` | 38767 | `ea46ecb2cbedc397b6b225a9318bcc092ddcc8eac10cba9bb531017c4e7e77aa` |
| `corporate-announcements/TRENT_01-10-2025_31-12-2025.raw` | 18998 | `1aae433140f51a622ddd06aab98f079458f45f9ab7ac0775c88bd6018960251e` |
| `corporate-announcements/ULTRACEMCO.json` | 334673 | `a224365579b863990c5045692320fd19e3bbcc7779f54e018ed3318f9b83370d` |
| `corporate-announcements/ULTRACEMCO_01-01-2024_31-03-2024.raw` | 47763 | `ab9bf80c05dc44fdd7e313256a46653c99e2c2bde505115d26adb86d610ce2f7` |
| `corporate-announcements/ULTRACEMCO_01-01-2025_31-03-2025.raw` | 41387 | `7e78ce83999ce59bf4fffb4ea53017dd3493774bdfa1c19efdf99446fd98574b` |
| `corporate-announcements/ULTRACEMCO_01-04-2024_30-06-2024.raw` | 51567 | `e3c6c76d8e73efc204aa131e95e2bc2393857f7de318da887588ead8f72cc21b` |
| `corporate-announcements/ULTRACEMCO_01-04-2025_30-06-2025.raw` | 23904 | `a40b4c75fe8fbb4f03bbbf7f105110da72cfdebe87036a747134c8215aa79729` |
| `corporate-announcements/ULTRACEMCO_01-07-2024_30-09-2024.raw` | 57077 | `3d92ddc13fdd57f082a2e21f76a3f016037e639e58c5c82a165b500ed0120d17` |
| `corporate-announcements/ULTRACEMCO_01-07-2025_30-09-2025.raw` | 27462 | `01a6fc8346534e6dfc42643c3223e44656623abc394bb071ba1075b423916fd9` |
| `corporate-announcements/ULTRACEMCO_01-10-2024_31-12-2024.raw` | 42561 | `9af4c187b068e844e04e04d9d3dda7508978494384d1fc7a67b6826e5827ab06` |
| `corporate-announcements/ULTRACEMCO_01-10-2025_31-12-2025.raw` | 24200 | `9476c844334935ec9447d2cbcb6e9ddbf4e4e10f0e8153d991bdced6c138aa29` |
| `corporate-announcements/WIPRO.json` | 343873 | `32c4f717524ab690ffe3118f5d9e392239b0024a6da1d11c48e1fcb63a8c66a0` |
| `corporate-announcements/WIPRO_01-01-2024_31-03-2024.raw` | 35998 | `11d56eb3a0fb97703304661acc2cb5bbfc09178356f4c8c278e26ef83748f2f3` |
| `corporate-announcements/WIPRO_01-01-2025_31-03-2025.raw` | 43907 | `36245e5d49a02ddd32486cdf9b089149e4e74b988788cc8f5ed9f1e0fdb04d73` |
| `corporate-announcements/WIPRO_01-04-2024_30-06-2024.raw` | 59706 | `d79c85a15db3eda3289faaa6e68eb3b63040171ab2069057d0f4c60afaacb3be` |
| `corporate-announcements/WIPRO_01-04-2025_30-06-2025.raw` | 35474 | `ce82b537cb9b34e23e98e30a453c6f160b64e14d0c50f4f2c30fde4a60bfc42a` |
| `corporate-announcements/WIPRO_01-07-2024_30-09-2024.raw` | 36878 | `0f5786331a8d4c40fe1c34b6620299d3dec145c4ffc0971f94cb0bf23d73e4ec` |
| `corporate-announcements/WIPRO_01-07-2025_30-09-2025.raw` | 33868 | `142fc601bb08e8dee8cc9014085684512b64ecb322922e3149a07f02b022f26a` |
| `corporate-announcements/WIPRO_01-10-2024_31-12-2024.raw` | 49670 | `a1932cd267896f94ddb7577f9acb45cee016921bca0812506f4a91533bf1ad95` |
| `corporate-announcements/WIPRO_01-10-2025_31-12-2025.raw` | 30700 | `f374d9de470c2e1332eb93fb1f27cc5090db7da92d4b0dc753f9799e6cf6e4b9` |
| `fetch_log.json` | 87397 | `183fa158744971403e8d04728920cd0008c71cfa3951b93344c36dade5951b04` |
| `financial-results/ADANIENT.raw` | 123492 | `003fb396b38b67620ef68aba596717d21641e0df117299e433fcc6b2e42fbbcf` |
| `financial-results/ADANIPORTS.raw` | 99679 | `a5a4a98413b9247675676ff8ddc890dd6ddeb2edb8f1e5ed833a55e04ce38ce7` |
| `financial-results/APOLLOHOSP.raw` | 83684 | `27307764765f212675bb6fd1781e8559eced5c450d7a52ed0df7bd3ed5bf7c06` |
| `financial-results/ASIANPAINT.raw` | 127812 | `c574686007d43377d785c420b7e251fecdb34b4f824105857fcce1503579b160` |
| `financial-results/AXISBANK.raw` | 77489 | `a7eb33ec072f3045959704803a62914c8834c1286004721a6363e89cfcd5016e` |
| `financial-results/BAJAJ-AUTO.raw` | 85934 | `6c3b422fc75c656535fe03e8602168a70917c8b51fa12d538d4919c89f1e48c9` |
| `financial-results/BAJAJFINSV.raw` | 105095 | `114fcc05248e77961856b092f02ec4d234fdf2c7a15da8ee6fcaf524d5458d80` |
| `financial-results/BAJFINANCE.raw` | 84998 | `6b23ff2c2b8790351aec1a6fde1cf160292b574082e39fa53224953c321d0f8e` |
| `financial-results/BEL.raw` | 81834 | `508afc353b7d7fca9598453e18ed852b89a7f623ac3d338c936f41fb5b73beb3` |
| `financial-results/BHARTIARTL.raw` | 106220 | `ccad5e4320a8c01add81cf62009f9933c56a8972be302f4fe27e4b484f0e3885` |
| `financial-results/BPCL.raw` | 84665 | `80ef00baf3666194207c59e6f2353b44ac072c9c1b8010ed89914fb2c4b1566c` |
| `financial-results/BRITANNIA.raw` | 101638 | `de3d620dcfca21a24698f13f9650b52fabdad8e71de7a80efa44f4a29a7b4829` |
| `financial-results/CIPLA.raw` | 101569 | `03e53a4efa1cb18b5a086badfc7626fad688e25ef40b481d8943c8a1c38d4427` |
| `financial-results/COALINDIA.raw` | 93821 | `21093e2b670682d6c5d63776d15282799f9df4f92b2119c737d2134b7e3fc86e` |
| `financial-results/DRREDDY.raw` | 107797 | `04ab4870b28cbf5c657cf91fe8aa2d3bced6c7d427660620fb5c45787702c12a` |
| `financial-results/EICHERMOT.raw` | 119435 | `61f99d727fc9f62ca8ca4d3014848168405b9e6719acb051e23b56e0dca33715` |
| `financial-results/GRASIM.raw` | 127537 | `a42301d9414a01c8eb4be389ef9934adc657191d5ea19504e487882ebafc432a` |
| `financial-results/HCLTECH.raw` | 91910 | `68346ba40e4c9f87f6248487cbc51309ffaac090bb9914a2a8c417ae9b2b63d2` |
| `financial-results/HDFCBANK.raw` | 79047 | `6eb918bdac37aba23950b11b34352a0b2266f6637533851bc98dd73a1a1c0531` |
| `financial-results/HDFCLIFE.raw` | 2 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `financial-results/HEROMOTOCO.raw` | 83195 | `5944e0714751211dbe187c227fef8765dfa538ea1cebfcc6cfdf697a54988a36` |
| `financial-results/HINDALCO.raw` | 82415 | `bde211cf831e5f05eaf44be7c6c2aa06f408e49996983e972f8bd5948a576c81` |
| `financial-results/HINDUNILVR.raw` | 82975 | `ae63d1eeab4b2b51d2e58d6afc1174785b388d3bfac5fa193f98e02e4cbd7f01` |
| `financial-results/ICICIBANK.raw` | 88669 | `4e1df093c60fc8fef4a8ed0f1f3e1bf1940586c937a4920e77b10a13b00a17fe` |
| `financial-results/INDUSINDBK.raw` | 78376 | `eccab86dbe04d4cc828e9ebbc0e60fb033380825832cc104631dfd642ca8c170` |
| `financial-results/INFY.raw` | 108132 | `2d1e248a0b55eab66ed36fa833349c65a94d61db372646f52f4c5a1d1e822c60` |
| `financial-results/ITC.raw` | 80168 | `fec6d4e1270e31ae3ec4f0a67b219b2fd509b4127630e0198a73329936f97837` |
| `financial-results/JSWSTEEL.raw` | 122923 | `73cdb2cfd47d9e714495458ad506c415e29a32fdf61f4bd55b862a6b42eac047` |
| `financial-results/KOTAKBANK.raw` | 124433 | `f7875e86c1e479ac753d0367d47da55a47a7150ac88e2136b5487c3de19c4f9e` |
| `financial-results/LT.raw` | 98465 | `82a7e65f0734ccb829ab477f89b55e089c84dd26af9305f4985f377d39c5c249` |
| `financial-results/M&M.raw` | 81848 | `67ae24f3e65fc702bcfbb20dd38eef01718c568eef484c3df08ff7e99b7a0808` |
| `financial-results/MARUTI.raw` | 83450 | `a3cfc9156706a1521212ba72b5a7837e90f1a1cf52f62e7f40416828e3a2ce32` |
| `financial-results/NESTLEIND.raw` | 6879 | `4507329dce5044f3509caee465008b2ed881404e33b183ae2c5cd4f94228dc4b` |
| `financial-results/NTPC.raw` | 81223 | `af61691a79277de46ac7e649f9a6d62dd7c74a75bb9bde7f6792ec4e31b6cdb7` |
| `financial-results/ONGC.raw` | 82483 | `235e28c1bbe83240e653fcab7690d89b2a5fb6a95a333cb374d5d7772eb6f269` |
| `financial-results/POWERGRID.raw` | 74077 | `e2271fd6cc334cf5aa7fd30bf06587ed5f4fa04fbd207ba7f706be84b863b254` |
| `financial-results/RELIANCE.raw` | 101760 | `ddcc87095ecb31bf94df441c84bfbe073790fa89f694c231f29e8aab8ccd051a` |
| `financial-results/SBILIFE.raw` | 2 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `financial-results/SBIN.raw` | 110541 | `12d01f461fbe90670e28b6976fb9991d88ca9c2345fe7b919db96a66ecbb9495` |
| `financial-results/SHRIRAMFIN.raw` | 94158 | `b0c87cfe5213f95ba2d27d28b8e827e03ec212a6d38bbd53534d328c851e7c65` |
| `financial-results/SUNPHARMA.raw` | 129274 | `c260c71d691c9ae4cf5122613ddaa919c543fc367f3feabc6b22d6870b349ebe` |
| `financial-results/TATACONSUM.raw` | 123238 | `35fc145fc5986fa0e8db2c807878aec8bdaf800c34566359f1f56b155549ddc0` |
| `financial-results/TATASTEEL.raw` | 120531 | `6f8f908e824eef2dc5afe42a72749e1d2a44ba97a92b4f0bc105f9f1e6d5428a` |
| `financial-results/TCS.raw` | 124738 | `746a848759b266faeec6de9ec011be11488e4fedda635146b3f3e2748e2be3f5` |
| `financial-results/TECHM.raw` | 113785 | `a16ac5a6f6bd5920842ef2dea94a45148755c15f8a578cfd2fb537c842a6e87d` |
| `financial-results/TITAN.raw` | 87955 | `66b7befee97bd7c4b1dc1896caa6be33c5f7def8b1f859481616990c350588ba` |
| `financial-results/TRENT.raw` | 77977 | `38323b92032dc8e7dfcee7bce3d9d019a615c5c0373de7e39df06a90b85e568c` |
| `financial-results/ULTRACEMCO.raw` | 100411 | `ff1e1477c2f6405e468a6b2accd0d708b91283fae6432003c8d0d8150fc95064` |
| `financial-results/WIPRO.raw` | 101298 | `e73fca826d1f7aebbbab0b8b75f75ec520ec2d19520f7f8e5e18805abc338a0a` |
| `retrieval.json` | 1384 | `123670b11f58d378388f06e23df119838eb6123faf73304e6c35bc10e6b91023` |
