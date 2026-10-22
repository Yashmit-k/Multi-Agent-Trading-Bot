# Intraday stop/target exploration: protocol (exploratory)

Status: written 2026-10-20, **after** the selective-intraday study's result was seen.

**This is exploratory, not a confirmation.** The 2026 test period has already been looked at, so results on it are reported as "already-seen data". They cannot confirm anything. A positive result here would only justify a fresh pre-registered test on new data (live paper bars collected from 2026-10-21 on).

Inputs are fixed from [`intraday-selective-protocol.md`](intraday-selective-protocol.md):
- the same validated fused intraday signal;
- the chosen entry: threshold 0.8, strongest qualifying stock only, at most one trade per stock per day, signal bars 09:30–14:30;
- exit at 15:15 if neither the stop nor the target is hit;
- MIS charges, 5 bp slippage per fill, ₹20,000 per trade.

Grid (20 settings):
- **Stop:** 1%, 1.5%, 2%, 3% below entry. It fills at min(open, stop); a touch on the fill bar counts as stopped.
- **Target:** none, 0.5%, 1%, 1.5%, 2% above entry. It fills at max(open, target), from the bar after the fill. If one bar touches both, the stop wins.

Selection and reporting:
1. Pick the setting with the highest mean per-session net P&L on train (Apr 2024 – Jun 2025).
2. Report it on validate (Jul – Dec 2025) and on the already-seen 2026 data, with trades, win rate, net per trade, total, and the 90% block-bootstrap lower bound of session P&L.
3. Report every setting's train result, so the whole picture is visible.

A setting is only worth a fresh pre-registered test if it is profitable on both train and validate.
