# H001 data-prep handoff (2026-10-13)

Initial git: branch `dev1/intelligence`, HEAD `1e6da831ba1cef5d3fb749bbb50c655ff07edd84`. Freeze not mutated. Holdout not accessed. Labels not generated. Gate 2 `DATA READY` remains **withdrawn**.

## Overall preparation status

Preparation **system** for Scope A exists and was executed on the real freeze. **Approved research scope is A** per Quant `h001-protocol-approval.md` (2026-10-12). Scope B is not required. Intelligence does not modify that protocol. Readiness flags are **unchanged**.

| Flag | Value |
|---|---|
| `DATA_PREP_READY` | **NO** |
| `READY_TO_RUN` | **NO** |
| `BLOCKED_PRECONDITION` | true |
| Approved scope | **A** (announcement-timing; three approved subjects) |
| Eligibility | **INCONCLUSIVE** (train minority **34** &lt; 50) |
| Protocol rows | `USER APPROVED — NOT AUTHORIZED TO EXECUTE` |

## Verified measurements (this run)

Command: `python -m intelligence_agents.h001v2.scan` (exit 0).

| Item | Result |
|---|---|
| Integrity v1 listing | `18dbec4a4712b1430a6dabeca03a157af03cba45dac346c1a21d6b39d3f77f2d` (493 files; matches prior named baseline) |
| Integrity v2 files manifest | `125d6dc018cb00348e38657630fd91e75fa27dd2804e2143435a08c4b292d8dc` |
| Historical `b0f4760f…` | **UNVERIFIED** (not replaced) |
| Classes | 392 announcement `.raw`, 49 concat `.json`, 49 financial-results auxiliary, retrieval + audit_stats |
| Parquet sidecar (not in listing) | PRESENT `8ae800ef…` 1,625,375 bytes |
| In-universe rows | 18,235 kept; 0 exclusions |
| Prepared output sha256 | `0b987622812e75db7570bafc51687e74c9424b7bf3c4b195aae35be3aeccaf93` |
| `exchdatetime` | **absent** (0/18235); not aliased |
| `exchdisstime` parse | 18,235/18,235; IST convention |
| `an_dt` after `exchdisstime` | 0 |
| Session buckets | after-close 12443, regular 5453, pre-open 339 |
| §15 kept | 3690 (hasXbrl-only 3374) |
| §16 | 345/392; **47 missing, all 2025Q2** |
| 2025Q2 slices | **49/49 files present**, none empty |
| 2025Q2 rows | 2016 announcements, **2** §15 — genuine missing qualifying events, not a failed query |
| Tests | `pytest …/test_h001v2_normalize.py …/test_h001_prep.py` — **18 passed** |

## Timestamp finding

`exchdisstime` is the availability clock in this pipeline (`exchdatetime` absent), tagged `Asia/Kolkata` by convention. The Quant protocol **accepts it as a proxy only**, not as proof of first public print or actionability.

## Missingness finding

The 47 cells are **this** H001 §16 grid (not a different dataset). Origin: source slices exist; rows exist (2016); §15 almost empty in 2025Q2 (2). Classifier was not tightened. No imputation.

## Outstanding blockers

1. Eligibility **INCONCLUSIVE**: training minority class **34** &lt; approved minimum **50**. Does not authorize labels or fit.
2. 47 §16 holes under the §15 classifier (2025Q2); not imputed. Separate from the 34-count eligibility audit.
3. Historical digest `b0f4760f…` recipe unknown.
4. Scope B fundamentals remain **unapproved**; sponsor decision is **neither** (no paid feed, no XBRL harvest). Keep fixtures. Do not build a Prowess/XBRL adapter.

## Recorded decisions (not execution authorization)

- Controlling protocol: `services/quant/docs/h001-protocol-approval.md`.
- Scope A approved; Scope B not required for this H001.
- `exchdisstime` IST proxy limitation accepted as **proxy only**.
- `DATA_PREP_READY = NO` · `READY_TO_RUN = NO` · Gate 2 DATA READY withdrawn.
- Every approved protocol row: `USER APPROVED — NOT AUTHORIZED TO EXECUTE`.

## Single highest-priority next action

Do **not** train, label, backtest, or execute H001 until a **separate explicit authorization**. Do not treat Scope A approval as that authorization.
