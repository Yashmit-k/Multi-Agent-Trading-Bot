# H001 v1 protocol — DRAFT, NOT APPROVED, NOT FROZEN

Status: `DRAFT_UNAPPROVED`. Execution remains unauthorized. This is not a target change.

## Frozen already (event class only)

- Include-list (normalized `desc`): `financial result updates`, `consolidated result updates ifrs`, `publish audited results`
- Train window: `exchdisstime` through 2024-06-30 23:59:59 IST
- Validate: 2024-07-01 through 2025-02-14 23:59:59 IST
- Later rows reported separately
- Minimum 50 **unique announcement events** per train/val (not session labels)
- Universe: 49 snapshot symbols with bars; no TATAMOTORS substitute
- Join rule if ever labelled: event `available_at` <= decision `as_of`
- Snapshot for bars: `nifty50_1d_20261005` (holdout not accessed)

## Unfrozen (require Quant/researcher approval)

- Target construction and label timing
- Feature vector and feature `available_at`
- Horizon `h`
- Decision session / clock
- Entry price
- Missing-data policy beyond “do not impute §16 cells”
- Restatement handling for values (Scope B)

Do **not** silently adopt [`services/quant/docs/label_v1.md`](../../quant/docs/label_v1.md) (`next_close_direction`) as H001.

v2 subject expansion remains **candidate only**.
