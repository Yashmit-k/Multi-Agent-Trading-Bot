# H001 Authorization B grant

Recorded 2026-10-14. This grant authorizes the **eligibility-only audit**. It does not authorize model fitting, training, optimization, evaluation, or a backtest.

## Gate fields

| Field | Value |
|---|---|
| `statement` | Verbatim match to `REQUIRED_AUTHORIZATION_B_STATEMENT` |
| `granted_by` | `user` |
| `granted_on` | `2026-10-14` |
| `scope` | `H001_ELIGIBILITY_AUDIT` |

## Grantor identity (verified, not invented)

H001 governance records methodological approval as issued by **the user** (`h001-protocol-approval.md`, 2026-10-12: “the user approved the methodological choices”). This instruction is the same role: the chat user issued the required Authorization B sentence in full.

No legal name, signature, or separate token was supplied in the instruction. None was invented. `granted_by` is therefore the established project identity `user`, not a guessed personal name.

## Statement (verbatim)

```
AUTHORIZATION B GRANTED: run the H001 eligibility-only audit on the frozen Scope A announcement tape identified in services/quant/docs/h001-protocol-approval.md (protocol dated 2026-10-12). Do not access snapshots/holdout_after_20261005. Do not fit, backtest, optimize, or evaluate an H001 model. Do not change the approved event class, features, split, minority threshold, or label definitions.
```

## What this does not authorize

- Fit, train, backtest, optimize, or evaluate any H001 model
- Access to `snapshots/holdout_after_20261005`
- Protocol, event-class, feature, split, purge, or minority-threshold changes
- Treating a completed audit as execution authorization
