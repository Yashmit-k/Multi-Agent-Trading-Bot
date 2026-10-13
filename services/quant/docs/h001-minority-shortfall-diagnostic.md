# H001 training minority shortfall — diagnostic (immutable baseline)

Status: **diagnostic only**. The 2026-10-14 Authorization B result in `h001-eligibility-audit-result.json` is **not modified**. Protocol `h001-protocol-approval.md` is **not amended**. No model was fitted. Holdout was not accessed.

Baseline (unchanged):

| Split | n | + | − | Minority | vs 50 |
|---|---:|---:|---:|---:|---|
| Train | 75 | 34 | 41 | 34 | INCONCLUSIVE |
| Validation | 149 | 70 | 79 | 70 | SATISFIED |

`AUDIT_COMPLETE_INCONCLUSIVE`. Not `DATA_READY`.

## 1. Implementation vs approved design

Checked against `h001-protocol-approval.md` table (2026-10-12) and `quant_agents.research.h001`.

| Step | Approved rule | What the code does | Diagnostic |
|---|---|---|---|
| Event class | Three normalized `desc` strings; contradiction phrases; no `hasXbrl` include | `events.classify_row` | 18,235 → 251 in class; 17,984 `desc_not_in_class`; 0 contradiction, clock, TATAMOTORS, window. Matches the 251 include-list. No duplicate `seq_id` in class. |
| Clock | `exchdisstime` `DD-MMM-YYYY HH:MM:SS` IST; must equal `available_at` | `parse_exchdisstime` + mismatch exclusion | 0 clock exclusions on this tape. |
| Rule B / P0 | Earliest session whose 09:15 IST is strictly after `available_at`; P0 = 09:15–09:20 open; no fill | `decision_session`, `select_entry` | All 251 in-class rows have P0. |
| P1 / H1 | Next session 15:30 close, not decision-day close; no fill | `horizon_close`, `make_label` | All 251 have P1 and an L-sign label. 0 missing prices. |
| Features | Minute of `available_at`; prior 1/5/20 session returns; 21 prior sessions; no future close | `build_features`, `REQUIRED_PRIOR_SESSIONS = 21` | 27 `short_history`; 0 `missing_daily_history`. |
| Split / purge | Train decision ≤ 2024-06-30 unless H1 session after that date; validation after cutoff through 2025-02-14 | `assign_partition` | 75 train, 149 validation, 0 purged, 0 after 2025-02-14. |
| Duplicates | Distinct `seq_id` stay separate | No collapse | Train: 75 rows, **72** symbol-session clusters (3 extra rows). |
| Minority bar | `p = 5`, `10 * p = 50` on the smaller **label class** in each partition | `smaller_class_check` | Train 34 < 50; validation 70 ≥ 50. |

No implementation error was found that would, if corrected, restore the approved design while adding the missing 16 training minority labels.

The 27 `short_history` drops are the interaction of the 20-session return with a research calendar that **starts 2024-01-01**. The 21st union session is **2024-01-30**. Those 27 events have decision dates **2024-01-12 through 2024-01-30** and only **9–20** prior calendar sessions. That matches the spec (do not look back past the tape or fill holes). It is not a mis-parse.

Labels exist for those 27 (features run after P0/P1). If they were kept, all 27 would be **training**. Their labels: **8** positive, **19** negative. Training would become 102 rows, **42** / **60**, minority **42**. Still below 50.

## 2. Earlier history: availability and risk

The approved freeze requested **49 symbols × eight quarters, 01-01-2024 … 31-12-2025** (`h001-nse-announcement-audit.md`). There are **no** pre-2024 announcement files in this extract. Daily and 5-minute research candles also start **2024-01-01** (`nifty50_*_20261005`). Holdout was not inspected.

To add earlier training events under the **same** class, Rule B, H1, and 21-session lookback, the project would need:

- A new NSE announcement harvest for dates **before 2024-01-01**, same 49 names, same `desc` rule, new integrity record (the current alternative basis does not cover it).
- Matching **point-in-time** daily (and 09:15–09:20 5-minute) bars **before 2024-01-01**. The approved snapshot cannot supply those closes. Filling from another tape, or from 2024 prices, would leak or invent history.
- Re-audit of eligibility; the 2026-10-14 JSON stays the baseline for the current freeze.

Even recovering the 27 January 2024 rows (by grafting pre-2024 **prices only**) yields minority **42**, not 50. Crossing 50 in training under this class therefore requires **additional 2023 (or earlier) announcement events**, not only extra candles. Density on this tape is about 50 include-list rows per covered quarter, but 2023 `desc` usage is unknown (the 2025Q2–Q4 gap shows the three strings are not stable). That count cannot be promised before a harvest.

Leakage if training is extended **forward** into the present validation window: validation independence is lost. Moving the cut from 2024-06-30 toward 2024-09-30 can enlarge training but shrinks validation (feasibility: 98 validation clusters at 30 Sep 2024; 49 at year-end, already below 50 clusters).

## 3. Design options (not selected here)

| Option | Effect on 50-gate | Methodological cost |
|---|---|---|
| A. Keep protocol; do not fit | Stays `INCONCLUSIVE` | Honest. No peeking. |
| B. Pre-2024 Scope A harvest + PIT candles, same class/split/bar | Unknown until re-audit; 27 recovered still leave 42 | New data project; new integrity; lookback must not use post-decision or holdout prices. |
| C. Widen `desc` / use 3,690-row predicate / XBRL | Likely more rows | Rejected 2026-10-11/12 as not the results print. 2025 coverage still a different subject mix. |
| D. Move split later | Train larger, validation smaller | Chosen 2024-06-30 because it was the earliest cut with nonempty validation. Later cuts can fail the validation bar. |
| E. Count `10 * p` on all training rows/clusters (75 or 72 > 50) | Gate would pass | Explicitly rejected: all-cluster form can pass while the minority is thin (`h001-decision-package.md` G). |
| F. Lower `r` after seeing 34 (e.g. `r = 6` → 30) | Gate would pass | Chooses the constant from the outcome. The protocol said missing the bar is `INCONCLUSIVE`, not a retune. |
| G. Drop the 20-session return (`p = 4` → bar 40) | 34 still fails | Feature change after seeing y. Dropping two returns (`p = 3` → 30) would pass and is the same problem. |

## 4. Recommendation (for supervisor, not executed)

**Do not retune `r`, the event class, or the feature list to clear the gate.** The pipeline matches the approved study. The shortfall is sample thinness on this freeze: 16 training minority labels short, and the only in-tape recovery (27 January rows) still leaves **8** short.

**Prefer option A** unless the supervisor authorizes option B as a **new data collection**, with a written protocol amendment **before** any new harvest is treated as H001 training. Option B is the only path that can stay inside the current inferential story (same class, same `10 * p` on the smaller class, chronological validation untouched). It is not guaranteed to yield 16 extra training positives.

A proposed amendment text is in `h001-protocol-amendment-request-minority-sample.md`. Until that (or a different) amendment is approved **and** a new execution authorization is recorded, do not fit, backtest, or mark `DATA_READY`. The 2026-10-14 audit remains the immutable baseline.
