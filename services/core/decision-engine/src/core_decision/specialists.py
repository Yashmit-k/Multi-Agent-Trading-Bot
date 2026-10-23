"""Specialist decision mode: every agent has one job in a swing BUY, instead of one weighted average.

Order (swing, daily bars), with the newest valid opinion of each agent:
  1. Trigger        technical or momentum >= TRIGGER (confidence >= TRIGGER_CONFIDENCE) proposes a candidate
  2. Confirm        volume <= VOLUME_BLOCK blocks (heavy selling)
  3. Not stretched  mean_reversion <= STRETCH_BLOCK blocks (closed above the upper band)
  4. Event check    news or earnings <= EVENT_BLOCK with confidence >= EVENT_CONFIDENCE blocks
  5. Quality check  fundamental and valuation both <= QUALITY_BLOCK blocks
  6. Market         regime risk-off (NIFTY downtrend and India VIX rising) halves the size; it never blocks
The portfolio manager and the risk engine then run as for any BUY. LLM opinions produced by the keyword
fallback (no model answered) are ignored here: they can neither block nor trigger. Only rule agents trigger,
so the system can still trade when the LLM quota is used up.

These thresholds are design choices, not a validated edge (see services/quant/docs/agent-tuning-result.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from contracts.enums import Horizon
from contracts.schemas.agent_signal import AgentSignal
from core_fusion import Aggregate, select_signals

TRIGGER = 0.3
TRIGGER_CONFIDENCE = 0.4
VOLUME_BLOCK = -0.3
STRETCH_BLOCK = -0.5
EVENT_BLOCK = -0.3
EVENT_CONFIDENCE = 0.3
QUALITY_BLOCK = -0.5
RISK_OFF_SIZE = 0.5

ROLES: dict[str, str] = {
    "technical": "trigger",
    "momentum": "trigger",
    "volume": "confirm",
    "mean_reversion": "not_stretched",
    "news": "event_check",
    "earnings": "event_check",
    "fundamental": "quality_check",
    "valuation": "quality_check",
    "regime": "market",
}


@dataclass(frozen=True)
class SpecialistDecision:
    buy: bool
    size_fraction: float
    verdicts: list[dict[str, object]] = field(default_factory=list)
    signal: float = 0.0
    confidence: float = 0.0
    supporting_signal_ids: tuple[str, ...] = ()

    def aggregate(self, symbol: str) -> Aggregate:
        """The proposal fields the decision engine needs, from the triggering agent."""
        return Aggregate(symbol, Horizon.SWING, self.signal, self.confidence, self.supporting_signal_ids)


def is_fallback(signal: AgentSignal) -> bool:
    """An LLM agent's opinion made by the keyword heuristic because no model answered."""
    if {"fixture.heuristic", "llm_unavailable"} & set(signal.reason_codes):
        return True
    llm = signal.metadata.get("llm")
    if isinstance(llm, dict):
        llm = [llm]
    return isinstance(llm, list) and bool(llm) and all(isinstance(item, dict) and (item.get("fallback") or item.get("model") == "fixture") for item in llm)


def _verdict(agent: str, signal: AgentSignal | None, outcome: str, detail: str) -> dict[str, object]:
    return {
        "agent": agent,
        "role": ROLES[agent],
        "outcome": outcome,  # trigger / pass / block / no_opinion / ignored_fallback / size
        "signal": None if signal is None else round(signal.signal, 4),
        "confidence": None if signal is None else round(signal.confidence, 4),
        "detail": detail,
    }


def _risk_off(signal: AgentSignal | None) -> bool:
    if signal is None:
        return False
    votes = {str(vote.get("name")): vote.get("value") for vote in signal.metadata.get("votes", []) if isinstance(vote, dict)}
    return votes.get("index_trend") == -1 and votes.get("fear_gauge") == -1


def decide(signals: list[AgentSignal], *, as_of: datetime) -> SpecialistDecision:
    """Run the six specialist steps on one stock's swing opinions. Every step is recorded, even after a block."""
    newest = {item.agent_name.value: item for item in select_signals(signals, horizon=Horizon.SWING, as_of=as_of)}
    verdicts: list[dict[str, object]] = []
    blocked = False

    trigger: AgentSignal | None = None
    for agent in ("technical", "momentum"):
        item = newest.get(agent)
        if item is None:
            verdicts.append(_verdict(agent, None, "no_opinion", "no valid opinion"))
        elif item.signal >= TRIGGER and item.confidence >= TRIGGER_CONFIDENCE:
            verdicts.append(_verdict(agent, item, "trigger", f"{item.signal:+.2f} >= {TRIGGER} with confidence {item.confidence:.2f}"))
            if trigger is None or item.signal * item.confidence > trigger.signal * trigger.confidence:
                trigger = item
        else:
            verdicts.append(_verdict(agent, item, "pass", f"{item.signal:+.2f} (confidence {item.confidence:.2f}) does not trigger"))

    def threshold_step(agent: str, limit: float, what: str, *, min_confidence: float = 0.0, llm: bool = False) -> None:
        nonlocal blocked
        item = newest.get(agent)
        if item is None:
            verdicts.append(_verdict(agent, None, "no_opinion", "no valid opinion"))
        elif llm and is_fallback(item):
            verdicts.append(_verdict(agent, item, "ignored_fallback", "keyword fallback, not a model answer: ignored"))
        elif item.signal <= limit and item.confidence >= min_confidence:
            verdicts.append(_verdict(agent, item, "block", f"{item.signal:+.2f} <= {limit}: {what}"))
            blocked = True
        else:
            verdicts.append(_verdict(agent, item, "pass", f"{item.signal:+.2f}: no {what}"))

    threshold_step("volume", VOLUME_BLOCK, "heavy selling")
    threshold_step("mean_reversion", STRETCH_BLOCK, "overstretched above the upper band")
    threshold_step("news", EVENT_BLOCK, "bad news", min_confidence=EVENT_CONFIDENCE, llm=True)
    threshold_step("earnings", EVENT_BLOCK, "bad results", min_confidence=EVENT_CONFIDENCE, llm=True)

    quality = []
    for agent in ("fundamental", "valuation"):
        item = newest.get(agent)
        if item is None:
            verdicts.append(_verdict(agent, None, "no_opinion", "no valid opinion"))
        elif is_fallback(item):
            verdicts.append(_verdict(agent, item, "ignored_fallback", "keyword fallback, not a model answer: ignored"))
        else:
            quality.append((agent, item))
    weak = [item for _, item in quality if item.signal <= QUALITY_BLOCK]
    both_weak = len(quality) == 2 and len(weak) == 2
    for agent, item in quality:
        if both_weak:
            verdicts.append(_verdict(agent, item, "block", f"{item.signal:+.2f}: fundamental and valuation both <= {QUALITY_BLOCK}"))
        else:
            verdicts.append(_verdict(agent, item, "pass", f"{item.signal:+.2f}: blocks only when both are <= {QUALITY_BLOCK}"))
    blocked = blocked or both_weak

    regime = newest.get("regime")
    off = _risk_off(regime)
    if regime is None:
        verdicts.append(_verdict("regime", None, "no_opinion", "no valid opinion: full size"))
    elif off:
        verdicts.append(_verdict("regime", regime, "size", f"risk-off (NIFTY downtrend, VIX rising): size x{RISK_OFF_SIZE}"))
    else:
        verdicts.append(_verdict("regime", regime, "pass", "not risk-off: full size"))

    buy = trigger is not None and not blocked
    consulted = tuple(item.signal_id for agent, item in newest.items() if agent in ROLES)
    return SpecialistDecision(
        buy=buy,
        size_fraction=RISK_OFF_SIZE if off else 1.0,
        verdicts=verdicts,
        signal=0.0 if trigger is None else float(trigger.signal),
        confidence=0.0 if trigger is None else float(trigger.confidence),
        # The trigger first: risk's evidence check reads these, and the trigger is a rule agent (never a fallback).
        supporting_signal_ids=((trigger.signal_id,) + tuple(sid for sid in consulted if sid != trigger.signal_id)) if trigger else consulted,
    )
