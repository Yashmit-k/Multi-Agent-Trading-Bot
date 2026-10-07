"""HTTP SignalSink. Core owns acceptance; this client only posts AgentSignal."""

from __future__ import annotations

import httpx

from contracts.enums import TradingMode
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.submission import SubmissionResult


class CoreSignalSink:
    def __init__(self, base_url: str, token: str, *, client: httpx.Client | None = None) -> None:
        self._url = f"{base_url.rstrip('/')}/api/v1/internal/signals"
        self._token = token
        self._client = client or httpx.Client(timeout=30.0)

    def submit(self, signal: AgentSignal) -> SubmissionResult:
        response = self._client.post(
            self._url,
            json=signal.model_dump(mode="json"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "X-Trading-Mode": TradingMode.PAPER.value,
            },
        )
        response.raise_for_status()
        return SubmissionResult.model_validate(response.json())
