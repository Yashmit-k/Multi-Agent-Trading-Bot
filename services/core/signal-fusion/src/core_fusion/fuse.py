"""Fuse one symbol and horizon. effective_signal = signal * confidence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import AgentName, Horizon
from contracts.schemas.agent_signal import AgentSignal

_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class Aggregate:
    symbol: str
    horizon: Horizon
    aggregated_signal: float
    aggregated_confidence: float
    supporting_signal_ids: tuple[str, ...]


def select_signals(signals: list[AgentSignal], *, horizon: Horizon, as_of: datetime) -> list[AgentSignal]:
    """Keep timestamp <= as_of and valid_until >= as_of, then the newest row per agent."""
    moment = _aware(as_of)
    window = [
        signal
        for signal in signals
        if signal.horizon == horizon and _aware(signal.timestamp) <= moment and _aware(signal.valid_until) >= moment
    ]
    newest: dict[AgentName, AgentSignal] = {}
    for signal in window:
        current = newest.get(signal.agent_name)
        if current is None or _newer(signal, current):
            newest[signal.agent_name] = signal
    return [newest[name] for name in sorted(newest, key=lambda item: item.value)]


def fuse(
    signals: list[AgentSignal],
    *,
    horizon: Horizon,
    as_of: datetime,
    weights: Mapping[Horizon, Mapping[str, float]] | None = None,
) -> Aggregate | None:
    selected = select_signals(signals, horizon=horizon, as_of=as_of)
    if not selected:
        return None
    weighted = [(signal, _weight(horizon, signal.agent_name, weights)) for signal in selected]
    total_weight = sum((weight for _, weight in weighted), Decimal("0"))
    if total_weight <= 0:
        return None
    signal_total = sum((weight * Decimal(str(signal.signal)) * Decimal(str(signal.confidence)) for signal, weight in weighted), Decimal("0"))
    confidence_total = sum((weight * Decimal(str(signal.confidence)) for signal, weight in weighted), Decimal("0"))
    return Aggregate(
        symbol=selected[0].symbol,
        horizon=horizon,
        aggregated_signal=_clipped_ratio(signal_total, total_weight),
        aggregated_confidence=_ratio(confidence_total, total_weight),
        supporting_signal_ids=tuple(signal.signal_id for signal in selected),
    )


def _weight(horizon: Horizon, agent: AgentName, weights: Mapping[Horizon, Mapping[str, float]] | None) -> Decimal:
    table = {} if weights is None else weights.get(horizon, {})
    value = Decimal(str(table.get(agent.value, 1.0)))
    if value < 0:
        raise ValueError("agent weights must be non-negative")
    return value


def _newer(candidate: AgentSignal, current: AgentSignal) -> bool:
    if _aware(candidate.timestamp) != _aware(current.timestamp):
        return _aware(candidate.timestamp) > _aware(current.timestamp)
    return candidate.signal_id > current.signal_id


def _ratio(numerator: Decimal, denominator: Decimal) -> float:
    return float((numerator / denominator).quantize(_QUANTUM))


def _clipped_ratio(numerator: Decimal, denominator: Decimal) -> float:
    raw = numerator / denominator
    if raw > 1:
        raw = Decimal("1")
    elif raw < -1:
        raw = Decimal("-1")
    return float(raw.quantize(_QUANTUM))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
