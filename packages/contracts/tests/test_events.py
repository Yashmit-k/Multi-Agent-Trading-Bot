"""Event envelope, channels, and duplicate detection."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.dedup import duplicate_event_ids
from contracts.enums import AgentName
from contracts.events import CHANNEL_FOR_EVENT, EventType, RedisChannel, channel_for
from contracts.fixtures import FIXTURE_AS_OF, sample_agent_signal
from contracts.schemas.event import EventEnvelope, event_envelope_json_schema


def _envelope(event_id: str = "evt-1") -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.AGENT_SIGNAL,
        timestamp=FIXTURE_AS_OF,
        source="technical",
        correlation_id="corr-1",
        payload=sample_agent_signal(),
    )


def test_duplicate_event_ids_are_detectable() -> None:
    first = _envelope("evt-shared")
    second = _envelope("evt-other")
    repeated = _envelope("evt-shared")
    assert duplicate_event_ids([first, second]) == []
    assert duplicate_event_ids([first, second, repeated]) == ["evt-shared"]


def test_event_type_and_channel_vocabulary() -> None:
    assert {item.value for item in EventType} == {
        "market.tick",
        "market.candle",
        "feature.updated",
        "agent.signal",
        "news.article",
        "news.signal",
        "fundamental.updated",
        "decision.created",
        "risk.approved",
        "risk.rejected",
        "order.created",
        "order.updated",
        "order.filled",
        "order.rejected",
        "position.updated",
        "portfolio.updated",
        "system.alert",
        "agent.heartbeat",
        "agent.request",
        "review.requested",
        "review.step",
        "review.completed",
    }
    assert {item.value for item in RedisChannel} == {
        "market.events",
        "feature.events",
        "agent.events",
        "news.events",
        "decision.events",
        "risk.events",
        "order.events",
        "portfolio.events",
        "system.events",
        "review.events",
    }
    assert set(CHANNEL_FOR_EVENT) == set(EventType)
    assert channel_for("agent.signal") == RedisChannel.AGENT_EVENTS
    assert channel_for(EventType.FUNDAMENTAL_UPDATED) == RedisChannel.MARKET_EVENTS
    per_agent = {f"agent.{agent.value}" for agent in AgentName}
    assert per_agent.isdisjoint({channel.value for channel in RedisChannel})


def test_event_envelope_schema_is_discriminated() -> None:
    schema = event_envelope_json_schema()
    assert schema["discriminator"]["propertyName"] == "event_type"
    assert "agent.signal" in schema["discriminator"]["mapping"]
    assert "order.filled" in schema["discriminator"]["mapping"]


def test_payload_must_match_event_type() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_id="evt-mismatch",
            event_type=EventType.MARKET_TICK,
            timestamp=datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc),
            source="market-data",
            correlation_id="corr-2",
            payload=sample_agent_signal(),
        )
