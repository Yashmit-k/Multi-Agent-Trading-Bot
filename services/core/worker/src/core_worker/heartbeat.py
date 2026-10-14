"""Worker liveness for the API process. This module does not start the worker loop."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DEFAULT_WORKER_INTERVAL_SECONDS = 30


def heartbeat_view(
    recorded_at: datetime | None,
    now: datetime,
    interval_seconds: int,
) -> dict[str, str]:
    """Unavailable until a beat arrives, and again once that beat is older than the interval."""
    if recorded_at is None or interval_seconds <= 0:
        return {"status": "unavailable"}
    age = _aware(now) - _aware(recorded_at)
    if age > timedelta(seconds=interval_seconds):
        return {"status": "unavailable"}
    return {"status": "available", "heartbeat_at": _aware(recorded_at).isoformat()}


def publish_heartbeat(
    base_url: str,
    token: str,
    moment: datetime,
    *,
    interval_seconds: int = DEFAULT_WORKER_INTERVAL_SECONDS,
    urlopen=urllib.request.urlopen,
) -> bool:
    """Tell Core API this pass is alive. A missing API does not stop the worker."""
    if not base_url or not token:
        return False
    body = json.dumps(
        {
            "heartbeat_at": _aware(moment).isoformat(),
            "interval_seconds": interval_seconds,
        }
    ).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/worker/heartbeat",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8):
            return True
    except Exception as exc:
        logger.info("worker_heartbeat_failed error_type=%s", type(exc).__name__)
        return False


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
