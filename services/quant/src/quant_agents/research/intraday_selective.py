"""Selective intraday trading on the validated signal, per services/quant/docs/intraday-selective-protocol.md.

Reuses the agent-tuning study's cached features and its validated intraday signal unchanged.

    python -m quant_agents.research.intraday_selective
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

from quant_agents.research import agent_tuning as at
from quant_agents.research import exit_rules as er

CONFIGS = {
    "momentum": ({"noise_z": 1.0, "adx_trend": 20.0}, True),
    "mean_reversion": ({"adx_cut": math.inf}, False),
    "volume": ({"surge": 3.0}, True),
    "technical": ({"dead_scale": 2.0}, True),
}
WEIGHTS = {"momentum": 0.575, "mean_reversion": 0.30, "volume": 0.125, "technical": 0.0}
THRESHOLDS = (0.4, 0.6, 0.8)
HOLDS = (12, 24, None)  # None = until the bar ending 15:15
SELECTIONS = ("all", "top1")
FIRST_SIGNAL, LAST_SIGNAL, SQUARE_OFF = 930, 1430, 1515
STOP = 0.02
SLIP = 0.0005
NOTIONAL = 20000.0


def simulate(panel: at.Panel, signal: np.ndarray, confidence: np.ndarray, period: tuple[date, date], threshold: float, hold: int | None, selection: str) -> dict[str, object]:
    from core_api.strategy_lab import leg_charges

    rows = np.where(at._period_mask(panel, period))[0]
    n_sym = len(panel.symbols)
    qualifies = (signal >= threshold) & (confidence >= 0.3) & (panel.clock[:, None] >= FIRST_SIGNAL) & (panel.clock[:, None] <= LAST_SIGNAL)
    qualifies &= ~np.isnan(panel.open)
    if selection == "top1":
        masked = np.where(qualifies, signal, -np.inf)
        best = np.argmax(masked, axis=1)
        top = np.zeros_like(qualifies)
        has = qualifies.any(axis=1)
        top[np.arange(len(best))[has], best[has]] = True
        qualifies = top
    traded_day = np.zeros((n_sym,), dtype=int)  # last session ordinal traded per stock
    busy_until = np.full(n_sym, -1)
    row_pos = {int(r): k for k, r in enumerate(rows)}
    trades: list[tuple[int, float, str]] = []
    for k, r in enumerate(rows):
        for j in np.where(qualifies[r])[0]:
            if traded_day[j] == panel.sessions[r] or busy_until[j] >= k:
                continue
            # next bar of the same stock, same session
            nxt = k + 1
            while nxt < len(rows) and np.isnan(panel.open[rows[nxt], j]):
                nxt += 1
            if nxt >= len(rows) or panel.sessions[rows[nxt]] != panel.sessions[r]:
                continue
            entry = float(panel.open[rows[nxt], j]) * (1 + SLIP)
            qty = int(NOTIONAL // entry)
            if qty < 1:
                continue
            stop = entry * (1 - STOP)
            exit_price, reason, last = None, "square_off", nxt
            held = 0
            m = nxt
            while m < len(rows) and panel.sessions[rows[m]] == panel.sessions[r]:
                q = rows[m]
                if np.isnan(panel.close[q, j]):
                    m += 1
                    continue
                if panel.clock[q] > SQUARE_OFF:
                    break
                last = m
                held += 1
                if panel.low[q, j] <= stop:
                    exit_price, reason = (stop if m == nxt else min(float(panel.open[q, j]), stop)), "stop"
                    break
                if hold is not None and held >= hold:
                    exit_price, reason = float(panel.close[q, j]), "hold"
                    break
                if panel.clock[q] == SQUARE_OFF:
                    exit_price, reason = float(panel.close[q, j]), "square_off"
                    break
                m += 1
            if exit_price is None:
                exit_price = float(panel.close[rows[last], j])
            exit_price *= 1 - SLIP
            net = (exit_price - entry) * qty - leg_charges(entry * qty, exit_price * qty, "MIS")
            trades.append((int(panel.sessions[r]), net, reason))
            traded_day[j] = panel.sessions[r]
            busy_until[j] = last
    days = sorted({int(d) for d in panel.sessions[rows]})
    per_day = {d: 0.0 for d in days}
    for day, net, _ in trades:
        per_day[day] += net
    series = np.array([per_day[d] for d in days])
    half = len(days) // 2
    nets = [t[1] for t in trades]
    return {
        "trades": len(trades),
        "win_rate": float(np.mean([v > 0 for v in nets])) if nets else None,
        "net_per_trade": float(np.mean(nets)) if nets else None,
        "total_net": float(sum(nets)),
        "mean_session_net": float(series.mean()) if len(series) else 0.0,
        "session_low90": at.bootstrap_low(series),
        "first_half": float(series[:half].sum()),
        "second_half": float(series[half:].sum()),
        "exits": {reason: sum(1 for t in trades if t[2] == reason) for reason in sorted({t[2] for t in trades})},
    }


def run() -> dict[str, object]:
    panel = at.build_panel("5m")
    signal, confidence = at.fused(panel, CONFIGS, WEIGHTS, old_rule=False)
    settings = [(t, h, s) for t in THRESHOLDS for h in HOLDS for s in SELECTIONS]
    grid = []
    for threshold, hold, selection in settings:
        train = simulate(panel, signal, confidence, at.TRAIN, threshold, hold, selection)
        grid.append({"threshold": threshold, "hold": hold or "15:15", "selection": selection, "train": train})
        print("train", threshold, hold, selection, train["trades"], round(train["total_net"]), round(train["net_per_trade"] or 0, 1), flush=True)
    eligible = [item for item in grid if item["train"]["trades"] >= 200]
    chosen = max(eligible, key=lambda item: item["train"]["mean_session_net"]) if eligible else None
    report: dict[str, object] = {"protocol": "services/quant/docs/intraday-selective-protocol.md", "grid": grid, "chosen": None}
    if chosen is None:
        report["verdict"] = "no setting had 200 train trades"
        return report
    hold = None if chosen["hold"] == "15:15" else chosen["hold"]
    validate = simulate(panel, signal, confidence, at.VALIDATE, chosen["threshold"], hold, chosen["selection"])
    test = simulate(panel, signal, confidence, at.TEST, chosen["threshold"], hold, chosen["selection"])
    validated = validate["total_net"] > 0
    works = bool(validated and test["trades"] >= 100 and test["total_net"] > 0 and test["session_low90"] > 0 and test["first_half"] > 0 and test["second_half"] > 0)
    report.update({"chosen": {k: chosen[k] for k in ("threshold", "hold", "selection")}, "train": chosen["train"], "validate": validate, "validated": validated, "test": test, "works": works})
    print("chosen", report["chosen"], "validate", round(validate["total_net"]), "test", round(test["total_net"]), "works", works, flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=er.ROOT / "services/quant/docs/results/intraday-selective-result.json")
    args = parser.parse_args()
    args.out.write_text(json.dumps(run(), indent=2, default=str))


if __name__ == "__main__":
    main()
