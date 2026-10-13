# H001-v2 candidate (not approved)

Status: `PROTOCOL APPROVED — EXECUTION NOT AUTHORIZED` for **v1**.  
H001-v2 is a **candidate only**.

`DATA NOT READY` · `BLOCKED_PRECONDITION` · `READY_TO_RUN = NO`

No labels, no fit, no backtest, no holdout.

Scope A evidence (hasher, §15, 49×8): `h001-scope-a-coverage.md`, `h001-scope-a-integrity.json`, `h001-scope-a-SHA256SUMS.txt`. Those artifacts do **not** authorize labels or fit.

## Original v1 include-list (immutable)

Normalized exact `desc`:

- `financial result updates`
- `consolidated result updates ifrs`
- `publish audited results`

Windows: train `exchdisstime` through 2024-06-30 IST; validate 2024-07-01 through 2025-02-14 IST. Later rows reported separately.

## Coverage reproduced from freeze `h001-nse-raw-20261010T140237Z`

Announcement-unique `seq_id` counts (not labelled decision sessions; not a train authorization):

| Class | Unique events | Train | Validate | Post-validation (not for threshold) | Announcement count >=50 train | >=50 val |
|---|---|---|---|---|---|---|
| v1 approved | 247 | 99 | 148 | 0 | yes | yes |
| v2 candidate | 434 | 105 | 213 | 116 | yes | yes |

These counts **do not** make H001 ready to run. They are not session-level positives after candle joins, leakage filters, or a frozen target. A prior brief of **34** minority training rows is **not reproduced** as unique v1 announcements (that figure likely used a stricter eligibility pipeline that this sprint did not re-implement and must not invent). `consolidated result updates ifrs` has **0** rows in the freeze.

Raw in-universe rows: 18235. Missing `exchdisstime`: 0.

v1 by desc: `{'Financial Result Updates': 245, 'Publish Audited Results': 2}`

v2 evidence kinds: `{'official_v1_subject': 247, 'source_backed_board_outcome_financial_results': 137, 'nse_circular_subject_nse_cml_2025_20': 50}`

v1 symbols with zero events: (none)

Integrity: historical `b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae` remains **UNVERIFIED**. New recipe `sha256 of sorted sha256sum-style lines (HASH two-spaces POSIX-relpath newline) over freeze .raw and .json files` digest `18dbec4a4712b1430a6dabeca03a157af03cba45dac346c1a21d6b39d3f77f2d` — **not equivalent**.

`exchdisstime`: candidate IST-tagged proxy; not proven first public print; not proven immutable

## v2 proposed rule (awaits approval)

1. Keep v1 subjects.
2. Keep `Integrated Filing- Financial` / close spelling variants (NSE/CML/2025/20 XBRL module).
3. Keep `Outcome of Board Meeting` **only if** attachment text matches financial-results language.
4. Do not keep all board outcomes, dividends, appointments.

Do not train on v2 until approved. Do not lower the 50-per-partition threshold.
