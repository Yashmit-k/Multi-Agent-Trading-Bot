"""One-shot fixture evaluation. No live LLM, RSS, or Core HTTP."""

from __future__ import annotations

import time
from collections import Counter

from contracts.enums import Horizon, TradingMode
from contracts.fakes import FakeSignalSink
from contracts.fixtures import FIXTURE_AS_OF, FIXTURE_SYMBOLS

from intelligence_agents.agents.earnings import EarningsAgent
from intelligence_agents.agents.fundamental import FundamentalAgent
from intelligence_agents.agents.news import NewsAgent
from intelligence_agents.agents.valuation import ValuationAgent
from intelligence_agents.clock import ReplayClock
from intelligence_agents.llm.cost import CostTracker
from intelligence_agents.llm.fixture import FixtureLLMProvider
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.runner import Runner
from intelligence_agents.testing import make_context, make_stores


def main() -> int:
    news, funds = make_stores()
    clock = ReplayClock(FIXTURE_AS_OF)
    router = LLMRouter(FixtureLLMProvider(), None, CostTracker(0), tier2_enabled=False)
    agents = (
        NewsAgent(clock, router),
        FundamentalAgent(clock, router),
        ValuationAgent(clock, router),
        EarningsAgent(clock, router),
    )
    sink = FakeSignalSink()

    def factory(symbol: str, as_of, horizon: Horizon):
        return make_context(news, funds, {"horizon": horizon.value})

    runner = Runner(agents, sink, clock, factory, TradingMode.BACKTEST)
    started = time.perf_counter()
    produced = runner.run(list(FIXTURE_SYMBOLS), FIXTURE_AS_OF)
    elapsed = time.perf_counter() - started
    counts = Counter(signal.agent_name.value for signal in produced)
    rate = len(produced) / elapsed if elapsed > 0 else 0.0
    print(f"symbols={len(FIXTURE_SYMBOLS)} as_of={FIXTURE_AS_OF.isoformat()}")
    print(f"signals={len(produced)} elapsed_s={elapsed:.3f} signals_per_s={rate:.1f}")
    print("per_agent=" + " ".join(f"{name}:{count}" for name, count in sorted(counts.items())))
    for signal in produced:
        print(f"  {signal.agent_name.value:12} {signal.symbol:10} {signal.signal_id}")
    if len(produced) != len(FIXTURE_SYMBOLS) * len(agents):
        print("smoke failed: expected one signal per agent per symbol")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
