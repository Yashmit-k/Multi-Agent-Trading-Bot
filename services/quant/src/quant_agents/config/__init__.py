"""Load EvaluationConfig from horizons.yaml. Horizon is never inferred from timeframe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from contracts.enums import Horizon, Timeframe
from quant_agents.errors import ConfigError

_DEFAULT_PATH = Path(__file__).with_name("horizons.yaml")


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    horizon: Horizon
    timeframe: Timeframe
    swing_valid_sessions: int
    staleness_max_sessions: int
    regime_index_symbols: tuple[str, ...]


def load_horizons_table(path: Path | None = None) -> dict[str, Any]:
    target = path or _DEFAULT_PATH
    with target.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError("horizons.yaml must be a mapping")
    return data


def parse_evaluation_config(
    configuration: Mapping[str, Any],
    table: dict[str, Any] | None = None,
) -> EvaluationConfig:
    data = table if table is not None else load_horizons_table()
    raw_horizon = configuration.get("horizon")
    raw_timeframe = configuration.get("timeframe")
    if raw_horizon is None or raw_timeframe is None:
        raise ConfigError("configuration must include horizon and timeframe")
    try:
        horizon = raw_horizon if isinstance(raw_horizon, Horizon) else Horizon(str(raw_horizon))
        timeframe = raw_timeframe if isinstance(raw_timeframe, Timeframe) else Timeframe(str(raw_timeframe))
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    allowed = data.get("allowed") or {}
    names = allowed.get(horizon.value)
    if names is None:
        raise ConfigError(f"horizon {horizon.value} is not in horizons.yaml")
    allowed_values = {Timeframe(item) for item in names}
    if timeframe not in allowed_values:
        raise ConfigError(f"timeframe {timeframe.value} is not allowed for {horizon.value}")
    staleness_map = data.get("staleness_max_sessions") or {}
    if timeframe.value not in staleness_map:
        raise ConfigError(f"no staleness_max_sessions for {timeframe.value}")
    swing_n = int(data.get("swing_valid_sessions", 5))
    raw_symbols = configuration.get("regime_index_symbols") or ("NIFTY50", "INDIAVIX")
    symbols = tuple(str(item) for item in raw_symbols)
    return EvaluationConfig(
        horizon=horizon,
        timeframe=timeframe,
        swing_valid_sessions=swing_n,
        staleness_max_sessions=int(staleness_map[timeframe.value]),
        regime_index_symbols=symbols,
    )
