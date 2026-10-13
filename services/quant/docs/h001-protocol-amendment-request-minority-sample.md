# Protocol amendment request — H001 training minority sample

To: authorized quant/research supervisor  
Date: 2026-10-14  
Protocol: `h001-protocol-approval.md` (2026-10-12)  
Baseline audit: `h001-eligibility-audit-result.json` (**immutable**; do not edit to pass the gate)  
Related diagnostic: `h001-minority-shortfall-diagnostic.md`

This request does **not** amend the protocol by itself. Silence is not approval. Fitting remains unauthorized.

## Why an amendment is being asked

Authorization B found training minority **34** against the approved bar **50**. Validation minority **70** meets the bar. Status **`AUDIT_COMPLETE_INCONCLUSIVE`**. A read-only diagnostic found **no implementation bug** that, if fixed, would produce 50 training minority labels under the current freeze and rules. Restoring the 27 January `short_history` events (if pre-2024 prices existed) would raise training minority only to **42**.

## Exact proposed changes (choose one)

### Preferred: no design change (accept inconclusive)

**Change:** none.  
**Rationale:** `r = 10` on the smaller class was approved knowing the run might be inconclusive. Changing `r`, class, or features after seeing 34 would select the rule from the result.  
**Leakage:** none.  
**Re-audit:** none. Do not fit.

### Alternative B (only if new data is authorized): extend Scope A **backward**

**Change to protocol § event window / source list (not to class, Rule B, H1, features, `p`, `r`, or validation cut):**

- Permit an additional frozen announcement extract for the **same 49 names**, **same three `desc` strings**, **same contradiction rule**, covering a stated pre-2024 interval (propose calendar year **2023** unless the supervisor names another).
- Permit matching research candles whose daily 15:30 IST and 09:15–09:20 IST bars cover that interval **and** the existing 2024–2025 tape, with documented `snapshot_id` and `candle_sha256`. Do not substitute `snapshots/nifty50` or the holdout.
- Training decision dates may then include the new interval **and** existing dates on or before **2024-06-30**. Validation remains **after 2024-06-30 through 2025-02-14**. H1 purge at 2024-06-30 unchanged.
- Features still use only closes **strictly before** decision session D (21 sessions). Pre-2024 lookback may use only the new PIT daily file, never validation-period or holdout prices.
- Integrity: new freeze gets its own digest procedure **written before hashing**. Do not claim `b0f4760f…` is verified. Do not overwrite the 2024–2025 baseline hashes.
- Re-audit: rerun eligibility-only under a **new** Authorization B-style grant that names the new snapshot IDs. Compare against the immutable 2026-10-14 baseline; do not edit that JSON. Fit still requires separate execution authorization **and** minority ≥ 50 in **both** splits.

**Risk:** 2023 `desc` mix may not resemble 2024Q1–2025Q1. Extra rows are not guaranteed. Collection cost and a new integrity surface.

### Rejected unless the supervisor explicitly overrides the 2026-10-12 table

- Widening the event class or using the 3,690-row / `hasXbrl` predicate.  
- Lowering `r` or switching `10 * p` to all-cluster counts after seeing 34.  
- Dropping the 20-session return (or other features) to shrink `p`.  
- Moving the training cut into the current validation window.

## Leakage controls (if B is approved)

- Holdout path never listed or joined.  
- No feature or label uses a price at or after 09:15 IST on D.  
- Validation labels still unused for cutoff, features, or fit.  
- New 2023 rows with H1 ending after 2024-06-30 cannot enter training (purge). They should not appear if training ends 2024-06-30 and 2023 H1 is in 2023.  
- PDF/XBRL/fundamentals remain out of the class and the feature list.

## Reply template

```
MINORITY-SAMPLE AMENDMENT (H001):
I [accept INCONCLUSIVE / approve backward Scope A harvest as Alternative B / other: ___].
I do not authorize fitting or backtesting by this reply unless I also issue a separate execution authorization after a passing re-audit.
Grantor: <identity>
Date: <YYYY-MM-DD>
```

## Recorded selection, 2026-10-14

The authorized project identity **`user`** resubmitted the diagnostic recommendation as the next instruction, including the preference to **accept inconclusive and not fit**, and not to retune class, `r`, or features to pass the gate. Alternative B (2023 harvest) is **not** authorized by that instruction.

Recorded as:

```
MINORITY-SAMPLE AMENDMENT (H001):
I accept INCONCLUSIVE.
I do not authorize fitting or backtesting by this reply unless I also issue a separate execution authorization after a passing re-audit.
Grantor: user
Date: 2026-10-14
```

**Protocol file not edited.** Baseline `h001-eligibility-audit-result.json` not edited. No 2023 harvest. No model.
