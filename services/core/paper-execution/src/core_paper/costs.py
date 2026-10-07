"""Configurable execution costs. Research mode can collapse every charge into one bps figure."""

from dataclasses import dataclass
from decimal import Decimal

from contracts.enums import Side

_BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class CostSchedule:
    brokerage_rate: Decimal = Decimal("0")
    exchange_rate: Decimal = Decimal("0")
    stt_rate: Decimal = Decimal("0")
    gst_rate: Decimal = Decimal("0")
    stamp_rate: Decimal = Decimal("0")
    sebi_rate: Decimal = Decimal("0")
    flat_bps: Decimal | None = None
    slippage_bps: Decimal = Decimal("0")

    @classmethod
    def research(cls, transaction_cost_bps: Decimal, slippage_bps: Decimal) -> "CostSchedule":
        return cls(flat_bps=transaction_cost_bps, slippage_bps=slippage_bps)


def slipped_price(side: Side, price: Decimal, slippage_bps: Decimal) -> Decimal:
    """Move the fill against the trader. Buys pay more and sells receive less."""
    shift = price * slippage_bps / _BPS
    if side == Side.BUY:
        return price + shift
    return price - shift


def fee_on(notional: Decimal, schedule: CostSchedule) -> Decimal:
    if schedule.flat_bps is not None:
        return abs(notional) * schedule.flat_bps / _BPS
    rate = (
        schedule.brokerage_rate
        + schedule.exchange_rate
        + schedule.stt_rate
        + schedule.gst_rate
        + schedule.stamp_rate
        + schedule.sebi_rate
    )
    return abs(notional) * rate
