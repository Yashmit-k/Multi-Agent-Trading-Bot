"""Storage for portfolio-manager reviews.

A review moves pending -> running (claimed by the manager) -> done (verdict stored). A running review
whose claim is older than STALE_CLAIM goes back to the queue, so a manager that crashed mid-review
does not leave a proposal waiting forever.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select

from contracts.schemas.review import ProposalReview, ReviewRequest
from core_db.clock import as_utc
from core_db.models import ProposalReviewRow

STALE_CLAIM = timedelta(minutes=4)
MAX_STEPS = 60


def _view(row: ProposalReviewRow) -> dict:
    return {
        "review_id": row.review_id,
        "proposal_id": row.proposal_id,
        "symbol": row.symbol,
        "kind": row.kind,
        "status": row.status,
        "created_at": as_utc(row.created_at).isoformat(),
        "updated_at": as_utc(row.updated_at).isoformat(),
        "request": dict(row.request),
        "steps": list(row.steps or []),
        "verdict": None if row.verdict is None else dict(row.verdict),
    }


def insert(session_factory, request: ReviewRequest) -> bool:
    with session_factory() as session:
        if session.get(ProposalReviewRow, request.review_id) is not None:
            return False
        moment = as_utc(request.requested_at)
        session.add(
            ProposalReviewRow(
                review_id=request.review_id,
                proposal_id=request.proposal_id,
                symbol=request.symbol,
                kind=request.kind.value,
                status="pending",
                created_at=moment,
                updated_at=moment,
                claimed_at=None,
                request=request.model_dump(mode="json"),
                steps=[],
                verdict=None,
            )
        )
        session.commit()
        return True


def get(session_factory, review_id: str) -> dict | None:
    with session_factory() as session:
        row = session.get(ProposalReviewRow, review_id)
        return None if row is None else _view(row)


def for_proposal(session_factory, proposal_id: str) -> dict | None:
    with session_factory() as session:
        row = session.scalars(select(ProposalReviewRow).where(ProposalReviewRow.proposal_id == proposal_id).limit(1)).first()
        return None if row is None else _view(row)


def recent(session_factory, *, limit: int = 50, symbol: str | None = None) -> list[dict]:
    with session_factory() as session:
        query = select(ProposalReviewRow).order_by(ProposalReviewRow.created_at.desc(), ProposalReviewRow.review_id)
        if symbol is not None:
            query = query.where(ProposalReviewRow.symbol == symbol)
        return [_view(row) for row in session.scalars(query.limit(limit))]


def claim(session_factory, now: datetime, *, limit: int = 2) -> list[ReviewRequest]:
    """Hand the oldest waiting reviews to the manager and mark them running."""
    moment = as_utc(now)
    with session_factory() as session:
        query = (
            select(ProposalReviewRow)
            .where(
                or_(
                    ProposalReviewRow.status == "pending",
                    (ProposalReviewRow.status == "running") & (ProposalReviewRow.claimed_at < moment - STALE_CLAIM),
                )
            )
            .order_by(ProposalReviewRow.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(session.scalars(query))
        for row in rows:
            row.status, row.claimed_at, row.updated_at = "running", moment, moment
        session.commit()
        return [ReviewRequest.model_validate(dict(row.request)) for row in rows]


def append_step(session_factory, review_id: str, step: dict, now: datetime) -> bool:
    with session_factory() as session:
        row = session.get(ProposalReviewRow, review_id, with_for_update=True)
        if row is None or row.status == "done" or len(row.steps or []) >= MAX_STEPS:
            return False
        row.steps = [*(row.steps or []), step]
        row.updated_at = as_utc(now)
        session.commit()
        return True


def complete(session_factory, review: ProposalReview, now: datetime) -> bool:
    """Store the verdict once. A second verdict for the same review is ignored."""
    with session_factory() as session:
        row = session.get(ProposalReviewRow, review.review_id, with_for_update=True)
        if row is None or row.status == "done":
            return False
        row.status, row.verdict, row.updated_at = "done", review.model_dump(mode="json"), as_utc(now)
        session.commit()
        return True
