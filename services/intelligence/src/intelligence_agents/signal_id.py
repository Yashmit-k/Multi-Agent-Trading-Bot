"""signal_id = sha256(agent, version, symbol, as_of, horizon, input_hash)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from contracts.enums import AgentName, Horizon


def input_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def make_signal_id(
    agent: AgentName,
    version: str,
    symbol: str,
    as_of: datetime,
    horizon: Horizon,
    payload: Any,
) -> str:
    digest = input_hash(
        {
            "agent": agent.value,
            "version": version,
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "horizon": horizon.value,
            "input_hash": input_hash(payload),
        }
    )
    return f"sig-{agent.value}-{digest[:24]}"
