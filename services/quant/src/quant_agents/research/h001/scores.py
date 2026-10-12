"""Diagnostics and the primary gate. Symbol resampling does not capture a common market day."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math

import numpy as np

from quant_agents.research.h001.net import validation_net_summary
from quant_agents.research.h001.split import INCONCLUSIVE, SATISFIED

CLIP_LOW = 1e-6
CLIP_HIGH = 1 - 1e-6
BOOTSTRAP_SEED = 20261011
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_LIMITATION = (
    "Symbol-cluster resampling does not capture a shock shared across symbols on the same day."
)
QUANT_AGENT_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class ScoredRow:
    symbol: str
    y: int
    probability: float
    net: Decimal
    take_trade: bool


@dataclass(frozen=True, slots=True)
class Interval:
    lower: float
    upper: float
    limitation: str


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    brier: Interval
    log_loss: Interval
    mean_net: Interval
    limitation: str


@dataclass(frozen=True, slots=True)
class GateDecision:
    passed: bool
    mean_net: Decimal
    lower_bound: float
    limitation: str


def clip_probability(probability: float) -> float:
    return min(max(float(probability), CLIP_LOW), CLIP_HIGH)


def brier_score(labels: tuple[int, ...] | list[int], probabilities: tuple[float, ...] | list[float]) -> float:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must be the same non-empty length")
    total = 0.0
    for label, probability in zip(labels, probabilities, strict=True):
        total += (float(probability) - float(label)) ** 2
    return total / len(labels)


def log_loss(labels: tuple[int, ...] | list[int], probabilities: tuple[float, ...] | list[float]) -> float:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must be the same non-empty length")
    total = 0.0
    for label, probability in zip(labels, probabilities, strict=True):
        clipped = clip_probability(probability)
        y = float(label)
        total += -(y * math.log(clipped) + (1.0 - y) * math.log(1.0 - clipped))
    return total / len(labels)


def scoring_baseline_probability(training_prevalence: float) -> float:
    return float(training_prevalence)


def always_flat_contributions(count: int) -> tuple[Decimal, ...]:
    if count < 1:
        raise ValueError("count must be positive")
    return tuple(Decimal(0) for _ in range(count))


def always_long_mean(nets: tuple[Decimal, ...] | list[Decimal]) -> Decimal:
    if not nets:
        raise ValueError("nets must be non-empty")
    return sum(nets, Decimal(0)) / Decimal(len(nets))


def quant_agent_comparison(signal: object | None = None) -> str:
    """No signal is invented. A supplied object is still not treated as aligned."""
    del signal
    return QUANT_AGENT_NOT_APPLICABLE


def _symbols(rows: tuple[ScoredRow, ...] | list[ScoredRow]) -> tuple[str, ...]:
    return tuple(sorted({row.symbol for row in rows}))


def draw_symbols(symbols: tuple[str, ...] | list[str], *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> tuple[tuple[str, ...], ...]:
    ordered = tuple(symbols)
    if not ordered or resamples < 1:
        raise ValueError("symbols and resamples must be non-empty")
    generator = np.random.default_rng(seed)
    picks = generator.choice(len(ordered), size=(resamples, len(ordered)), replace=True)
    return tuple(tuple(ordered[int(index)] for index in draw) for draw in picks)


def pool_rows(draw: tuple[str, ...] | list[str], rows: tuple[ScoredRow, ...] | list[ScoredRow]) -> tuple[ScoredRow, ...]:
    """Each time a symbol is drawn, all of its rows are appended again."""
    grouped: dict[str, tuple[ScoredRow, ...]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, ())
        grouped[row.symbol] = grouped[row.symbol] + (row,)
    pooled: list[ScoredRow] = []
    for symbol in draw:
        pooled.extend(grouped[symbol])
    return tuple(pooled)


def _mean_contribution(rows: tuple[ScoredRow, ...]) -> float:
    summary = validation_net_summary(
        [row.net for row in rows],
        [row.take_trade for row in rows],
    )
    return float(summary.mean_all)


def _percentile_interval(values: list[float]) -> Interval:
    lower, upper = np.percentile(values, [2.5, 97.5])
    return Interval(float(lower), float(upper), BOOTSTRAP_LIMITATION)


def bootstrap(rows: tuple[ScoredRow, ...] | list[ScoredRow]) -> BootstrapResult:
    if not rows:
        raise ValueError("rows must be non-empty")
    draws = draw_symbols(_symbols(rows))
    brier_values: list[float] = []
    loss_values: list[float] = []
    mean_values: list[float] = []
    for draw in draws:
        pooled = pool_rows(draw, rows)
        labels = [row.y for row in pooled]
        probabilities = [row.probability for row in pooled]
        brier_values.append(brier_score(labels, probabilities))
        loss_values.append(log_loss(labels, probabilities))
        mean_values.append(_mean_contribution(pooled))
    return BootstrapResult(
        _percentile_interval(brier_values),
        _percentile_interval(loss_values),
        _percentile_interval(mean_values),
        BOOTSTRAP_LIMITATION,
    )


def acceptance_gate(
    *,
    mean_net: Decimal,
    lower_bound: float,
    leakage_ok: bool,
    train_status: str,
    validation_status: str,
) -> GateDecision:
    """A positive mean with a lower bound at or below zero does not pass."""
    sample_ok = train_status == SATISFIED and validation_status == SATISFIED
    passed = mean_net > 0 and lower_bound > 0 and leakage_ok and sample_ok
    if train_status == INCONCLUSIVE or validation_status == INCONCLUSIVE:
        passed = False
    return GateDecision(passed, mean_net, lower_bound, BOOTSTRAP_LIMITATION)
