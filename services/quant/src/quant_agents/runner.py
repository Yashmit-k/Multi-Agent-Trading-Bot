"""Evaluate agents and submit through an injected SignalSink. No HTTP sink here."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from contracts.enums import Horizon, TradingMode
from contracts.interfaces import AgentContext, SignalSink, TradingAgent
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.submission import SubmissionResult

from quant_agents.calendar.protocol import TradingCalendar
from quant_agents.clock import Clock
from quant_agents.errors import LeakageError

logger = logging.getLogger(__name__)

ContextFactory = Callable[[str, datetime, Horizon], AgentContext]


class Runner:
    def __init__(
        self,
        agents: Sequence[TradingAgent],
        sink: SignalSink,
        clock: Clock,
        calendar: TradingCalendar,
        context_factory: ContextFactory,
        mode: TradingMode,
    ) -> None:
        self.agents = list(agents)
        self.sink = sink
        self.clock = clock
        self.calendar = calendar
        self.context_factory = context_factory
        self.mode = mode
        self.stopped: set[str] = set()
        self.results: list[SubmissionResult] = []
        self.skipped: list[str] = []

    def run(self, symbols: Sequence[str], horizons: Sequence[Horizon], as_of: datetime) -> list[AgentSignal]:
        produced: list[AgentSignal] = []
        now = self.clock.now()
        if as_of > now:
            logger.warning("as_of_after_clock", extra={"as_of": as_of.isoformat(), "now": now.isoformat()})
            self.skipped.append("as_of_after_clock")
            return produced
        for symbol in symbols:
            for horizon in horizons:
                if horizon is Horizon.INTRADAY and not self.calendar.is_session_open(now):
                    logger.info("skip_intraday_session_closed", extra={"now": now.isoformat()})
                    self.skipped.append("intraday_session_closed")
                    continue
                context = self.context_factory(symbol, as_of, horizon)
                for agent in self.agents:
                    name = str(getattr(agent, "agent_name", type(agent).__name__))
                    if name in self.stopped:
                        continue
                    try:
                        signal = agent.evaluate(symbol, as_of, context)
                    except LeakageError:
                        if self.mode is TradingMode.BACKTEST:
                            raise
                        logger.critical("leakage_in_live", extra={"agent": name})
                        self.stopped.add(name)
                        continue
                    except Exception:
                        logger.exception("agent_failed", extra={"agent": name})
                        continue
                    produced.append(signal)
                    self.results.append(self.sink.submit(signal))
        return produced
