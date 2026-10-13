"""SQLAlchemy tables. Import this module only from core_db."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String, UniqueConstraint
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


class PaperSessionRow(Base):
    __tablename__ = "paper_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    starting_cash: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    peak_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)


class TradeProposalRow(Base):
    __tablename__ = "trade_proposals"

    proposal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class RiskDecisionRow(Base):
    __tablename__ = "risk_decisions"

    risk_decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class OrderRow(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class ExecutionRow(Base):
    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class PositionRow(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("session_id", "instrument_id", name="uq_positions_session_instrument"),)

    position_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class PortfolioSnapshotRow(Base):
    __tablename__ = "portfolio_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestRunRow(Base):
    __tablename__ = "backtest_runs"

    backtest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestCostRow(Base):
    __tablename__ = "backtest_costs"

    backtest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestOrderRow(Base):
    __tablename__ = "backtest_orders"

    row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    backtest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestFillRow(Base):
    __tablename__ = "backtest_fills"

    row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    backtest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestPositionRow(Base):
    __tablename__ = "backtest_positions"

    row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    backtest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestPortfolioRow(Base):
    __tablename__ = "backtest_portfolio_snapshots"

    row_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    backtest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class BacktestMetricRow(Base):
    __tablename__ = "backtest_metrics"

    backtest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class CashReservationRow(Base):
    """One cash hold for an open BUY. Converted or released at most once."""

    __tablename__ = "cash_reservations"

    reservation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    applied_debit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChargeLedgerRow(Base):
    __tablename__ = "charge_ledger"
    __table_args__ = (UniqueConstraint("session_id", "order_id", "kind", name="uq_charge_ledger_kind"),)

    ledger_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_VALUE, nullable=False)


class DpChargeRow(Base):
    """One depository charge per scrip per trading day per session."""

    __tablename__ = "dp_charges"
    __table_args__ = (
        UniqueConstraint("session_id", "trading_day", "exchange", "symbol", name="uq_dp_scrip_day"),
    )

    dp_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trading_day: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False)


class EntryDayGateRow(Base):
    """Mutex row for one IST date. The entry count itself is derived from orders."""

    __tablename__ = "entry_day_gates"

    trading_day: Mapped[str] = mapped_column(String(10), primary_key=True)


class OrderBarCheckRow(Base):
    __tablename__ = "order_bar_checks"
    __table_args__ = (UniqueConstraint("order_id", "bar_key", name="uq_order_bar_check"),)

    check_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bar_key: Mapped[str] = mapped_column(String(64), nullable=False)


class RuntimeFlagRow(Base):
    __tablename__ = "runtime_flags"

    flag_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    paper_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    peak_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
