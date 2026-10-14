"""Approved per-fill net return. This identity does not call price_trade or fee_on."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ENTRY_FEE = Decimal("0.0002")
EXIT_FEE = Decimal("0.0002")


@dataclass(frozen=True, slots=True)
class NetSummary:
    mean_all: Decimal
    mean_trades: Decimal | None
    trade_count: int
    total_net: Decimal


def net_return(p0: Decimal, p1: Decimal) -> Decimal:
    """`net = (P1-P0)/P0 - 0.0002 - (P1/P0)*0.0002`. Each fee is applied once."""
    if not isinstance(p0, Decimal) or not isinstance(p1, Decimal) or p0 <= 0 or p1 <= 0:
        raise ValueError("invalid price")
    ratio = p1 / p0
    gross = ratio - Decimal(1)
    return gross - ENTRY_FEE - ratio * EXIT_FEE


def validation_net_summary(nets: tuple[Decimal, ...] | list[Decimal], take_trade: tuple[bool, ...] | list[bool]) -> NetSummary:
    """No-trade contributes zero to the all-event mean. Trade diagnostics ignore those zeros."""
    if len(nets) != len(take_trade) or not nets:
        raise ValueError("nets and trade flags must be the same non-empty length")
    contributions = [net if take else Decimal(0) for net, take in zip(nets, take_trade, strict=True)]
    traded = [net for net, take in zip(nets, take_trade, strict=True) if take]
    mean_trades = sum(traded, Decimal(0)) / Decimal(len(traded)) if traded else None
    return NetSummary(
        sum(contributions, Decimal(0)) / Decimal(len(contributions)),
        mean_trades,
        len(traded),
        sum(traded, Decimal(0)),
    )
