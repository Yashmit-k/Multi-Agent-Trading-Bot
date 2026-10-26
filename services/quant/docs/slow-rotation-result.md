# Slow rotation: result

Protocol: [slow-rotation-protocol.md](slow-rotation-protocol.md), pre-registered 2026-10-26. Numbers: [results/slow-rotation-result.json](results/slow-rotation-result.json).

**Verdict:**
- Three rules pass the gate as written: `mom_12_1`, `mom_6_1` and `rev_21`.
- But simply **buying the same stocks equal-weight and holding them** does as well or better in most periods.
- So the gate's benchmark (NIFTY) was too easy. Most of the "beat" comes from the stock list (today's NIFTY 50 members, equal-weighted), not from the ranking.
- Weekly reversal (`rev_5`) loses heavily to charges.
- **No rule is moved to paper trading on this evidence.**

## Universe A (49 current members), simple annual return on capital

| Rule | Train 2016–20 | Validate 2021–23 | Test 2024–26 | Buys (train) | Charges (train) | Gate |
|---|---|---|---|---|---|---|
| NIFTY 50 (index) | 15.2% | 18.5% | 1.4% | — | — | — |
| **Equal-weight hold** | **24.6%** | **32.5%** | **6.2%** | 47 | ₹1,097 | — |
| `mom_12_1` monthly | 24.1% | 34.4% | 4.5% | 152 | ₹8,773 | pass |
| `mom_6_1` monthly | 22.2% | 24.9% | 2.5% | 207 | ₹12,005 | pass |
| `mom_12_1_q` quarterly | 21.7% | 22.8% | 2.6% | 81 | ₹4,581 | fail (bootstrap) |
| `rev_21` monthly | 22.3% | 23.1% | **9.0%** | 446 | ₹26,142 | pass |
| `rev_5` weekly | −4.1% | 3.2% | −11.0% | 1,085 | ₹63,886 | fail |

All returns are simple (not compounded): P&L ÷ capital ÷ years. Capital is ₹2,00,000 for top 10 and ₹1,00,000 for top 5.

Pooled 10th-percentile bootstrap of the mean monthly excess over NIFTY:
- `mom_12_1` +0.30%, `mom_6_1` +0.14%, `rev_21` +0.35% (above zero, so they pass);
- `mom_12_1_q` −0.14% and `rev_5` −1.71% (fail).

## Against equal-weight hold of the same stocks (percentage points a year)

This comparison is reported, not part of the gate.

| Rule | Train | Validate | Test | A+B train | A+B validate | A+B test |
|---|---|---|---|---|---|---|
| `mom_12_1` | −0.5 | +1.8 | −1.7 | +4.6 | +7.6 | −4.2 |
| `mom_6_1` | −2.5 | −7.7 | −3.7 | +5.9 | −9.4 | −3.1 |
| `mom_12_1_q` | −2.9 | −9.8 | −3.7 | +6.3 | −2.9 | −4.3 |
| `rev_21` | −2.4 | −9.4 | +2.8 | +2.9 | −4.4 | +0.3 |
| `rev_5` | −28.8 | −29.4 | −17.2 | −35.2 | −26.5 | −25.6 |

No rule beats equal-weight hold in all three periods on either universe.
- **`mom_12_1` comes closest:** it is roughly level on today's members, and ahead in 2016–2023 once former members are included. It falls behind in 2024–26.
- **`rev_21` is the only rule ahead in 2024–26 on both universes**, but it was well behind in 2021–23.

## Why the NIFTY benchmark misled

- **Survivorship.** Equal-weight hold of today's 49 members beat NIFTY by 9.5 points a year in 2016–20. Many of them are in the index today *because* they rose. With the 18 former members added, the gap shrinks to 2.7 points.
- **Equal weight vs market-cap weight.** NIFTY is dominated by its largest stocks, and equal weight tilts toward the smaller ones. That tilt paid in these years.
- **Compounding.** Equal-weight hold lets its winners compound, while the rotations take profit into cash that is not reinvested. This handicaps the rotations a little over five-year periods. The study does not correct for it.

The protocol should have used equal-weight hold as the gate benchmark. That is noted here and not changed after the fact.

## What it means (no change is made without approval)

1. **Slow rotation fixes the charges problem.** Monthly rules pay ₹5–26k over five years on ₹2 lakh, against more than ₹60k for weekly reversal. That is why `rev_5` fails while the monthly rules are profitable.
2. **It does not show stock-picking skill.** On NIFTY 50, a 12-month momentum or 1-month reversal ranking adds little or nothing over holding the stocks equally. Fifty large, heavily-researched stocks leave little to pick.
3. **The defensible use** is long-term holding with a simple rule, not short-term trading. If a rotation is tried, `mom_12_1` (strongest with former members included) is the candidate. It should go into a **paper forward test** against an equal-weight hold benchmark, in a new pre-registered protocol, before any claim is made.
