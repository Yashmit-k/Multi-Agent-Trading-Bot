"""Assemble stores, agents, and a Runner from settings. No secrets in AgentContext."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from contracts.enums import Horizon, TradingMode
from contracts.fakes import FakeFeatureProvider, FakeMarketDataProvider, FakeSignalSink
from contracts.interfaces import AgentContext, SignalSink

from intelligence_agents.agents.earnings import EarningsAgent
from intelligence_agents.agents.fundamental import FundamentalAgent
from intelligence_agents.agents.news import NewsAgent
from intelligence_agents.agents.valuation import ValuationAgent
from intelligence_agents.clock import Clock, ReplayClock, SystemClock
from intelligence_agents.fundamentals.provider import IntelligenceFundamentalProvider
from intelligence_agents.fundamentals.store import MemoryFundamentalStore, SqliteFundamentalStore
from intelligence_agents.llm.router import LLMRouter, build_router
from intelligence_agents.news.fixtures import load_fundamental_fixtures, load_news_fixtures
from intelligence_agents.news.provider import IntelligenceNewsProvider
from intelligence_agents.news.store import MemoryNewsStore, SqliteNewsStore
from intelligence_agents.runner import Runner
from intelligence_agents.settings import IntelligenceSettings
from intelligence_agents.sink.http import HttpSignalSink


@dataclass
class RunnerHealth:
    last_run_at: str | None = None
    signals_emitted_last_run: int = 0
    last_error: str | None = None
    consecutive_failures: int = 0
    sink_reachable: bool | None = None
    runner_running: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    fallbacks: int = 0
    extras: dict[str, object] = field(default_factory=dict)


def make_clock(settings: IntelligenceSettings, as_of: datetime | None = None) -> Clock:
    if settings.trading_mode is TradingMode.BACKTEST:
        return ReplayClock(as_of or datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc))
    return SystemClock()


def make_stores(settings: IntelligenceSettings):
    if settings.store == "memory":
        news = MemoryNewsStore()
        funds = MemoryFundamentalStore()
    else:
        news = SqliteNewsStore(settings.sqlite_path)
        funds = SqliteFundamentalStore(settings.sqlite_path)
    if settings.data_source == "fixtures":
        now = datetime.now(timezone.utc)
        load_news_fixtures(news, now=now)
        load_fundamental_fixtures(funds)
    return news, funds


def make_router(settings: IntelligenceSettings) -> LLMRouter:
    return build_router(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        tier1_model=settings.llm_tier1_model,
        tier2_model=settings.llm_tier2_model,
        timeout=settings.llm_timeout_seconds,
        daily_budget_usd=settings.llm_daily_budget_usd,
        tier2_enabled=settings.tier2_enabled,
        use_cache=False,
    )


def make_sink(settings: IntelligenceSettings, *, sink: SignalSink | None = None) -> SignalSink:
    if sink is not None:
        return sink
    if settings.trading_mode is TradingMode.BACKTEST:
        return FakeSignalSink()
    return HttpSignalSink(settings.core_api_url, settings.internal_signal_token, settings.trading_mode)


def make_runner(
    settings: IntelligenceSettings,
    *,
    sink: SignalSink | None = None,
    clock: Clock | None = None,
) -> tuple[Runner, LLMRouter]:
    news, funds = make_stores(settings)
    resolved_clock = clock or make_clock(settings)
    router = make_router(settings)
    agents = (
        NewsAgent(resolved_clock, router),
        FundamentalAgent(resolved_clock),
        ValuationAgent(resolved_clock),
        EarningsAgent(resolved_clock, router),
    )

    def factory(symbol: str, as_of: datetime, horizon: Horizon) -> AgentContext:
        return AgentContext(
            market_data_provider=FakeMarketDataProvider(),
            feature_provider=FakeFeatureProvider(),
            news_provider=IntelligenceNewsProvider(news),
            fundamental_provider=IntelligenceFundamentalProvider(funds),
            configuration={"horizon": horizon.value},
        )

    runner = Runner(agents, make_sink(settings, sink=sink), resolved_clock, factory, settings.trading_mode)
    return runner, router
