"""Point-in-time portfolio totals."""

from decimal import Decimal

from pydantic import AwareDatetime, Field

from contracts.schemas.common import ContractModel, DrawdownFraction, NonNegativeDecimal


class PortfolioSnapshot(ContractModel):
    """Account totals at one timestamp. drawdown is the fraction of peak equity given back."""

    timestamp: AwareDatetime
    cash: Decimal
    equity: Decimal
    market_value: Decimal
    gross_exposure: NonNegativeDecimal
    net_exposure: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    drawdown: DrawdownFraction = Field(description="Fraction of peak equity given back, in [0, 1].")
