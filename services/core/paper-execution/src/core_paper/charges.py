"""Zerodha resident-individual equity charges.

Rates were read from Zerodha on 2026-10-12. This module does not fall back to
the flat research schedule. A schedule without a version, effective date,
access date, and source URL is refused.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

_CRORE = Decimal("10000000")
_PAISE = Decimal("0.01")
_RUPEE = Decimal("1")


class ChargeConfigError(ValueError):
    """The schedule cannot support an exact charge calculation."""


@dataclass(frozen=True, slots=True)
class EquityChargeSchedule:
    version: str
    broker: str
    account_category: str
    exchange: str
    segment: str
    effective_from: date | None
    effective_to: date | None
    accessed_on: date | None
    source_urls: tuple[str, ...]
    delivery_brokerage: Decimal
    intraday_brokerage_rate: Decimal
    intraday_brokerage_cap: Decimal
    delivery_stt_rate: Decimal
    intraday_stt_rate: Decimal
    transaction_rate: Decimal
    sebi_inr_per_crore: Decimal
    delivery_stamp_rate: Decimal
    intraday_stamp_rate: Decimal
    gst_rate: Decimal
    ipft_inr_per_crore: Decimal
    dp_inr_per_scrip: Decimal
    stt_rounding: str
    component_rounding: str

    def covers(self, day: date) -> bool:
        if self.effective_from is None or day < self.effective_from:
            return False
        if self.effective_to is not None and day > self.effective_to:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ChargeQuote:
    version: str
    classification: str
    total: Decimal
    lines: tuple[tuple[str, str], ...]


ZERODHA_EQUITY_RI = EquityChargeSchedule(
    version="zerodha-equity-ri-2026-10-12",
    broker="zerodha",
    account_category="resident_individual",
    exchange="NSE",
    segment="equity",
    effective_from=date(2026, 10, 12),
    effective_to=None,
    accessed_on=date(2026, 10, 12),
    source_urls=(
        "https://zerodha.com/charges/",
        "https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/how-is-the-securities-transaction-tax-stt-calculated",
        "https://support.zerodha.com/category/trading-and-markets/charts-and-orders/order/articles/what-does-cnc-mis-and-nrml-mean",
        "https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/brokerage-charged-for-partial-delivery",
    ),
    delivery_brokerage=Decimal("0"),
    intraday_brokerage_rate=Decimal("0.0003"),
    intraday_brokerage_cap=Decimal("20"),
    delivery_stt_rate=Decimal("0.001"),
    intraday_stt_rate=Decimal("0.00025"),
    transaction_rate=Decimal("0.0000307"),
    sebi_inr_per_crore=Decimal("10"),
    delivery_stamp_rate=Decimal("0.00015"),
    intraday_stamp_rate=Decimal("0.00003"),
    gst_rate=Decimal("0.18"),
    ipft_inr_per_crore=Decimal("0.01"),
    dp_inr_per_scrip=Decimal("15.34"),
    stt_rounding="nearest_rupee_half_up",
    component_rounding="paise_half_up",
)


def require_schedule(schedule: EquityChargeSchedule | None) -> EquityChargeSchedule:
    if schedule is None:
        raise ChargeConfigError("exact charges require a versioned schedule")
    if not schedule.version or schedule.effective_from is None or schedule.accessed_on is None or not schedule.source_urls:
        raise ChargeConfigError("exact charges require version, effective date, access date, and source URLs")
    if schedule.stt_rounding != "nearest_rupee_half_up" or schedule.component_rounding != "paise_half_up":
        raise ChargeConfigError("unsupported rounding policy")
    return schedule


def delivery_buy(notional: Decimal, schedule: EquityChargeSchedule, *, ceiling: bool = False) -> ChargeQuote:
    book = require_schedule(schedule)
    return _quote(book, "delivery_buy", notional, brokerage=book.delivery_brokerage, stt_rate=book.delivery_stt_rate, stamp_rate=book.delivery_stamp_rate, ceiling=ceiling)


def delivery_sell(notional: Decimal, schedule: EquityChargeSchedule, *, include_dp: bool, ceiling: bool = False) -> ChargeQuote:
    book = require_schedule(schedule)
    quote = _quote(book, "delivery_sell", notional, brokerage=book.delivery_brokerage, stt_rate=book.delivery_stt_rate, stamp_rate=Decimal("0"), ceiling=ceiling)
    if not include_dp:
        return quote
    lines = quote.lines + (("dp", str(book.dp_inr_per_scrip)),)
    total = quote.total + book.dp_inr_per_scrip
    return ChargeQuote(quote.version, quote.classification, total, lines)


def intraday_brokerage(notional: Decimal, schedule: EquityChargeSchedule) -> Decimal:
    book = require_schedule(schedule)
    raw = abs(notional) * book.intraday_brokerage_rate
    return min(raw, book.intraday_brokerage_cap).quantize(_PAISE, rounding=ROUND_HALF_UP)


def intraday_stt(average_price: Decimal, quantity: int, schedule: EquityChargeSchedule) -> Decimal:
    book = require_schedule(schedule)
    raw = average_price * quantity * book.intraday_stt_rate
    return raw.quantize(_RUPEE, rounding=ROUND_HALF_UP)


def reclassified_buy(
    buy_price: Decimal,
    bought_qty: int,
    sold_qty: int,
    schedule: EquityChargeSchedule,
) -> ChargeQuote:
    """Whole-order intraday brokerage when any quantity is squared the same day.

    STT and stamp follow the squared and unsold quantities. Brokerage does not
    get split across shares: Zerodha applies it to the executed order.
    """
    book = require_schedule(schedule)
    if sold_qty <= 0 or sold_qty > bought_qty:
        raise ChargeConfigError("same-day sold quantity must be within the buy")
    unsold = bought_qty - sold_qty
    full_notional = buy_price * bought_qty
    brokerage = intraday_brokerage(full_notional, book)
    stt = (buy_price * unsold * book.delivery_stt_rate).quantize(_RUPEE, rounding=ROUND_HALF_UP)
    stamp = _money(buy_price * unsold * book.delivery_stamp_rate, ceiling=False) + _money(
        buy_price * sold_qty * book.intraday_stamp_rate, ceiling=False
    )
    transaction = _money(full_notional * book.transaction_rate, ceiling=False)
    sebi = _money(full_notional * book.sebi_inr_per_crore / _CRORE, ceiling=False)
    ipft = _money(full_notional * book.ipft_inr_per_crore / _CRORE, ceiling=False)
    gst = _money((brokerage + sebi + transaction) * book.gst_rate, ceiling=False)
    gst_ipft = _money(ipft * book.gst_rate, ceiling=False)
    lines = (
        ("brokerage", str(brokerage)),
        ("stt", str(stt)),
        ("transaction", str(transaction)),
        ("sebi", str(sebi)),
        ("stamp", str(stamp)),
        ("ipft", str(ipft)),
        ("gst", str(gst)),
        ("gst_on_ipft", str(gst_ipft)),
    )
    total = brokerage + stt + transaction + sebi + stamp + ipft + gst + gst_ipft
    return ChargeQuote(book.version, "same_day_buy_reclass", total, lines)


def intraday_sell(
    sell_price: Decimal,
    quantity: int,
    buy_price: Decimal,
    schedule: EquityChargeSchedule,
    *,
    include_dp: bool,
) -> ChargeQuote:
    book = require_schedule(schedule)
    notional = sell_price * quantity
    brokerage = intraday_brokerage(notional, book)
    average = (buy_price + sell_price) / Decimal("2")
    stt = intraday_stt(average, quantity, book)
    transaction = _money(notional * book.transaction_rate, ceiling=False)
    sebi = _money(notional * book.sebi_inr_per_crore / _CRORE, ceiling=False)
    ipft = _money(notional * book.ipft_inr_per_crore / _CRORE, ceiling=False)
    gst = _money((brokerage + sebi + transaction) * book.gst_rate, ceiling=False)
    gst_ipft = _money(ipft * book.gst_rate, ceiling=False)
    total = brokerage + stt + transaction + sebi + ipft + gst + gst_ipft
    lines = (
        ("brokerage", str(brokerage)),
        ("stt", str(stt)),
        ("transaction", str(transaction)),
        ("sebi", str(sebi)),
        ("stamp", "0.00"),
        ("ipft", str(ipft)),
        ("gst", str(gst)),
        ("gst_on_ipft", str(gst_ipft)),
    )
    if include_dp:
        lines = lines + (("dp", str(book.dp_inr_per_scrip)),)
        total += book.dp_inr_per_scrip
    return ChargeQuote(book.version, "same_day_sell", total, lines)


def stamp_on(notional: Decimal, rate: Decimal, *, ceiling: bool = False) -> Decimal:
    return _money(abs(notional) * rate, ceiling=ceiling)


def reservation_buy(notional: Decimal, schedule: EquityChargeSchedule) -> Decimal:
    quote = delivery_buy(notional, schedule, ceiling=True)
    return notional + quote.total


def _quote(
    schedule: EquityChargeSchedule,
    classification: str,
    notional: Decimal,
    *,
    brokerage: Decimal,
    stt_rate: Decimal,
    stamp_rate: Decimal,
    ceiling: bool,
) -> ChargeQuote:
    turnover = abs(notional)
    brokerage_amount = brokerage.quantize(_PAISE, rounding=ROUND_HALF_UP)
    stt = (turnover * stt_rate).quantize(_RUPEE, rounding=ROUND_CEILING if ceiling else ROUND_HALF_UP)
    transaction = _money(turnover * schedule.transaction_rate, ceiling=ceiling)
    sebi = _money(turnover * schedule.sebi_inr_per_crore / _CRORE, ceiling=ceiling)
    stamp = _money(turnover * stamp_rate, ceiling=ceiling)
    ipft = _money(turnover * schedule.ipft_inr_per_crore / _CRORE, ceiling=ceiling)
    gst = _money((brokerage_amount + sebi + transaction) * schedule.gst_rate, ceiling=ceiling)
    gst_ipft = _money(ipft * schedule.gst_rate, ceiling=ceiling)
    lines = (
        ("brokerage", str(brokerage_amount)),
        ("stt", str(stt)),
        ("transaction", str(transaction)),
        ("sebi", str(sebi)),
        ("stamp", str(stamp)),
        ("ipft", str(ipft)),
        ("gst", str(gst)),
        ("gst_on_ipft", str(gst_ipft)),
    )
    total = brokerage_amount + stt + transaction + sebi + stamp + ipft + gst + gst_ipft
    return ChargeQuote(schedule.version, classification, total, lines)


def _money(value: Decimal, *, ceiling: bool) -> Decimal:
    return value.quantize(_PAISE, rounding=ROUND_CEILING if ceiling else ROUND_HALF_UP)
