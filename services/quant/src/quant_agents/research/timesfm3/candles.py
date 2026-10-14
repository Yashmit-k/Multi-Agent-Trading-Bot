"""Read qualifying daily closes from the frozen snapshot. The holdout is not a path."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from quant_agents.research.timesfm3.paths import daily_candle_file
from quant_agents.research.timesfm3.scores import ClosePoint, official_session_date


def load_closes(path: Path | None = None) -> tuple[ClosePoint, ...]:
    candle_file = daily_candle_file() if path is None else _checked(path)
    points: list[ClosePoint] = []
    with candle_file.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            end = datetime.fromisoformat(str(payload["end"])).astimezone(timezone.utc)
            if official_session_date(end) is None:
                continue
            points.append(
                ClosePoint(
                    symbol=str(payload["symbol"]).strip().upper(),
                    end=end,
                    close=Decimal(str(payload["close"])),
                )
            )
    return tuple(points)


def _checked(path: Path) -> Path:
    from quant_agents.research.timesfm3.paths import _refuse_unless_daily_snapshot

    resolved = path.resolve()
    _refuse_unless_daily_snapshot(resolved)
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved
