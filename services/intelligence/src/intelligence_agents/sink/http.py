"""HTTP SignalSink client. Does not write Core Postgres directly."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime

import httpx
from contracts.enums import TradingMode
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.submission import SubmissionResult

logger = logging.getLogger(__name__)


class HttpSignalSink:
    def __init__(
        self,
        base_url: str,
        token: str,
        mode: TradingMode,
        *,
        replay_as_of: datetime | None = None,
        timeout: float = 10.0,
        retries: int = 3,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/api/v1/internal/signals"
        self._token = token
        self._mode = mode
        self._replay_as_of = replay_as_of
        self._timeout = timeout
        self._retries = retries
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleeper or time.sleep

    def submit(self, signal: AgentSignal) -> SubmissionResult:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-Trading-Mode": self._mode.value,
        }
        if self._mode is TradingMode.BACKTEST:
            if self._replay_as_of is None:
                raise ValueError("BACKTEST sink requires replay_as_of")
            headers["X-Replay-As-Of"] = self._replay_as_of.isoformat()
        delay = 0.2
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                response = self._client.post(
                    self._url,
                    json=signal.model_dump(mode="json"),
                    headers=headers,
                    timeout=self._timeout,
                )
                if response.status_code >= 500:
                    raise httpx.HTTPError(f"status {response.status_code}")
                if response.status_code == 422:
                    logger.warning(
                        "sink_invalid_schema",
                        extra={"signal_id": signal.signal_id, "body": response.text[:500]},
                    )
                    return SubmissionResult(
                        accepted=False,
                        signal_id=signal.signal_id,
                        duplicate=False,
                        message="invalid_schema",
                    )
                if response.status_code >= 400:
                    logger.warning(
                        "sink_http_error",
                        extra={"signal_id": signal.signal_id, "status": response.status_code, "body": response.text[:500]},
                    )
                response.raise_for_status()
                return SubmissionResult.model_validate(response.json())
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("sink_retry", extra={"attempt": attempt, "signal_id": signal.signal_id})
                if attempt + 1 == self._retries:
                    break
                self._sleep(delay)
                delay *= 2
        raise last_error or RuntimeError("sink_failed")
