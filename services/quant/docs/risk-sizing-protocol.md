# Risk-based sizing study: pre-registered protocol

Status: **PRE-REGISTERED 2026-10-15, before any result of this study was computed.**

Study 3 (`ml-combined-*`) found a robust risk edge. Out of sample, a walk-forward logistic model predicts which stocks will be more volatile over the next 10 sessions with 62.7% accuracy, beating the persistence rule by 2.2–4.6 points. This study tests the use it was suited for: **sizing positions by predicted risk**.

Sizing changes how much is held, not which way prices move. It can lower volatility and drawdown, and so raise the Sharpe ratio, but it turns a losing book profitable only by luck. The verdict is therefore about risk-adjusted results, and profitability is reported separately.

## Data and model

Identical to study 3: 49 stocks; the same 37 features; walk-forward refits every 21 sessions with a 10-session embargo. The model is target B, P(high volatility over the next 10 sessions). No refitting or tuning for this study.

## Books (rebalanced every 10 sessions, Zerodha delivery costs and 5 bp slippage per fill)

| Book | Holdings | Equal weights | Risk weights |
|---|---|---|---|
| A. All stocks | every eligible stock | 1/N | ∝ (1 − p_high_vol), normalized |
| B. Momentum top 6 | 6 highest 20-session returns | 1/6 | ∝ (1 − p_high_vol), normalized |
| C. Model calm 24 | 24 lowest p_high_vol | 1/24 | ∝ (1 − p_high_vol), normalized |

Each position's net return is that stock's ₹20,000 delivery round trip. The portfolio return is the weighted mean of those net returns.

## Measures

For each book's risk-weighted and equal-weighted versions:
- annualized net return and annualized volatility;
- Sharpe ratio (per-window mean ÷ standard deviation, annualized);
- maximum drawdown of the compounded curve.

## Gate (per book)

"Risk sizing helps" requires all three:
1. Risk-weighted annualized volatility is lower than equal-weighted.
2. The risk-weighted maximum drawdown is no larger than equal-weighted.
3. The paired per-window difference in return ÷ volatility, i.e. Sharpe improvement (risk-weighted − equal-weighted), has a 90% stationary-block-bootstrap lower bound above −0.05 (mean block 4 windows, 2,000 resamples, seed 0).

**Profitable** is reported separately: risk-weighted annualized net return > 0.

## Use

If book B passes, risk weights may replace equal sizing in paper trading, but only after approval as an explicit change to the sizing rule. Each order still keeps the ₹20,000 cap. Nothing changes otherwise.
