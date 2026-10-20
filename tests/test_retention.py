"""Retention: old signals are summarised then removed, cited signals and important events are kept."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from contracts.fixtures import sample_agent_signal
from core_db.models import AgentSignalDailyRow, AuditLogRow, SystemEventRow
from core_db.repository import CoreRepository

NOW = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)


def test_prune_keeps_what_trades_need(repository: CoreRepository) -> None:
    old = NOW - timedelta(days=40)
    base = sample_agent_signal("RELIANCE")
    for i in range(5):
        item = base.model_copy(update={"signal_id": f"old-{i}", "signal": 0.5 if i % 2 else -0.5})
        repository.insert_signal(item.signal_id, item.symbol, item.exchange.value, item.model_dump(mode="json"), old)
    fresh = base.model_copy(update={"signal_id": "fresh"})
    repository.insert_signal(fresh.signal_id, fresh.symbol, fresh.exchange.value, fresh.model_dump(mode="json"), NOW)
    with repository._session_factory() as session:  # an old cited signal, an old trace copy, an old order event, old audit rows
        from core_db.models import TradeProposalRow

        session.add(TradeProposalRow(proposal_id="p1", session_id=None, instrument_id="x", symbol="RELIANCE", horizon="SWING", as_of=old, payload={"supporting_signal_ids": ["old-0"]}))
        session.add(SystemEventRow(event_id="e1", event_type="agent.signal", recorded_at=old, payload={}))
        session.add(SystemEventRow(event_id="e2", event_type="order.filled", recorded_at=old, payload={}))
        session.add(AuditLogRow(audit_id="a1", action="signal_accepted", entity_type="signal", entity_id="x", recorded_at=old, payload={}))
        session.add(AuditLogRow(audit_id="a2", action="paper_order_cancel", entity_type="order", entity_id="y", recorded_at=old, payload={}))
        session.commit()
    counts = repository.prune_history(NOW)
    assert counts["signals_deleted"] == 4  # old-0 is cited by a proposal
    assert repository.get_signal_payload("old-0") is not None and repository.get_signal_payload("fresh") is not None
    assert repository.get_signal_payload("old-1") is None
    with repository._session_factory() as session:
        daily = session.scalars(select(AgentSignalDailyRow)).all()
        assert sum(row.payload["n"] for row in daily) == 4
        assert {row.event_id for row in session.scalars(select(SystemEventRow))} == {"e2"}
        assert {row.audit_id for row in session.scalars(select(AuditLogRow))} == {"a2"}
    assert repository.prune_history(NOW)["signals_deleted"] == 0  # idempotent
