"""Repository used by every other core service."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contracts.enums import Exchange, Timeframe
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.execution import Execution
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.market import Candle
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from contracts.schemas.risk_decision import RiskDecision
from contracts.schemas.trade_proposal import TradeProposal
from core_db.clock import as_utc
from core_db.models import (
    AgentSignalRow,
    AuditLogRow,
    CandleRow,
    ExecutionRow,
    FeatureRow,
    InstrumentRow,
    MarketTickRow,
    OrderRow,
    PortfolioSnapshotRow,
    PositionRow,
    RiskDecisionRow,
    RuntimeFlagRow,
    SignalRejectionRow,
    TradeProposalRow,
    UniverseMembershipRow,
)
from core_db.records import InstrumentRecord, TickRecord

NSE = Exchange.NSE.value


class NonNseWriteError(ValueError):
    """Phase 1–2 refuses to store BSE market data."""


class CoreRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert_instrument(
        self,
        *,
        symbol: str,
        exchange: str = NSE,
        trading_symbol: str | None = None,
        instrument_token: int | None = None,
        lot_size: int = 1,
        tick_size: Decimal = Decimal("0.05"),
    ) -> InstrumentRecord:
        symbol = symbol.strip().upper()
        exchange = exchange.strip().upper()
        if exchange != NSE:
            raise NonNseWriteError("Phase 1-2 ingestion is NSE-only")
        instrument_id = f"{exchange}:{symbol}"
        with self._session_factory() as session:
            row = session.get(InstrumentRow, instrument_id)
            if row is None:
                row = InstrumentRow(
                    instrument_id=instrument_id,
                    exchange=exchange,
                    symbol=symbol,
                    trading_symbol=trading_symbol or symbol,
                    instrument_token=instrument_token,
                    lot_size=lot_size,
                    tick_size=tick_size,
                )
                session.add(row)
            else:
                if instrument_token is not None:
                    row.instrument_token = instrument_token
                if trading_symbol:
                    row.trading_symbol = trading_symbol
            session.commit()
            session.refresh(row)
            return _instrument(row)

    def get_by_symbol(self, symbol: str, exchange: str = NSE) -> InstrumentRecord | None:
        symbol = symbol.strip().upper()
        with self._session_factory() as session:
            row = session.scalar(
                select(InstrumentRow).where(
                    InstrumentRow.symbol == symbol,
                    InstrumentRow.exchange == exchange.strip().upper(),
                )
            )
            return _instrument(row) if row else None

    def list_instruments(self, exchange: str = NSE) -> list[InstrumentRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(InstrumentRow).where(InstrumentRow.exchange == exchange).order_by(InstrumentRow.symbol)
            )
            return [_instrument(row) for row in rows]

    def add_membership(
        self,
        instrument_id: str,
        universe: str,
        effective_from: datetime,
        effective_to: datetime | None,
    ) -> None:
        membership_id = f"{instrument_id}:{universe}:{effective_from.date().isoformat()}"
        with self._session_factory() as session:
            if session.get(UniverseMembershipRow, membership_id) is None:
                session.add(
                    UniverseMembershipRow(
                        membership_id=membership_id,
                        instrument_id=instrument_id,
                        universe=universe,
                        effective_from=as_utc(effective_from),
                        effective_to=as_utc(effective_to) if effective_to else None,
                    )
                )
                session.commit()

    def remove_membership(self, instrument_id: str, universe: str, effective_from: datetime) -> None:
        membership_id = f"{instrument_id}:{universe}:{as_utc(effective_from).date().isoformat()}"
        with self._session_factory() as session:
            row = session.get(UniverseMembershipRow, membership_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def members_at(self, as_of: datetime, universe: str = "NIFTY50") -> list[InstrumentRecord]:
        moment = as_utc(as_of)
        with self._session_factory() as session:
            rows = session.scalars(select(UniverseMembershipRow).where(UniverseMembershipRow.universe == universe))
            instrument_ids = [
                row.instrument_id
                for row in rows
                if as_utc(row.effective_from) <= moment and (row.effective_to is None or as_utc(row.effective_to) > moment)
            ]
            if not instrument_ids:
                return []
            instruments = session.scalars(
                select(InstrumentRow).where(InstrumentRow.instrument_id.in_(instrument_ids)).order_by(InstrumentRow.symbol)
            )
            return [_instrument(row) for row in instruments]

    def insert_ticks(self, ticks: list[TickRecord]) -> int:
        written = 0
        with self._session_factory() as session:
            for tick in ticks:
                if tick.exchange != NSE:
                    raise NonNseWriteError("Phase 1-2 ingestion is NSE-only")
                tick_id = f"{tick.instrument_id}:{as_utc(tick.timestamp).isoformat()}"
                if session.get(MarketTickRow, tick_id) is not None:
                    continue
                session.add(
                    MarketTickRow(
                        tick_id=tick_id,
                        instrument_id=tick.instrument_id,
                        exchange=tick.exchange,
                        symbol=tick.symbol,
                        timestamp=as_utc(tick.timestamp),
                        price=tick.price,
                        volume=tick.volume,
                    )
                )
                written += 1
            session.commit()
        return written

    def ticks_until(self, instrument_id: str, as_of: datetime) -> list[TickRecord]:
        moment = as_utc(as_of)
        with self._session_factory() as session:
            rows = session.scalars(
                select(MarketTickRow)
                .where(MarketTickRow.instrument_id == instrument_id)
                .order_by(MarketTickRow.timestamp)
            )
            return [
                TickRecord(
                    instrument_id=row.instrument_id,
                    exchange=row.exchange,
                    symbol=row.symbol,
                    timestamp=as_utc(row.timestamp),
                    price=row.price,
                    volume=row.volume,
                )
                for row in rows
                if as_utc(row.timestamp) <= moment
            ]

    def upsert_candles(self, candles: list[Candle]) -> None:
        with self._session_factory() as session:
            for candle in candles:
                if candle.exchange.value != NSE:
                    raise NonNseWriteError("Phase 1-2 ingestion is NSE-only")
                instrument = session.scalar(
                    select(InstrumentRow).where(
                        InstrumentRow.symbol == candle.symbol,
                        InstrumentRow.exchange == NSE,
                    )
                )
                if instrument is None:
                    raise KeyError(candle.symbol)
                candle_id = f"{instrument.instrument_id}:{candle.timeframe.value}:{as_utc(candle.start).isoformat()}"
                row = session.get(CandleRow, candle_id)
                values = dict(
                    instrument_id=instrument.instrument_id,
                    exchange=NSE,
                    symbol=candle.symbol,
                    timeframe=candle.timeframe.value,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    start=as_utc(candle.start),
                    end=as_utc(candle.end),
                )
                if row is None:
                    session.add(CandleRow(candle_id=candle_id, **values))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
            session.commit()

    def candles_until(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        as_of: datetime,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        moment = as_utc(as_of)
        with self._session_factory() as session:
            rows = session.scalars(
                select(CandleRow)
                .where(CandleRow.symbol == symbol.strip().upper(), CandleRow.timeframe == parsed.value)
                .order_by(CandleRow.start)
            )
            candles = []
            for row in rows:
                bar_end = as_utc(row.end)
                bar_start = as_utc(row.start)
                if bar_end > moment:
                    continue
                if start is not None and bar_start < as_utc(start):
                    continue
                if end is not None and bar_end > as_utc(end):
                    continue
                candles.append(_candle(row))
            return candles

    def stored_candles(self, symbol: str, timeframe: Timeframe | str) -> list[Candle]:
        """Every row in the candle table for this symbol and timeframe, with no as_of filter."""
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        with self._session_factory() as session:
            rows = session.scalars(
                select(CandleRow)
                .where(
                    CandleRow.symbol == symbol.strip().upper(),
                    CandleRow.timeframe == parsed.value,
                )
                .order_by(CandleRow.start)
            )
            return [_candle(row) for row in rows]

    def upsert_feature(self, feature_set: FeatureSet, instrument_id: str) -> None:
        with self._session_factory() as session:
            key = (
                instrument_id,
                as_utc(feature_set.timestamp),
                feature_set.timeframe.value,
                feature_set.feature_version,
            )
            row = session.get(FeatureRow, key)
            payload = {
                "symbol": feature_set.symbol,
                "exchange": NSE,
                "features": dict(feature_set.features),
                "source_data_timestamp": as_utc(feature_set.source_data_timestamp),
            }
            if row is None:
                session.add(
                    FeatureRow(
                        instrument_id=key[0],
                        timestamp=key[1],
                        timeframe=key[2],
                        feature_version=key[3],
                        **payload,
                    )
                )
            else:
                row.features = payload["features"]
                row.source_data_timestamp = payload["source_data_timestamp"]
            session.commit()

    def feature_at(self, symbol: str, timeframe: Timeframe | str, as_of: datetime, feature_version: str) -> FeatureSet | None:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        moment = as_utc(as_of)
        with self._session_factory() as session:
            rows = session.scalars(
                select(FeatureRow).where(
                    FeatureRow.symbol == symbol.strip().upper(),
                    FeatureRow.timeframe == parsed.value,
                    FeatureRow.feature_version == feature_version,
                )
            )
            visible = [row for row in rows if as_utc(row.timestamp) <= moment and as_utc(row.source_data_timestamp) <= moment]
            if not visible:
                return None
            row = max(visible, key=lambda item: as_utc(item.timestamp))
            return FeatureSet(
                symbol=row.symbol,
                timestamp=as_utc(row.timestamp),
                timeframe=parsed,
                feature_version=row.feature_version,
                features=dict(row.features),
                source_data_timestamp=as_utc(row.source_data_timestamp),
            )

    def get_signal_payload(self, signal_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(AgentSignalRow, signal_id)
            return dict(row.payload) if row else None

    def list_signal_payloads(self) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(select(AgentSignalRow).order_by(AgentSignalRow.symbol, AgentSignalRow.signal_id))
            return [dict(row.payload) for row in rows]

    def insert_signal(self, signal_id: str, symbol: str, exchange: str, payload: dict, recorded_at: datetime) -> bool:
        with self._session_factory() as session:
            if session.get(AgentSignalRow, signal_id) is not None:
                return False
            session.add(
                AgentSignalRow(
                    signal_id=signal_id,
                    symbol=symbol,
                    exchange=exchange,
                    payload=payload,
                    recorded_at=as_utc(recorded_at),
                )
            )
            session.commit()
            return True

    def insert_rejection(self, rejection_id: str, signal_id: str, reason_code: str, detail: str, recorded_at: datetime) -> None:
        with self._session_factory() as session:
            session.add(
                SignalRejectionRow(
                    rejection_id=rejection_id,
                    signal_id=signal_id,
                    reason_code=reason_code,
                    detail=detail,
                    recorded_at=as_utc(recorded_at),
                )
            )
            session.commit()

    def rejection_count(self, signal_id: str) -> int:
        with self._session_factory() as session:
            rows = session.scalars(select(SignalRejectionRow).where(SignalRejectionRow.signal_id == signal_id))
            return len(list(rows))

    def insert_audit(
        self,
        audit_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        recorded_at: datetime,
        payload: dict,
    ) -> None:
        with self._session_factory() as session:
            session.add(
                AuditLogRow(
                    audit_id=audit_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    recorded_at=as_utc(recorded_at),
                    payload=payload,
                )
            )
            session.commit()

    def signal_count(self) -> int:
        with self._session_factory() as session:
            return len(list(session.scalars(select(AgentSignalRow))))

    def signals_for(self, symbol: str) -> list[AgentSignal]:
        name = symbol.strip().upper()
        with self._session_factory() as session:
            rows = session.scalars(select(AgentSignalRow).where(AgentSignalRow.symbol == name))
            return [AgentSignal.model_validate(dict(row.payload)) for row in rows]

    def latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle | None:
        """Latest stored bar for this symbol and timeframe. Stored bars are already complete."""
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(CandleRow).where(
                        CandleRow.symbol == symbol.strip().upper(),
                        CandleRow.timeframe == parsed.value,
                    )
                )
            )
        if not rows:
            return None
        return _candle(max(rows, key=lambda item: as_utc(item.end)))

    def insert_proposal(self, proposal: TradeProposal) -> bool:
        instrument = self._require_instrument(proposal.symbol)
        with self._session_factory() as session:
            if session.get(TradeProposalRow, proposal.proposal_id) is not None:
                return False
            session.add(
                TradeProposalRow(
                    proposal_id=proposal.proposal_id,
                    instrument_id=instrument.instrument_id,
                    symbol=proposal.symbol,
                    horizon=proposal.horizon.value,
                    as_of=as_utc(proposal.timestamp),
                    payload=proposal.model_dump(mode="json"),
                )
            )
            session.commit()
            return True

    def get_proposal(self, proposal_id: str) -> TradeProposal | None:
        with self._session_factory() as session:
            row = session.get(TradeProposalRow, proposal_id)
            return TradeProposal.model_validate(dict(row.payload)) if row else None

    def proposal_instrument_id(self, proposal_id: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(TradeProposalRow, proposal_id)
            return row.instrument_id if row else None

    def list_proposals(self) -> list[TradeProposal]:
        with self._session_factory() as session:
            rows = session.scalars(select(TradeProposalRow).order_by(TradeProposalRow.as_of, TradeProposalRow.proposal_id))
            return [TradeProposal.model_validate(dict(row.payload)) for row in rows]

    def insert_risk_decision(self, decision: RiskDecision) -> bool:
        proposal = self.get_proposal(decision.proposal_id)
        if proposal is None:
            raise KeyError(decision.proposal_id)
        instrument = self._require_instrument(proposal.symbol)
        with self._session_factory() as session:
            if session.scalar(select(RiskDecisionRow).where(RiskDecisionRow.proposal_id == decision.proposal_id)) is not None:
                return False
            session.add(
                RiskDecisionRow(
                    risk_decision_id=decision.risk_decision_id,
                    proposal_id=decision.proposal_id,
                    instrument_id=instrument.instrument_id,
                    payload=decision.model_dump(mode="json"),
                )
            )
            session.commit()
            return True

    def risk_for_proposal(self, proposal_id: str) -> RiskDecision | None:
        with self._session_factory() as session:
            row = session.scalar(select(RiskDecisionRow).where(RiskDecisionRow.proposal_id == proposal_id))
            return RiskDecision.model_validate(dict(row.payload)) if row else None

    def list_risk_decisions(self) -> list[RiskDecision]:
        with self._session_factory() as session:
            rows = session.scalars(select(RiskDecisionRow).order_by(RiskDecisionRow.risk_decision_id))
            return [RiskDecision.model_validate(dict(row.payload)) for row in rows]

    def insert_order(self, order: Order) -> bool:
        instrument = self._require_instrument(order.symbol)
        with self._session_factory() as session:
            if session.scalar(select(OrderRow).where(OrderRow.proposal_id == order.proposal_id)) is not None:
                return False
            session.add(
                OrderRow(
                    order_id=order.order_id,
                    proposal_id=order.proposal_id,
                    instrument_id=instrument.instrument_id,
                    payload=order.model_dump(mode="json"),
                )
            )
            session.commit()
            return True

    def order_for_proposal(self, proposal_id: str) -> Order | None:
        with self._session_factory() as session:
            row = session.scalar(select(OrderRow).where(OrderRow.proposal_id == proposal_id))
            return Order.model_validate(dict(row.payload)) if row else None

    def order_instrument_id(self, order_id: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(OrderRow, order_id)
            return row.instrument_id if row else None

    def list_orders(self) -> list[Order]:
        with self._session_factory() as session:
            rows = session.scalars(select(OrderRow).order_by(OrderRow.order_id))
            return [Order.model_validate(dict(row.payload)) for row in rows]

    def insert_execution(self, execution: Execution) -> bool:
        order = self._order_row_instrument(execution.order_id)
        if order is None:
            raise KeyError(execution.order_id)
        with self._session_factory() as session:
            if session.scalar(select(ExecutionRow).where(ExecutionRow.order_id == execution.order_id)) is not None:
                return False
            session.add(
                ExecutionRow(
                    execution_id=execution.execution_id,
                    order_id=execution.order_id,
                    instrument_id=order,
                    payload=execution.model_dump(mode="json"),
                )
            )
            session.commit()
            return True

    def list_executions(self) -> list[Execution]:
        with self._session_factory() as session:
            rows = session.scalars(select(ExecutionRow).order_by(ExecutionRow.execution_id))
            return [Execution.model_validate(dict(row.payload)) for row in rows]

    def execution_count(self) -> int:
        with self._session_factory() as session:
            return len(list(session.scalars(select(ExecutionRow))))

    def save_position(self, position: Position) -> str:
        instrument = self._require_instrument(position.symbol)
        payload = position.model_dump(mode="json")
        with self._session_factory() as session:
            row = session.get(PositionRow, instrument.instrument_id)
            if row is None:
                session.add(PositionRow(instrument_id=instrument.instrument_id, symbol=position.symbol, payload=payload))
            else:
                row.symbol = position.symbol
                row.payload = payload
            session.commit()
        return instrument.instrument_id

    def position_for(self, symbol: str) -> Position | None:
        instrument = self.get_by_symbol(symbol)
        if instrument is None:
            return None
        with self._session_factory() as session:
            row = session.get(PositionRow, instrument.instrument_id)
            return Position.model_validate(dict(row.payload)) if row else None

    def held_quantity(self, symbol: str) -> int:
        position = self.position_for(symbol)
        return 0 if position is None else position.quantity

    def list_positions(self) -> list[Position]:
        with self._session_factory() as session:
            rows = session.scalars(select(PositionRow).order_by(PositionRow.symbol))
            return [Position.model_validate(dict(row.payload)) for row in rows]

    def insert_snapshot(self, snapshot_id: str, snapshot: PortfolioSnapshot) -> None:
        with self._session_factory() as session:
            if session.get(PortfolioSnapshotRow, snapshot_id) is not None:
                return
            session.add(
                PortfolioSnapshotRow(
                    snapshot_id=snapshot_id,
                    timestamp=as_utc(snapshot.timestamp),
                    payload=snapshot.model_dump(mode="json"),
                )
            )
            session.commit()

    def latest_snapshot(self) -> PortfolioSnapshot | None:
        with self._session_factory() as session:
            rows = list(session.scalars(select(PortfolioSnapshotRow)))
        if not rows:
            return None
        row = max(rows, key=lambda item: (as_utc(item.timestamp), item.snapshot_id))
        return PortfolioSnapshot.model_validate(dict(row.payload))

    def cash_balance(self, starting_cash: Decimal) -> Decimal:
        snapshot = self.latest_snapshot()
        return starting_cash if snapshot is None else snapshot.cash

    def paper_running(self) -> bool:
        with self._session_factory() as session:
            row = session.get(RuntimeFlagRow, "paper")
            return True if row is None else bool(row.paper_running)

    def set_paper_running(self, running: bool) -> bool:
        with self._session_factory() as session:
            row = session.get(RuntimeFlagRow, "paper")
            if row is None:
                session.add(RuntimeFlagRow(flag_id="paper", paper_running=running, peak_equity=None))
            else:
                row.paper_running = running
            session.commit()
        return running

    def note_peak_equity(self, equity: Decimal) -> Decimal:
        with self._session_factory() as session:
            row = session.get(RuntimeFlagRow, "paper")
            if row is None:
                session.add(RuntimeFlagRow(flag_id="paper", paper_running=True, peak_equity=equity))
                session.commit()
                return equity
            peak = equity if row.peak_equity is None else max(row.peak_equity, equity)
            row.peak_equity = peak
            session.commit()
            return peak

    def _require_instrument(self, symbol: str) -> InstrumentRecord:
        instrument = self.get_by_symbol(symbol)
        if instrument is None:
            raise KeyError(symbol)
        return instrument

    def _order_row_instrument(self, order_id: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(OrderRow, order_id)
            return row.instrument_id if row else None


def _instrument(row: InstrumentRow) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=row.instrument_id,
        exchange=row.exchange,
        symbol=row.symbol,
        trading_symbol=row.trading_symbol,
        instrument_token=row.instrument_token,
        lot_size=row.lot_size,
        tick_size=row.tick_size,
    )


def _candle(row: CandleRow) -> Candle:
    return Candle(
        symbol=row.symbol,
        exchange=Exchange(row.exchange),
        timeframe=Timeframe(row.timeframe),
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        start=as_utc(row.start),
        end=as_utc(row.end),
    )
