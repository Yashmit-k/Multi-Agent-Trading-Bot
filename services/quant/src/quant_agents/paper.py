"""PAPER evaluation against Core FeatureSets. Does not train and does not place orders."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from contracts.enums import Horizon, Timeframe
from contracts.fakes import FakeFundamentalProvider, FakeMarketDataProvider, FakeNewsProvider
from contracts.interfaces import AgentContext, SignalSink
from contracts.schemas.feature_set import FeatureSet

from quant_agents.agents import MeanReversionAgent, MomentumAgent, RegimeAgent, TechnicalAgent, VolumeAgent
from quant_agents.calendar.static_nse import StaticNseCalendar
from quant_agents.clock import ReplayClock

logger = logging.getLogger(__name__)

_AGENTS = (TechnicalAgent, MomentumAgent, MeanReversionAgent, VolumeAgent, RegimeAgent)
_SWING = {"horizon": Horizon.SWING, "timeframe": Timeframe.D1, "regime_index_symbols": ()}


class _OneFeatureProvider:
    def __init__(self, feature_set: FeatureSet) -> None:
        self._feature_set = feature_set

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        if symbol.strip().upper() != self._feature_set.symbol:
            raise LookupError(symbol)
        return self._feature_set


def publish_symbol_signals(symbol: str, feature_set: FeatureSet, sink: SignalSink) -> int:
    """Evaluate every quant agent once at the feature timestamp and submit each signal."""
    as_of = feature_set.timestamp
    clock = ReplayClock(as_of)
    calendar = StaticNseCalendar()
    context = AgentContext(
        market_data_provider=FakeMarketDataProvider(),
        feature_provider=_OneFeatureProvider(feature_set),
        news_provider=FakeNewsProvider(),
        fundamental_provider=FakeFundamentalProvider(),
        configuration=_SWING,
    )
    written = 0
    for agent_cls in _AGENTS:
        signal = agent_cls(clock, calendar).evaluate(symbol, as_of, context)
        sink.submit(signal)
        written += 1
    return written


def fetch_feature(client: httpx.Client, base_url: str, token: str, symbol: str) -> FeatureSet | None:
    response = client.get(
        f"{base_url.rstrip('/')}/api/v1/features/{symbol}",
        params={"timeframe": Timeframe.D1.value},
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return FeatureSet.model_validate(response.json())


def run_paper_pass(base_url: str, read_token: str, symbols: tuple[str, ...], sink: SignalSink, *, client: httpx.Client | None = None) -> int:
    owned = client or httpx.Client(timeout=30.0)
    close = client is None
    written = 0
    try:
        for symbol in symbols:
            feature_set = fetch_feature(owned, base_url, read_token, symbol)
            if feature_set is None:
                logger.info("quant_skip_symbol", extra={"symbol": symbol, "reason": "no_features"})
                continue
            written += publish_symbol_signals(symbol, feature_set, sink)
    finally:
        if close:
            owned.close()
    logger.info("quant_paper_pass", extra={"signals": written, "symbols": len(symbols)})
    return written
