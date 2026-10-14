"""Record every message on the Redis event buses into ``system_events``.

The recorder only listens. It never publishes, places orders, or changes
paper state, so it can run while the worker is stopped. Each stored row is the
full ``EventEnvelope`` plus the channel it arrived on. ``event_id`` is the
deduplication key, so a replayed message is stored once.
"""

import json
import logging
from collections.abc import Iterable
from datetime import datetime, timezone

from contracts.events import RedisChannel
from contracts.schemas.event import EventEnvelope
from core_db.repository import CoreRepository

logger = logging.getLogger(__name__)

CHANNELS = tuple(channel.value for channel in RedisChannel)


def record_message(repository: CoreRepository, channel: str, data: bytes | str, *, now: datetime | None = None) -> bool:
    """Validate one bus message and store it. Invalid messages are logged and skipped."""
    raw = data.decode("utf-8") if isinstance(data, bytes) else data
    try:
        envelope = EventEnvelope.model_validate_json(raw)
    except ValueError as exc:
        logger.warning("trace_invalid_message channel=%s error=%s", channel, exc)
        return False
    body = envelope.model_dump(mode="json")
    body["channel"] = channel
    stamp = now or datetime.now(timezone.utc)
    stored = repository.insert_system_event(envelope.event_id, envelope.event_type.value, stamp, body)
    if stored:
        logger.info(
            "trace_recorded channel=%s event_type=%s source=%s correlation_id=%s",
            channel,
            envelope.event_type.value,
            envelope.source,
            envelope.correlation_id,
        )
    return stored


def run(repository: CoreRepository, messages: Iterable[dict]) -> int:
    """Consume pub/sub messages until the iterable ends. Returns rows stored."""
    stored = 0
    for message in messages:
        if message.get("type") not in {"message", "pmessage"}:
            continue
        channel = message.get("channel")
        channel = channel.decode("utf-8") if isinstance(channel, bytes) else str(channel)
        if record_message(repository, channel, message.get("data", b"")):
            stored += 1
    return stored


def main() -> None:
    import os

    import redis

    from core_db.session import make_session_factory

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    repository = CoreRepository(make_session_factory(os.environ.get("DATABASE_URL", "sqlite:///./core.db")))
    client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(*CHANNELS)
    logger.info("trace_recorder_listening channels=%s", json.dumps(CHANNELS))
    run(repository, pubsub.listen())


if __name__ == "__main__":
    main()
