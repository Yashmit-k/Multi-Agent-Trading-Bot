"""Delivery round trip for one held name. The 2 bp research schedule is not used."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from core_paper.charges import ZERODHA_EQUITY_RI, delivery_buy, delivery_sell

from quant_agents.research.daily_rules.rules import BOOK, ENTRY_SLIPPAGE, NAME_CAP


def trade_pnl(p0: Decimal, p1: Decimal, slice_cash: Decimal) -> Decimal:
    """Rupee PnL of one long delivery trade. Zero when the slice cannot buy a share."""
    if p0 <= 0 or p1 <= 0 or slice_cash <= 0:
        raise ValueError("prices and slice must be positive")
    entry = p0 * (Decimal(1) + ENTRY_SLIPPAGE)
    quantity = int((min(slice_cash, NAME_CAP) / entry).to_integral_value(rounding=ROUND_DOWN))
    if quantity < 1:
        return Decimal(0)
    buy_notional = entry * quantity
    sell_notional = p1 * quantity
    fees = delivery_buy(buy_notional, ZERODHA_EQUITY_RI).total
    fees += delivery_sell(sell_notional, ZERODHA_EQUITY_RI, include_dp=True).total
    return sell_notional - buy_notional - fees


def window_return(pnls: tuple[Decimal, ...] | list[Decimal]) -> Decimal:
    return sum(pnls, Decimal(0)) / BOOK
