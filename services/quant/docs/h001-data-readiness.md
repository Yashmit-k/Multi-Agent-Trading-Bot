# H001 PIT Data Readiness Audit

**Task 3 (documentation reconciliation only).** This revision does **not** open raw announcement JSON, parquet, ZIP, `retrieval.json`, `audit_stats.json`, or the parquet manifest. It does **not** recount rows, recompute hashes, run classifiers, download data, access holdout, freeze target/features/horizon, train, or backtest.

**Status (current, supersedes Gate 2 §13):**

`DATA NOT READY`  
`BLOCKED_PRECONDITION`  
`READY_TO_RUN = NO`

- `MARKET_DATA_READY` (unchanged; snapshots not modified by this task)
- Event source: NSE corporate announcements (a freeze was acquired at Gate 2; see historical findings below)
- Event dataset: frozen candidate under gitignored `datasets/` (not committed)
- Gate 2 **PIT conclusion `DATA READY` is withdrawn**. Historical statistics and field notes from Gate 2 are retained as **reported findings**, not as independently verified facts of Task 3.
- `H001` modelling: **not started**

---

## 1. Source

**Primary:** National Stock Exchange of India — corporate announcements JSON.

- UI: https://www.nseindia.com/companies-listing/corporate-filings-announcements
- API: `https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY&symbol={SYMBOL}`
- Attachments: `nsearchives.nseindia.com`

**Auxiliary (not merged):** NSE financial-results JSON (`/api/corporates-financial-results`). Used only to inspect `toDate` / `oldNewFlag` / XBRL links. Values in that table are a **live vendor extract**, not a vintage of restated EPS.

**BSE `DissemDT`:** not pulled. Provenance would stay separate if added later.

Fixtures, Yahoo, FMP, RSS, and period_end were **not** used as `available_at`.

---

## 2. Retrieval details

Historical Gate 2 retrieval record (not re-verified by Task 3):

| Item | Value |
|---|---|
| Retrieval start (UTC) | 2026-10-10T14:02:37Z |
| Retrieval finish (UTC) | 2026-10-10T14:17:43Z |
| Method | HTTP GET, browser User-Agent; NSE homepage returned 403; announcements API returned HTTP 200 with cookies |
| Coverage requested | 49 snapshot symbols × eight calendar quarters, 01-01-2024 … 31-12-2025 |
| Calls | 392/392 announcement slices HTTP 200; 49/49 financial-results HTTP 200 (`HDFCLIFE` and `SBILIFE` bodies were empty `[]`) |
| Raw store | `datasets/h001-nse-raw-20261010T140237Z/` (gitignored). Each slice saved as unmodified `.raw`; per-symbol concatenation as `.json` |
| Universe file | `snapshots 2/nifty50/1D/manifest.json` (`nifty50_1d_20261005`); 5m manifest agrees on the same 49 names with bars |
| TATAMOTORS | Excluded (`count = 0`). Not substituted. Not a coverage hole for the 49-name bar universe |
| Holdout | Not accessed |

---

## 3. Dataset version / checksum provenance

| Item | Value |
|---|---|
| Raw freeze id | `h001-nse-raw-20261010T140237Z` |
| Historical digest | `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` |
| Digest status | **UNVERIFIED**; **recipe unknown** |
| Normalized (gitignored, not committed) | `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` |
| Manifest | `datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json` |
| `dataset_version` | `nse-ann-2024-2025-v1` |
| `schema_version` | `1.0` |

The hex `b0f4760f…` is a **historical identifier** recorded at Gate 2 as “SHA256 of named raw/json files.” This repository does **not** document which files were included, path sort order, path encoding, or byte-stream construction. No checked-in hasher reproduces it. Task 3 did **not** recompute hashes and does **not** invent a recipe.

The same hex also appears (Gate 2) as `sha256_of_named_files` in `retrieval.json` and as `SHA256` on the parquet manifest. That is **copied identity**, not three independent integrity proofs. It must **not** be treated as a verified digest of parquet bytes or of any ZIP archive.

A separately authorized, reproducible recipe and new measurements are required before any digest can be called verified. Do not mutate this freeze; any real integrity baseline is a **new named measurement**, not a silent replacement of `b0f4760f…`.

---

## 4. Coverage (historical Gate 2 report)

The following figures are **Gate 2 reported findings**. Task 3 did not recount them.

Announcement API date filters were reported as **18,235** rows, all mapped to the 49 names, all with `exchdisstime` inside 2024-01-01 00:00 IST through 2025-12-31 23:59 IST.

Results-like rows were reported as **3,690**. Gate 2 described this as subjects matching `result` / `financial` / `earnings` / XBRL flag. The stored `audit_stats.json` field `results_like_kept: 3690` used an **undocumented predicate**. **3,690 is not re-verified by Task 3.** See §15 for the proposed classifier to use in a later authorized audit.

Financial-results auxiliary (historical): 5,844 rows in the live tables; **453** with `exchdisstime` in-window across **47/49** names (`HDFCLIFE`, `SBILIFE` empty on that endpoint). **Not merged** into the announcement parquet. Do not infer 49×quarter coverage from this auxiliary table.

---

## 5. Universe mapping

Rules: strip, uppercase, strip documented `.NS`. Map only onto the 49 manifest strings. `BAJAJ-AUTO` and `M&M` kept as those strings.

Historical Gate 2 report (not re-counted here):

| Metric | Count |
|---|---|
| Mapped symbols / 49 | **49 / 49** |
| Unmapped | 0 |
| TATAMOTORS in extract | 0 (never requested) |

NSE `symbol` on rows was reported to already match snapshot strings.

---

## 6. Timestamp fields (Gate 2 recorded)

Observed on announcement rows according to the Gate 2 write-up (Task 3 did not re-inspect rows):

| Field | Role as recorded at Gate 2 |
|---|---|
| `exchdisstime` | Offset-naive `DD-MMM-YYYY HH:MM:SS`. Gate 2 labeled this Exchange Dissemination Time. Task 3 treats that label as a **candidate proxy**, not a proven first-public-print clock (see §7 and §16) |
| `an_dt` | Broadcast / announcement datetime (same format); typically a few seconds before `exchdisstime` (`difference` e.g. `00:00:06`) |
| `sort_date` | Sort key (`YYYY-MM-DD HH:MM:SS`), aligned with `an_dt` |
| `dt` | Compact id-like stamp from broadcast (`DDMMYYYYHHMMSS`) |
| `difference` | Broadcast-to-dissemination lag |
| Retrieval time | **Not in the NSE record**; only in `retrieval.json` |

Financial-results (auxiliary): `exchdisstime`, `broadCastDate`, `filingDate` (minute precision), `fromDate` / `toDate` (period), `financialYear`.

No scraper timestamp was copied into `available_at` (Gate 2 claim).

---

## 7. Timestamp semantics

| Concept | This extract (Gate 2 + Task 3 overlay) |
|---|---|
| period_end | **Not** on the announcements feed. On results rows: `toDate`. Fiscal close. **Forbidden** as `available_at` |
| announcement / broadcast | `an_dt` — Gate 2: when the filing hit NSE’s announcement bus |
| publication / dissemination | `exchdisstime` — **candidate proxy** for an exchange dissemination clock; **not** proven first-public or tradeable time (Task 3) |
| retrieval | 2026-10-10 crawl. **Not** availability |
| revision time | No populated `old_new` on announcements (Gate 2). 69 rows whose text matches `/revis/i`. Results `oldNewFlag` is `N` or null on that pull |
| availability | Gate 2 set `available_at` from `exchdisstime`, not period_end, crawl time, +N hours, or session open. Task 3 does **not** certify that mapping as PIT-correct |

Timezone: strings are offset-naive. Gate 2 **tagged** them as `Asia/Kolkata` (`+05:30`) and kept the original string in `exchdisstime_raw`. That is a **documented convention**, not verified source metadata and **not** RFC3339 inside the vendor JSON.

Authoritative NSE field dictionary and historical immutability of `exchdisstime` for 2024–2025 rows: **unresolved** in this repository. BSE `DissemDT` was not retrieved. See [`h001-source-audit.md`](../../intelligence/docs/h001-source-audit.md) (Exchange Dissemination Time as strongest **proxy** among free/official candidates; immutability unproven).

---

## 8. available_at validation (Gate 2 rule; not recertified)

Gate 2 rule: `available_at = parse(exchdisstime)` as `Asia/Kolkata`. Rows without a parseable **date and time** would be discarded. Gate 2 reported every announcement row had `exchdisstime` at second resolution.

Not used: `toDate`, `filingDate` as first print for 2024 PDF-vs-XBRL lag, crawl time, midnight, session open.

After-hours and pre-open disseminations were stored as-is (Gate 2). No session adjustment.

Task 3 does **not** re-validate those counts or prove dissemination = first public knowledge.

---

## 9. Revision audit (historical)

Announcements: `old_new` was null on sampled full-symbol files; **69** text-flagged revision-ish rows kept as **separate `seq_id`s**. Prior values are **not** overwritten in this freeze because every API row was appended (Gate 2).

Financial-results `oldNewFlag` did not expose an Original/Revision series (`N` or null). `reInd` takes codes `N/-/A/I/F` without a documented first-print EPS history.

**Limitation (still current):** you can replay “which announcement ids existed with a stored `available_at` <= t” only as **Scope A**. You cannot reconstruct restated **line-item values** (Scope B) from this freeze alone.

---

## 10. Duplicate audit (historical)

Stable key: `nse_corporate_announcements` + `seq_id`.

Identical extra copies: **0**. Non-identical same-id groups: **0**. (Gate 2; not re-counted.)

---

## 11. Discarded rows (historical)

Announcement feed (date-filtered by NSE), Gate 2 table:

| Reason | Count |
|---|---|
| missing available_at | 0 |
| naive timestamp (date-only) | 0 |
| untrusted timestamp | 0 |
| invalid timestamp relationship (`an_dt` after `exchdisstime` by >2s) | 0 |
| unmapped symbol | 0 |
| duplicate | 0 |
| outside 2024-2025 window | 0 |
| other | 0 |

(Offset-naive IST tagging is an assumption on **kept** rows, not a discard bucket.)

---

## 12. Coverage summary (historical Gate 2)

Not independently verified by Task 3.

| Metric | Value |
|---|---|
| Total announcement rows in | 18,235 |
| Kept rows | 18,235 |
| Discarded rows | 0 |
| Symbols covered / 49 | **49 / 49** |
| First available_at | 2024-01-01T09:04:57+05:30 |
| Last available_at | 2025-12-31T22:09:34+05:30 |
| Duplicate count | 0 |
| Revision-ish announcement rows | 69 |
| Results-like kept | 3,690 (undocumented predicate) |

---

## 13. PIT conclusion

**DATA NOT READY**

`BLOCKED_PRECONDITION`  
`READY_TO_RUN = NO`

Gate 2’s conclusion that the freeze is PIT-ready because `available_at` equals NSE Exchange Dissemination Time is **withdrawn**. A freeze exists; checksum recipe, dissemination semantics, immutability, 49×quarter results coverage, and restatement-safe values are **not** established by this documentation pass.

Do not train H001.

---

## 14. Exact blockers

1. Historical digest `b0f4760f…` is **UNVERIFIED** (recipe unknown). Integrity is not proven.
2. `exchdisstime` is a **candidate proxy**, not proven first-public-dissemination time; IST is a convention; immutability **unresolved**; BSE `DissemDT` not pulled.
3. No authorized 49-symbol × 8-quarter coverage table under a frozen classifier; historical 3,690 is undocumented.
4. Scope B (restatement-safe earnings **values**) is not established.
5. Target, features, horizon, decision time, and entry price are **not frozen**. This document is **not** that protocol approval.
6. Holdout remains forbidden (`snapshots/holdout_after_20261005` not accessed).

---

## 15. Proposed results-classifier specification

**Proposed rule for a later authorized audit. Not validated. Not run in Task 3.**

Keep a row if **either**:

- `hasXbrl` is true; **or**
- `desc` matches the case-insensitive regular expression `result|financial|earnings`.

The later audit must report counts **under this exact rule** and separately list ambiguous categories or likely false positives. Do **not** silently change the rule to improve results.

Historical `results_like_kept: 3690` used an undocumented predicate and is **not** a count under this specification.

---

## 16. Required 49-symbol × 8-quarter coverage audit (procedure only)

**Do not generate this table until separately authorized.** Task 3 specifies output only.

- **Universe:** the 49 snapshot symbols with `count > 0` in `snapshots 2/nifty50/1D/manifest.json`. `TATAMOTORS` (`count = 0`) is excluded and must not be substituted.
- **Quarters:** 2024Q1 through 2025Q4 (eight IST calendar quarters).
- **Covered cell:** at least one announcement that satisfies §15 **and** has a parseable `exchdisstime` falling inside that calendar quarter.
- **Missing cells stay missing.** Do not impute events or timestamps.

Required report columns / notes:

- Covered vs missing symbol-quarter cells
- Results-class rows with missing or unparseable `exchdisstime`
- Symbols with zero qualifying announcements
- The IST timezone **assumption** and the unresolved `exchdisstime` semantics limitation (§7)
- Ambiguous categories / likely false positives under §15

The historical financial-results endpoint remains **auxiliary-only** and incomplete (Gate 2: empty arrays for HDFCLIFE and SBILIFE). Do not merge it into the announcement dataset or infer coverage from it.

---

## 17. Scope A vs Scope B

**Scope A — announcement-event tape:** announcement identifiers (`seq_id`), announcement metadata, and a **candidate** `available_at` proxy derived from `exchdisstime`. Gate 2 produced a freeze intended as Scope A. Task 3 does **not** certify Scope A as PIT-ready.

**Scope B — restatement-safe historical earnings values:** point-in-time EPS or other fundamentals with defensible first-publication timing and version/restatement history.

The existing freeze does **not** establish Scope B. Announcement availability is **not** proof that restatement-safe earnings values exist. **H001-as-earnings-values remains blocked** unless a suitable versioned fundamentals source is separately authorized and validated.

---

## 18. Future readiness-gate prerequisites

Not performed now:

1. Reproducible integrity recipe and separately verified artifact digests (raw vs parquet vs ZIP distinguished).
2. Authoritative `exchdisstime` semantics and historical-immutability evidence, **or** an explicitly approved and documented limitation.
3. Authorized 49×8 coverage audit using §15.
4. Explicit decision on Scope A versus Scope B.
5. Only after 1–4: a separate protocol freeze of target, features, horizon, decision time, and entry price.
6. Separate explicit authorization before any training, backtest, or holdout use.

---

## 19. Next separately authorized action

Choose **one** later (neither is done here):

- A reproducible artifact-integrity audit with a written hasher; **or**
- The §15 classifier and §16 49-symbol × 8-quarter coverage audit.

`DATA NOT READY` · `BLOCKED_PRECONDITION` · `READY_TO_RUN = NO`
