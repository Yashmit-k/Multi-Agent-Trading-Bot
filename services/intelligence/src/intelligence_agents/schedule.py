"""When the intelligence agents may spend LLM calls: an IST weekday window from INTELLIGENCE_ACTIVE_HOURS."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from intelligence_agents.errors import ConfigError

IST = ZoneInfo("Asia/Kolkata")


def parse_active_hours(raw: str) -> tuple[time, time]:
    try:
        start_text, end_text = raw.split("-")
        start, end = time.fromisoformat(start_text.strip()), time.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise ConfigError(f"INTELLIGENCE_ACTIVE_HOURS must be HH:MM-HH:MM, got {raw!r}") from exc
    if not start < end:
        raise ConfigError("INTELLIGENCE_ACTIVE_HOURS must start before it ends")
    return start, end


def scoring_allowed(active_hours: str, now: datetime) -> bool:
    """True when the LLM agents may score now. An empty window means always."""
    if not active_hours:
        return True
    start, end = parse_active_hours(active_hours)
    local = now.astimezone(IST)
    return local.weekday() < 5 and start <= local.time() < end
