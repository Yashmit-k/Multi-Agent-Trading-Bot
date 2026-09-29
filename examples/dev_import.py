"""Dev 1 and Dev 2 import the shared contract package. No strategy logic lives here."""

from contracts import __version__
from contracts.fakes import FakeMarketDataProvider, FakeSignalSink
from contracts.fixtures import FIXTURE_AS_OF
from contracts.interfaces import MarketDataProvider, SignalSink
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.event import EventEnvelope
from contracts.schemas.execution import Execution
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.news_article import NewsArticle
from contracts.schemas.news_signal import NewsSignal
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from contracts.schemas.risk_decision import RiskDecision
from contracts.schemas.trade_proposal import TradeProposal
from contracts.fixtures import sample_agent_signal


def main() -> None:
    provider: MarketDataProvider = FakeMarketDataProvider()
    sink: SignalSink = FakeSignalSink()
    quote = provider.get_quote("RELIANCE", FIXTURE_AS_OF)
    signal: AgentSignal = sample_agent_signal("RELIANCE")
    result = sink.submit(signal)
    public_types = (
        AgentSignal,
        NewsArticle,
        NewsSignal,
        FundamentalDataPoint,
        FeatureSet,
        TradeProposal,
        RiskDecision,
        Order,
        Execution,
        Position,
        PortfolioSnapshot,
        EventEnvelope,
    )
    print(f"contracts {__version__}")
    print(f"RELIANCE {quote.last_price} at {quote.timestamp.isoformat()}")
    print(f"submitted {result.signal_id} accepted={result.accepted}")
    print(f"imported {len(public_types)} contract types")


if __name__ == "__main__":
    main()
