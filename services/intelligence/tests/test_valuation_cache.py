"""The valuation prompt must stay the same between cycles so the LLM answer cache hits (and the quota lasts)."""

import hashlib
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from contracts.fakes import FakeFeatureProvider, FakeMarketDataProvider
from contracts.fixtures import FIXTURE_AS_OF
from contracts.interfaces import AgentContext
from contracts.schemas.news_article import NewsArticle

from intelligence_agents.agents.earnings import EarningsAgent
from intelligence_agents.agents.fundamental import FundamentalAgent
from intelligence_agents.agents.valuation import ValuationAgent, valuation_prompt
from intelligence_agents.fundamentals.csv_loader import load_csv_text
from intelligence_agents.fundamentals.provider import IntelligenceFundamentalProvider
from intelligence_agents.fundamentals.store import MemoryFundamentalStore
from intelligence_agents.llm.cache import LLMCache
from intelligence_agents.llm.cost import CostTracker
from intelligence_agents.llm.fixture import FixtureLLMProvider
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.news.provider import IntelligenceNewsProvider
from intelligence_agents.testing import CLOCK, make_stores


class _CountingProvider:
    """Answers like the fixture model and remembers every request that reached it."""

    def __init__(self) -> None:
        self._inner = FixtureLLMProvider()
        self.model = "counting-model"
        self.requests = []

    def complete(self, request, *, tier):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        return self._inner.complete(request, tier=tier)


class _PricedMarket(FakeMarketDataProvider):
    def __init__(self, price: str) -> None:
        self._price = Decimal(price)

    def get_quote(self, symbol, as_of):  # type: ignore[no-untyped-def]
        return super().get_quote(symbol, as_of).model_copy(update={"last_price": self._price})


def _router(provider: _CountingProvider) -> LLMRouter:
    return LLMRouter(provider, None, CostTracker(0), tier2_enabled=False, cache=LLMCache(), use_cache=True)


def _funds(**metrics: str) -> MemoryFundamentalStore:
    stamp = (FIXTURE_AS_OF - timedelta(days=1)).isoformat()
    lines = ["symbol,metric,value,unit,period,announced_at,available_at,source,source_id"]
    lines += [f"RELIANCE,{metric},{value},ratio,2026Q3,{stamp},{stamp},test,rel-{metric}" for metric, value in metrics.items()]
    funds = MemoryFundamentalStore()
    load_csv_text(funds, "\n".join(lines) + "\n")
    return funds


def _context(price: str, *, eps: str = "100", peer_pe: str = "20") -> AgentContext:
    funds = _funds(eps=eps, peer_median_pe=peer_pe)
    news, _ = make_stores()
    return AgentContext(
        market_data_provider=_PricedMarket(price),
        feature_provider=FakeFeatureProvider(),
        news_provider=IntelligenceNewsProvider(news),
        fundamental_provider=IntelligenceFundamentalProvider(funds),
        configuration={"horizon": "SWING"},
    )


def test_small_price_moves_reuse_the_cached_answer_and_still_move_the_score() -> None:
    provider = _CountingProvider()
    agent = ValuationAgent(CLOCK, _router(provider))
    first = agent.evaluate("RELIANCE", FIXTURE_AS_OF, _context("2000"))  # P/E 20.0
    second = agent.evaluate("RELIANCE", FIXTURE_AS_OF + timedelta(minutes=10), _context("2010"))  # P/E 20.1, same bucket
    assert len(provider.requests) == 1  # the second cycle was served from the cache
    assert first.signal != second.signal  # the score still follows the live price
    assert first.features["last_price"] != second.features["last_price"]


def test_a_new_pe_bucket_calls_the_model_again() -> None:
    provider = _CountingProvider()
    agent = ValuationAgent(CLOCK, _router(provider))
    agent.evaluate("RELIANCE", FIXTURE_AS_OF, _context("2000"))  # P/E 20
    agent.evaluate("RELIANCE", FIXTURE_AS_OF, _context("2600"))  # P/E 26
    assert len(provider.requests) == 2
    assert provider.requests[0].content_hash != provider.requests[1].content_hash


def test_the_prompt_holds_no_raw_price_or_exact_score() -> None:
    text = valuation_prompt(Decimal("20.1234"), Decimal("20"), "sector_peers")
    assert "pe_bucket=20 " in text and "comparison_pe_bucket=20 " in text and "relation=in line" in text
    assert "20.12" not in text and "last_price" not in text and "score" not in text
    assert "relation=cheaper than peers" in valuation_prompt(Decimal("17"), Decimal("20"), "sector_peers")
    assert "relation=richer than peers" in valuation_prompt(Decimal("23"), Decimal("20"), "fixed_pe_20")
    assert valuation_prompt(Decimal("20.1"), Decimal("20"), "sector_peers") == valuation_prompt(Decimal("19.9"), Decimal("20"), "sector_peers")


class _ResultsNews:
    """One quarterly-results article for RELIANCE, published two hours before the fixture time."""

    def get_articles(self, symbol, as_of):  # type: ignore[no-untyped-def]
        text = "Reliance Industries quarterly results: net profit rises 9% on retail and telecom."
        published = FIXTURE_AS_OF - timedelta(hours=2)
        return [
            NewsArticle(
                article_id="rel-q-results",
                source="test",
                title="Reliance Q2 results beat estimates",
                url="https://example.com/reliance-q2",
                published_at=published,
                retrieved_at=published,
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                symbols=["RELIANCE"],
                raw_text=text,
                metadata={},
            )
        ]


def test_fundamental_and_earnings_prompts_do_not_change_between_cycles() -> None:
    news, _ = make_stores()
    funds = _funds(eps="100", profit_growth="0.12", revenue_growth="0.08", roe="0.18", rank_roe="0.7")
    for agent_class, news_provider in ((FundamentalAgent, IntelligenceNewsProvider(news)), (EarningsAgent, _ResultsNews())):
        provider = _CountingProvider()
        agent = agent_class(CLOCK, LLMRouter(provider, None, CostTracker(0), tier2_enabled=False))  # no cache: see every request
        for minutes, price in ((0, "2000"), (10, "2013")):
            context = AgentContext(
                market_data_provider=_PricedMarket(price),
                feature_provider=FakeFeatureProvider(),
                news_provider=news_provider,
                fundamental_provider=IntelligenceFundamentalProvider(funds),
                configuration={"horizon": "SWING"},
            )
            agent.evaluate("RELIANCE", FIXTURE_AS_OF + timedelta(minutes=minutes), context)
        assert len(provider.requests) == 2, agent_class.__name__  # both cycles reached the model...
        assert provider.requests[0].content_hash == provider.requests[1].content_hash, agent_class.__name__  # ...with the same text


def test_the_quality_gate_accepts_last_price_on_the_real_valuation_prompt() -> None:
    # The counting provider above skips the gate; real model answers go through it (openai_compat.py).
    from intelligence_agents.agents.grounding import quality_gate, sanitize_llm_text
    from intelligence_agents.llm.types import LLMAssessment

    evidence = sanitize_llm_text(valuation_prompt(Decimal("21.45"), Decimal("20"), "sector_peers"))
    answer = LLMAssessment(
        sentiment=-0.1, impact=0.3, confidence=0.5, event_type="valuation.note", reason_codes=("last_price",),
        horizon="SWING", high_impact=False, model="gemini-test", tier="tier1",
    )
    assert quality_gate(answer, task="valuation", evidence=evidence).reason_codes == ("last_price",)
    # A price-like code from the model maps to the allowed code too.
    assert quality_gate(replace(answer, reason_codes=("valuation.price",)), task="valuation", evidence=evidence).reason_codes == ("last_price",)
