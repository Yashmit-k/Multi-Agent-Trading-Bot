"""Chronological split, H1 purge, and the smaller-class check. No rows are loaded here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_agents.research.h001.events import ExclusionReason

TRAIN_END = date(2024, 6, 30)
VALIDATION_END = date(2025, 2, 14)
PREDICTOR_COUNT = 4
P_WITH_INTERCEPT = PREDICTOR_COUNT + 1
MINORITY_BAR = 10 * P_WITH_INTERCEPT
SATISFIED = "SATISFIED"
INCONCLUSIVE = "INCONCLUSIVE"


class UnexpectedDecisionDate(ValueError):
    """An eligible decision falls after the approved validation window."""

    def __init__(self, decision: date) -> None:
        self.decision = decision
        super().__init__(
            f"decision session {decision.isoformat()} is after {VALIDATION_END.isoformat()}; "
            "the window is not extended"
        )


@dataclass(frozen=True, slots=True)
class Assignment:
    seq_id: str
    symbol: str
    decision: date
    h1_session: date
    partition: str
    reason: ExclusionReason | None


@dataclass(frozen=True, slots=True)
class SampleCheck:
    status: str
    minority_count: int
    both_classes: bool


def assign_partition(seq_id: str, symbol: str, decision: date, h1_session: date) -> Assignment:
    """Training on or before 2024-06-30, unless the H1 session ends after that date."""
    if decision > VALIDATION_END:
        raise UnexpectedDecisionDate(decision)
    if decision <= TRAIN_END:
        if h1_session > TRAIN_END:
            return Assignment(seq_id, symbol, decision, h1_session, "purged", ExclusionReason.PURGED_EMBARGO)
        return Assignment(seq_id, symbol, decision, h1_session, "train", None)
    return Assignment(seq_id, symbol, decision, h1_session, "validation", None)


def smaller_class_check(labels: tuple[int, ...] | list[int]) -> SampleCheck:
    """50 is the bar on the smaller class. Missing it is INCONCLUSIVE, not a retune."""
    if any(label not in (0, 1) for label in labels):
        raise ValueError("labels must be 0 or 1")
    positives = sum(labels)
    negatives = len(labels) - positives
    both = positives > 0 and negatives > 0
    minority = min(positives, negatives) if both else 0
    status = SATISFIED if both and minority >= MINORITY_BAR else INCONCLUSIVE
    return SampleCheck(status, minority, both)
