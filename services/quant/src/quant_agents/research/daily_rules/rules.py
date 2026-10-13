"""Pre-registered daily rules. Selection uses only closes at or before the decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median, pstdev

BOOK = Decimal("1000000")
NAME_CAP = Decimal("100000")
ENTRY_SLIPPAGE = Decimal("0.0005")
HORIZONS = (5, 10)
MOMENTUM_LOOKBACK = 20
SKIP_SESSIONS = 21
YEAR_LOOKBACK = 252
VOLATILITY_LOOKBACK = 20
MIN_12_1_NAMES = 20
ALWAYS_LONG_FRACTION = Decimal("0.90")
SCORE_UNTIL = date(2025, 12, 31)
BOOTSTRAP_DRAWS = 1000
BLOCK_LENGTH = 4
BOOTSTRAP_SEED = 0


@dataclass(frozen=True, slots=True)
class WindowResult:
    horizon: int
    rule: str
    sessions: int
    mean_return: Decimal
    mean_excess: Decimal
    lower: Decimal
    upper: Decimal
    average_selected_fraction: Decimal
    passed: bool


def momentum_20(history: tuple[Decimal, ...]) -> bool | None:
    """True when the latest close is above the close 20 sessions earlier."""
    if len(history) <= MOMENTUM_LOOKBACK:
        return None
    return history[-1] > history[-1 - MOMENTUM_LOOKBACK]


def momentum_12_1(history: tuple[Decimal, ...]) -> bool | None:
    """12-minus-1 signal. None means the name does not have a year of history."""
    if len(history) <= YEAR_LOOKBACK:
        return None
    recent = history[-1 - SKIP_SESSIONS]
    base = history[-1 - YEAR_LOOKBACK]
    return recent > base


def low_volatility_names(volatilities: dict[str, Decimal]) -> frozenset[str]:
    """Names at or below the cross-sectional median. One name is the median itself."""
    if not volatilities:
        return frozenset()
    cutoff = median(volatilities.values())
    return frozenset(symbol for symbol, value in volatilities.items() if value <= cutoff)


def realized_volatility(history: tuple[Decimal, ...]) -> Decimal | None:
    if len(history) <= VOLATILITY_LOOKBACK:
        return None
    returns = [
        history[index] / history[index - 1] - Decimal(1)
        for index in range(len(history) - VOLATILITY_LOOKBACK, len(history))
    ]
    if any(item <= Decimal("-1") for item in returns):
        return None
    return Decimal(str(pstdev([float(item) for item in returns])))
