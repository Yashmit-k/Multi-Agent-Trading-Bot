"""Agent and provider interfaces.

``ZerodhaMarketDataProvider`` and ``HistoricalReplayMarketDataProvider`` must
implement ``MarketDataProvider`` with these method names. Agents receive
``AgentContext`` only. It does not carry execution credentials.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from contracts.enums import Timeframe
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.market import Candle, Quote
from contracts.schemas.news_article import NewsArticle
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.submission import SubmissionResult

_FORBIDDEN_CONFIGURATION_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "api_secret",
        "client_secret",
        "password",
        "request_token",
        "zerodha_api_key",
        "zerodha_api_secret",
    }
)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Quote and candle access shared by live and historical replay providers."""

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        """Return the quote knowable at as_of."""

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Return bars in the window. Bar end is the time the bar became knowable."""

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        """Return the newest stored bar for the timeframe."""


@runtime_checkable
class FeatureProvider(Protocol):
    """Read model for the Core Feature Engine. Agents do not recompute indicators."""

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        """Return the feature set knowable at as_of."""


@runtime_checkable
class NewsProvider(Protocol):
    def get_articles(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        """Return articles published and retrieved at or before as_of."""


@runtime_checkable
class FundamentalProvider(Protocol):
    def get_fundamentals(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        """Return points with available_at <= as_of."""


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Approved dependencies for ``TradingAgent.evaluate``.

    The context has no broker client and no order router. ``configuration``
    rejects known execution-credential keys.
    """

    market_data_provider: MarketDataProvider
    feature_provider: FeatureProvider
    news_provider: NewsProvider
    fundamental_provider: FundamentalProvider
    configuration: Mapping[str, Any]
    current_portfolio_snapshot: PortfolioSnapshot | None = None

    def __post_init__(self) -> None:
        forbidden = {key.lower() for key in self.configuration} & _FORBIDDEN_CONFIGURATION_KEYS
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ValueError(f"AgentContext cannot carry execution credentials: {names}")


@runtime_checkable
class TradingAgent(Protocol):
    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        """Produce one signal from context. Do not place orders or call other agents."""


@runtime_checkable
class SignalSink(Protocol):
    """The only way an agent publishes a signal.

    Agents do not write PostgreSQL, change portfolio state, place orders, call
    Zerodha, call the Risk Engine, or call another agent. Core owns the
    implementation of this sink.
    """

    def submit(self, signal: AgentSignal) -> SubmissionResult:
        """Accept a signal and return the acknowledgement."""
