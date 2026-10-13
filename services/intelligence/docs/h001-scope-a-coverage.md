# H001 Scope A coverage

`DATA NOT READY` · `BLOCKED_PRECONDITION` · `READY_TO_RUN = NO`

Scope A only: announcement tape + named hasher + §15/§16 table. **Not** PIT-certified. **Not** fit authorization.
No labels. No train. Historical digest `b0f4760f…` remains **UNVERIFIED**.

## Integrity

Freeze `h001-nse-raw-20261010T140237Z`. Recipe: `sha256 of sorted sha256sum-style lines (HASH two-spaces POSIX-relpath newline) over freeze .raw and .json files`.
New baseline `18dbec4a4712b1430a6dabeca03a157af03cba45dac346c1a21d6b39d3f77f2d`. Files: 493.
Matches prior listing digest 18dbec4a…: `True`.
`equivalent_to_b0f4760f`: false.

## v1 (immutable three-desc; unique seq_id)

| Unique | Train | Validate | Post-val | >=50 train | >=50 val |
|---|---|---|---|---|---|
| 247 | 99 | 148 | 0 | True | True |

v1 by desc: `{'Financial Result Updates': 245, 'Publish Audited Results': 2}`

Announcement count ≥50 is **not** fit authorization.

## §15 results-like (exact rule)

Keep if `hasXbrl` is truthy **or** `desc` matches `result|financial|earnings` (case-insensitive).
Not the undocumented historical 3,690.

| kept | not kept | hasXbrl only | regex only | both | unparseable exchdisstime |
|---|---|---|---|---|---|
| 3690 | 14545 | 3374 | 315 | 1 | 0 |

This scan's kept count is **under the written §15 rule**. It happens to equal Gate 2's undocumented `results_like_kept: 3690`; that coincidence does **not** certify Gate 2's predicate. `hasXbrl`-only rows (analyst meets, general updates, newspaper copies, etc.) dominate and are **false positives for an earnings-print class**. The rule was not tightened.

False-positive / ambiguous buckets (not a filter): `{'official_v1_subject': 247, 'nse_cml_2025_20_subject': 50, 'ambiguous_regex_or_xbrl': 3218, 'board_outcome_regex_hit': 156, 'clarification_regex_hit': 15, 'results_language': 4}`

desc histogram (top 15; full list in `h001-scope-a-coverage.json`): Analysts/Institutional Investor Meet/Con. Call Updates: 692, General Updates: 510, Updates: 367, Copy of Newspaper Publication: 290, Financial Result Updates: 245, Press Release: 210, Outcome of Board Meeting: 156, Shareholders meeting: 119, ESOP/ESOS/ESPS: 119, Investor Presentation: 90, Trading Window: 88, Action(s) taken or orders passed: 65, Change in Management: 58, Certificate under SEBI (Depositories and Participants) Regulations, 2018: 54, Acquisition: 53

Symbols with zero §15 rows: (none)

## §16 49 × 8 IST calendar quarters

Universe: 49 snapshot symbols with bars (`TATAMOTORS` excluded, not substituted).
Covered cell: ≥1 §15-kept row with parseable `exchdisstime` in that IST quarter.
Financial-results auxiliary endpoint: **not merged**.

Covered cells: **345 / 392**. Missing cells: **47**.
Missing cells stay missing (no imputation). Observed missing quarters are listed below (this freeze: almost all `2025Q2`).

Missing cells:

- `ADANIENT` 2025Q2
- `ADANIPORTS` 2025Q2
- `APOLLOHOSP` 2025Q2
- `ASIANPAINT` 2025Q2
- `AXISBANK` 2025Q2
- `BAJFINANCE` 2025Q2
- `BAJAJFINSV` 2025Q2
- `BEL` 2025Q2
- `BHARTIARTL` 2025Q2
- `BPCL` 2025Q2
- `BRITANNIA` 2025Q2
- `CIPLA` 2025Q2
- `COALINDIA` 2025Q2
- `DRREDDY` 2025Q2
- `EICHERMOT` 2025Q2
- `GRASIM` 2025Q2
- `HCLTECH` 2025Q2
- `HDFCBANK` 2025Q2
- `HDFCLIFE` 2025Q2
- `HEROMOTOCO` 2025Q2
- `HINDALCO` 2025Q2
- `HINDUNILVR` 2025Q2
- `ICICIBANK` 2025Q2
- `INDUSINDBK` 2025Q2
- `ITC` 2025Q2
- `JSWSTEEL` 2025Q2
- `KOTAKBANK` 2025Q2
- `LT` 2025Q2
- `M&M` 2025Q2
- `MARUTI` 2025Q2
- `NESTLEIND` 2025Q2
- `NTPC` 2025Q2
- `ONGC` 2025Q2
- `POWERGRID` 2025Q2
- `RELIANCE` 2025Q2
- `SBILIFE` 2025Q2
- `SBIN` 2025Q2
- `SHRIRAMFIN` 2025Q2
- `SUNPHARMA` 2025Q2
- `TATACONSUM` 2025Q2
- `TATASTEEL` 2025Q2
- `TCS` 2025Q2
- `TECHM` 2025Q2
- `TITAN` 2025Q2
- `TRENT` 2025Q2
- `ULTRACEMCO` 2025Q2
- `WIPRO` 2025Q2

| symbol | 2024Q1 | 2024Q2 | 2024Q3 | 2024Q4 | 2025Q1 | 2025Q2 | 2025Q3 | 2025Q4 |
|---|---|---|---|---|---|---|---|---|
| `ADANIENT` | Y | Y | Y | Y | Y | n | Y | Y |
| `ADANIPORTS` | Y | Y | Y | Y | Y | n | Y | Y |
| `APOLLOHOSP` | Y | Y | Y | Y | Y | n | Y | Y |
| `ASIANPAINT` | Y | Y | Y | Y | Y | n | Y | Y |
| `AXISBANK` | Y | Y | Y | Y | Y | n | Y | Y |
| `BAJAJ-AUTO` | Y | Y | Y | Y | Y | Y | Y | Y |
| `BAJFINANCE` | Y | Y | Y | Y | Y | n | Y | Y |
| `BAJAJFINSV` | Y | Y | Y | Y | Y | n | Y | Y |
| `BEL` | Y | Y | Y | Y | Y | n | Y | Y |
| `BHARTIARTL` | Y | Y | Y | Y | Y | n | Y | Y |
| `BPCL` | Y | Y | Y | Y | Y | n | Y | Y |
| `BRITANNIA` | Y | Y | Y | Y | Y | n | Y | Y |
| `CIPLA` | Y | Y | Y | Y | Y | n | Y | Y |
| `COALINDIA` | Y | Y | Y | Y | Y | n | Y | Y |
| `DRREDDY` | Y | Y | Y | Y | Y | n | Y | Y |
| `EICHERMOT` | Y | Y | Y | Y | Y | n | Y | Y |
| `GRASIM` | Y | Y | Y | Y | Y | n | Y | Y |
| `HCLTECH` | Y | Y | Y | Y | Y | n | Y | Y |
| `HDFCBANK` | Y | Y | Y | Y | Y | n | Y | Y |
| `HDFCLIFE` | Y | Y | Y | Y | Y | n | Y | Y |
| `HEROMOTOCO` | Y | Y | Y | Y | Y | n | Y | Y |
| `HINDALCO` | Y | Y | Y | Y | Y | n | Y | Y |
| `HINDUNILVR` | Y | Y | Y | Y | Y | n | Y | Y |
| `ICICIBANK` | Y | Y | Y | Y | Y | n | Y | Y |
| `INDUSINDBK` | Y | Y | Y | Y | Y | n | Y | Y |
| `INFY` | Y | Y | Y | Y | Y | Y | Y | Y |
| `ITC` | Y | Y | Y | Y | Y | n | Y | Y |
| `JSWSTEEL` | Y | Y | Y | Y | Y | n | Y | Y |
| `KOTAKBANK` | Y | Y | Y | Y | Y | n | Y | Y |
| `LT` | Y | Y | Y | Y | Y | n | Y | Y |
| `M&M` | Y | Y | Y | Y | Y | n | Y | Y |
| `MARUTI` | Y | Y | Y | Y | Y | n | Y | Y |
| `NESTLEIND` | Y | Y | Y | Y | Y | n | Y | Y |
| `NTPC` | Y | Y | Y | Y | Y | n | Y | Y |
| `ONGC` | Y | Y | Y | Y | Y | n | Y | Y |
| `POWERGRID` | Y | Y | Y | Y | Y | n | Y | Y |
| `RELIANCE` | Y | Y | Y | Y | Y | n | Y | Y |
| `SBILIFE` | Y | Y | Y | Y | Y | n | Y | Y |
| `SBIN` | Y | Y | Y | Y | Y | n | Y | Y |
| `SHRIRAMFIN` | Y | Y | Y | Y | Y | n | Y | Y |
| `SUNPHARMA` | Y | Y | Y | Y | Y | n | Y | Y |
| `TATACONSUM` | Y | Y | Y | Y | Y | n | Y | Y |
| `TATASTEEL` | Y | Y | Y | Y | Y | n | Y | Y |
| `TCS` | Y | Y | Y | Y | Y | n | Y | Y |
| `TECHM` | Y | Y | Y | Y | Y | n | Y | Y |
| `TITAN` | Y | Y | Y | Y | Y | n | Y | Y |
| `TRENT` | Y | Y | Y | Y | Y | n | Y | Y |
| `ULTRACEMCO` | Y | Y | Y | Y | Y | n | Y | Y |
| `WIPRO` | Y | Y | Y | Y | Y | n | Y | Y |

## Timestamp limitation

candidate IST-tagged proxy; not proven first public print; not proven immutable (see `h001-timestamp-leakage.md`).

Scope B restatement-safe earnings values: **not established**.
