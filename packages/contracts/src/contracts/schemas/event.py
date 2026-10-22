"""Event envelope. Consumers deduplicate on event_id."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, TypeAdapter, create_model, model_validator

from contracts.enums import OrderStatus, RiskStatus
from contracts.events import EventType
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.common import ContractModel, NonEmptyStr
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
from contracts.schemas.risk_decision import RiskDecision
from contracts.schemas.system import AgentHeartbeat, SystemAlert
from contracts.schemas.trade_proposal import TradeProposal

PAYLOAD_MODELS: dict[EventType, type[ContractModel]] = {
    EventType.MARKET_TICK: Quote,
    EventType.MARKET_CANDLE: Candle,
    EventType.FEATURE_UPDATED: FeatureSet,
    EventType.AGENT_SIGNAL: AgentSignal,
    EventType.NEWS_ARTICLE: NewsArticle,
    EventType.NEWS_SIGNAL: NewsSignal,
    EventType.FUNDAMENTAL_UPDATED: FundamentalDataPoint,
    EventType.DECISION_CREATED: TradeProposal,
    EventType.RISK_APPROVED: RiskDecision,
    EventType.RISK_REJECTED: RiskDecision,
    EventType.ORDER_CREATED: Order,
    EventType.ORDER_UPDATED: Order,
    EventType.ORDER_FILLED: Execution,
    EventType.ORDER_REJECTED: Order,
    EventType.POSITION_UPDATED: Position,
    EventType.PORTFOLIO_UPDATED: PortfolioSnapshot,
    EventType.SYSTEM_ALERT: SystemAlert,
    EventType.AGENT_HEARTBEAT: AgentHeartbeat,
    EventType.AGENT_REQUEST: AgentRequest,
    EventType.REVIEW_REQUESTED: ReviewRequest,
    EventType.REVIEW_STEP: ReviewStep,
    EventType.REVIEW_COMPLETED: ProposalReview,
}

if set(PAYLOAD_MODELS) != set(EventType):
    raise RuntimeError("every event type needs a payload model")


class _EnvelopeCommon(ContractModel):
    event_id: NonEmptyStr
    timestamp: AwareDatetime
    source: NonEmptyStr
    schema_version: Literal["1.0"] = "1.0"
    correlation_id: NonEmptyStr


def _variant_name(event_type: EventType) -> str:
    parts = event_type.value.replace(".", "_").split("_")
    return "".join(part.capitalize() for part in parts) + "Envelope"


ENVELOPE_VARIANTS: dict[EventType, type[ContractModel]] = {
    event_type: create_model(
        _variant_name(event_type),
        __base__=_EnvelopeCommon,
        event_type=(Literal[event_type], ...),
        payload=(payload_model, ...),
    )
    for event_type, payload_model in PAYLOAD_MODELS.items()
}

_variant_union: object = next(iter(ENVELOPE_VARIANTS.values()))
for _variant in list(ENVELOPE_VARIANTS.values())[1:]:
    _variant_union = _variant_union | _variant

EnvelopeVariant = Annotated[_variant_union, Field(discriminator="event_type")]
_ENVELOPE_ADAPTER = TypeAdapter(EnvelopeVariant)

EventPayload = (
    Quote
    | Candle
    | FeatureSet
    | AgentSignal
    | NewsArticle
    | NewsSignal
    | FundamentalDataPoint
    | TradeProposal
    | RiskDecision
    | Order
    | Execution
    | Position
    | PortfolioSnapshot
    | SystemAlert
    | AgentHeartbeat
    | AgentRequest
    | ReviewRequest
    | ReviewStep
    | ProposalReview
)


class EventEnvelope(ContractModel):
    """Wrapper for every Redis message. event_id is the deduplication key."""

    event_id: NonEmptyStr
    event_type: EventType
    timestamp: AwareDatetime
    source: NonEmptyStr
    schema_version: Literal["1.0"] = "1.0"
    correlation_id: NonEmptyStr
    payload: EventPayload

    @model_validator(mode="before")
    @classmethod
    def _parse_payload(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw_type = data.get("event_type")
        raw_payload = data.get("payload")
        if raw_type is None or raw_payload is None:
            return data
        try:
            event_type = raw_type if isinstance(raw_type, EventType) else EventType(raw_type)
        except ValueError:
            return data
        model = PAYLOAD_MODELS[event_type]
        if isinstance(raw_payload, model):
            parsed: ContractModel = raw_payload
        else:
            payload_data = raw_payload.model_dump() if isinstance(raw_payload, ContractModel) else raw_payload
            parsed = model.model_validate(payload_data)
        _assert_payload_status(event_type, parsed)
        return {**data, "event_type": event_type, "payload": parsed}

    @model_validator(mode="after")
    def _status_matches_event(self) -> Self:
        _assert_payload_status(self.event_type, self.payload)
        return self


def event_envelope_json_schema() -> dict[str, object]:
    """OpenAPI schema for the envelope, discriminated on event_type."""
    return _ENVELOPE_ADAPTER.json_schema()


def _assert_payload_status(event_type: EventType, payload: ContractModel) -> None:
    if event_type == EventType.RISK_APPROVED and isinstance(payload, RiskDecision):
        if payload.status != RiskStatus.APPROVED:
            raise ValueError("risk.approved requires status APPROVED")
    elif event_type == EventType.RISK_REJECTED and isinstance(payload, RiskDecision):
        if payload.status != RiskStatus.REJECTED:
            raise ValueError("risk.rejected requires status REJECTED")
    elif event_type == EventType.ORDER_CREATED and isinstance(payload, Order):
        if payload.status != OrderStatus.CREATED:
            raise ValueError("order.created requires status CREATED")
    elif event_type == EventType.ORDER_REJECTED and isinstance(payload, Order):
        if payload.status != OrderStatus.REJECTED:
            raise ValueError("order.rejected requires status REJECTED")
