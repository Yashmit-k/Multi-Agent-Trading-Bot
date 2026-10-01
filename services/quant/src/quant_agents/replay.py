"""Deterministic replay using ReplayClock and FakeSignalSink."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from contracts.enums import Horizon, TradingMode
from contracts.fakes import FakeSignalSink

from quant_agents.calendar.static_nse import StaticNseCalendar
from quant_agents.clock import ReplayClock
from quant_agents.runner import ContextFactory, Runner


def replay(
    agents: Sequence[Any],
    *,
    symbols: Sequence[str],
    horizons: Sequence[Horizon],
    as_of_points: Sequence[datetime],
    context_factory: ContextFactory,
    ml_training_data_cutoff: datetime | None = None,
) -> dict[str, Any]:
    sink = FakeSignalSink()
    calendar = StaticNseCalendar()
    all_signals = []
    for as_of in as_of_points:
        runner = Runner(
            agents,
            sink,
            ReplayClock(as_of),
            calendar,
            context_factory,
            TradingMode.BACKTEST,
        )
        all_signals.extend(runner.run(symbols, horizons, as_of))
    backtest_start = as_of_points[0]
    out_of_sample = None
    if ml_training_data_cutoff is not None:
        out_of_sample = ml_training_data_cutoff < backtest_start
    return {
        "signals": all_signals,
        "submitted": sink.submitted,
        "training_data_cutoff": None if ml_training_data_cutoff is None else ml_training_data_cutoff.isoformat(),
        "backtest_start": backtest_start.isoformat(),
        "out_of_sample": out_of_sample,
    }
