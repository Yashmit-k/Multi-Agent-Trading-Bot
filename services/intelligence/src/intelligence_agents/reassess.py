"""Re-check one stock with one intelligence agent, when the portfolio manager asks.

The regular loop scores all 50 stocks every ten minutes. A re-check is different: it pulls the news
feeds again, runs only the requested agent on only that stock, uses the re-check model (a second,
independent look), tags the signal with the request it answers, and submits it through Core like any
other signal. It has its own stores and router, so it never waits for a running loop cycle.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from contracts.enums import Horizon
from contracts.fakes import FakeFeatureProvider
from contracts.interfaces import AgentContext

from intelligence_agents.agents.earnings import EarningsAgent
from intelligence_agents.agents.fundamental import FundamentalAgent
from intelligence_agents.agents.news import NewsAgent
from intelligence_agents.agents.valuation import ValuationAgent
from intelligence_agents.clock import SystemClock
from intelligence_agents.fundamentals.provider import IntelligenceFundamentalProvider
from intelligence_agents.leakage import LeakageGuard
from intelligence_agents.news.provider import IntelligenceNewsProvider
from intelligence_agents.runtime import make_price_provider, make_router, make_stores
from intelligence_agents.settings import IntelligenceSettings

logger = logging.getLogger(__name__)

AGENTS = {"news": NewsAgent, "fundamental": FundamentalAgent, "valuation": ValuationAgent, "earnings": EarningsAgent}


class Reassessor:
    def __init__(self, settings: IntelligenceSettings, sink) -> None:
        self._settings = settings
        self._sink = sink
        self._clock = SystemClock()
        self._news, self._funds = make_stores(settings)
        self.model = settings.llm_reassess_model or settings.llm_tier2_model or settings.llm_tier1_model
        router = make_router(settings, tier1_model=self.model)
        self._agents = {name: cls(self._clock, router) for name, cls in AGENTS.items()}
        self._prices = make_price_provider(settings)
        self._puller = None
        if settings.data_source == "rss":
            from intelligence_agents.news.rss import RssPuller

            self._puller = RssPuller(
                self._news,
                self._clock,
                settings.symbols,
                max_bytes=settings.rss_max_bytes,
                max_items=settings.rss_max_items,
                interval_seconds=60,
                keep_market_wide=settings.news_keep_market_wide,
            )
        self._lock = threading.Lock()

    def run(self, *, agent: str, symbol: str, horizon: Horizon, request_id: str, review_id: str) -> dict[str, object]:
        with self._lock:
            fresh = 0
            if agent == "news" and self._puller is not None:
                for url in self._settings.news_rss_urls:
                    try:
                        fresh += self._puller.pull(url) or 0
                    except Exception:  # noqa: BLE001 - one bad feed must not fail the re-check
                        logger.warning("reassess_feed_failed", extra={"url": url})
            as_of = datetime.now(timezone.utc).replace(microsecond=0)
            context = AgentContext(
                market_data_provider=LeakageGuard(self._prices, self._settings.trading_mode),
                feature_provider=LeakageGuard(FakeFeatureProvider(), self._settings.trading_mode),
                news_provider=LeakageGuard(IntelligenceNewsProvider(self._news), self._settings.trading_mode),
                fundamental_provider=LeakageGuard(IntelligenceFundamentalProvider(self._funds), self._settings.trading_mode),
                configuration={"horizon": horizon.value},
            )
            signal = self._agents[agent].evaluate(symbol, as_of, context)
            tagged = signal.model_copy(update={"metadata": {**signal.metadata, "requested_by": "portfolio_manager", "request_id": request_id, "review_id": review_id}})
            result = self._sink.submit(tagged)
            llm = (tagged.metadata.get("llm") or [{}])[0] if isinstance(tagged.metadata.get("llm"), list) else {}
            logger.info("reassess_done", extra={"agent": agent, "symbol": symbol, "signal_id": tagged.signal_id, "accepted": result.accepted})
            return {
                "signal_id": tagged.signal_id,
                "agent": agent,
                "symbol": symbol,
                "score": round(tagged.signal, 3),
                "confidence": round(tagged.confidence, 3),
                "reason_codes": tagged.reason_codes[:5],
                "headlines": [item.get("title") for item in tagged.metadata.get("headlines", [])][:5],
                "insufficient_data": bool(tagged.metadata.get("insufficient_data")),
                "model": llm.get("model") if isinstance(llm, dict) else None,
                "llm_fallback": bool(llm.get("fallback")) if isinstance(llm, dict) else False,
                "new_articles_pulled": fresh,
                "accepted_by_core": result.accepted,
            }
