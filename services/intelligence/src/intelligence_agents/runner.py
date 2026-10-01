"""Evaluate intelligence agents and submit through SignalSink."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from contracts.enums import Horizon, TradingMode
from contracts.interfaces import AgentContext, SignalSink, TradingAgent
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.submission import SubmissionResult
from contracts.time import require_aware

from intelligence_agents.clock import Clock, ReplayClock
from intelligence_agents.errors import LeakageError
from intelligence_agents.leakage import LeakageGuard

logger = logging.getLogger(__name__)

ContextFactory = Callable[[str, datetime, Horizon], AgentContext]


class Runner:
    def __init__(
        self,
        agents: Sequence[TradingAgent],
        sink: SignalSink,
        clock: Clock,
        context_factory: ContextFactory,
        mode: TradingMode,
        horizons: Sequence[Horizon] | None = None,
    ) -> None:
        self.agents = list(agents)
        self.sink = sink
        self.clock = clock
        self.context_factory = context_factory
        self.mode = mode
        self.horizons = list(horizons or (Horizon.SWING,))
        self.results: list[SubmissionResult] = []
        self.produced: list[AgentSignal] = []

    def run(self, symbols: Sequence[str], as_of: datetime) -> list[AgentSignal]:
        aware = require_aware(as_of, "as_of")
        produced: list[AgentSignal] = []
        for symbol in symbols:
            for horizon in self.horizons:
                context = self._guarded_context(self.context_factory(symbol, aware, horizon))
                for agent in self.agents:
                    name = str(getattr(agent, "agent_name", type(agent).__name__))
                    try:
                        signal = agent.evaluate(symbol, aware, context)
                    except LeakageError:
                        if self.mode is TradingMode.BACKTEST:
                            raise
                        logger.critical("leakage_in_live", extra={"agent": name})
                        continue
                    except Exception:
                        logger.exception("agent_failed", extra={"agent": name, "symbol": symbol})
                        continue
                    produced.append(signal)
                    result = self.sink.submit(signal)
                    self.results.append(result)
                    logger.info(
                        "signal_submitted",
                        extra={
                            "agent_name": signal.agent_name.value,
                            "symbol": signal.symbol,
                            "as_of": signal.as_of.isoformat(),
                            "signal_id": signal.signal_id,
                            "duplicate": result.duplicate,
                            "accepted": result.accepted,
                            "correlation_id": signal.signal_id,
                        },
                    )
        self.produced.extend(produced)
        return produced

    def run_window(self, symbols: Sequence[str], steps: Sequence[datetime]) -> list[AgentSignal]:
        produced: list[AgentSignal] = []
        for step in steps:
            self.clock = ReplayClock(step)
            produced.extend(self.run(symbols, step))
        return produced

    def _guarded_context(self, context: AgentContext) -> AgentContext:
        return AgentContext(
            market_data_provider=LeakageGuard(context.market_data_provider, self.mode),
            feature_provider=LeakageGuard(context.feature_provider, self.mode),
            news_provider=LeakageGuard(context.news_provider, self.mode),
            fundamental_provider=LeakageGuard(context.fundamental_provider, self.mode),
            configuration=context.configuration,
            current_portfolio_snapshot=context.current_portfolio_snapshot,
        )
