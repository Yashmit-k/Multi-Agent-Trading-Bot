# Earnings drift: result

Protocol: [earnings-drift-protocol.md](earnings-drift-protocol.md), pre-registered 2026-10-27. Numbers: [results/earnings-drift-result.json](results/earnings-drift-result.json).

1,866 quarterly results (48 NIFTY 50 stocks, 2015–2025) had a full price window. Returns are after delivery charges and 10 bp of slippage. **Excess** means relative to the equal-weight average of the other stocks over the same days.

> **Update 2026-10-27: rejected.** The candidate below failed the clean test on 42 unseen trades (−1.53% net excess per trade). See the last section.

**Verdict (in-sample):**
- **One rule of four passes the gate:** `pos4_h40` (buy when the reaction is ≥ +4%, hold 40 sessions).
- It does **not** survive the stricter check for having tried four rules.
- So it is a **candidate, not a proven edge**. It needs a clean test on results the study has never seen before anything else.

## Mean net excess per trade

| Rule | Train 2015–19 | Validate 2020–22 | Test 2023–25 | Pooled | 10th pct (quarter bootstrap) | Gate |
|---|---|---|---|---|---|---|
| `pos2_h20` | −0.53% (184) | +0.55% (159) | +0.18% (104) | +0.02% | −0.32% | fail |
| `pos4_h20` | −0.29% (69) | +0.42% (85) | −0.13% (55) | +0.04% | −0.51% | fail |
| `pos2_h40` | −0.15% (184) | +0.58% (159) | +0.10% (104) | +0.17% | −0.41% | fail |
| **`pos4_h40`** | **+1.55%** (69) | **+0.84%** (85) | **+0.59%** (55) | **+1.01%** | **+0.15%** | **pass** |

For `pos4_h40`:
- Median net excess per period: +1.76%, −0.23%, +1.49%.
- Win rate against the universe: 58%, 47%, 60%.
- Raw net return per trade (not market-adjusted): +3.1%, +5.9%, +3.4%.
- The pooled 2.5th percentile is −0.32%, so it fails the four-rule (Bonferroni-style) check.
- The edge shrinks period by period: +1.55%, then +0.84%, then +0.59%.

## The drift curve (20 sessions, gross excess, all periods)

| Reaction quintile | Mean reaction | Mean excess over the next 20 sessions |
|---|---|---|
| Q1 (worst) | −4.6% | **−0.73%** |
| Q2 | −1.4% | +0.33% |
| Q3 | −0.1% | +0.11% |
| Q4 | +1.4% | +0.12% |
| Q5 (best) | +5.3% | **+0.39%** |

The pattern is there at the extremes: strong reactions keep drifting the same way. It is small, though.
- Over 20 sessions the best quintile drifts about +0.4%, roughly the cost of a round trip, which is why the 20-session rules fail.
- Only the strongest reactions, held about two months, clear the costs.
- **Bad results keep falling** (−0.7%). That can't be shorted in the cash market, but it is a useful *avoid* signal for any other strategy.

## What it means (no change is made without approval)

1. **This is the most promising signal found so far, apart from the dip rule.** It also fits theory: post-earnings drift is one of the best-documented market anomalies.
2. **It is not yet good enough to trade.**
   - One of four rules passed, and the bootstrap margin is thin.
   - The edge is shrinking over time.
   - There are only about 14 trades a year across NIFTY 50.
3. **A clean next test is possible.** NSE has published about six more quarters of results since this extract ended (March 2025 to October 2026). Those results have never been seen by any study. They could be fetched and `pos4_h40` scored on them **once, unchanged**.
4. **The "avoid" side** (do not buy a stock in the 20 sessions after a reaction worse than about −2.3%) could be tested as a blocker for the dip strategy. That would be its own pre-registered study.

## Clean test on unseen results (Amendment A, 2026-10-27)

Results published from March 2025 to August 2026 were fetched from NSE announcements on 2026-10-27. That is 295 events across 7 results seasons. The announcement rule found 180 of 180 of the 2024 events correctly (Amendment A.1). `pos4_h40` was scored once, unchanged. Numbers: [results/earnings-drift-clean-result.json](results/earnings-drift-clean-result.json).

**Verdict: `pos4_h40` fails the clean test. The earnings-drift candidate is rejected.**

| Rule | Trades | Mean net excess | Median | Win rate vs universe | Mean net raw | 10th pct |
|---|---|---|---|---|---|---|
| **`pos4_h40` (scored)** | 42 | **−1.53%** | −2.14% | 36% | −2.45% | −2.36% |
| `pos2_h40` (info) | 80 | −0.81% | −1.07% | 39% | −1.38% | −1.75% |
| `pos4_h20` (info) | 45 | −1.45% | −0.91% | 40% | −2.28% | −2.07% |
| `pos2_h20` (info) | 85 | −1.02% | −0.95% | 41% | −1.06% | −1.62% |

`pos4_h40` by results season (mean net excess):

| Season | Trades | Mean |
|---|---|---|
| 2025 Q2 | 6 | +1.7% |
| 2025 Q3 | 5 | −2.0% |
| 2025 Q4 | 6 | +0.7% |
| 2026 Q1 | 10 | −3.1% |
| 2026 Q2 | 10 | −2.3% |
| 2026 Q3 | 5 | −3.0% |

It lost in four of six seasons. **On recent data, the strongest positive reactions were followed by underperformance, not drift.**

**The new timing is not the cause.** As a diagnostic on 2024 (already seen), the earlier announcement times give `pos4_h40` **+2.20%** (35 trades), against +0.59% with the endpoint's times. The earlier times make the rule look better, not worse.

**What it means:**
- The in-sample edge was already shrinking (+1.55% → +0.84% → +0.59%), and on unseen data it is gone.
- The drift that research found in older and smaller-stock markets does not survive on today's NIFTY 50 after costs.
- No change follows. The "avoid after a bad reaction" idea is untested and stays only an idea.
