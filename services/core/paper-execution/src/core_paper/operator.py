"""Authorised cancel and replace for one paper order.

The running KOTAKBANK order is not cancelled by tests or by the worker. An
operator must call this operation with the session id, order id, operator id,
expected status, and a reason. Replace also requires a decision timestamp
strictly after the original decision, and it builds a new order from the daily
close available at that later timestamp.
"""

import hashlib
from datetime import datetime, timezone

from contracts.enums import OrderStatus
from contracts.schemas.trade_proposal import TradeProposal
from core_db.repository import CoreRepository
from core_paper.execute import queue_entry

class OperatorRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def cancel_order(
    repository: CoreRepository,
    *,
    session_id: str,
    order_id: str,
    operator_id: str,
    reason: str,
    expected_status: str,
    now: datetime | None = None,
) -> dict[str, object]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    order = _load(repository, session_id, order_id, operator_id, reason, expected_status)
    if order.status != OrderStatus.OPEN:
        raise OperatorRejected("order_not_open")
    updated = order.model_copy(
        update={
            "status": OrderStatus.CANCELLED,
            "updated_at": moment,
            "metadata": {**order.metadata, "cancel_reason": reason, "cancelled_by": operator_id},
        }
    )
    repository.commit_policy_transition(updated, release=True)
    _audit(repository, "paper_order_cancel", session_id, order_id, moment, operator_id, reason, expected_status, {"status": "CANCELLED"})
    return {"order_id": order_id, "status": "CANCELLED", "session_id": session_id, "recorded_at": moment.isoformat()}


def replace_order(
    repository: CoreRepository,
    *,
    session_id: str,
    order_id: str,
    operator_id: str,
    reason: str,
    expected_status: str,
    decision_at: datetime,
    now: datetime | None = None,
) -> dict[str, object]:
    active = repository.active_paper_session()
    if active is None or active.session_id != session_id:
        raise OperatorRejected("session_not_active")
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    order = _load(repository, session_id, order_id, operator_id, reason, expected_status)
    if order.status != OrderStatus.OPEN:
        raise OperatorRejected("order_not_open")
    previous = datetime.fromisoformat(str(order.metadata.get("decision_end")))
    fresh = decision_at.astimezone(timezone.utc)
    if fresh <= previous:
        raise OperatorRejected("stale_decision_rejected")
    proposal = repository.get_proposal(order.proposal_id)
    if proposal is None:
        raise OperatorRejected("proposal_missing")
    replacement_id = hashlib.sha256(f"replace|{session_id}|{order_id}|{fresh.isoformat()}".encode("utf-8")).hexdigest()
    cloned = TradeProposal.model_validate(proposal.model_dump(mode="json")).model_copy(
        update={"proposal_id": replacement_id, "timestamp": fresh, "metadata": {**proposal.metadata, "replaces_order_id": order_id}}
    )
    repository.insert_proposal(cloned)
    created = queue_entry(repository, cloned, fresh)
    if created is None or created.status != OrderStatus.OPEN:
        raise OperatorRejected("replacement_rejected")
    cancel_order(
        repository,
        session_id=session_id,
        order_id=order_id,
        operator_id=operator_id,
        reason=reason,
        expected_status=expected_status,
        now=moment,
    )
    _audit(
        repository,
        "paper_order_replace",
        session_id,
        order_id,
        moment,
        operator_id,
        reason,
        expected_status,
        {"status": "REPLACED", "replacement_order_id": created.order_id, "decision_at": fresh.isoformat()},
    )
    return {
        "order_id": order_id,
        "status": "CANCELLED",
        "replacement_order_id": created.order_id,
        "session_id": session_id,
        "recorded_at": moment.isoformat(),
    }


def _load(repository, session_id: str, order_id: str, operator_id: str, reason: str, expected_status: str):
    if not operator_id.strip() or not reason.strip() or not expected_status.strip():
        raise OperatorRejected("missing_operator_fields")
    book = repository.paper_session(session_id)
    if book is None:
        raise OperatorRejected("unknown_session")
    matches = [item for item in repository.list_orders(session_id) if item.order_id == order_id]
    if not matches:
        raise OperatorRejected("unknown_order")
    order = matches[0]
    if order.status.value != expected_status:
        raise OperatorRejected("status_conflict")
    return order


def _audit(repository, action: str, session_id: str, order_id: str, moment: datetime, operator_id: str, reason: str, expected_status: str, result: dict) -> None:
    audit_id = hashlib.sha256(f"{action}|{session_id}|{order_id}|{moment.isoformat()}|{operator_id}|{result}".encode("utf-8")).hexdigest()
    repository.insert_audit(
        audit_id,
        action,
        "order",
        order_id,
        moment,
        {
            "session_id": session_id,
            "operator_id": operator_id,
            "reason": reason,
            "expected_status": expected_status,
            "result": result,
        },
    )
