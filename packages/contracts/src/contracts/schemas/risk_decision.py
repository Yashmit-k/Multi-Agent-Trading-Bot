"""Risk Engine verdict for one trade proposal."""

from decimal import Decimal
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from contracts.enums import RiskStatus
from contracts.schemas.common import ContractModel, JsonObject, NonEmptyStr, NonNegativeInt, ReasonCode


class RiskCheck(ContractModel):
    """One named risk check and whether it passed."""

    name: ReasonCode
    passed: bool
    detail: NonEmptyStr


class RiskDecision(ContractModel):
    """Approval or rejection of a proposal. Execution starts only after APPROVED."""

    risk_decision_id: NonEmptyStr
    proposal_id: NonEmptyStr
    timestamp: AwareDatetime
    status: RiskStatus
    risk_version: NonEmptyStr
    checks: list[RiskCheck]
    rejection_reason: str | None
    approved_quantity: NonNegativeInt
    approved_price: Decimal | None
    metadata: JsonObject

    @model_validator(mode="after")
    def _status_constraints(self) -> Self:
        if self.status == RiskStatus.APPROVED:
            if self.rejection_reason is not None:
                raise ValueError("APPROVED decisions cannot include rejection_reason")
            if self.approved_quantity <= 0:
                raise ValueError("APPROVED decisions require approved_quantity > 0")
            if self.approved_price is None or self.approved_price <= 0:
                raise ValueError("APPROVED decisions require approved_price > 0")
            return self
        reason = (self.rejection_reason or "").strip()
        if not reason:
            raise ValueError("REJECTED decisions require rejection_reason")
        if self.approved_quantity != 0:
            raise ValueError("REJECTED decisions require approved_quantity == 0")
        if self.approved_price is not None:
            raise ValueError("REJECTED decisions cannot include approved_price")
        return self
