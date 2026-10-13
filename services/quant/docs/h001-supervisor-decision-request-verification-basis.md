# Decision request — H001 eligibility-audit integrity basis

To: authorized quant/research supervisor  
From: H001 Authorization B eligibility work  
Date: 2026-10-14  
Protocol: `h001-protocol-approval.md` (2026-10-12)  
Existing grant: Authorization B recorded (`h001-authorization-b-grant.md`). Eligibility-only. Not model execution.

Please answer in writing. Do not treat silence as approval. This request does not change the protocol, the event class, features, labels, split, purge, or the minority bar of 50.

## 1. Why the original digest cannot be verified

The protocol lists historical digest

`b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae`

as unverified. Investigation (`h001-integrity-procedure-investigation.md`) did not recover:

- which files were hashed,
- root and path spelling,
- sort order,
- whether the hash covered file bytes, names plus bytes, or another stream,
- encoding or separators,
- the original script or command.

The string is stored in `retrieval.json` as `sha256_of_named_files` and copied into the parquet manifest field `SHA256`. Those records do not describe a procedure. Git history first contains the hex in commit `2d687ff` as a documentation table cell. No generator is in the repository. Candidate hash orders were not searched.

Until that procedure exists, the freeze **cannot** be verified against `b0f4760f…`.

## 2. What the supplementary artifacts actually cover

| Artifact | Digest | What it is | This checkout |
|---|---|---|---|
| `NEW_VERIFICATION_BASELINE` | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` | Documented 493-file tree fingerprint of the freeze (path + length + bytes). Approved earlier as a **different** checksum. | Recomputed; **match** on `datasets/h001-nse-raw-20261010T140237Z/`. |
| Parquet file | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` | SHA-256 of `datasets/h001-pit-events-nse-ann-2024-2025-v1.parquet` bytes. The eligibility plan reads this file, not the raw JSON, once authorized. | Present; **match**. |
| Historical digest | `b0f4760f…` | Unknown “named raw/json files”. | **UNVERIFIED**. |

Matching `adda9d82…` means the freeze tree has not changed relative to the 2026-10-11 baseline. It does not prove `b0f4760f…`. Matching `8ae800ef…` means the parquet file bytes match the recorded parquet digest. It does not prove the raw/json aggregate.

## 3. Risks and limitations of proceeding under the supplementary baseline

- The original named-file set might have differed from the 493-file tree (for example excluding `financial-results/`, metadata JSON, or using another order).
- A later undetected rewrite of the original procedure’s inputs could theoretically coexist with an unchanged `NEW_VERIFICATION_BASELINE` if that procedure hashed a different set (unlikely if the tree is the whole freeze, but unknown).
- The parquet is a derived table. Row-level agreement with announcement JSON was reported in an earlier recovery audit; that is not the same as reproducing `b0f4760f…`.
- Candle files are a **separate** blocker. They are missing here. Approving a digest basis does not restore `snapshots 2/nifty50`.

## 4. Decision requested

Does the supervisor approve a **new verification basis for the eligibility-only audit only**, namely:

- Freeze tree must match `NEW_VERIFICATION_BASELINE` `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2`, and
- Parquet bytes must match `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494`, and
- Research candles must still be the approved `nifty50_5m_20261005` / `nifty50_1d_20261005` files at `snapshots 2/nifty50` with the recorded `candle_sha256` values,

**instead of** requiring reproduction of `b0f4760f…` before eligibility counts?

If no: leave historical verification UNVERIFIED and do not run eligibility.

If yes: record the exact wording, grantor identity, and date. That decision is not Authorization C (fit).

## 5. What approval would not do

Approval of the supplementary basis would **not**:

- establish historical verification of `b0f4760f…` (it stays UNVERIFIED),
- change `h001-protocol-approval.md`,
- authorize model fitting, training, backtesting, optimization, or evaluation,
- authorize holdout access,
- lower the minority-class bar of 50 or widen the event class.

## 6. Candle restoration (also required)

Even after a digest decision, eligibility cannot run until `snapshots 2/nifty50/5m` and `…/1D` exist and match:

- 5m `candle_sha256` `0f2df34d35e5a02ab6cd725882afd3fca7354eff65e4c1d219cf7fa9bdf1cb9b`
- 1d `candle_sha256` `0411a89535ab50ae6488c7d93c5ce7572feba4f55fd9ecb0f73478bf33bd2a7d`

Those files are gitignored and are not on this checkout. Restore from the MARKET_DATA_READY backup; do not use `snapshots/nifty50` or the holdout.

## Reply template

```
VERIFICATION BASIS DECISION (H001 eligibility-only):
I [approve / do not approve] using NEW_VERIFICATION_BASELINE adda9d82… plus parquet 8ae800ef… as the integrity basis for the Authorization B eligibility audit.
This does not verify b0f4760f….
This does not authorize fitting or backtesting.
Grantor: <identity>
Date: <YYYY-MM-DD>
```

## Recorded decision, 2026-10-14

The authorized project identity **`user`** (same role as `h001-protocol-approval.md` and `h001-authorization-b-grant.md`) issued the following. No legal name was invented.

```
VERIFICATION BASIS DECISION (H001 eligibility-only):
I approve using NEW_VERIFICATION_BASELINE adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2 plus parquet SHA-256 8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494 as the integrity basis for the Authorization B eligibility audit.
This does not verify historical digest b0f4760f626f8ebd8bc030475f22fd75be5323491d33313388778fb730decaae.
This does not authorize fitting, backtesting, optimization, or model evaluation.
Grantor: user
Date: 2026-10-14
```

Scope: Authorization B eligibility-only. Not execution authorization. Not historical verification of `b0f4760f…`.

Recomputed on this checkout immediately before recording:

| Object | Expected | Actual | Match |
|---|---|---|---|
| Freeze tree `NEW_VERIFICATION_BASELINE` | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` | `adda9d82e8af7bbff4c03043dad3db2a84d5b3ce4219b1ac184da3fc231161a2` | yes |
| Parquet file bytes | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` | `8ae800ef9f895e7767ff9ac582c5936d263f7492fec5ed7322f0d7b1b393e494` | yes |

Historical digest `b0f4760f…` remains **UNVERIFIED**.
