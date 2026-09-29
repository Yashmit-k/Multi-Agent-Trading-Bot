"""Detect repeated event_id values so consumers can drop duplicates."""

from collections.abc import Sequence

from contracts.schemas.event import EventEnvelope


def duplicate_event_ids(envelopes: Sequence[EventEnvelope]) -> list[str]:
    """Return event ids that appear more than once, in first-seen order."""
    seen: set[str] = set()
    duplicates: list[str] = []
    recorded: set[str] = set()
    for envelope in envelopes:
        event_id = envelope.event_id
        if event_id in seen:
            if event_id not in recorded:
                duplicates.append(event_id)
                recorded.add(event_id)
        else:
            seen.add(event_id)
    return duplicates
