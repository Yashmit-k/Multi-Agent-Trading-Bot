# H001 local coverage audit, 2026-10-13

Local evidence only. H001 was not built, labeled, or fit. No frozen file was rewritten. `snapshots/holdout_after_20261005` was not opened. Status is unchanged: `DATA NOT READY`, `BLOCKED_PRECONDITION`, `READY_TO_RUN = NO`.

## Controlling rules

Scope A is the announcement-event study. The controlling class is the 2026-10-12 approval table in `services/quant/docs/h001-protocol-approval.md`, which says that table controls where an earlier paragraph still lists an open option. A row is included only when normalized `desc` is exactly `financial result updates`, `consolidated result updates ifrs`, or `publish audited results`, and the attachment text does not contain `trading window`, `divestment`, or `loss of share`. Normalization is casefold, then every non-letter and non-digit becomes a space, then spaces are collapsed. `hasXbrl`, `integrated filing financial`, board outcomes, press releases, investor presentations, and filename matches do not include a row.

The controlling sample rule is the same table: `p = 5`, and the smaller label class must have at least 50 rows in training and again in validation. Missing that bar is `INCONCLUSIVE`. The bar was not changed.

Scope B is a separate earnings-surprise project. It needs versioned point-in-time EPS or revenue. It is not this class.

Two older sentences do not change those rules. `h001-event-class-provisional.md` still lists sample size as unresolved. The later approval table supersedes that sentence. `h001-nse-announcement-audit.md` says the announcement clock is `DATA READY` for `exchdisstime` as a field. The study status stays `DATA NOT READY` because actionability and class completeness are still open. The 3,690 figure is the older keyword-or-`hasXbrl` predicate. It is not this class.

## What was counted

Announcement JSON and the 392 `.raw` slices were read from `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/corporate-announcements/`. The parquet was read for `symbol`, `source_id`, and `exchdisstime_raw` only. Quarter is the calendar quarter of `exchdisstime`, parsed as `DD-Mon-YYYY HH:MM:SS` and tagged `Asia/Kolkata`. `datasets/h001-nse-raw-20261010T140237Z/` is still absent and was not created.

| Check | Result |
|---|---|
| JSON files | 49 |
| Announcement `.raw` slices | 392, none empty |
| JSON rows | 18,235 |
| `.raw` rows | 18,235, equal to JSON for every symbol |
| Duplicate `seq_id` | 0 |
| Unparseable `exchdisstime` | 0 |
| Rows outside 2024Q1–2025Q4 | 0 |
| Empty `desc` | 0 |
| Symbol differing from the JSON filename | 0 |
| Parquet rows | 18,235 |
| Parquet versus JSON, symbol-quarter cells | 0 mismatches |
| Include-list rows | 251 |
| Include-list rows removed by the contradiction check | 0 |

`Financial Result Updates` is 49, 49, 49, 49, and 49 in 2024Q1 through 2025Q1, and 0 afterward. Six further include-list rows are `Consolidated Result Updates - IFRS` for HCLTECH (2024Q1, two in 2024Q2, 2024Q3) and `Publish Audited Results` for EICHERMOT (2024Q2) and SBILIFE (2024Q3).

## Quarterly counts

Source rows and parquet rows are the same number in every quarter. Include is the controlling class.

| Quarter | Source and parquet rows | Symbols with a source row | Include-list rows | Symbols with an include-list row |
|---|---:|---:|---:|---:|
| 2024Q1 | 2,704 | 49 | 50 | 49 |
| 2024Q2 | 2,917 | 49 | 52 | 49 |
| 2024Q3 | 2,787 | 49 | 51 | 49 |
| 2024Q4 | 2,258 | 49 | 49 | 49 |
| 2025Q1 | 1,823 | 49 | 49 | 49 |
| 2025Q2 | 2,016 | 49 | 0 | 0 |
| 2025Q3 | 1,967 | 49 | 0 | 0 |
| 2025Q4 | 1,763 | 49 | 0 | 0 |

`integrated filing financial` is 49 rows in 2025Q1 and 1 row in 2025Q3. It is not in the class. `Outcome of Board Meeting` is present in every quarter, including 83, 86, and 81 rows in 2025Q2–2025Q4. Those rows are records rejected by the approved filter. They are not missing source files, and they are not eligible events.

## Include-list coverage

Cell value is the controlling class. Every symbol has a source row in every quarter. The 147 zero cells are the class cells in 2025Q2, 2025Q3, and 2025Q4.

| Symbol | 2024Q1 | 2024Q2 | 2024Q3 | 2024Q4 | 2025Q1 | 2025Q2 | 2025Q3 | 2025Q4 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ADANIENT | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| ADANIPORTS | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| APOLLOHOSP | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| ASIANPAINT | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| AXISBANK | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BAJAJ-AUTO | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BAJAJFINSV | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BAJFINANCE | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BEL | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BHARTIARTL | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BPCL | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| BRITANNIA | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| CIPLA | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| COALINDIA | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| DRREDDY | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| EICHERMOT | 1 | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 6 |
| GRASIM | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| HCLTECH | 2 | 3 | 2 | 1 | 1 | 0 | 0 | 0 | 9 |
| HDFCBANK | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| HDFCLIFE | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| HEROMOTOCO | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| HINDALCO | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| HINDUNILVR | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| ICICIBANK | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| INDUSINDBK | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| INFY | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| ITC | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| JSWSTEEL | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| KOTAKBANK | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| LT | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| M&M | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| MARUTI | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| NESTLEIND | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| NTPC | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| ONGC | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| POWERGRID | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| RELIANCE | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| SBILIFE | 1 | 1 | 2 | 1 | 1 | 0 | 0 | 0 | 6 |
| SBIN | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| SHRIRAMFIN | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| SUNPHARMA | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| TATACONSUM | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| TATASTEEL | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| TCS | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| TECHM | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| TITAN | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| TRENT | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| ULTRACEMCO | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |
| WIPRO | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 5 |

## Why 2025Q2–2025Q4 have no included events

This is not a missing local artifact. All 49 symbols have announcement slices for those quarters, the slices are non-empty, and `fetch_log.json` records 392 announcement calls at HTTP 200. `audit_stats.json` records 0 discarded announcement rows.

The three approved `desc` strings do not occur in those quarters. The contradiction check removed 0 rows there because there was no include-list row to remove. Later eligibility rules did not remove them either. The stored eligibility audit at `datasets/research/h001_eligibility_audit_20261012_json_metadata/summary.json` has the same 251 class rows, then 27 `short_history` exclusions, 224 rows past the feature-history check, 75 training rows, and 149 validation rows. No decision session after 2025-02-14 is in that split.

The cause that remains unknown is external. The local file cannot show whether NSE stopped using those three subject strings, or whether the results print moved to another subject. Promoting `Outcome of Board Meeting` or `integrated filing financial` would change the approved class. That is not done here.

## Comparison with 34 and 50

The independently counted class is 251 rows. That number is not the training minority class. The stored eligibility audit, which this note did not rerun, reports 34 positive and 41 negative training rows after rule B, H1, and the short-history exclusion. The smaller training class is 34, below 50, so the sample check stays `INCONCLUSIVE`. Validation's smaller class is 70, which meets 50, and that does not repair the training side. The 18,235 source rows and the 3,690 predicate are not evidence that the class is complete.

## Scope B, counted and not used

`financial-results/` has 49 `.raw` files and 5,844 rows. `HDFCLIFE.raw` and `SBILIFE.raw` are empty arrays. Rows with `exchdisstime` inside 2024-01-01 through 2025-12-31: 453. Rows with no clock: 1,792. `oldNewFlag` is `N` on 3,631 rows and null on 2,213. `params` on the inspected ADANIENT row is a 38-character string, not a versioned earnings history. These files are not Scope A and they are not a point-in-time EPS source.

## Dev 1 handoff

| Gap | Already checked locally | Still unknown | Dev 1 action | Evidence to return |
|---|---|---|---|---|
| No include-list row in 2025Q2–2025Q4 | 49 non-empty slices per quarter; 0 of the three `desc` strings; board-meeting and other subjects are present and stay out | Whether NSE renamed the results subject after 2025Q1 | Verify the vendor subject history. Do not add a subject to the class | A subject crosswalk for those three quarters, with the vendor page or response it came from |
| `exchdisstime` | Present on all 18,235 announcement rows, parseable, and equal to parquet `exchdisstime_raw` in the stored join | Whether that clock is the time the information was public | Document the vendor definition of Exchange Dissemination Time | The vendor definition and any stated delay or timezone rule |
| Historical digest `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` | Recomputed baseline is `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2`. The manifest copies the historical string. No file list or order reproduces it | The original hashed names and order | Recover that list and order if it exists. Do not replace the digest with the later baseline | The filename list, order, and the command that emits `b0f4760f…`, or a written statement that the procedure is gone |
| Scope B EPS and revenue | Financial-results extract is 5,844 rows, 453 in window, two empty symbols, no old-versus-new chain | A versioned point-in-time EPS or revenue series | Supply that series under a separate Scope B decision | A file with symbol, period, value, and an `available_at` that is the public time, plus its revision history |
| PDF body | The class rule can only see `attchmntText`. The JSON has no PDF | Whether an attachment summary hides a non-results document | Do not fetch PDFs unless a later decision asks for them | Nothing until that decision |

## Decisions that still require approval

- Adding any 2025Q2–2025Q4 subject, including board outcomes or integrated filings, to the class.
- Lowering the 50-row smaller-class bar.
- A fit or a backtest. Training remains 34 against 50.
- Treating Scope B as part of this announcement study.

## Next step

Dev 1 verifies the vendor subject history for 2025Q2–2025Q4 and the meaning of `exchdisstime`. H001 stays unbuilt until that evidence is back and a separate approval changes the class or authorizes a fit. `READY_TO_RUN` stays NO.
