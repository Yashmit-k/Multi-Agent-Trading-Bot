"""Swing agent replay, per services/quant/docs/agent-replay-protocol.md.

Each quant agent trades alone with the live swing order rules; then the specialists blockers and the
regime's half size are judged on the technical/momentum candidates; then trigger-only vs full specialists.

    python -m quant_agents.research.agent_replay
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

PERIODS = {"train": at.TRAIN, "validate": at.VALIDATE, "test": at.TEST}
TRIGGER, TRIGGER_CONFIDENCE = 0.30, 0.40
VOLUME_BLOCK, STRETCH_BLOCK = -0.30, -0.50
LIMIT_PREMIUM, TICK = 0.0025, 0.05
STOP, TARGET = 0.98, 1.04
MAX_SESSIONS = 10
SIZE = 20_000.0
EXIT_SLIP = 0.0005
QUANT = ("technical", "momentum", "mean_reversion", "volume")


def _charges(buy: float, sell: float) -> float:
    from core_api.strategy_lab import leg_charges

    return leg_charges(buy, sell, "CNC")


def simulate(panel: at.Panel, j: int, rows: np.ndarray, k: int, size: float) -> tuple[float, str, int] | None:
    """One swing BUY signalled at the close of rows[k]: (net, exit reason, index of the exit row), or None if unfilled."""
    if k + 1 >= len(rows):
        return None
    close = float(panel.close[rows[k], j])
    limit = math.floor(close * (1 + LIMIT_PREMIUM) / TICK + 1e-9) * TICK
    e = rows[k + 1]
    open_, low = float(panel.open[e, j]), float(panel.low[e, j])
    if open_ <= limit:
        entry = open_
    elif low <= limit:
        entry = limit
    else:
        return None
    qty = int(size // entry)
    if qty < 1:
        return None
    stop, target = round(close * STOP, 2), round(close * TARGET, 2)
    exit_price, reason, m = None, "end", k + 1
    last = min(k + 1 + MAX_SESSIONS, len(rows) - 1)
    while m <= last:
        q = rows[m]
        o, h, lo, c = (float(a[q, j]) for a in (panel.open, panel.high, panel.low, panel.close))
        if m == k + 1:
            if lo <= stop:
                exit_price, reason = min(stop, entry), "stop"
                break
        elif lo <= stop:
            exit_price, reason = min(stop, o), "stop"
            break
        elif h >= target:
            exit_price, reason = max(target, o), "target"
            break
        if m == last:
            exit_price, reason = c, ("time" if m == k + 1 + MAX_SESSIONS else "end")
            break
        m += 1
    assert exit_price is not None
    exit_price *= 1 - EXIT_SLIP
    net = (exit_price - entry) * qty - _charges(entry * qty, exit_price * qty)
    return net, reason, m


def _mean_ci(values: list[float], seed: int = 0) -> tuple[float, float, float]:
    if not values:
        return (math.nan, math.nan, math.nan)
    arr = np.array(values)
    rng = np.random.default_rng(seed)
    means = arr[rng.integers(0, len(arr), size=(2000, len(arr)))].mean(axis=1)
    return float(arr.mean()), float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))


def _summary(trades: list[tuple[int, float, str]], days: list[int]) -> dict[str, object]:
    """trades: (exit session ordinal, net, reason)."""
    nets = [t[1] for t in trades]
    per_day: dict[int, float] = {}
    for day, net, _ in trades:
        per_day[day] = per_day.get(day, 0.0) + net
    mean, low, high = _mean_ci(nets)
    return {
        "trades": len(nets),
        "win_rate": float(np.mean([n > 0 for n in nets])) if nets else math.nan,
        "total_net": float(sum(nets)),
        "mean_net": mean,
        "mean_net_90": [low, high],
        "session_pnl_low90": at.bootstrap_low(np.array([per_day.get(d, 0.0) for d in days])) if days else math.nan,
        "exits": {r: sum(1 for t in trades if t[2] == r) for r in sorted({t[2] for t in trades})},
    }


def risk_off(panel: at.Panel) -> np.ndarray:
    nifty, vix = at.load("NIFTY50", "1d"), at.load("INDIAVIX", "1d")
    n_pos = {v: k for k, v in enumerate(nifty["ends"])}
    v_pos = {v: k for k, v in enumerate(vix["ends"])}
    out = np.zeros(len(panel.stamps), dtype=bool)
    for r, stamp in enumerate(panel.stamps):
        a, b = n_pos.get(stamp), v_pos.get(stamp)
        if a is not None and b is not None:
            out[r] = bool(nifty["ema_12"][a] < nifty["ema_26"][a] and vix["return_1"][b] > 0)
    return out


def _trigger(signal: np.ndarray, confidence: np.ndarray) -> np.ndarray:
    return (np.nan_to_num(signal, nan=-9) >= TRIGGER - 1e-12) & (np.nan_to_num(confidence, nan=0) >= TRIGGER_CONFIDENCE - 1e-12)


def run_book(panel: at.Panel, entries: np.ndarray, size: np.ndarray, period: tuple[date, date]) -> dict[str, object]:
    """One position per stock: a new entry only after the previous trade has exited."""
    mask = at._period_mask(panel, period)
    trades = []
    for j, symbol in enumerate(panel.symbols):
        rows = panel.index_of[symbol]
        k = 0
        while k < len(rows):
            r = rows[k]
            if mask[r] and entries[r, j]:
                result = simulate(panel, j, rows, k, SIZE * size[r])
                if result is not None:
                    net, reason, m = result
                    trades.append((int(panel.sessions[rows[m]]), net, reason))
                    k = m  # the exit session's close may signal the next entry
                    continue
            k += 1
    days = sorted({int(d) for d in panel.sessions[mask]})
    return _summary(trades, days)


def blockers(panel: at.Panel, sig: dict[str, tuple[np.ndarray, np.ndarray]], off: np.ndarray) -> dict[str, object]:
    candidates = _trigger(*sig["technical"]) | _trigger(*sig["momentum"])
    steps = {
        "volume": np.nan_to_num(sig["volume"][0], nan=0) <= VOLUME_BLOCK + 1e-12,
        "mean_reversion": np.nan_to_num(sig["mean_reversion"][0], nan=0) <= STRETCH_BLOCK + 1e-12,
        "regime_risk_off": np.repeat(off[:, None], len(panel.symbols), axis=1),
    }
    out: dict[str, object] = {}
    for label, period in PERIODS.items():
        mask = at._period_mask(panel, period)
        outcome: dict[tuple[int, int], float] = {}
        for j, symbol in enumerate(panel.symbols):
            rows = panel.index_of[symbol]
            for k, r in enumerate(rows):
                if mask[r] and candidates[r, j]:
                    result = simulate(panel, j, rows, k, SIZE)
                    if result is not None:
                        outcome[(r, j)] = result[0]
        part: dict[str, object] = {"candidates_filled": len(outcome), "all": _summary([(0, n, "") for n in outcome.values()], [])}
        for name, flag in steps.items():
            blocked = [n for (r, j), n in outcome.items() if flag[r, j]]
            passed = [n for (r, j), n in outcome.items() if not flag[r, j]]
            part[name] = {
                "blocked": {k: v for k, v in _summary([(0, n, "") for n in blocked], []).items() if k in ("trades", "win_rate", "mean_net", "mean_net_90")},
                "passed": {k: v for k, v in _summary([(0, n, "") for n in passed], []).items() if k in ("trades", "win_rate", "mean_net", "mean_net_90")},
            }
        out[label] = part
    verdict = {}
    for name in steps:
        wins = 0
        for label in PERIODS:
            b, p = out[label][name]["blocked"], out[label][name]["passed"]  # type: ignore[index]
            if b["trades"] and b["mean_net"] < p["mean_net"] and b["mean_net_90"][1] < 0:
                wins += 1
        verdict[name] = {"periods_meeting_rule": wins, "useful": wins >= 2}
    out["verdict"] = verdict
    return out


def run() -> dict[str, object]:
    panel = at.build_panel("1d")
    sig = {name: at.agent_matrix(panel, name, at.DEFAULTS[name]) for name in QUANT}
    off = risk_off(panel)
    full = np.ones(len(panel.stamps))
    report: dict[str, object] = {
        "protocol": "services/quant/docs/agent-replay-protocol.md",
        "periods": PERIODS,
        "symbols": len(panel.symbols),
        "risk_off_share": {label: float(off[at._period_mask(panel, p)].mean()) for label, p in PERIODS.items()},
    }
    report["alone"] = {name: {label: run_book(panel, _trigger(*sig[name]), full, p) for label, p in PERIODS.items()} for name in QUANT}
    print("alone done", flush=True)
    report["blockers"] = blockers(panel, sig, off)
    print("blockers done", flush=True)
    trigger = _trigger(*sig["technical"]) | _trigger(*sig["momentum"])
    blocked = (np.nan_to_num(sig["volume"][0], nan=0) <= VOLUME_BLOCK + 1e-12) | (np.nan_to_num(sig["mean_reversion"][0], nan=0) <= STRETCH_BLOCK + 1e-12)
    half = np.where(off, 0.5, 1.0)
    report["specialists"] = {
        label: {
            "trigger_only": run_book(panel, trigger, full, p),
            "specialists": run_book(panel, trigger & ~blocked, half, p),
        }
        for label, p in PERIODS.items()
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=er.ROOT / "services/quant/docs/results/agent-replay-result.json")
    args = parser.parse_args()
    report = run()
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
