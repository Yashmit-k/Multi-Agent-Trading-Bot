"""Notifications: reminder only when logged out, once per day; summary once after the close; nothing unconfigured."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core_db.repository import CoreRepository
from core_worker.notify import Notifier, maybe_notify

UTC = timezone.utc
MORNING = datetime(2026, 10, 19, 3, 5, tzinfo=UTC)  # Mon 08:35 IST
URGENT = datetime(2026, 10, 19, 3, 41, tzinfo=UTC)  # 09:11 IST
EVENING = datetime(2026, 10, 19, 10, 10, tzinfo=UTC)  # 15:40 IST


class Recorder:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def __call__(self, request, timeout):  # type: ignore[no-untyped-def]
        self.bodies.append({"url": request.full_url, **json.loads(request.data)})

        class _Done:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *args):  # type: ignore[no-untyped-def]
                return False

        return _Done()


def _notifier(recorder: Recorder) -> Notifier:
    class Wired(Notifier):
        def send(self, text, *, urlopen=None):  # type: ignore[no-untyped-def,override]
            return Notifier.send(self, text, urlopen=recorder)

    return Wired(telegram_token="t", telegram_chat="c")


def test_nothing_without_configuration(repository: CoreRepository) -> None:
    assert maybe_notify(repository, Notifier(), MORNING) == []


def test_reminder_when_logged_out_once_then_urgent(repository: CoreRepository) -> None:
    recorder = Recorder()
    notifier = _notifier(recorder)
    assert maybe_notify(repository, notifier, MORNING) == ["reminder"]
    assert maybe_notify(repository, notifier, MORNING + timedelta(minutes=5)) == []
    assert maybe_notify(repository, notifier, URGENT) == ["reminder_urgent"]
    assert "Zerodha is not logged in" in recorder.bodies[0]["text"] and recorder.bodies[1]["text"].startswith("URGENT")
    assert recorder.bodies[0]["url"].startswith("https://api.telegram.org/bott/sendMessage")


def test_no_reminder_when_logged_in_or_on_a_holiday(repository: CoreRepository) -> None:
    notifier = _notifier(Recorder())
    repository.save_broker_token("zerodha", "tok", MORNING - timedelta(minutes=10))  # 08:25 IST today
    assert maybe_notify(repository, notifier, MORNING) == []
    sunday = datetime(2026, 10, 18, 3, 5, tzinfo=UTC)
    assert maybe_notify(repository, notifier, sunday) == []


def test_summary_once_after_the_close(repository: CoreRepository) -> None:
    recorder = Recorder()
    notifier = _notifier(recorder)
    repository.open_paper_session(Decimal("1000000"))
    assert maybe_notify(repository, notifier, EVENING, site="https://example.test") == ["summary"]
    assert maybe_notify(repository, notifier, EVENING + timedelta(minutes=30)) == []
    assert "StockX paper summary" in recorder.bodies[-1]["text"]
