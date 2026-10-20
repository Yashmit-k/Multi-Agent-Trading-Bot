"""Keep the database from filling the disk, without losing what matters.

- agent_signals: raw rows for SIGNAL_DAYS; older rows are summarised per day, agent, horizon and version
  into agent_signal_daily, then deleted. A signal cited by any trade proposal is never deleted, so the
  Journal can still show the votes behind every trade.
- system_events: the trace recorder's copies of agent.signal messages for EVENT_DAYS (the signals
  themselves are kept as above); decision, risk, order and fill events are kept forever.
- audit_logs: signal_accepted rows for AUDIT_DAYS; operator actions are kept forever.
Candles, orders, fills and positions are never pruned.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from core_db.models import AgentSignalDailyRow, AgentSignalRow, AuditLogRow, SystemEventRow, TradeProposalRow

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
SIGNAL_DAYS = 30
EVENT_DAYS = 7
AUDIT_DAYS = 30
CHUNK = 5000


def prune(session_factory, now: datetime, *, signal_days: int = SIGNAL_DAYS, event_days: int = EVENT_DAYS, audit_days: int = AUDIT_DAYS) -> dict[str, int]:  # type: ignore[no-untyped-def]
    now = now.astimezone(timezone.utc)
    counts = {"signals_summarised": 0, "signals_deleted": 0, "events_deleted": 0, "audit_deleted": 0}
    with session_factory() as session:
        cited: set[str] = set()
        for payload in session.scalars(select(TradeProposalRow.payload)):
            cited.update(str(item) for item in (payload or {}).get("supporting_signal_ids") or [])
        cutoff = now - timedelta(days=signal_days)
        while True:
            rows = session.execute(
                select(AgentSignalRow.signal_id, AgentSignalRow.payload, AgentSignalRow.recorded_at)
                .where(AgentSignalRow.recorded_at < cutoff)
                .limit(CHUNK)
            ).all()
            rows = [row for row in rows if row[0] not in cited]
            if not rows:
                break
            groups: dict[tuple[str, str, str, str], list[tuple[float, float, str]]] = defaultdict(list)
            for _, payload, recorded in rows:
                day = recorded.astimezone(IST).date().isoformat() if recorded.tzinfo else recorded.date().isoformat()
                key = (day, str(payload.get("agent_name")), str(payload.get("horizon")), str(payload.get("agent_version")))
                groups[key].append((float(payload.get("signal") or 0), float(payload.get("confidence") or 0), str(payload.get("symbol"))))
            for (day, agent, horizon, version), items in groups.items():
                existing = session.get(AgentSignalDailyRow, (day, agent, horizon, version))
                summary = dict(existing.payload) if existing else {"n": 0, "sum_signal": 0.0, "sum_confidence": 0.0, "positive": 0, "negative": 0, "symbols": []}
                summary["n"] += len(items)
                summary["sum_signal"] += sum(item[0] for item in items)
                summary["sum_confidence"] += sum(item[1] for item in items)
                summary["positive"] += sum(1 for item in items if item[0] > 0)
                summary["negative"] += sum(1 for item in items if item[0] < 0)
                summary["symbols"] = sorted(set(summary["symbols"]) | {item[2] for item in items})
                summary["mean_signal"] = summary["sum_signal"] / summary["n"]
                summary["mean_confidence"] = summary["sum_confidence"] / summary["n"]
                if existing:
                    existing.payload = summary
                else:
                    session.add(AgentSignalDailyRow(day=day, agent=agent, horizon=horizon, version=version, payload=summary))
            ids = [row[0] for row in rows]
            session.execute(delete(AgentSignalRow).where(AgentSignalRow.signal_id.in_(ids)))
            session.commit()
            counts["signals_summarised"] += len(ids)
            counts["signals_deleted"] += len(ids)
            if len(ids) < CHUNK:
                break
        result = session.execute(
            delete(SystemEventRow).where(SystemEventRow.event_type == "agent.signal", SystemEventRow.recorded_at < now - timedelta(days=event_days))
        )
        counts["events_deleted"] = int(result.rowcount or 0)
        result = session.execute(
            delete(AuditLogRow).where(AuditLogRow.action == "signal_accepted", AuditLogRow.recorded_at < now - timedelta(days=audit_days))
        )
        counts["audit_deleted"] = int(result.rowcount or 0)
        session.commit()
    logger.info("retention %s", counts)
    return counts
