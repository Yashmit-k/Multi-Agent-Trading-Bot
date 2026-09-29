"""SQLAlchemy tables. Import this module only from core_db."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class InstrumentRow(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_instruments_exchange_symbol"),)

    instrument_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_token: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class UniverseMembershipRow(Base):
    __tablename__ = "universe_membership"
    __table_args__ = (
        UniqueConstraint("instrument_id", "universe", "effective_from", name="uq_universe_membership"),
    )

    membership_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    universe: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketTickRow(Base):
    __tablename__ = "market_ticks"
    __table_args__ = (UniqueConstraint("instrument_id", "timestamp", name="uq_market_ticks"),)

    tick_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)


class CandleRow(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("instrument_id", "timeframe", "start", name="uq_candles"),)

    candle_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeatureRow(Base):
    __tablename__ = "features"

    instrument_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    features: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    source_data_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentSignalRow(Base):
    __tablename__ = "agent_signals"

    signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalRejectionRow(Base):
    __tablename__ = "signal_rejections"

    rejection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(String(512), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLogRow(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class SystemEventRow(Base):
    __tablename__ = "system_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)
