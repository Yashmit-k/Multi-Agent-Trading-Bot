"""Repository used by every other core service."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
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
    BrokerSessionRow,
    BacktestCostRow,
    BacktestFillRow,
    BacktestMetricRow,
    BacktestOrderRow,
    BacktestPortfolioRow,
    BacktestPositionRow,
    BacktestRunRow,
    CandleRow,
    CashReservationRow,
    DailyEquityRow,
    ChargeLedgerRow,
    DpChargeRow,
    ExecutionRow,
    FeatureRow,
    InstrumentRow,
    MarketTickRow,
    EntryDayGateRow,
    OrderBarCheckRow,
    OrderRow,
    PaperSessionRow,
    PortfolioSnapshotRow,
    PositionRow,
    RiskDecisionRow,
    RuntimeFlagRow,
    SignalRejectionRow,
    SystemEventRow,
    TradeProposalRow,
    UserSettingRow,
    UserStrategyRow,
    UniverseMembershipRow,
)
from core_db.paper_sessions import (
    LEGACY_ASSESSMENT_AUDIT_ID,
    LEGACY_SESSION_ID,
    ActivePaperSessionError,
    AmbiguousPaperSessionError,
    ClosedPaperSessionError,
    LegacyAssessment,
    MissingPaperSessionError,
    assess_legacy_book,
    payload_dict,
)
from core_db.records import InstrumentRecord, PaperSessionRecord, TickRecord

NSE = Exchange.NSE.value
_ACTIVE = object()
_IST = ZoneInfo("Asia/Kolkata")
DAILY_ENTRY_LIMIT = 6
ENTRY_POLICY_VERSION = "cnc-limit-v1"


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

    def sync_membership(
        self,
        instrument_id: str,
        universe: str,
        effective_from: datetime,
        effective_to: datetime | None,
    ) -> None:
        """Insert a seed interval or update its close. Stored candles are not touched."""
        opened = as_utc(effective_from)
        closed = as_utc(effective_to) if effective_to else None
        membership_id = f"{instrument_id}:{universe}:{opened.date().isoformat()}"
        with self._session_factory() as session:
            row = session.get(UniverseMembershipRow, membership_id)
            if row is None:
                session.add(
                    UniverseMembershipRow(
                        membership_id=membership_id,
                        instrument_id=instrument_id,
                        universe=universe,
                        effective_from=opened,
                        effective_to=closed,
                    )
                )
            else:
                current = as_utc(row.effective_to) if row.effective_to else None
                if current != closed:
                    row.effective_to = closed
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

    def overlapping_memberships(
        self,
        start: datetime,
        end: datetime,
        universe: str = "NIFTY50",
    ) -> list[tuple[InstrumentRecord, datetime, datetime | None]]:
        """Members whose interval overlaps [start, end), with that interval's bounds."""
        window_start = as_utc(start)
        window_end = as_utc(end)
        found: list[tuple[InstrumentRecord, datetime, datetime | None]] = []
        with self._session_factory() as session:
            rows = session.scalars(
                select(UniverseMembershipRow).where(UniverseMembershipRow.universe == universe)
            )
            for row in rows:
                opened = as_utc(row.effective_from)
                closed = as_utc(row.effective_to) if row.effective_to else None
                if opened >= window_end or (closed is not None and closed <= window_start):
                    continue
                instrument = session.get(InstrumentRow, row.instrument_id)
                if instrument is not None:
                    found.append((_instrument(instrument), opened, closed))
        found.sort(key=lambda item: item[0].symbol)
        return found

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
        last: int | None = None,
    ) -> list[Candle]:
        """Completed bars with end <= as_of, oldest first. ``last`` keeps only the newest N."""
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        moment = as_utc(as_of)
        with self._session_factory() as session:
            query = (
                select(CandleRow)
                .where(CandleRow.symbol == symbol.strip().upper(), CandleRow.timeframe == parsed.value)
                .where(CandleRow.end <= moment)
            )
            if last is not None:
                newest = list(session.scalars(query.order_by(CandleRow.end.desc()).limit(last)))
                rows = sorted(newest, key=lambda row: as_utc(row.start))
            else:
                rows = session.scalars(query.order_by(CandleRow.start))
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

    def stored_candles(
        self, symbol: str, timeframe: Timeframe | str, *, start: datetime | None = None, end: datetime | None = None
    ) -> list[Candle]:
        """Stored rows for this symbol and timeframe, with no as_of filter.

        start/end narrow the read in SQL (bar start >= start, bar end <= end); without them every row is read.
        """
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        with self._session_factory() as session:
            query = select(CandleRow).where(
                CandleRow.symbol == symbol.strip().upper(),
                CandleRow.timeframe == parsed.value,
            )
            if start is not None:
                query = query.where(CandleRow.start >= as_utc(start))
            if end is not None:
                query = query.where(CandleRow.end <= as_utc(end))
            rows = session.scalars(query.order_by(CandleRow.start))
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

    def latest_signal_per_agent(self) -> list[dict]:
        """Newest stored signal for each agent: one indexed lookup per agent name.

        Uses ix_agent_signals_agent_recorded (migration 0013) on Postgres, instead of a group-by over every signal.
        """
        from contracts.enums import AgentName

        agent = AgentSignalRow.payload["agent_name"].as_string()
        latest: list[dict] = []
        with self._session_factory() as session:
            for name in sorted(item.value for item in AgentName):
                row = session.scalars(select(AgentSignalRow).where(agent == name).order_by(AgentSignalRow.recorded_at.desc()).limit(1)).first()
                if row is not None:
                    latest.append(dict(row.payload))
        return latest

    def recent_signal_payloads(self, limit: int = 500, symbol: str | None = None, agent_name: str | None = None) -> list[dict]:
        """Newest signals first, bounded, so the dashboard never pulls the whole table."""
        with self._session_factory() as session:
            query = select(AgentSignalRow).order_by(AgentSignalRow.recorded_at.desc())
            if symbol:
                query = query.where(AgentSignalRow.symbol == symbol.strip().upper())
            if agent_name:
                query = query.where(AgentSignalRow.payload["agent_name"].as_string() == agent_name)
            return [dict(row.payload) for row in session.scalars(query.limit(limit))]

    def signal_points_since(self, start: datetime, *, with_version: bool = False) -> list[tuple]:
        """(signal_id, agent, horizon, symbol, timestamp, signal, confidence[, agent_version]) since start, without metadata."""
        payload = AgentSignalRow.payload
        columns = [
            AgentSignalRow.signal_id,
            payload["agent_name"].as_string(),
            payload["horizon"].as_string(),
            AgentSignalRow.symbol,
            payload["timestamp"].as_string(),
            payload["signal"].as_float(),
            payload["confidence"].as_float(),
        ]
        if with_version:
            columns.append(payload["agent_version"].as_string())
        with self._session_factory() as session:
            rows = session.execute(select(*columns).where(AgentSignalRow.recorded_at >= start))
            return [tuple(row) for row in rows]

    def closes_since(self, timeframe: Timeframe | str, start: datetime) -> dict[str, list[tuple[datetime, float]]]:
        """(bar end, close) per symbol for bars ending at or after start, in one query, without building Candles."""
        value = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        out: dict[str, list[tuple[datetime, float]]] = {}
        with self._session_factory() as session:
            rows = session.execute(
                select(CandleRow.symbol, CandleRow.end, CandleRow.close).where(CandleRow.timeframe == value, CandleRow.end >= start)
            )
            for symbol, end, close in rows:
                out.setdefault(symbol, []).append((as_utc(end), float(close)))
        return out

    def ohlcv(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[tuple[datetime, datetime, float, float, float, float, float]]:
        """(start, end, open, high, low, close, volume) for bars ending in [start, end], oldest first, without building Candles."""
        value = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        with self._session_factory() as session:
            rows = session.execute(
                select(CandleRow.start, CandleRow.end, CandleRow.open, CandleRow.high, CandleRow.low, CandleRow.close, CandleRow.volume)
                .where(CandleRow.symbol == symbol, CandleRow.timeframe == value, CandleRow.end >= start, CandleRow.end <= end)
                .order_by(CandleRow.end)
            )
            return [(as_utc(b), as_utc(e), float(o), float(h), float(l), float(c), float(v)) for b, e, o, h, l, c, v in rows]

    def proposal_support_since(self, start: datetime) -> list[tuple[list[str], bool]]:
        """For each proposal since start: its supporting signal ids and whether risk approved it."""
        with self._session_factory() as session:
            rows = session.execute(
                select(TradeProposalRow.payload, RiskDecisionRow.payload)
                .outerjoin(RiskDecisionRow, RiskDecisionRow.proposal_id == TradeProposalRow.proposal_id)
                .where(TradeProposalRow.as_of >= start)
            )
            return [
                (list(proposal.get("supporting_signal_ids") or []), bool(decision) and decision.get("status") == "APPROVED")
                for proposal, decision in rows
            ]

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

    def save_broker_token(self, broker: str, token: str, issued_at: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(BrokerSessionRow, broker)
            if row is None:
                session.add(BrokerSessionRow(broker=broker, access_token=token, issued_at=as_utc(issued_at)))
            else:
                row.access_token = token
                row.issued_at = as_utc(issued_at)
            session.commit()

    def broker_token(self, broker: str, *, not_before: datetime) -> str | None:
        """The stored token if it was issued at or after ``not_before``."""
        with self._session_factory() as session:
            row = session.get(BrokerSessionRow, broker)
            if row is None or as_utc(row.issued_at) < as_utc(not_before):
                return None
            return row.access_token

    def broker_token_issued_at(self, broker: str) -> datetime | None:
        with self._session_factory() as session:
            row = session.get(BrokerSessionRow, broker)
            return None if row is None else as_utc(row.issued_at)

    def get_setting(self, key: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(UserSettingRow, key)
            if row is None:
                return None
            return {"payload": dict(row.payload), "updated_at": as_utc(row.updated_at).isoformat(), "updated_by": row.updated_by}

    def save_setting(self, key: str, payload: dict, *, updated_by: str, now: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(UserSettingRow, key)
            if row is None:
                session.add(UserSettingRow(key=key, payload=payload, updated_at=as_utc(now), updated_by=updated_by))
            else:
                row.payload, row.updated_at, row.updated_by = payload, as_utc(now), updated_by
            session.commit()

    def save_strategy(self, strategy_id: str, name: str, payload: dict, now: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(UserStrategyRow, strategy_id)
            if row is None:
                session.add(UserStrategyRow(strategy_id=strategy_id, name=name, payload=payload, created_at=as_utc(now), updated_at=as_utc(now)))
            else:
                row.name, row.payload, row.updated_at = name, payload, as_utc(now)
            session.commit()

    def list_strategies(self) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(select(UserStrategyRow).order_by(UserStrategyRow.updated_at.desc()))
            return [
                {"strategy_id": row.strategy_id, "name": row.name, "definition": dict(row.payload), "updated_at": as_utc(row.updated_at).isoformat()}
                for row in rows
            ]

    def get_strategy(self, strategy_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(UserStrategyRow, strategy_id)
            if row is None:
                return None
            return {"strategy_id": row.strategy_id, "name": row.name, "definition": dict(row.payload), "updated_at": as_utc(row.updated_at).isoformat()}

    def delete_strategy(self, strategy_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(UserStrategyRow, strategy_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    # Portfolio-manager reviews (core_db.reviews).
    def insert_review(self, request) -> bool:
        from core_db import reviews

        return reviews.insert(self._session_factory, request)

    def get_review(self, review_id: str) -> dict | None:
        from core_db import reviews

        return reviews.get(self._session_factory, review_id)

    def review_for_proposal(self, proposal_id: str) -> dict | None:
        from core_db import reviews

        return reviews.for_proposal(self._session_factory, proposal_id)

    def list_reviews(self, *, limit: int = 50, symbol: str | None = None) -> list[dict]:
        from core_db import reviews

        return reviews.recent(self._session_factory, limit=limit, symbol=symbol)

    def claim_reviews(self, now: datetime, *, limit: int = 2) -> list:
        from core_db import reviews

        return reviews.claim(self._session_factory, now, limit=limit)

    def append_review_step(self, review_id: str, step: dict, now: datetime) -> bool:
        from core_db import reviews

        return reviews.append_step(self._session_factory, review_id, step, now)

    def complete_review(self, review, now: datetime) -> bool:
        from core_db import reviews

        return reviews.complete(self._session_factory, review, now)

    def prune_history(self, now: datetime) -> dict[str, int]:
        """Age out bulky history (see core_db.retention); keeps everything trades depend on."""
        from core_db.retention import prune

        return prune(self._session_factory, now)

    def daily_equity_exists(self, session_id: str, trading_day: str) -> bool:
        with self._session_factory() as session:
            return session.get(DailyEquityRow, f"{session_id}:{trading_day}") is not None

    def insert_daily_equity(self, session_id: str, trading_day: str, written_at: datetime, payload: dict) -> bool:
        """Store one end-of-day book; an existing row for that session and day is kept, not overwritten."""
        with self._session_factory() as session:
            key = f"{session_id}:{trading_day}"
            if session.get(DailyEquityRow, key) is not None:
                return False
            session.add(DailyEquityRow(daily_id=key, session_id=session_id, trading_day=trading_day, written_at=as_utc(written_at), payload=payload))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True

    def list_daily_equity(self, session_id: str) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(select(DailyEquityRow).where(DailyEquityRow.session_id == session_id).order_by(DailyEquityRow.trading_day))
            return [{**dict(row.payload), "written_at": as_utc(row.written_at).isoformat()} for row in rows]

    def insert_system_event(self, event_id: str, event_type: str, recorded_at: datetime, payload: dict) -> bool:
        """Store one bus message. A repeated event_id is ignored and returns False."""
        with self._session_factory() as session:
            if session.get(SystemEventRow, event_id) is not None:
                return False
            session.add(SystemEventRow(event_id=event_id, event_type=event_type, recorded_at=as_utc(recorded_at), payload=payload))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return False
            return True

    def get_system_event(self, event_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(SystemEventRow, event_id)
            if row is None:
                return None
            return {"event_id": row.event_id, "event_type": row.event_type, "recorded_at": as_utc(row.recorded_at), "envelope": dict(row.payload)}

    def list_system_events(
        self,
        *,
        correlation_id: str | None = None,
        event_type: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Newest bus messages first. Filters on the stored envelope."""
        with self._session_factory() as session:
            query = select(SystemEventRow).order_by(SystemEventRow.recorded_at.desc(), SystemEventRow.event_id)
            if event_type is not None:
                query = query.where(SystemEventRow.event_type == event_type)
            if correlation_id is not None:
                query = query.where(SystemEventRow.payload["correlation_id"].as_string() == correlation_id)
            if source is None:
                query = query.limit(limit)
            rows = session.scalars(query)
            found: list[dict] = []
            for row in rows:
                envelope = dict(row.payload)
                if correlation_id is not None and envelope.get("correlation_id") != correlation_id:
                    continue
                if source is not None and envelope.get("source") != source and _agent_of(envelope) != source:
                    continue
                found.append({"event_id": row.event_id, "event_type": row.event_type, "recorded_at": as_utc(row.recorded_at), "envelope": envelope})
                if len(found) >= limit:
                    break
            return found

    def signal_count(self) -> int:
        with self._session_factory() as session:
            return len(list(session.scalars(select(AgentSignalRow))))

    def list_signals(self) -> list[AgentSignal]:
        with self._session_factory() as session:
            rows = session.scalars(select(AgentSignalRow))
            return [AgentSignal.model_validate(dict(row.payload)) for row in rows]

    def signals_for(self, symbol: str) -> list[AgentSignal]:
        name = symbol.strip().upper()
        with self._session_factory() as session:
            rows = session.scalars(select(AgentSignalRow).where(AgentSignalRow.symbol == name))
            return [AgentSignal.model_validate(dict(row.payload)) for row in rows]

    def latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle | None:
        """Latest stored bar for this symbol and timeframe. Stored bars are already complete."""
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        with self._session_factory() as session:
            row = session.scalars(
                select(CandleRow)
                .where(CandleRow.symbol == symbol.strip().upper(), CandleRow.timeframe == parsed.value)
                .order_by(CandleRow.end.desc())
                .limit(1)
            ).first()
        return None if row is None else _candle(row)

    def earliest_candle_end(self, symbol: str, timeframe: Timeframe | str) -> datetime | None:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        with self._session_factory() as session:
            value = session.scalar(
                select(func.min(CandleRow.end)).where(CandleRow.symbol == symbol.strip().upper(), CandleRow.timeframe == parsed.value)
            )
        return None if value is None else as_utc(value)

    def insert_proposal(self, proposal: TradeProposal) -> bool:
        instrument = self._require_instrument(proposal.symbol)
        session_id = self._trading_session_id()
        with self._session_factory() as session:
            if session.get(TradeProposalRow, proposal.proposal_id) is not None:
                return False
            session.add(
                TradeProposalRow(
                    proposal_id=proposal.proposal_id,
                    session_id=session_id,
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

    def list_proposals(self, session_id: str | None | object = _ACTIVE) -> list[TradeProposal]:
        with self._session_factory() as session:
            rows = session.scalars(
                self._scoped(select(TradeProposalRow), TradeProposalRow.session_id, session_id).order_by(
                    TradeProposalRow.as_of, TradeProposalRow.proposal_id
                )
            )
            return [TradeProposal.model_validate(dict(row.payload)) for row in rows]

    def insert_risk_decision(self, decision: RiskDecision) -> bool:
        proposal = self.get_proposal(decision.proposal_id)
        if proposal is None:
            raise KeyError(decision.proposal_id)
        instrument = self._require_instrument(proposal.symbol)
        session_id = self._session_id_for_proposal(decision.proposal_id)
        with self._session_factory() as session:
            if session.scalar(select(RiskDecisionRow).where(RiskDecisionRow.proposal_id == decision.proposal_id)) is not None:
                return False
            session.add(
                RiskDecisionRow(
                    risk_decision_id=decision.risk_decision_id,
                    session_id=session_id,
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

    def list_risk_decisions(self, session_id: str | None | object = _ACTIVE) -> list[RiskDecision]:
        with self._session_factory() as session:
            rows = session.scalars(
                self._scoped(select(RiskDecisionRow), RiskDecisionRow.session_id, session_id).order_by(
                    RiskDecisionRow.risk_decision_id
                )
            )
            return [RiskDecision.model_validate(dict(row.payload)) for row in rows]

    def insert_order(self, order: Order) -> bool:
        instrument = self._require_instrument(order.symbol)
        session_id = self._session_id_for_proposal(order.proposal_id)
        with self._session_factory() as session:
            if session.scalar(select(OrderRow).where(OrderRow.proposal_id == order.proposal_id)) is not None:
                return False
            session.add(
                OrderRow(
                    order_id=order.order_id,
                    session_id=session_id,
                    proposal_id=order.proposal_id,
                    instrument_id=instrument.instrument_id,
                    payload=order.model_dump(mode="json"),
                )
            )
            session.commit()
            return True

    def save_order(self, order: Order) -> None:
        with self._session_factory() as session:
            row = session.get(OrderRow, order.order_id)
            if row is None:
                return
            row.payload = order.model_dump(mode="json")
            session.commit()

    def commit_policy_order(self, order: Order, reserve: Decimal | None, *, daily_limit: int = DAILY_ENTRY_LIMIT) -> bool:
        """Insert one order and, for a BUY hold, its cash reservation in one transaction.

        A new CNC entry is counted under its IST calendar date before the insert.
        The gate row and the order commit together, so a concurrent insert cannot
        pass the same daily count.
        """
        instrument = self._require_instrument(order.symbol)
        session_id = self._session_id_for_proposal(order.proposal_id)
        payload = order.model_dump(mode="json")
        with self._session_factory() as session:
            counted = _counted_entry(payload)
            if counted:
                _lock_entry_day(session, _ist_day(order.created_at))
            if session.scalar(select(OrderRow).where(OrderRow.proposal_id == order.proposal_id)) is not None:
                return False
            if counted and _entry_count(session, _ist_day(order.created_at)) >= daily_limit:
                return False
            session.add(
                OrderRow(
                    order_id=order.order_id,
                    session_id=session_id,
                    proposal_id=order.proposal_id,
                    instrument_id=instrument.instrument_id,
                    payload=payload,
                )
            )
            if reserve is not None:
                session.add(
                    CashReservationRow(
                        reservation_id=order.order_id,
                        session_id=session_id,
                        order_id=order.order_id,
                        amount=reserve,
                        status="HELD",
                        applied_debit=None,
                        created_at=as_utc(order.created_at),
                        updated_at=as_utc(order.updated_at),
                    )
                )
            session.commit()
            return True

    def daily_entry_count(self, moment: datetime) -> int:
        """CNC entry orders whose creation instant falls on this IST date, across sessions."""
        with self._session_factory() as session:
            return _entry_count(session, _ist_day(moment))

    def dp_claimed(self, trading_day: str, exchange: str, symbol: str, session_id: str | None | object = _ACTIVE) -> bool:
        target = self._resolve_session_id(session_id)
        if target is None:
            return False
        with self._session_factory() as session:
            row = session.scalar(
                select(DpChargeRow).where(
                    DpChargeRow.session_id == target,
                    DpChargeRow.trading_day == trading_day,
                    DpChargeRow.exchange == exchange,
                    DpChargeRow.symbol == symbol.strip().upper(),
                )
            )
            return row is not None

    def commit_policy_transition(
        self,
        order: Order,
        *,
        release: bool = False,
        convert_amount: Decimal | None = None,
        execution: Execution | None = None,
        position: Position | None = None,
        clear_symbol: str | None = None,
        snapshot: PortfolioSnapshot | None = None,
        snapshot_id: str | None = None,
        bar_keys: list[str] | None = None,
        ledger: list[dict] | None = None,
        dp: dict | None = None,
        fee_updates: list[tuple[str, dict]] | None = None,
    ) -> bool:
        """Persist an order transition once. A repeated bar key or fill does not apply again."""
        session_id = self._session_id_for_order(order.order_id)
        keys = list(bar_keys or [])
        with self._session_factory() as session:
            if execution is not None and session.scalar(
                select(ExecutionRow).where(ExecutionRow.order_id == order.order_id)
            ) is not None:
                return False
            if keys and session.scalar(
                select(OrderBarCheckRow).where(
                    OrderBarCheckRow.order_id == order.order_id,
                    OrderBarCheckRow.bar_key.in_(keys),
                )
            ) is not None:
                return False
            row = session.get(OrderRow, order.order_id)
            if row is None or row.session_id != session_id:
                return False
            row.payload = order.model_dump(mode="json")
            for key in keys:
                session.add(OrderBarCheckRow(check_id=f"{order.order_id}:{key}", order_id=order.order_id, bar_key=key))
            reservation = session.scalar(select(CashReservationRow).where(CashReservationRow.order_id == order.order_id))
            if release and reservation is not None and reservation.status == "HELD":
                reservation.status = "RELEASED"
                reservation.updated_at = as_utc(order.updated_at)
            if convert_amount is not None and reservation is not None and reservation.status == "HELD":
                reservation.status = "CONVERTED"
                reservation.applied_debit = convert_amount
                reservation.updated_at = as_utc(order.updated_at)
            if execution is not None:
                instrument_id = row.instrument_id
                session.add(
                    ExecutionRow(
                        execution_id=execution.execution_id,
                        session_id=session_id,
                        order_id=order.order_id,
                        instrument_id=instrument_id,
                        payload=execution.model_dump(mode="json"),
                    )
                )
            for execution_id, payload in fee_updates or []:
                fill_row = session.get(ExecutionRow, execution_id)
                if fill_row is not None and fill_row.session_id == session_id:
                    fill_row.payload = payload
            if position is not None:
                instrument = session.scalar(
                    select(InstrumentRow).where(InstrumentRow.symbol == position.symbol, InstrumentRow.exchange == "NSE")
                )
                if instrument is None:
                    return False
                current = self._position_row(session, session_id, instrument.instrument_id)
                payload = position.model_dump(mode="json")
                if current is None:
                    session.add(
                        PositionRow(
                            position_id=f"{session_id}:{instrument.instrument_id}",
                            session_id=session_id,
                            instrument_id=instrument.instrument_id,
                            symbol=position.symbol,
                            payload=payload,
                        )
                    )
                else:
                    current.payload = payload
                    current.symbol = position.symbol
            if clear_symbol is not None:
                instrument = session.scalar(
                    select(InstrumentRow).where(InstrumentRow.symbol == clear_symbol, InstrumentRow.exchange == "NSE")
                )
                current = None if instrument is None else self._position_row(session, session_id, instrument.instrument_id)
                if current is not None:
                    session.delete(current)
            if snapshot is not None and snapshot_id is not None and session.get(PortfolioSnapshotRow, snapshot_id) is None:
                session.add(
                    PortfolioSnapshotRow(
                        snapshot_id=snapshot_id,
                        session_id=session_id,
                        timestamp=as_utc(snapshot.timestamp),
                        payload=snapshot.model_dump(mode="json"),
                    )
                )
            for item in ledger or []:
                if session.scalar(
                    select(ChargeLedgerRow).where(
                        ChargeLedgerRow.session_id == session_id,
                        ChargeLedgerRow.order_id == order.order_id,
                        ChargeLedgerRow.kind == item["kind"],
                    )
                ) is None:
                    session.add(
                        ChargeLedgerRow(
                            ledger_id=item["ledger_id"],
                            session_id=session_id,
                            order_id=order.order_id,
                            execution_id=item.get("execution_id"),
                            kind=item["kind"],
                            amount=item["amount"],
                            payload=item["payload"],
                        )
                    )
            if dp is not None and session.scalar(
                select(DpChargeRow).where(
                    DpChargeRow.session_id == session_id,
                    DpChargeRow.trading_day == dp["trading_day"],
                    DpChargeRow.exchange == dp["exchange"],
                    DpChargeRow.symbol == dp["symbol"],
                )
            ) is None:
                session.add(
                    DpChargeRow(
                        dp_id=dp["dp_id"],
                        session_id=session_id,
                        trading_day=dp["trading_day"],
                        exchange=dp["exchange"],
                        symbol=dp["symbol"],
                        amount=dp["amount"],
                        execution_id=dp["execution_id"],
                    )
                )
            session.commit()
            return True

    def clear_position(self, symbol: str) -> None:
        instrument = self.get_by_symbol(symbol)
        book = self.active_paper_session()
        if instrument is None or book is None:
            return
        with self._session_factory() as session:
            row = self._position_row(session, book.session_id, instrument.instrument_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def kill_switch_armed(self) -> bool:
        with self._session_factory() as session:
            row = session.get(RuntimeFlagRow, "kill")
            return bool(row and row.paper_running)

    def set_kill_switch(self, armed: bool) -> bool:
        with self._session_factory() as session:
            row = session.get(RuntimeFlagRow, "kill")
            if row is None:
                session.add(RuntimeFlagRow(flag_id="kill", paper_running=armed, peak_equity=None))
            else:
                row.paper_running = armed
            session.commit()
        return armed

    def order_for_proposal(self, proposal_id: str) -> Order | None:
        with self._session_factory() as session:
            row = session.scalar(select(OrderRow).where(OrderRow.proposal_id == proposal_id))
            return Order.model_validate(dict(row.payload)) if row else None

    def order_instrument_id(self, order_id: str) -> str | None:
        with self._session_factory() as session:
            row = session.get(OrderRow, order_id)
            return row.instrument_id if row else None

    def list_orders(self, session_id: str | None | object = _ACTIVE) -> list[Order]:
        with self._session_factory() as session:
            rows = session.scalars(
                self._scoped(select(OrderRow), OrderRow.session_id, session_id).order_by(OrderRow.order_id)
            )
            return [Order.model_validate(dict(row.payload)) for row in rows]

    def insert_execution(self, execution: Execution) -> bool:
        order = self._order_row_instrument(execution.order_id)
        if order is None:
            raise KeyError(execution.order_id)
        session_id = self._session_id_for_order(execution.order_id)
        with self._session_factory() as session:
            if session.scalar(select(ExecutionRow).where(ExecutionRow.order_id == execution.order_id)) is not None:
                return False
            session.add(
                ExecutionRow(
                    execution_id=execution.execution_id,
                    session_id=session_id,
                    order_id=execution.order_id,
                    instrument_id=order,
                    payload=execution.model_dump(mode="json"),
                )
            )
            session.commit()
            return True

    def list_executions(self, session_id: str | None | object = _ACTIVE) -> list[Execution]:
        with self._session_factory() as session:
            rows = session.scalars(
                self._scoped(select(ExecutionRow), ExecutionRow.session_id, session_id).order_by(ExecutionRow.execution_id)
            )
            return [Execution.model_validate(dict(row.payload)) for row in rows]

    def execution_count(self) -> int:
        with self._session_factory() as session:
            return len(list(session.scalars(select(ExecutionRow))))

    def save_position(self, position: Position) -> str:
        instrument = self._require_instrument(position.symbol)
        session_id = self._trading_session_id()
        payload = position.model_dump(mode="json")
        position_id = f"{session_id}:{instrument.instrument_id}"
        with self._session_factory() as session:
            row = self._position_row(session, session_id, instrument.instrument_id)
            if row is None:
                session.add(
                    PositionRow(
                        position_id=position_id,
                        session_id=session_id,
                        instrument_id=instrument.instrument_id,
                        symbol=position.symbol,
                        payload=payload,
                    )
                )
            else:
                row.symbol = position.symbol
                row.payload = payload
            session.commit()
        return instrument.instrument_id

    def position_for(self, symbol: str, session_id: str | None | object = _ACTIVE) -> Position | None:
        instrument = self.get_by_symbol(symbol)
        target = self._resolve_session_id(session_id)
        if instrument is None or target is None and session_id is _ACTIVE:
            return None
        with self._session_factory() as session:
            if target is None:
                row = session.scalar(
                    select(PositionRow).where(
                        PositionRow.symbol == instrument.symbol,
                        PositionRow.session_id.is_(None),
                    )
                )
            else:
                row = self._position_row(session, target, instrument.instrument_id)
            return Position.model_validate(dict(row.payload)) if row else None

    def held_quantity(self, symbol: str, session_id: str | None | object = _ACTIVE) -> int:
        position = self.position_for(symbol, session_id)
        return 0 if position is None else position.quantity

    def list_positions(self, session_id: str | None | object = _ACTIVE) -> list[Position]:
        with self._session_factory() as session:
            rows = session.scalars(
                self._scoped(select(PositionRow), PositionRow.session_id, session_id).order_by(PositionRow.symbol)
            )
            return [Position.model_validate(dict(row.payload)) for row in rows]

    def insert_snapshot(self, snapshot_id: str, snapshot: PortfolioSnapshot) -> None:
        session_id = self._trading_session_id()
        with self._session_factory() as session:
            if session.get(PortfolioSnapshotRow, snapshot_id) is not None:
                return
            session.add(
                PortfolioSnapshotRow(
                    snapshot_id=snapshot_id,
                    session_id=session_id,
                    timestamp=as_utc(snapshot.timestamp),
                    payload=snapshot.model_dump(mode="json"),
                )
            )
            session.commit()

    def latest_snapshot(self, session_id: str | None | object = _ACTIVE) -> PortfolioSnapshot | None:
        with self._session_factory() as session:
            rows = list(session.scalars(self._scoped(select(PortfolioSnapshotRow), PortfolioSnapshotRow.session_id, session_id)))
        if not rows:
            return None
        row = max(rows, key=lambda item: (as_utc(item.timestamp), item.snapshot_id))
        return PortfolioSnapshot.model_validate(dict(row.payload))

    def open_reservation_total(self, session_id: str | None | object = _ACTIVE) -> Decimal:
        target = self._resolve_session_id(session_id)
        if session_id is _ACTIVE and target is None:
            return Decimal("0")
        with self._session_factory() as session:
            rows = session.scalars(select(CashReservationRow).where(CashReservationRow.status == "HELD"))
            return sum(
                (row.amount for row in rows if target is None or row.session_id == target),
                Decimal("0"),
            )

    def available_cash(self, starting_cash: Decimal, session_id: str | None | object = _ACTIVE) -> Decimal:
        return self.cash_balance(starting_cash, session_id) - self.open_reservation_total(session_id)

    def reserved_sell_quantity(self, symbol: str, session_id: str | None | object = _ACTIVE) -> int:
        from contracts.enums import OrderStatus, Side

        name = symbol.strip().upper()
        return sum(
            order.quantity
            for order in self.list_orders(session_id)
            if order.symbol == name and order.side == Side.SELL and order.status == OrderStatus.OPEN
        )

    def completed_daily(self, symbol: str, as_of: datetime) -> tuple[Candle, str] | None:
        moment = as_utc(as_of)
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(CandleRow).where(
                        CandleRow.symbol == symbol.strip().upper(),
                        CandleRow.timeframe == Timeframe.D1.value,
                    )
                )
            )
        done = [row for row in rows if as_utc(row.end) <= moment]
        if not done:
            return None
        row = max(done, key=lambda item: as_utc(item.end))
        return _candle(row), row.candle_id

    def bar_already_checked(self, order_id: str, bar_key: str) -> bool:
        with self._session_factory() as session:
            found = session.scalar(
                select(OrderBarCheckRow).where(
                    OrderBarCheckRow.order_id == order_id,
                    OrderBarCheckRow.bar_key == bar_key,
                )
            )
            return found is not None

    def cash_balance(self, starting_cash: Decimal, session_id: str | None | object = _ACTIVE) -> Decimal:
        if session_id is _ACTIVE:
            book = self.active_paper_session()
            if book is None:
                return starting_cash
            target: str | None = book.session_id
            base = book.starting_cash if book.starting_cash is not None else starting_cash
        elif session_id is None:
            target = None
            base = starting_cash
        else:
            book = self.paper_session(str(session_id))
            if book is None:
                raise KeyError(session_id)
            target = book.session_id
            base = book.starting_cash if book.starting_cash is not None else starting_cash
        # Cash is derived from the fill ledger, not from the latest snapshot: several fills on the same
        # 5-minute bar share a snapshot timestamp, so "latest snapshot" is ambiguous and lost debits.
        return base + self._fill_cash_delta(target)

    def _fill_cash_delta(self, session_id: str | None) -> Decimal:
        with self._session_factory() as session:
            executions = list(session.scalars(select(ExecutionRow).where(ExecutionRow.session_id == session_id)))
            if not executions:
                return Decimal("0")
            orders = {row.order_id: row for row in session.scalars(select(OrderRow).where(OrderRow.order_id.in_([row.order_id for row in executions])))}
        delta = Decimal("0")
        for row in executions:
            execution = Execution.model_validate(dict(row.payload))
            order = orders.get(row.order_id)
            side = None if order is None else str(order.payload.get("side"))
            notional = execution.price * execution.quantity
            if side == "BUY":
                delta -= notional + execution.fees
            elif side == "SELL":
                delta += notional - execution.fees
        return delta

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
        book = self.active_paper_session()
        if book is not None:
            with self._session_factory() as session:
                row = session.get(PaperSessionRow, book.session_id)
                if row is None:
                    return equity
                peak = equity if row.peak_equity is None else max(row.peak_equity, equity)
                row.peak_equity = peak
                session.commit()
                return peak
        with self._session_factory() as session:
            has_session = session.scalar(select(PaperSessionRow.session_id).limit(1))
            if has_session is not None:
                return equity
            row = session.get(RuntimeFlagRow, "paper")
            if row is None:
                session.add(RuntimeFlagRow(flag_id="paper", paper_running=True, peak_equity=equity))
                session.commit()
                return equity
            peak = equity if row.peak_equity is None else max(row.peak_equity, equity)
            row.peak_equity = peak
            session.commit()
            return peak

    def open_paper_session(self, starting_cash: Decimal, *, created_at: datetime | None = None) -> PaperSessionRecord:
        if starting_cash <= 0:
            raise ValueError("starting cash must be positive")
        if self.active_paper_session() is not None:
            raise ActivePaperSessionError("an active paper session already exists")
        moment = as_utc(created_at or datetime.now(timezone.utc))
        session_id = uuid.uuid4().hex
        with self._session_factory() as session:
            session.add(
                PaperSessionRow(
                    session_id=session_id,
                    status="active",
                    created_at=moment,
                    closed_at=None,
                    starting_cash=starting_cash,
                    peak_equity=starting_cash,
                )
            )
            session.commit()
        opened = self.paper_session(session_id)
        if opened is None:
            raise MissingPaperSessionError(session_id)
        return opened

    def close_paper_session(self, session_id: str, *, closed_at: datetime | None = None) -> PaperSessionRecord:
        moment = as_utc(closed_at or datetime.now(timezone.utc))
        with self._session_factory() as session:
            row = session.get(PaperSessionRow, session_id)
            if row is None:
                raise KeyError(session_id)
            if row.status != "active":
                raise ClosedPaperSessionError(session_id)
            row.status = "closed"
            row.closed_at = moment
            session.commit()
        closed = self.paper_session(session_id)
        if closed is None:
            raise KeyError(session_id)
        return closed

    def paper_session(self, session_id: str) -> PaperSessionRecord | None:
        with self._session_factory() as session:
            row = session.get(PaperSessionRow, session_id)
            return _paper_session(row) if row else None

    def list_paper_sessions(self) -> list[PaperSessionRecord]:
        with self._session_factory() as session:
            rows = session.scalars(select(PaperSessionRow).order_by(PaperSessionRow.created_at, PaperSessionRow.session_id))
            return [_paper_session(row) for row in rows]

    def active_paper_session(self) -> PaperSessionRecord | None:
        with self._session_factory() as session:
            rows = list(session.scalars(select(PaperSessionRow).where(PaperSessionRow.status == "active")))
        if len(rows) > 1:
            raise AmbiguousPaperSessionError("more than one paper session is active")
        return _paper_session(rows[0]) if rows else None

    def assign_legacy_paper_session(self, *, now: datetime | None = None) -> str | None:
        """Attach rows that have no session to the deterministic legacy session.

        Existing rows are updated in place. They are not copied onto whatever
        session is already active. Returns None when there is nothing to attach.
        """
        moment = as_utc(now or datetime.now(timezone.utc))
        tables = (TradeProposalRow, RiskDecisionRow, OrderRow, ExecutionRow, PositionRow, PortfolioSnapshotRow)
        with self._session_factory() as session:
            has_unassigned = any(
                session.scalars(select(table).where(table.session_id.is_(None)).limit(1)).first() is not None
                for table in tables
            )
            existing = session.get(PaperSessionRow, LEGACY_SESSION_ID)
            if not has_unassigned:
                return LEGACY_SESSION_ID if existing is not None else None
            if existing is None:
                assessment = _legacy_assessment(session)
                other_active = any(
                    row.session_id != LEGACY_SESSION_ID
                    for row in session.scalars(select(PaperSessionRow).where(PaperSessionRow.status == "active"))
                )
                status = "closed" if other_active or not assessment.consistent else "active"
                diagnostics = list(assessment.diagnostics)
                if other_active:
                    diagnostics.append("legacy session stored closed because another session is already active")
                session.add(
                    PaperSessionRow(
                        session_id=LEGACY_SESSION_ID,
                        status=status,
                        created_at=moment,
                        closed_at=moment if status == "closed" else None,
                        starting_cash=assessment.starting_cash if assessment.consistent else None,
                        peak_equity=assessment.peak_equity if assessment.consistent else None,
                    )
                )
                session.add(
                    AuditLogRow(
                        audit_id=LEGACY_ASSESSMENT_AUDIT_ID,
                        action="legacy_paper_session",
                        entity_type="paper_session",
                        entity_id=LEGACY_SESSION_ID,
                        recorded_at=moment,
                        payload={
                            "consistent": assessment.consistent,
                            "starting_cash": _decimal_text(assessment.starting_cash),
                            "peak_equity": _decimal_text(assessment.peak_equity),
                            "peak_source": assessment.peak_source,
                            "peak_complete": assessment.peak_complete,
                            "diagnostics": diagnostics,
                        },
                    )
                )
            for table in (TradeProposalRow, RiskDecisionRow, OrderRow, ExecutionRow, PortfolioSnapshotRow):
                for row in session.scalars(select(table).where(table.session_id.is_(None))):
                    row.session_id = LEGACY_SESSION_ID
            for row in list(session.scalars(select(PositionRow).where(PositionRow.session_id.is_(None)))):
                payload = row.payload
                symbol = row.symbol
                instrument_id = row.instrument_id
                session.delete(row)
                session.flush()
                session.add(
                    PositionRow(
                        position_id=f"{LEGACY_SESSION_ID}:{instrument_id}",
                        session_id=LEGACY_SESSION_ID,
                        instrument_id=instrument_id,
                        symbol=symbol,
                        payload=payload,
                    )
                )
            session.commit()
        return LEGACY_SESSION_ID

    def insert_backtest(self, backtest_id: str, snapshot_id: str, payload: dict) -> None:
        with self._session_factory() as session:
            session.add(
                BacktestRunRow(
                    backtest_id=backtest_id,
                    snapshot_id=snapshot_id,
                    created_at=datetime.now(timezone.utc),
                    payload=payload,
                )
            )
            session.commit()
        self._write_backtest_children(backtest_id, payload)

    def _write_backtest_children(self, backtest_id: str, payload: dict) -> None:
        try:
            with self._session_factory() as session:
                session.add(BacktestCostRow(backtest_id=backtest_id, payload=payload.get("cost_schedule") or {}))
                session.add(BacktestMetricRow(backtest_id=backtest_id, payload=payload.get("metrics") or {}))
                for index, item in enumerate(payload.get("trades") or []):
                    session.add(BacktestFillRow(row_id=f"{backtest_id}:fill:{index}", backtest_id=backtest_id, payload=item))
                for index, item in enumerate(payload.get("equity_curve") or []):
                    session.add(
                        BacktestPortfolioRow(row_id=f"{backtest_id}:equity:{index}", backtest_id=backtest_id, payload=item)
                    )
                for symbol, quantity in (payload.get("positions") or {}).items():
                    session.add(
                        BacktestPositionRow(
                            row_id=f"{backtest_id}:position:{symbol}",
                            backtest_id=backtest_id,
                            payload={"symbol": symbol, "quantity": quantity},
                        )
                    )
                session.add(
                    BacktestOrderRow(
                        row_id=f"{backtest_id}:orders",
                        backtest_id=backtest_id,
                        payload={"orders_generated": payload.get("orders_generated"), "orders_filled": payload.get("orders_filled")},
                    )
                )
                session.commit()
        except Exception:
            return

    def list_backtests(self) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(select(BacktestRunRow).order_by(BacktestRunRow.created_at.desc())).all()
            return [row.payload | {"backtest_id": row.backtest_id} for row in rows]

    def get_backtest(self, backtest_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(BacktestRunRow, backtest_id)
            if row is None:
                return None
            return row.payload | {"backtest_id": row.backtest_id}

    def _trading_session_id(self) -> str:
        book = self.active_paper_session()
        if book is None or book.starting_cash is None:
            raise MissingPaperSessionError("no active paper session")
        return book.session_id

    def _session_id_for_proposal(self, proposal_id: str) -> str:
        with self._session_factory() as session:
            row = session.get(TradeProposalRow, proposal_id)
            if row is None or row.session_id is None:
                raise MissingPaperSessionError(proposal_id)
            return row.session_id

    def _session_id_for_order(self, order_id: str) -> str:
        with self._session_factory() as session:
            row = session.get(OrderRow, order_id)
            if row is None or row.session_id is None:
                raise MissingPaperSessionError(order_id)
            return row.session_id

    def _resolve_session_id(self, session_id: str | None | object) -> str | None:
        if session_id is _ACTIVE:
            book = self.active_paper_session()
            return None if book is None else book.session_id
        return None if session_id is None else str(session_id)

    def _scoped(self, statement, column, session_id: str | None | object):
        target = self._resolve_session_id(session_id)
        if session_id is _ACTIVE and target is None:
            return statement.where(column == "__no_active_paper_session__")
        if target is None:
            return statement.where(column.is_(None))
        return statement.where(column == target)

    def _position_row(self, session, session_id: str, instrument_id: str) -> PositionRow | None:
        return session.scalar(
            select(PositionRow).where(
                PositionRow.session_id == session_id,
                PositionRow.instrument_id == instrument_id,
            )
        )

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


def _paper_session(row: PaperSessionRow) -> PaperSessionRecord:
    return PaperSessionRecord(
        session_id=row.session_id,
        status=row.status,
        created_at=as_utc(row.created_at),
        closed_at=as_utc(row.closed_at) if row.closed_at else None,
        starting_cash=row.starting_cash,
        peak_equity=row.peak_equity,
    )


def _legacy_assessment(session: Session) -> LegacyAssessment:
    flag = session.get(RuntimeFlagRow, "paper")
    return assess_legacy_book(
        snapshots=[
            {"snapshot_id": row.snapshot_id, "timestamp": as_utc(row.timestamp), "payload": payload_dict(row.payload)}
            for row in session.scalars(select(PortfolioSnapshotRow).where(PortfolioSnapshotRow.session_id.is_(None)))
        ],
        orders=[
            {"order_id": row.order_id, "payload": payload_dict(row.payload)}
            for row in session.scalars(select(OrderRow).where(OrderRow.session_id.is_(None)))
        ],
        executions=[
            {"execution_id": row.execution_id, "order_id": row.order_id, "payload": payload_dict(row.payload)}
            for row in session.scalars(select(ExecutionRow).where(ExecutionRow.session_id.is_(None)))
        ],
        positions=[
            {"instrument_id": row.instrument_id, "symbol": row.symbol, "payload": payload_dict(row.payload)}
            for row in session.scalars(select(PositionRow).where(PositionRow.session_id.is_(None)))
        ],
        runtime_peak=None if flag is None else flag.peak_equity,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _ist_day(moment: datetime) -> str:
    return as_utc(moment).astimezone(_IST).date().isoformat()


def _counted_entry(payload: dict) -> bool:
    """A submitted CNC buy. Rejections, sells, and legacy orders are not entries."""
    if payload.get("side") != "BUY" or payload.get("status") == "REJECTED":
        return False
    metadata = payload.get("metadata") or {}
    return metadata.get("policy_version") == ENTRY_POLICY_VERSION and metadata.get("reason") == "entry"


def _entry_count(session: Session, day: str) -> int:
    total = 0
    for row in session.scalars(select(OrderRow)):
        payload = dict(row.payload)
        if _counted_entry(payload) and _ist_day(datetime.fromisoformat(str(payload["created_at"]))) == day:
            total += 1
    return total


def _lock_entry_day(session: Session, day: str) -> None:
    """Take a write lock on this IST date before reading the entry count."""
    locked = session.execute(update(EntryDayGateRow).where(EntryDayGateRow.trading_day == day).values(trading_day=day))
    if locked.rowcount == 1:
        return
    try:
        with session.begin_nested():
            session.add(EntryDayGateRow(trading_day=day))
            session.flush()
    except IntegrityError:
        session.execute(update(EntryDayGateRow).where(EntryDayGateRow.trading_day == day).values(trading_day=day))


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


def _agent_of(envelope: dict) -> str | None:
    payload = envelope.get("payload")
    if isinstance(payload, dict):
        name = payload.get("agent_name")
        return str(name) if name is not None else None
    return None
