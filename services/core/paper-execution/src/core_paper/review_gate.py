"""The portfolio-manager gate in the paper cycle.

A decision-engine BUY is queued for the manager (an LLM agent in its own container). The cycle waits
up to REVIEW_TIMEOUT for its verdict, then the risk engine runs with it:
- APPROVE: unchanged; REDUCE: the order quantity shrinks; VETO: the risk check "portfolio_manager" fails.
- No verdict in time: recorded as UNAVAILABLE and the normal rules decide, so a dead or rate-limited
  manager can slow an entry by at most REVIEW_TIMEOUT but never stop the system.
The manager can never create an order, enlarge one, or skip the risk engine.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from contracts.events import EventType, channel_for
from contracts.schemas.event import EventEnvelope
from contracts.schemas.review import ProposalReview, ReviewKind, ReviewRequest, ReviewVerdict

if TYPE_CHECKING:
    from core_db.repository import CoreRepository

REVIEW_TIMEOUT = timedelta(seconds=240)


def review_id_for(proposal_id: str) -> str:
    return "rv-" + hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()[:40]


def correlation_for(request: ReviewRequest) -> str:
    """A pipeline review joins its proposal's trace; an ad-hoc review is its own chain."""
    return request.proposal_id or request.review_id


def publish(publisher, event_type: EventType, event_id: str, correlation_id: str, payload, *, source: str, now: datetime) -> None:
    envelope = EventEnvelope(event_id=event_id, event_type=event_type, timestamp=now, source=source, correlation_id=correlation_id, payload=payload)
    publisher.publish(channel_for(event_type).value, envelope.model_dump_json())


def request_pipeline_review(repository: CoreRepository, publisher, proposal, now: datetime) -> ReviewRequest | None:
    """Queue a decision-engine BUY for the manager. Returns None when it is already queued."""
    request = ReviewRequest(
        review_id=review_id_for(proposal.proposal_id),
        kind=ReviewKind.PIPELINE,
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        horizon=proposal.horizon,
        side=proposal.side,
        quantity=proposal.quantity,
        entry_price=proposal.entry_price,
        aggregated_signal=proposal.aggregated_signal,
        aggregated_confidence=proposal.aggregated_confidence,
        requested_at=now,
        requested_by="decision-engine",
        metadata={"stop_loss": str(proposal.stop_loss), "take_profit": str(proposal.take_profit), "supporting_signal_ids": list(proposal.supporting_signal_ids)},
    )
    if not repository.insert_review(request):
        return None
    publish(publisher, EventType.REVIEW_REQUESTED, f"review.requested:{request.review_id}", correlation_for(request), request, source="decision-engine", now=now)
    return request


def expire_unanswered(repository: CoreRepository, publisher, request: ReviewRequest, now: datetime, *, waited: timedelta) -> ProposalReview:
    """The manager did not answer in time: record that, so the trace shows why the normal rules decided."""
    review = ProposalReview(
        review_id=request.review_id,
        kind=request.kind,
        proposal_id=request.proposal_id,
        symbol=request.symbol,
        verdict=ReviewVerdict.UNAVAILABLE,
        size_fraction=1.0,
        critique=f"No verdict within {int(waited.total_seconds())} s; the risk engine decides on its own.",
        reviewer="none",
        steps=len((repository.get_review(request.review_id) or {}).get("steps", [])),
        timestamp=now,
        metadata={"timeout_seconds": int(waited.total_seconds())},
    )
    if repository.complete_review(review, now):
        publish(publisher, EventType.REVIEW_COMPLETED, f"review.completed:{request.review_id}", correlation_for(request), review, source="paper-execution", now=now)
    return review


@dataclass(frozen=True)
class GateResult:
    wait: bool
    verdict: ReviewVerdict | None = None
    size_fraction: float = 1.0
    critique: str = ""


def review_gate(repository, publisher, proposal, now: datetime, *, timeout: timedelta = REVIEW_TIMEOUT) -> GateResult:
    """Where a BUY stands with the manager: still waiting, or a verdict to hand the risk engine."""
    row = repository.review_for_proposal(proposal.proposal_id)
    if row is None:
        request = request_pipeline_review(repository, publisher, proposal, now)
        if request is None:
            return GateResult(wait=True)
        row = repository.review_for_proposal(proposal.proposal_id)
    if row is None:
        return GateResult(wait=True)
    verdict = row.get("verdict")
    if verdict is None:
        waited = now - datetime.fromisoformat(row["created_at"]).astimezone(timezone.utc)
        if waited < timeout:
            return GateResult(wait=True)
        review = expire_unanswered(repository, publisher, ReviewRequest.model_validate(row["request"]), now, waited=waited)
        return GateResult(wait=False, verdict=review.verdict, size_fraction=1.0, critique=review.critique)
    parsed = ProposalReview.model_validate(verdict)
    return GateResult(wait=False, verdict=parsed.verdict, size_fraction=parsed.size_fraction, critique=parsed.critique)
