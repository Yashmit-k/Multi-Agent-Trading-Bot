"""Models written to docs/contracts."""

from pydantic import BaseModel

from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.catalog import ContractCatalog
from contracts.schemas.event import EventEnvelope
from contracts.schemas.execution import Execution
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.market import Candle, Quote
from contracts.schemas.news_article import NewsArticle
from contracts.schemas.news_signal import NewsSignal
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from contracts.schemas.review import AgentRequest, ProposalReview, ReviewRequest, ReviewStep
from contracts.schemas.risk_decision import RiskCheck, RiskDecision
from contracts.schemas.submission import SubmissionResult
from contracts.schemas.system import AgentHeartbeat, SystemAlert
from contracts.schemas.trade_proposal import TradeProposal

EXPORT_MODELS: dict[str, type[BaseModel]] = {
    "AgentHeartbeat": AgentHeartbeat,
    "AgentRequest": AgentRequest,
    "AgentSignal": AgentSignal,
    "Candle": Candle,
    "ContractCatalog": ContractCatalog,
    "EventEnvelope": EventEnvelope,
    "Execution": Execution,
    "FeatureSet": FeatureSet,
    "FundamentalDataPoint": FundamentalDataPoint,
    "NewsArticle": NewsArticle,
    "NewsSignal": NewsSignal,
    "Order": Order,
    "PortfolioSnapshot": PortfolioSnapshot,
    "Position": Position,
    "ProposalReview": ProposalReview,
    "Quote": Quote,
    "ReviewRequest": ReviewRequest,
    "ReviewStep": ReviewStep,
    "RiskCheck": RiskCheck,
    "RiskDecision": RiskDecision,
    "SubmissionResult": SubmissionResult,
    "SystemAlert": SystemAlert,
    "TradeProposal": TradeProposal,
}
