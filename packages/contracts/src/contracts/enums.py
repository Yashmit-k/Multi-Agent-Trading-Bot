"""Canonical vocabulary. These spellings are the only ones contracts accept."""

from enum import StrEnum


class AgentName(StrEnum):
    TECHNICAL = "technical"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    VOLUME = "volume"
    REGIME = "regime"
    ML = "ml"
    NEWS = "news"
    FUNDAMENTAL = "fundamental"
    VALUATION = "valuation"
    EARNINGS = "earnings"


class Horizon(StrEnum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    LONG_TERM = "LONG_TERM"


class TradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXPIRED_NO_DATA = "EXPIRED_NO_DATA"
    FAILED = "FAILED"


class RiskStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"
