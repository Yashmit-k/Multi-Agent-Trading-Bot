"""Reference price, BUY limit, and OHLC limit-fill rules.

Fills are simulations. A five-minute bar does not establish queue priority,
volume at the limit, or the path inside the bar.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

from core_paper.trading_calendar import IST, EntryWindow

POLICY_VERSION = "cnc-limit-v1"
SELL_POLICY_VERSION = "cnc-sell-v1"
REFERENCE_RULE = "latest_completed_daily_close_v1"
PRODUCT_CNC = "CNC"
MAX_ENTRY_PREMIUM_BPS = Decimal("25")
FILL_MODEL = "ohlc_limit_simulation_v1"


def buy_limit(reference: Decimal, tick: Decimal, premium_bps: Decimal = MAX_ENTRY_PREMIUM_BPS) -> Decimal:
    if reference <= 0 or tick <= 0:
        raise ValueError("reference and tick must be positive")
    raw = reference * (Decimal("1") + premium_bps / Decimal("10000"))
    steps = (raw / tick).to_integral_value(rounding=ROUND_DOWN)
    return steps * tick


def reference_from(candles: list[Candle], decision_at: datetime) -> Candle | None:
    moment = decision_at.astimezone(timezone.utc)
    completed = [
        bar
        for bar in candles
        if _is_daily(bar) and bar.end.astimezone(timezone.utc) <= moment
    ]
    if not completed:
        return None
    return max(completed, key=lambda bar: bar.end.astimezone(timezone.utc))


def limit_fill_price(limit: Decimal, bar: Candle) -> Decimal | None:
    """BUY fill price at or below the limit, or None when the bar does not qualify."""
    if bar.open <= limit:
        return bar.open
    if bar.low < limit:
        return limit
    return None


def bar_eligible(bar: Candle, window: EntryWindow, activation: datetime, evaluation: datetime) -> bool:
    if not _is_five_minute(bar):
        return False
    start = bar.start.astimezone(IST)
    end = bar.end.astimezone(timezone.utc)
    if start.date() != window.session_date:
        return False
    if start.time() < window.entry_start or start.time() >= window.entry_end:
        return False
    if end > evaluation.astimezone(timezone.utc):
        return False
    if start.astimezone(timezone.utc) <= activation.astimezone(timezone.utc):
        return False
    if bar.end.astimezone(timezone.utc) - bar.start.astimezone(timezone.utc) != timedelta(minutes=5):
        return False
    return True


def _is_daily(bar: Candle) -> bool:
    return bar.timeframe == Timeframe.D1 or str(bar.timeframe) == Timeframe.D1.value


def _is_five_minute(bar: Candle) -> bool:
    return bar.timeframe == Timeframe.M5 or str(bar.timeframe) == Timeframe.M5.value
