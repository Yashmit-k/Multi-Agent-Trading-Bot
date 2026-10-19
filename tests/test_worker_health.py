"""Worker health: silent during market hours with paper on is DOWN; repeated failed cycles are DOWN."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core_api.app import _worker_check

UTC = timezone.utc
OPEN = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)  # Monday 10:30 IST
CLOSED = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)  # 19:30 IST


def _app(beat=None, failures=0, error=None, started=OPEN - timedelta(hours=1)):  # type: ignore[no-untyped-def]
    return SimpleNamespace(state=SimpleNamespace(worker_heartbeat_at=beat, worker_heartbeat_interval_seconds=30, worker_failed_cycles=failures, worker_last_error=error, started_at=started))


def test_silent_worker_in_market_hours_is_down() -> None:
    assert _worker_check(_app(beat=OPEN - timedelta(minutes=10)), True, OPEN)["status"] == "down"
    assert _worker_check(_app(), True, OPEN)["status"] == "down"


def test_not_down_when_paper_off_market_closed_or_just_started() -> None:
    assert _worker_check(_app(), False, OPEN)["status"] == "idle"
    assert _worker_check(_app(), True, CLOSED)["status"] == "idle"
    assert _worker_check(_app(started=OPEN - timedelta(seconds=30)), True, OPEN)["status"] == "warn"


def test_failing_cycles_escalate() -> None:
    fresh = OPEN - timedelta(seconds=20)
    assert _worker_check(_app(beat=fresh), True, OPEN)["status"] == "ok"
    assert _worker_check(_app(beat=fresh, failures=1, error="ValueError: x"), True, OPEN)["status"] == "warn"
    down = _worker_check(_app(beat=fresh, failures=3, error="ValidationError: updated_at"), True, OPEN)
    assert down["status"] == "down" and "ValidationError" in str(down["detail"])
