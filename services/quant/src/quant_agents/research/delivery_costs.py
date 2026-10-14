"""Zerodha equity charges used by the delivery-target study.

The rates are the equity table on https://zerodha.com/charges/ as read on
2026-10-09. They are applied uniformly across 2024–2026. This is not a
reconstruction of every historical revision.

A same-session round trip is classified as intraday, including when the buy
was CNC. An overnight sale stays on the equity-delivery schedule. Brokerage
can be switched off for a sensitivity run. Statutory charges stay.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

SCHEDULE_ID = "zerodha_page_2026-10-09"
CENT = Decimal("0.01")
CRORE = Decimal("10000000")
TXN_NSE = Decimal("0.0000307")
SEBI_PER_CRORE = Decimal("10")
GST_RATE = Decimal("0.18")
STT_DELIVERY = Decimal("0.001")
STT_INTRADAY_SELL = Decimal("0.00025")
STAMP_DELIVERY_BUY = Decimal("0.00015")
STAMP_INTRADAY_BUY = Decimal("0.00003")
BROKERAGE_RATE = Decimal("0.0003")
BROKERAGE_CAP = Decimal("20")
DP_PER_SELL = Decimal("15.34")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class ChargeBreakdown:
    brokerage: Decimal
    stt: Decimal
    transaction: Decimal
    sebi: Decimal
    gst: Decimal
    stamp: Decimal
    dp: Decimal

    @property
    def total(self) -> Decimal:
        return self.brokerage + self.stt + self.transaction + self.sebi + self.gst + self.stamp + self.dp

    def as_dict(self) -> dict[str, str]:
        payload = {
            "brokerage": self.brokerage,
            "stt": self.stt,
            "transaction": self.transaction,
            "sebi": self.sebi,
            "gst": self.gst,
            "stamp": self.stamp,
            "dp": self.dp,
            "total": self.total,
        }
        return {key: format(value, "f") for key, value in payload.items()}


def _brokerage(notional: Decimal, enabled: bool) -> Decimal:
    if not enabled:
        return Decimal("0")
    raw = abs(notional) * BROKERAGE_RATE
    if raw > BROKERAGE_CAP:
        raw = BROKERAGE_CAP
    return money(raw)


def _breakdown(
    notional: Decimal,
    *,
    brokerage: bool,
    stt_rate: Decimal,
    stamp_rate: Decimal,
    dp: Decimal,
) -> ChargeBreakdown:
    transaction = money(abs(notional) * TXN_NSE)
    sebi = money(abs(notional) / CRORE * SEBI_PER_CRORE)
    bro = _brokerage(notional, brokerage)
    gst = money((bro + sebi + transaction) * GST_RATE)
    return ChargeBreakdown(
        brokerage=bro,
        stt=money(abs(notional) * stt_rate),
        transaction=transaction,
        sebi=sebi,
        gst=gst,
        stamp=money(abs(notional) * stamp_rate),
        dp=money(dp),
    )


def delivery_buy(notional: Decimal) -> ChargeBreakdown:
    return _breakdown(notional, brokerage=False, stt_rate=STT_DELIVERY, stamp_rate=STAMP_DELIVERY_BUY, dp=Decimal("0"))


def delivery_sell(notional: Decimal) -> ChargeBreakdown:
    return _breakdown(notional, brokerage=False, stt_rate=STT_DELIVERY, stamp_rate=Decimal("0"), dp=DP_PER_SELL)


def intraday_buy(notional: Decimal, *, brokerage: bool = True) -> ChargeBreakdown:
    return _breakdown(notional, brokerage=brokerage, stt_rate=Decimal("0"), stamp_rate=STAMP_INTRADAY_BUY, dp=Decimal("0"))


def intraday_sell(notional: Decimal, *, brokerage: bool = True) -> ChargeBreakdown:
    return _breakdown(notional, brokerage=brokerage, stt_rate=STT_INTRADAY_SELL, stamp_rate=Decimal("0"), dp=Decimal("0"))
