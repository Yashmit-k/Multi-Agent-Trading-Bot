# H001 PIT Data Readiness Audit

Gate 2 frozen NSE extract. No labels, no model, no backtest, no holdout access, no snapshot mutation.

Status after this audit:

- `MARKET_DATA_READY` (unchanged; snapshots not modified)
- Event source: NSE corporate announcements (acquired)
- Event dataset: frozen candidate under gitignored `datasets/` (not committed)
- **PIT conclusion: DATA READY** for announcement-level `available_at` using NSE `exchdisstime` as Exchange Dissemination Time, interpreted as `Asia/Kolkata`
- `H001` modelling: still **not started** (hard stop after this report)

---

## 1. Source

**Primary:** National Stock Exchange of India — corporate announcements JSON.

- UI: https://www.nseindia.com/companies-listing/corporate-filings-announcements
- API: `https://www.nseindia.com/api/corporate-announcements?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY&symbol={SYMBOL}`
- Attachments: `nsearchives.nseindia.com`

**Auxiliary (not merged):** NSE financial-results JSON (`/api/corporates-financial-results`). Used only to inspect `toDate` / `oldNewFlag` / XBRL links. Values in that table are a **live vendor extract**, not a vintage of restated EPS.

**BSE `DissemDT`:** not pulled. Provenance would stay separate if added later. Not required to use this freeze.

Fixtures, Yahoo, FMP, RSS, and period_end were **not** used as `available_at`.

---

## 2. Retrieval details

| Item | Value |
|---|---|
| Retrieval start (UTC) | 2026-10-10T14:02:37Z |
| Retrieval finish (UTC) | 2026-10-10T14:17:43Z |
| Method | HTTP GET, browser User-Agent; NSE homepage returned 403; announcements API returned HTTP 200 with cookies |
| Coverage requested | 49 snapshot symbols × eight calendar quarters, 01-01-2024 … 31-12-2025 |
| Calls | 392/392 announcement slices HTTP 200; 49/49 financial-results HTTP 200 (`HDFCLIFE` and `SBILIFE` bodies were empty `[]`) |
| Raw store | `datasets/h001-nse-raw-20261010T140237Z/` (gitignored). Each slice saved as unmodified `.raw`; per-symbol concatenation as `.json` |
| Universe file | `snapshots 2/nifty50/1D/manifest.json` (`nifty50_1d_20261005`); 5m manifest agrees on the same 49 names with bars |
| TATAMOTORS | Excluded (`count = 0`). Not substituted |
| Holdout | Not accessed |

---

## 3. Dataset version/hash

| Item | Value |
|---|---|
| Raw freeze id | `h001-nse-raw-20261010T140237Z` |
| SHA256 of named raw/json files in the freeze | `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` |
| Normalized (gitignored, not committed) | `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` |
| Manifest | `datasets/h001-pit-events-nse-ann-2024-2025-v1.manifest.json` |
| `dataset_version` | `nse-ann-2024-2025-v1` |
| `schema_version` | `1.0` |

Any change requires a new `dataset_version`. Do not mutate this freeze.

---

## 4. Coverage

Announcement API date filters returned **18,235** rows. All mapped to the 49 names and all carried `exchdisstime` inside 2024-01-01 00:00 IST through 2025-12-31 23:59 IST.

Results-like subjects (`result` / `financial` / `earnings` / XBRL flag): **3,690** of those rows. The rest are other LODR corporate announcements (still timed events, not earnings-only).

Financial-results auxiliary: 5,844 rows in the live tables; **453** with `exchdisstime` in-window across **47/49** names (`HDFCLIFE`, `SBILIFE` empty on that endpoint). **Not merged** into the parquet.

---

## 5. Universe mapping

Rules: strip, uppercase, strip documented `.NS`. Map only onto the 49 manifest strings. `BAJAJ-AUTO` and `M&M` kept as those strings.

| Metric | Count |
|---|---|
| Mapped symbols / 49 | **49 / 49** |
| Unmapped | 0 |
| TATAMOTORS in extract | 0 (never requested) |

NSE `symbol` on rows already matched snapshot strings.

---

## 6. Timestamp fields

Observed on **actual announcement rows**:

| Field | Role on this extract |
|---|---|
| `exchdisstime` | Exchange Dissemination Time (`DD-MMM-YYYY HH:MM:SS`, no offset in JSON) |
| `an_dt` | Broadcast / announcement datetime (same format); typically a few seconds before `exchdisstime` (`difference` e.g. `00:00:06`) |
| `sort_date` | Sort key (`YYYY-MM-DD HH:MM:SS`), aligned with `an_dt` |
| `dt` | Compact id-like stamp from broadcast (`DDMMYYYYHHMMSS`) |
| `difference` | Broadcast-to-dissemination lag |
| Retrieval time | **Not in the NSE record**; only in `retrieval.json` |

Financial-results (auxiliary): `exchdisstime`, `broadCastDate`, `filingDate` (minute precision), `fromDate` / `toDate` (period), `financialYear`.

No scraper timestamp was copied into `available_at`.

---

## 7. Timestamp semantics

| Concept | This extract |
|---|---|
| period_end | **Not** on the announcements feed. On results rows: `toDate`. Fiscal close. **Forbidden** as `available_at` |
| announcement / broadcast | `an_dt` — when the filing hit NSE’s announcement bus |
| publication / dissemination | `exchdisstime` — NSE’s recorded market dissemination clock |
| retrieval | 2026-10-10 crawl. **Not** availability |
| revision time | No populated `old_new` on announcements. 69 rows whose text matches `/revis/i`. Results `oldNewFlag` is `N` or null on this pull |
| availability | **`exchdisstime`**, not period_end, not crawl time, not +N hours, not session open |

Timezone: strings are offset-naive. NSE’s corporate filings UI/API is the Indian exchange clock. This audit **tags** them as `Asia/Kolkata` (`+05:30`) and **keeps the original string** in `exchdisstime_raw`. That is a documented convention, not a fabricated instant. It is **not** RFC3339 inside the vendor JSON.

---

## 8. available_at validation

Rule used: `available_at = parse(exchdisstime)` as `Asia/Kolkata`. Rows without a parseable **date and time** would be discarded. On this freeze, **every** announcement row had `exchdisstime` with a second-resolution clock.

Not used: `toDate`, `filingDate` as first print for 2024 PDF-vs-XBRL lag, crawl time, midnight, session open.

After-hours and pre-open disseminations are stored as-is (examples exist after 15:30 IST and before 09:15 IST). No session adjustment.

---

## 9. Revision audit

Announcements: `old_new` was null on sampled full-symbol files; **69** text-flagged revision-ish rows kept as **separate `seq_id`s**. Prior values are **not** overwritten in this freeze because every API row was appended.

Financial-results `oldNewFlag` did not expose an Original/Revision series (`N` or null). `reInd` takes codes `N/-/A/I/F` without a documented first-print EPS history.

**Limitation:** you can replay “which announcement ids existed with `available_at <= t`.” You cannot reconstruct restated **line-item values** from this freeze alone.

---

## 10. Duplicate audit

Stable key: `nse_corporate_announcements` + `seq_id`.

Identical extra copies: **0**. Non-identical same-id groups: **0**.

---

## 11. Discarded rows

Announcement feed (date-filtered by NSE):

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

## 12. Coverage summary

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
| Results-like kept | 3,690 |

---

## 13. PIT conclusion

**DATA READY**

for a frozen, versioned announcement event tape whose `available_at` is NSE **Exchange Dissemination Time**.

Still **not** a restatement-safe XBRL fundamentals panel. Do not train H001 in this task.

---

## 14. Exact blocker

None for Gate 2 announcement-level availability.

Residual caveats (do not reopen as fake timestamps):

1. Vendor JSON has no explicit timezone offset; IST is applied as NSE’s clock.
2. This is one freeze of a public API; NSE could change historical JSON later — use this immutable copy.
3. BSE `DissemDT` was not cross-checked.
4. `HDFCLIFE` / `SBILIFE` financial-results endpoint was empty; announcements for those names are present.
5. Modelling (target, features, horizon, MlAgent) is **out of scope** until a later task.

`READY_TO_RUN` for **training** remains **NO** until that next gate. Event data for availability timestamps is no longer `EVENT_DATA_BLOCKED`.
