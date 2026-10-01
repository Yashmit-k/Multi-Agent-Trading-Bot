"""Injected clocks. Agents never read the wall clock themselves."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from contracts.time import require_aware


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Aware UTC instant used as AgentSignal.timestamp."""


class ReplayClock:
    def __init__(self, as_of: datetime) -> None:
        self._as_of = require_aware(as_of, "as_of")

    def now(self) -> datetime:
        return self._as_of


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
