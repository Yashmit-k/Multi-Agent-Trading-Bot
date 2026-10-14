# H001 coverage audit

Coverage count only. This note does not approve an event class, train a model, or change readiness. `DATA NOT READY`, `BLOCKED_PRECONDITION`, and `READY_TO_RUN` = NO stay.

The named directory `datasets/h001-nse-raw-20261010T140237Z/` is absent. Rows were read from the extracted announcement JSON files under `datasets/h001-nse-ann-2024-2025-v1/h001-nse-raw-20261010T140237Z/corporate-announcements/`. Financial-results files were not opened. `TATAMOTORS` is not in the freeze.

## Methodology

The Parquet schema is `symbol`, `event_type`, `announced_at`, `published_at`, `available_at`, `source`, `source_id`, `period_end`, `has_xbrl`, `sm_isin`, `attachment_url`, `exchdisstime_raw`, `an_dt_raw`. It has no `desc`. Classification uses announcement JSON. Parquet is the cross-check.

A row qualifies when `hasXbrl` is JSON boolean `true`, or when `desc` matches the substring pattern `result|financial|earnings` with `re.IGNORECASE`. A missing or non-text `desc` does not match. No other keyword is used. Attachment text is not read for this rule. This is an audit predicate. It is not the proposed event class in `h001-event-classification-proposal.md`.

The quarter is the calendar quarter of `exchdisstime`. The vendor string is `DD-Mon-YYYY HH:MM:SS` with no offset. It is parsed with that format and tagged `Asia/Kolkata`. Q1 is January–March, Q2 April–June, Q3 July–September, and Q4 October–December, using that IST date. `an_dt`, `period_end`, `toDate`, and retrieval time are not the quarter clock.

Duplicate key is `seq_id`. Distinct ids stay separate. None was repeated. A qualifying row with an unparseable `exchdisstime`, or a date outside 2024Q1–2025Q4, would be counted outside the table. Both counts were zero.

## Counts

| Item | Value |
|---|---:|
| Announcement JSON files | 49 |
| Announcement rows | 18,235 |
| Symbols | 49 |
| `desc` substring hits | 316 |
| `hasXbrl` true | 3,375 |
| Text only | 315 |
| XBRL only | 3,374 |
| Intersection | 1 |
| Qualifying rows in the eight quarters | 3,690 |
| Symbols with at least one qualifying row | 49 |
| Zero symbol-quarter cells | 47 |

The historical claim of 3,690 results-like rows is reproduced by this predicate on these JSON files. The original generator is still absent, so this does not recover that program. It does mean the number 3,690 is the output of this rule, not an unchecked prior figure. `hasXbrl` true alone is 3,375 and is not the qualifying count.

The six `desc` values in the text hit are `Financial Result Updates` (245), `Integrated Filing- Financial` (50), `Clarification - Financial Results` (8), `Reply to Clarification- Financial results` (7), `Consolidated Result Updates - IFRS` (4), and `Publish Audited Results` (2).

Missing `desc`: 0. Non-text `desc`: 0. Missing or non-boolean `hasXbrl`: 0. Symbol field differing from the JSON filename: 0. File read errors: 0.

## Coverage table

Cell value is the number of qualifying announcements. Quarter is the IST calendar quarter of `exchdisstime`.

| Symbol | 2024Q1 | 2024Q2 | 2024Q3 | 2024Q4 | 2025Q1 | 2025Q2 | 2025Q3 | 2025Q4 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ADANIENT | 1 | 1 | 1 | 1 | 2 | 0 | 29 | 70 | 105 |
| ADANIPORTS | 1 | 1 | 1 | 1 | 2 | 0 | 26 | 28 | 60 |
| APOLLOHOSP | 1 | 1 | 3 | 2 | 3 | 0 | 23 | 13 | 46 |
| ASIANPAINT | 1 | 1 | 1 | 1 | 2 | 0 | 17 | 26 | 49 |
| AXISBANK | 1 | 1 | 1 | 1 | 2 | 0 | 41 | 50 | 97 |
| BAJAJ-AUTO | 1 | 1 | 1 | 1 | 2 | 1 | 26 | 32 | 65 |
| BAJAJFINSV | 1 | 1 | 1 | 1 | 2 | 0 | 25 | 20 | 51 |
| BAJFINANCE | 1 | 1 | 1 | 1 | 2 | 0 | 30 | 23 | 59 |
| BEL | 1 | 3 | 1 | 1 | 2 | 0 | 25 | 16 | 49 |
| BHARTIARTL | 1 | 1 | 1 | 1 | 2 | 0 | 32 | 52 | 90 |
| BPCL | 1 | 1 | 3 | 1 | 2 | 0 | 24 | 22 | 54 |
| BRITANNIA | 1 | 1 | 1 | 1 | 2 | 0 | 26 | 30 | 62 |
| CIPLA | 1 | 1 | 1 | 1 | 2 | 0 | 22 | 23 | 51 |
| COALINDIA | 1 | 1 | 1 | 1 | 2 | 0 | 43 | 40 | 89 |
| DRREDDY | 1 | 1 | 1 | 1 | 2 | 0 | 37 | 34 | 77 |
| EICHERMOT | 1 | 2 | 1 | 1 | 2 | 0 | 36 | 28 | 71 |
| GRASIM | 1 | 1 | 3 | 1 | 2 | 0 | 35 | 34 | 77 |
| HCLTECH | 2 | 3 | 2 | 1 | 2 | 0 | 32 | 53 | 95 |
| HDFCBANK | 1 | 1 | 1 | 1 | 2 | 0 | 33 | 29 | 68 |
| HDFCLIFE | 1 | 1 | 1 | 1 | 2 | 0 | 10 | 17 | 33 |
| HEROMOTOCO | 1 | 1 | 1 | 1 | 2 | 0 | 31 | 37 | 74 |
| HINDALCO | 1 | 1 | 1 | 1 | 2 | 0 | 34 | 37 | 77 |
| HINDUNILVR | 1 | 1 | 1 | 1 | 2 | 0 | 27 | 37 | 70 |
| ICICIBANK | 1 | 1 | 1 | 1 | 2 | 0 | 45 | 57 | 108 |
| INDUSINDBK | 1 | 1 | 1 | 1 | 2 | 0 | 47 | 34 | 87 |
| INFY | 1 | 1 | 1 | 1 | 2 | 1 | 40 | 52 | 99 |
| ITC | 1 | 1 | 1 | 1 | 2 | 0 | 19 | 22 | 47 |
| JSWSTEEL | 1 | 1 | 1 | 1 | 2 | 0 | 32 | 33 | 71 |
| KOTAKBANK | 1 | 1 | 1 | 1 | 2 | 0 | 29 | 43 | 78 |
| LT | 1 | 1 | 1 | 1 | 2 | 0 | 31 | 36 | 73 |
| M&M | 1 | 1 | 1 | 1 | 2 | 0 | 62 | 70 | 138 |
| MARUTI | 1 | 1 | 1 | 1 | 2 | 0 | 46 | 37 | 89 |
| NESTLEIND | 1 | 1 | 1 | 1 | 2 | 0 | 36 | 31 | 73 |
| NTPC | 1 | 1 | 1 | 1 | 2 | 0 | 49 | 41 | 96 |
| ONGC | 1 | 1 | 3 | 1 | 2 | 0 | 29 | 28 | 65 |
| POWERGRID | 1 | 1 | 1 | 1 | 2 | 0 | 35 | 27 | 68 |
| RELIANCE | 1 | 1 | 1 | 1 | 2 | 0 | 45 | 36 | 87 |
| SBILIFE | 1 | 1 | 2 | 1 | 2 | 0 | 23 | 19 | 49 |
| SBIN | 1 | 1 | 1 | 1 | 2 | 0 | 44 | 44 | 94 |
| SHRIRAMFIN | 1 | 1 | 1 | 1 | 2 | 0 | 84 | 88 | 178 |
| SUNPHARMA | 1 | 1 | 1 | 1 | 2 | 0 | 19 | 23 | 48 |
| TATACONSUM | 1 | 1 | 1 | 1 | 2 | 0 | 21 | 24 | 51 |
| TATASTEEL | 1 | 1 | 1 | 1 | 2 | 0 | 33 | 42 | 81 |
| TCS | 1 | 1 | 1 | 1 | 2 | 0 | 32 | 59 | 97 |
| TECHM | 1 | 1 | 1 | 1 | 2 | 0 | 25 | 37 | 68 |
| TITAN | 1 | 1 | 1 | 1 | 2 | 0 | 33 | 26 | 65 |
| TRENT | 1 | 1 | 1 | 1 | 2 | 0 | 25 | 27 | 58 |
| ULTRACEMCO | 1 | 1 | 1 | 1 | 2 | 0 | 35 | 35 | 76 |
| WIPRO | 1 | 1 | 1 | 1 | 2 | 0 | 30 | 41 | 77 |
| All 49 | 50 | 54 | 59 | 50 | 99 | 2 | 1,613 | 1,763 | 3,690 |

## Zero cells

Forty-seven symbols have no qualifying row in 2025Q2. `BAJAJ-AUTO` and `INFY` each have one. The zero cells are:

`ADANIENT`, `ADANIPORTS`, `APOLLOHOSP`, `ASIANPAINT`, `AXISBANK`, `BAJAJFINSV`, `BAJFINANCE`, `BEL`, `BHARTIARTL`, `BPCL`, `BRITANNIA`, `CIPLA`, `COALINDIA`, `DRREDDY`, `EICHERMOT`, `GRASIM`, `HCLTECH`, `HDFCBANK`, `HDFCLIFE`, `HEROMOTOCO`, `HINDALCO`, `HINDUNILVR`, `ICICIBANK`, `INDUSINDBK`, `ITC`, `JSWSTEEL`, `KOTAKBANK`, `LT`, `M&M`, `MARUTI`, `NESTLEIND`, `NTPC`, `ONGC`, `POWERGRID`, `RELIANCE`, `SBILIFE`, `SBIN`, `SHRIRAMFIN`, `SUNPHARMA`, `TATACONSUM`, `TATASTEEL`, `TCS`, `TECHM`, `TITAN`, `TRENT`, `ULTRACEMCO`, and `WIPRO`, each for 2025Q2 only.

Every other symbol-quarter cell is at least 1. `HDFCLIFE` and `SBILIFE` are counted from announcement JSON only. Their empty financial-results files were not used to fill a cell.

## Parquet cross-check

18,235 parquet rows. The symbol set matches the 49 JSON filenames. Every `source_id` matches a JSON `seq_id`, and the reverse is true. Symbol mismatches: 0. `has_xbrl` versus JSON `hasXbrl is True`: 0. `event_type` versus JSON `desc`: 0. `available_at` is the ISO string of `exchdisstime` tagged `Asia/Kolkata`: 0 mismatches. `source` is `nse_corporate_announcements` on every parquet row.

## Limitations

The qualifying set is mostly the XBRL flag: 3,374 of 3,690 rows have no `desc` substring hit. A true `hasXbrl` on a non-results subject still enters this table. The substring rule also keeps `Integrated Filing- Financial`, which the proposed event class leaves in review. This table is not that class.

The quarter is when NSE disseminated the announcement, not the fiscal period the filing describes. The 2025Q2 gap is a gap in this dissemination clock under this predicate. It is not a claim that those companies published no accounts for that fiscal quarter.

`TATAMOTORS` remains outside the 49. Protocol items 1–13 are still unresolved. This count does not authorize H001.

## Files

Read: 49 `corporate-announcements/*.json` files, and parquet columns `symbol`, `event_type`, `available_at`, `source`, `source_id`, `has_xbrl`, `exchdisstime_raw`. Not read: financial-results files, announcement `.raw` slices, the ZIP, snapshots, and `snapshots/holdout_after_20261005`.

Command: `.venv/bin/python datasets/research/h001_coverage_audit/coverage_audit.py`

Outputs: `datasets/research/h001_coverage_audit/coverage.csv`, `datasets/research/h001_coverage_audit/summary.json`, and this note. Source dataset files were not modified. Nothing was committed.
