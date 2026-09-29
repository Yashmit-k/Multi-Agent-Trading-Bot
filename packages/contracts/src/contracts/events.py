"""Redis event types and channels.

The event type is carried inside ``EventEnvelope``. Channels are shared buses.
There is one channel per domain, never one channel per agent.
"""

from enum import StrEnum

from contracts.enums import AgentName


class EventType(StrEnum):
    MARKET_TICK = "market.tick"
    MARKET_CANDLE = "market.candle"
    FEATURE_UPDATED = "feature.updated"
    AGENT_SIGNAL = "agent.signal"
    NEWS_ARTICLE = "news.article"
    NEWS_SIGNAL = "news.signal"
    FUNDAMENTAL_UPDATED = "fundamental.updated"
    DECISION_CREATED = "decision.created"
    RISK_APPROVED = "risk.approved"
    RISK_REJECTED = "risk.rejected"
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_FILLED = "order.filled"
    ORDER_REJECTED = "order.rejected"
    POSITION_UPDATED = "position.updated"
    PORTFOLIO_UPDATED = "portfolio.updated"
    SYSTEM_ALERT = "system.alert"
    AGENT_HEARTBEAT = "agent.heartbeat"


class RedisChannel(StrEnum):
    MARKET_EVENTS = "market.events"
    FEATURE_EVENTS = "feature.events"
    AGENT_EVENTS = "agent.events"
    NEWS_EVENTS = "news.events"
    DECISION_EVENTS = "decision.events"
    RISK_EVENTS = "risk.events"
    ORDER_EVENTS = "order.events"
    PORTFOLIO_EVENTS = "portfolio.events"
    SYSTEM_EVENTS = "system.events"


# fundamental.updated is reference data. The channel list has no
# fundamental.events bus, so that event type is published on market.events.
CHANNEL_FOR_EVENT: dict[EventType, RedisChannel] = {
    EventType.MARKET_TICK: RedisChannel.MARKET_EVENTS,
    EventType.MARKET_CANDLE: RedisChannel.MARKET_EVENTS,
    EventType.FEATURE_UPDATED: RedisChannel.FEATURE_EVENTS,
    EventType.AGENT_SIGNAL: RedisChannel.AGENT_EVENTS,
    EventType.NEWS_ARTICLE: RedisChannel.NEWS_EVENTS,
    EventType.NEWS_SIGNAL: RedisChannel.NEWS_EVENTS,
    EventType.FUNDAMENTAL_UPDATED: RedisChannel.MARKET_EVENTS,
    EventType.DECISION_CREATED: RedisChannel.DECISION_EVENTS,
    EventType.RISK_APPROVED: RedisChannel.RISK_EVENTS,
    EventType.RISK_REJECTED: RedisChannel.RISK_EVENTS,
    EventType.ORDER_CREATED: RedisChannel.ORDER_EVENTS,
    EventType.ORDER_UPDATED: RedisChannel.ORDER_EVENTS,
    EventType.ORDER_FILLED: RedisChannel.ORDER_EVENTS,
    EventType.ORDER_REJECTED: RedisChannel.ORDER_EVENTS,
    EventType.POSITION_UPDATED: RedisChannel.PORTFOLIO_EVENTS,
    EventType.PORTFOLIO_UPDATED: RedisChannel.PORTFOLIO_EVENTS,
    EventType.SYSTEM_ALERT: RedisChannel.SYSTEM_EVENTS,
    EventType.AGENT_HEARTBEAT: RedisChannel.AGENT_EVENTS,
}

if set(CHANNEL_FOR_EVENT) != set(EventType):
    missing = set(EventType) - set(CHANNEL_FOR_EVENT)
    raise RuntimeError(f"every event type needs a channel, missing {missing}")

_AGENT_CHANNELS = {f"agent.{agent.value}" for agent in AgentName}
if _AGENT_CHANNELS & {channel.value for channel in RedisChannel}:
    raise RuntimeError("Redis channels must not be per-agent")


def channel_for(event_type: EventType | str) -> RedisChannel:
    """Return the Redis channel that carries this event type."""
    parsed = event_type if isinstance(event_type, EventType) else EventType(event_type)
    return CHANNEL_FOR_EVENT[parsed]
