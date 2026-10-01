"""Combine votes or a model probability into signal and confidence.

This module is exempt from the feature-arithmetic scanner. It must never
accept a FeatureView or a raw feature dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from quant_agents.vote import Vote


@dataclass(frozen=True, slots=True)
class Score:
    signal: float
    confidence: float


def _clamp(value: float) -> float:
    if value < -1.0:
        return -1.0
    if value > 1.0:
        return 1.0
    return value


def _unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def score_votes(
    votes: Sequence[Vote],
    *,
    required: Sequence[str],
    missing: Sequence[str],
) -> Score:
    if isinstance(votes, dict) or (votes is not None and hasattr(votes, "get") and not isinstance(votes, (list, tuple))):
        raise TypeError("score_votes does not accept a FeatureView or feature dict")
    if not isinstance(votes, (list, tuple)):
        raise TypeError("score_votes accepts only a sequence of Vote objects")
    for item in votes:
        if not isinstance(item, Vote):
            raise TypeError("score_votes accepts only Vote objects")
    missing_set = set(missing)
    required_total = len(tuple(required))
    missing_required = len([name for name in required if name in missing_set])
    present_ratio = 1.0 if required_total == 0 else (required_total - missing_required) / required_total
    weight_sum = 0.0
    signed = 0.0
    for vote in votes:
        weight_sum += vote.weight
        signed += vote.value * vote.weight
    if weight_sum == 0.0:
        raw = 0.0
        conf = 0.0
    else:
        raw = signed / weight_sum
        conf = min(1.0, abs(raw)) * present_ratio
    return Score(signal=_clamp(raw), confidence=_unit(conf))


def score_probability(probability: float, *, present_ratio: float = 1.0) -> Score:
    if isinstance(probability, Mapping) or hasattr(probability, "snapshot_features"):
        raise TypeError("score_probability does not accept a FeatureView or feature dict")
    if not isinstance(probability, (int, float)) or isinstance(probability, bool):
        raise TypeError("score_probability accepts a model probability in [0, 1]")
    if probability < 0.0 or probability > 1.0:
        raise ValueError("probability must be in [0, 1]")
    signal = _clamp((2.0 * float(probability)) - 1.0)
    return Score(signal=signal, confidence=_unit(abs(signal) * present_ratio))
