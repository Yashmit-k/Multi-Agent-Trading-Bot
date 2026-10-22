"""Portfolio-manager review messages: request, reasoning steps, agent requests, verdict.

The portfolio manager is an LLM agent that critiques a proposed BUY before the risk engine sees it.
It can approve it, shrink it or veto it. It can never create a trade, enlarge one, or skip risk.
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from contracts.enums import AgentName, Horizon, Side
from contracts.schemas.common import ContractModel, JsonObject, NonEmptyStr, NonNegativeInt, PositiveDecimal, PositiveInt, Symbol


class ReviewKind(StrEnum):
    PIPELINE = "pipeline"  # a real proposal from the decision engine; the verdict gates it
    AD_HOC = "ad_hoc"  # an operator asked "would you buy this now?"; nothing is traded


class ReviewVerdict(StrEnum):
    APPROVE = "APPROVE"
    REDUCE = "REDUCE"
    VETO = "VETO"
    UNAVAILABLE = "UNAVAILABLE"  # the manager did not answer in time; the normal rules decide


class ReviewStepKind(StrEnum):
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_REPLY = "agent_reply"
    CRITIQUE = "critique"  # the code rejected a draft verdict and asked the model to revise it
    REPLAN = "replan"  # an LLM or tool failure changed the plan
    LLM_ERROR = "llm_error"


class ReviewRequest(ContractModel):
    """A proposal waiting for the portfolio manager. Published on review.events as review.requested."""

    review_id: NonEmptyStr
    kind: ReviewKind
    proposal_id: NonEmptyStr | None = None
    symbol: Symbol
    horizon: Horizon
    side: Side
    quantity: PositiveInt
    entry_price: PositiveDecimal
    aggregated_signal: float = Field(ge=-1, le=1)
    aggregated_confidence: float = Field(ge=0, le=1)
    requested_at: AwareDatetime
    requested_by: NonEmptyStr
    metadata: JsonObject


class ReviewStep(ContractModel):
    """One step of the manager's reasoning: a plan, a tool call and its result, a critique, a replan."""

    review_id: NonEmptyStr
    step: NonNegativeInt
    kind: ReviewStepKind
    actor: NonEmptyStr
    timestamp: AwareDatetime
    tool: str | None = None
    purpose: str | None = None
    arguments: JsonObject = Field(default_factory=dict)
    summary: str = ""
    metadata: JsonObject = Field(default_factory=dict)


class AgentRequest(ContractModel):
    """The manager asks another agent to look again. Published on agent.events as agent.request."""

    request_id: NonEmptyStr
    review_id: NonEmptyStr
    from_agent: Literal["portfolio_manager"] = "portfolio_manager"
    to_agent: AgentName
    symbol: Symbol
    question: NonEmptyStr
    timestamp: AwareDatetime


class ProposalReview(ContractModel):
    """The manager's verdict. Published on review.events as review.completed."""

    review_id: NonEmptyStr
    kind: ReviewKind
    proposal_id: NonEmptyStr | None = None
    symbol: Symbol
    verdict: ReviewVerdict
    size_fraction: float = Field(ge=0, le=1)
    conflicts: list[str] = Field(default_factory=list)
    critique: str
    reviewer: NonEmptyStr
    steps: NonNegativeInt
    timestamp: AwareDatetime
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fraction_matches_verdict(self) -> "ProposalReview":
        expected = {ReviewVerdict.APPROVE: (1.0, 1.0), ReviewVerdict.UNAVAILABLE: (1.0, 1.0), ReviewVerdict.VETO: (0.0, 0.0), ReviewVerdict.REDUCE: (0.1, 0.9)}
        low, high = expected[self.verdict]
        if not low <= self.size_fraction <= high:
            raise ValueError(f"size_fraction {self.size_fraction} does not fit verdict {self.verdict.value}")
        return self
