"""Validate, persist, and publish agent signals. Retries of one signal_id publish once."""

from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

from contracts.enums import Exchange, TradingMode
from contracts.events import EventType, channel_for
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.event import EventEnvelope
from contracts.schemas.submission import SubmissionResult
from core_db.repository import CoreRepository

LIVE_MODES = {TradingMode.LIVE, TradingMode.PAPER, TradingMode.SHADOW}


class EventPublisher(Protocol):
    def publish(self, channel: str, payload: str) -> None:
        """Send one Redis message."""


class MemoryEventPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def publish(self, channel: str, payload: str) -> None:
        self.events.append((channel, payload))


class RedisEventPublisher:
    def __init__(self, client: object) -> None:
        self._client = client

    def publish(self, channel: str, payload: str) -> None:
        self._client.publish(channel, payload)  # type: ignore[attr-defined]


def ingest_signal(
    repository: CoreRepository,
    publisher: EventPublisher,
    signal: AgentSignal,
    *,
    mode: TradingMode,
    now: datetime,
    replay_as_of: datetime | None,
    skew_seconds: int,
) -> SubmissionResult:
    existing = repository.get_signal_payload(signal.signal_id)
    if existing is not None:
        return SubmissionResult(
            accepted=False,
            signal_id=signal.signal_id,
            duplicate=True,
            message="already stored",
        )
    reason = _reject_reason(repository, signal, mode=mode, now=_aware(now), replay_as_of=replay_as_of, skew_seconds=skew_seconds)
    if reason is not None:
        repository.insert_rejection(str(uuid4()), signal.signal_id, reason, reason, _aware(now))
        return SubmissionResult(accepted=False, signal_id=signal.signal_id, duplicate=False, message=reason)
    created = repository.insert_signal(
        signal.signal_id,
        signal.symbol,
        signal.exchange.value,
        signal.model_dump(mode="json"),
        _aware(now),
    )
    if not created:
        return SubmissionResult(accepted=False, signal_id=signal.signal_id, duplicate=True, message="already stored")
    repository.insert_audit(
        str(uuid4()),
        "signal_accepted",
        "agent_signal",
        signal.signal_id,
        _aware(now),
        {"symbol": signal.symbol, "agent_name": signal.agent_name.value},
    )
    envelope = EventEnvelope(
        event_id=f"agent.signal:{signal.signal_id}",
        event_type=EventType.AGENT_SIGNAL,
        timestamp=signal.timestamp,
        source="signal-ingestion",
        correlation_id=signal.signal_id,
        payload=signal,
    )
    publisher.publish(channel_for(EventType.AGENT_SIGNAL).value, envelope.model_dump_json())
    return SubmissionResult(accepted=True, signal_id=signal.signal_id, duplicate=False, message="accepted")


def _reject_reason(
    repository: CoreRepository,
    signal: AgentSignal,
    *,
    mode: TradingMode,
    now: datetime,
    replay_as_of: datetime | None,
    skew_seconds: int,
) -> str | None:
    if signal.exchange != Exchange.NSE:
        return "non_nse"
    if repository.get_by_symbol(signal.symbol, Exchange.NSE.value) is None:
        return "unknown_symbol"
    if mode == TradingMode.BACKTEST:
        if replay_as_of is None:
            return "missing_replay_as_of"
        boundary = _aware(replay_as_of)
        if signal.timestamp > boundary or signal.as_of > boundary:
            return "future_timestamp"
        if signal.valid_until < boundary:
            return "stale_signal"
        return None
    if mode in LIVE_MODES:
        limit = now + timedelta(seconds=skew_seconds)
        if signal.timestamp > limit or signal.as_of > limit:
            return "future_timestamp"
        if signal.valid_until < now:
            return "stale_signal"
        return None
    return "unsupported_mode"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
