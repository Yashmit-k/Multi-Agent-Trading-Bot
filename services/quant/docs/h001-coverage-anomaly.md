# H001 coverage anomaly

Diagnostic only. The coverage table in `h001-coverage-audit.md` is unchanged. This note does not change the audit predicate, the event class, or readiness. `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay.

## Question

The coverage table has only 2 qualifying rows in 2025Q2, and about one qualifying row per symbol in each 2024 quarter. The check is whether that shape is in the local records or is a missing pull or a quarter-assignment error.

## Confirmed facts

The quarter is the calendar quarter of `exchdisstime`, parsed as `DD-Mon-YYYY HH:MM:SS` and tagged `Asia/Kolkata`. Every row in the 392 announcement `.raw` slices has an `exchdisstime` in the same calendar quarter as that slice's requested window. No 2025Q2 row was assigned to another quarter, and no other slice's row was assigned to 2025Q2. Unparseable clocks: 0.

`fetch_log.json` records 392 announcement calls and 49 financial-results calls. All 441 calls have status 200 and an empty error. Each of the eight windows, including `01-04-2025` through `30-06-2025`, has 49 calls. No `.raw` slice is empty. The 2025Q2 slices contain 2,016 rows and 1,409,590 bytes. The eight slice row counts sum to 18,235, the same count as the per-symbol JSON files. `audit_stats.json` records 0 discarded rows and 0 missing symbols. It does not store a quarterly breakdown.

`hasXbrl` is a boolean on all 18,235 rows. It is false on every row through `2025-07-17T23:18:35+05:30` and true on every row from `2025-07-18T10:05:43+05:30`. No calendar day contains both values.

| Quarter | Announcement rows | Symbols with rows | `hasXbrl` true | Keyword `desc` | Both | Qualifying |
|---|---:|---:|---:|---:|---:|---:|
| 2024Q1 | 2,704 | 49 | 0 | 50 | 0 | 50 |
| 2024Q2 | 2,917 | 49 | 0 | 54 | 0 | 54 |
| 2024Q3 | 2,787 | 49 | 0 | 59 | 0 | 59 |
| 2024Q4 | 2,258 | 49 | 0 | 50 | 0 | 50 |
| 2025Q1 | 1,823 | 49 | 0 | 99 | 0 | 99 |
| 2025Q2 | 2,016 | 49 | 0 | 2 | 0 | 2 |
| 2025Q3 | 1,967 | 49 | 1,612 | 2 | 1 | 1,613 |
| 2025Q4 | 1,763 | 49 | 1,763 | 0 | 0 | 1,763 |

The early uniform counts are one `Financial Result Updates` row per symbol in each quarter from 2024Q1 through 2025Q1 (49, 49, 49, 49, 49). Extra qualifying rows in those quarters are other keyword subjects. 2025Q1 also has 49 `Integrated Filing- Financial` rows, which is why that quarter is about two qualifying rows per symbol. 2025Q2 has 0 rows with either of those two subjects. Its only keyword hits are 2 `Clarification - Financial Results` rows, one for `BAJAJ-AUTO` and one for `INFY`.

2025Q2 still has announcements for every symbol. Examples of subjects present in that quarter, and not counted by the predicate: `Outcome of Board Meeting` 83, `Investor Presentation` 55, `Press Release` 137. Attachment text was not read.

Monthly keyword hits are concentrated in the first two months of each 2024 quarter and in January–February 2025. March 2024, March 2025, April 2025, and May 2025 have zero keyword hits. June 2025 has the two clarification rows. `hasXbrl` is 0 through June 2025, 420 of 775 rows in July 2025, and every row from August 2025 through December 2025.

## 2025Q2 by symbol

`hasXbrl` is 0 for every symbol. Qualifying equals the keyword count.

| Symbol | Rows | `hasXbrl` | Keyword `desc` | Qualifying |
|---|---:|---:|---:|---:|
| ADANIENT | 40 | 0 | 0 | 0 |
| ADANIPORTS | 54 | 0 | 0 | 0 |
| APOLLOHOSP | 30 | 0 | 0 | 0 |
| ASIANPAINT | 41 | 0 | 0 | 0 |
| AXISBANK | 54 | 0 | 0 | 0 |
| BAJAJ-AUTO | 39 | 0 | 1 | 1 |
| BAJAJFINSV | 29 | 0 | 0 | 0 |
| BAJFINANCE | 44 | 0 | 0 | 0 |
| BEL | 25 | 0 | 0 | 0 |
| BHARTIARTL | 44 | 0 | 0 | 0 |
| BPCL | 24 | 0 | 0 | 0 |
| BRITANNIA | 24 | 0 | 0 | 0 |
| CIPLA | 39 | 0 | 0 | 0 |
| COALINDIA | 40 | 0 | 0 | 0 |
| DRREDDY | 38 | 0 | 0 | 0 |
| EICHERMOT | 31 | 0 | 0 | 0 |
| GRASIM | 38 | 0 | 0 | 0 |
| HCLTECH | 63 | 0 | 0 | 0 |
| HDFCBANK | 33 | 0 | 0 | 0 |
| HDFCLIFE | 21 | 0 | 0 | 0 |
| HEROMOTOCO | 40 | 0 | 0 | 0 |
| HINDALCO | 30 | 0 | 0 | 0 |
| HINDUNILVR | 29 | 0 | 0 | 0 |
| ICICIBANK | 57 | 0 | 0 | 0 |
| INDUSINDBK | 47 | 0 | 0 | 0 |
| INFY | 93 | 0 | 1 | 1 |
| ITC | 27 | 0 | 0 | 0 |
| JSWSTEEL | 33 | 0 | 0 | 0 |
| KOTAKBANK | 35 | 0 | 0 | 0 |
| LT | 41 | 0 | 0 | 0 |
| M&M | 83 | 0 | 0 | 0 |
| MARUTI | 42 | 0 | 0 | 0 |
| NESTLEIND | 32 | 0 | 0 | 0 |
| NTPC | 45 | 0 | 0 | 0 |
| ONGC | 23 | 0 | 0 | 0 |
| POWERGRID | 33 | 0 | 0 | 0 |
| RELIANCE | 43 | 0 | 0 | 0 |
| SBILIFE | 13 | 0 | 0 | 0 |
| SBIN | 68 | 0 | 0 | 0 |
| SHRIRAMFIN | 98 | 0 | 0 | 0 |
| SUNPHARMA | 26 | 0 | 0 | 0 |
| TATACONSUM | 39 | 0 | 0 | 0 |
| TATASTEEL | 49 | 0 | 0 | 0 |
| TCS | 52 | 0 | 0 | 0 |
| TECHM | 38 | 0 | 0 | 0 |
| TITAN | 33 | 0 | 0 | 0 |
| TRENT | 32 | 0 | 0 | 0 |
| ULTRACEMCO | 35 | 0 | 0 | 0 |
| WIPRO | 49 | 0 | 0 | 0 |
| All 49 | 2,016 | 0 | 2 | 2 |

## Plausible explanations

The 2024 pattern is one `Financial Result Updates` subject per symbol per quarter, not a copied count. That subject is absent in 2025Q2. `Integrated Filing- Financial` appears as 49 rows in 2025Q1 and 1 row in 2025Q3, and is also absent in 2025Q2. A subject change around that time is consistent with the records. It is not proved by an NSE taxonomy document in this freeze.

The 2025Q3 and 2025Q4 qualifying surge is the `hasXbrl` flag turning true for every announcement from 2025-07-18 onward. In 2025Q4 the flag is true on all 1,763 rows and the keyword list matches none. Those quarters are not a surge of earnings subjects under this predicate.

## Unresolved

Whether the 83 `Outcome of Board Meeting` rows, or another 2025Q2 subject, are the earnings filings that used to be labeled `Financial Result Updates`. Attachment text was not used, and this note does not add them to the predicate.

Whether `hasXbrl: false` before 2025-07-18 means the filing had no XBRL, or only that the API flag was false. The key is present. The records do not include the XBRL document.

## Conclusion

The pattern is in the records. 2025Q2 was requested, returned HTTP 200 for all 49 symbols, and contains 2,016 announcements whose clocks fall in that quarter. It is not a dropped slice or a quarter-assignment error. The qualifying count is 2 because the keyword subjects used in earlier quarters are absent and `hasXbrl` is false on every row until 2025-07-18.

Do not treat the 3,690-row table as stable earnings coverage across the eight quarters. Do not fill 2025Q2 from board-meeting subjects or from the financial-results files. The predicate remains an audit rule, not an approved event class. H001 stays unauthorized.

## Files

Read: `fetch_log.json`, `retrieval.json`, `audit_stats.json`, 49 announcement JSON files, and 392 announcement `.raw` slices, using counts and subject strings only. Not read: financial-results files, attachment bodies, the ZIP, snapshots, and `snapshots/holdout_after_20261005`.

`h001-coverage-audit.md` and `datasets/research/h001_coverage_audit/` were not overwritten. Source dataset files were not modified. Nothing was committed.
