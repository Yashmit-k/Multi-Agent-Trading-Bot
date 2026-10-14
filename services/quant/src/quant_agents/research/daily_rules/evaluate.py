"""Score the pre-registered rules. No model is fit and no holdout path is accepted."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from random import Random

from quant_agents.research.daily_rules.costs import trade_pnl, window_return
from quant_agents.research.daily_rules.rules import (
    ALWAYS_LONG_FRACTION,
    BLOCK_LENGTH,
    BOOK,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    HORIZONS,
    MIN_12_1_NAMES,
    SCORE_UNTIL,
    WindowResult,
    low_volatility_names,
    momentum_12_1,
    momentum_20,
    realized_volatility,
)

RULES = ("buy_and_hold", "momentum_20", "momentum_12_1", "low_volatility")


def score_rules(series: dict[str, tuple[tuple[date, Decimal], ...]]) -> tuple[WindowResult, ...]:
    calendar = _calendar(series)
    results: list[WindowResult] = []
    for horizon in HORIZONS:
        hold = _windows(series, calendar, horizon, "buy_and_hold")
        for rule in RULES:
            windows = hold if rule == "buy_and_hold" else _windows(series, calendar, horizon, rule)
            shared = _paired(windows, hold)
            results.append(_summarize(horizon, rule, shared))
    return tuple(results)


def _calendar(series: dict[str, tuple[tuple[date, Decimal], ...]]) -> tuple[date, ...]:
    found = {session for rows in series.values() for session, _close in rows}
    return tuple(sorted(session for session in found if session <= SCORE_UNTIL))


def _windows(
    series: dict[str, tuple[tuple[date, Decimal], ...]],
    calendar: tuple[date, ...],
    horizon: int,
    rule: str,
) -> dict[date, tuple[Decimal, Decimal]]:
    indexed = {symbol: {session: close for session, close in rows} for symbol, rows in series.items()}
    ordered = {symbol: tuple(session for session, _close in rows) for symbol, rows in series.items()}
    out: dict[date, tuple[Decimal, Decimal]] = {}
    for start in range(0, len(calendar) - horizon, horizon):
        decision = calendar[start]
        horizon_day = calendar[start + horizon]
        if horizon_day > SCORE_UNTIL:
            continue
        selected, eligible = _select(rule, decision, horizon_day, indexed, ordered)
        if rule == "momentum_12_1" and len(eligible) < MIN_12_1_NAMES:
            continue
        if not eligible:
            continue
        if not selected:
            out[decision] = (Decimal(0), Decimal(0))
            continue
        slice_cash = BOOK / Decimal(len(selected))
        pnls = []
        for symbol in selected:
            p0 = indexed[symbol].get(decision)
            p1 = indexed[symbol].get(horizon_day)
            if p0 is None or p1 is None:
                continue
            pnls.append(trade_pnl(p0, p1, slice_cash))
        fraction = Decimal(len(selected)) / Decimal(len(eligible)) if eligible else Decimal(0)
        out[decision] = (window_return(pnls), fraction)
    return out


def _select(rule, decision, horizon_day, indexed, ordered) -> tuple[tuple[str, ...], tuple[str, ...]]:
    eligible = tuple(
        symbol
        for symbol, closes in indexed.items()
        if decision in closes and horizon_day in closes
    )
    if rule == "buy_and_hold":
        return eligible, eligible
    if rule == "momentum_20":
        chosen = []
        ready = []
        for symbol in eligible:
            signal = momentum_20(_history(ordered[symbol], indexed[symbol], decision))
            if signal is None:
                continue
            ready.append(symbol)
            if signal:
                chosen.append(symbol)
        return tuple(chosen), tuple(ready)
    if rule == "momentum_12_1":
        chosen = []
        ready = []
        for symbol in eligible:
            signal = momentum_12_1(_history(ordered[symbol], indexed[symbol], decision))
            if signal is None:
                continue
            ready.append(symbol)
            if signal:
                chosen.append(symbol)
        return tuple(chosen), tuple(ready)
    if rule == "low_volatility":
        vols = {}
        for symbol in eligible:
            value = realized_volatility(_history(ordered[symbol], indexed[symbol], decision))
            if value is not None:
                vols[symbol] = value
        return tuple(sorted(low_volatility_names(vols))), tuple(vols)
    raise ValueError(rule)


def _history(dates: tuple[date, ...], closes: dict[date, Decimal], decision: date) -> tuple[Decimal, ...]:
    return tuple(closes[session] for session in dates if session <= decision)


def _paired(
    rule_windows: dict[date, tuple[Decimal, Decimal]],
    hold_windows: dict[date, tuple[Decimal, Decimal]],
) -> tuple[tuple[date, Decimal, Decimal], ...]:
    shared = []
    for session, (rule_return, fraction) in rule_windows.items():
        if session not in hold_windows:
            continue
        shared.append((session, rule_return, hold_windows[session][0], fraction))
    return tuple(shared)


def _summarize(horizon: int, rule: str, shared: tuple[tuple[date, Decimal, Decimal, Decimal], ...]) -> WindowResult:
    if not shared:
        return WindowResult(horizon, rule, 0, Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(1), False)
    mean_return = sum((item[1] for item in shared), Decimal(0)) / Decimal(len(shared))
    excesses = [item[1] - item[2] for item in shared]
    mean_excess = sum(excesses, Decimal(0)) / Decimal(len(excesses))
    fraction = sum((item[3] for item in shared), Decimal(0)) / Decimal(len(shared))
    if rule == "buy_and_hold":
        return WindowResult(horizon, rule, len(shared), mean_return, Decimal(0), Decimal(0), Decimal(0), Decimal(1), False)
    lower, upper = _interval(excesses)
    passed = lower > 0 and fraction < ALWAYS_LONG_FRACTION
    return WindowResult(horizon, rule, len(shared), mean_return, mean_excess, lower, upper, fraction, passed)


def _interval(excesses: list[Decimal]) -> tuple[Decimal, Decimal]:
    if len(excesses) < BLOCK_LENGTH:
        return Decimal(0), Decimal(0)
    rng = Random(BOOTSTRAP_SEED)
    blocks = [excesses[index : index + BLOCK_LENGTH] for index in range(0, len(excesses) - BLOCK_LENGTH + 1)]
    needed = len(excesses)
    means: list[Decimal] = []
    for _draw in range(BOOTSTRAP_DRAWS):
        sample: list[Decimal] = []
        while len(sample) < needed:
            sample.extend(rng.choice(blocks))
        sample = sample[:needed]
        means.append(sum(sample, Decimal(0)) / Decimal(needed))
    means.sort()
    low_index = int(Decimal("0.025") * Decimal(len(means)))
    high_index = min(len(means) - 1, int(Decimal("0.975") * Decimal(len(means))))
    return means[low_index], means[high_index]
