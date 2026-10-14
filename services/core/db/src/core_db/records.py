"""Plain records returned by repositories. These are not SQLAlchemy models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InstrumentRecord:
    instrument_id: str
    exchange: str
    symbol: str
    trading_symbol: str
    instrument_token: int | None
    lot_size: int
    tick_size: Decimal


@dataclass(frozen=True, slots=True)
class TickRecord:
    instrument_id: str
    exchange: str
    symbol: str
    timestamp: datetime
    price: Decimal
    volume: int


@dataclass(frozen=True, slots=True)
class PaperSessionRecord:
    session_id: str
    status: str
    created_at: datetime
    closed_at: datetime | None
    starting_cash: Decimal | None
    peak_equity: Decimal | None


@dataclass(frozen=True, slots=True)
class MembershipRecord:
    instrument_id: str
    symbol: str
    exchange: str
    universe: str
    effective_from: datetime
    effective_to: datetime | None
