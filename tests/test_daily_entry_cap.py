"""Six CNC entries per IST date. Offline SQLite only. No worker and no production database."""

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from contracts.enums import Exchange, OrderStatus, OrderType, Side, Timeframe, TradingMode
from contracts.schemas.market import Candle
from contracts.schemas.order import Order
from core_db.models import Base
from core_db.repository import CoreRepository, DAILY_ENTRY_LIMIT
from core_db.seed import load_seed
from core_paper.charges import reservation_buy
from core_paper.cycle import run_paper_cycle
from core_paper.execute import queue_entry
from test_execution_policy import CASH, DECISION, _proposal, _sell, _sink
from test_phase4 import _signal, _store

UTC = timezone.utc
FRIDAY = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def test_sixth_entry_is_stored_and_the_seventh_is_not(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    _legacy_same_day(repository)
    assert repository.daily_entry_count(DECISION) == 0
    symbols = _symbols(repository, 7)
    opened = [_enter(repository, symbol, DECISION, f"entry-{symbol}") for symbol in symbols]
    assert opened[5] is not None and opened[5].status == OrderStatus.OPEN
    assert opened[6] is None
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    kept = opened[0]
    assert kept is not None and kept.limit_price is not None
    notional = kept.limit_price * kept.quantity
    assert notional <= Decimal("20000")
    assert Decimal(kept.metadata["reserved_amount"]) == reservation_buy(notional, _schedule())
    assert Decimal(kept.metadata["reserved_amount"]) > notional
    cancelled = kept.model_copy(update={"status": OrderStatus.CANCELLED})
    repository.commit_policy_transition(cancelled, release=True)
    expired = opened[1]
    assert expired is not None
    repository.commit_policy_transition(expired.model_copy(update={"status": OrderStatus.EXPIRED}), release=True)
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    assert _enter(repository, symbols[0], DECISION, "after-cancel") is None
    _sell(repository, 1, DECISION, Decimal("100"), name="exit-after-cap")
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    assert any(item.side == Side.SELL and item.status == OrderStatus.OPEN for item in repository.list_orders())


def test_cap_survives_another_cycle_a_restart_and_a_new_session(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    symbols = _symbols(repository, 7)
    for symbol in symbols:
        _put_daily(repository, symbol, Decimal("99.76"), DECISION)
        _store(repository, _signal(signal_id=f"sig-{symbol}", symbol=symbol, timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    restarted = CoreRepository(repository._session_factory)
    assert restarted.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    assert _enter(restarted, symbols[0], DECISION, "after-restart") is None
    current = repository.active_paper_session()
    assert current is not None
    repository.close_paper_session(current.session_id)
    repository.open_paper_session(CASH)
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT
    assert _enter(repository, symbols[0], DECISION, "other-session") is None


def test_previous_ist_date_does_not_consume_today(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    symbols = _symbols(repository, 7)
    friday = [_enter(repository, symbol, FRIDAY, f"friday-{symbol}") for symbol in symbols]
    assert friday[5] is not None and friday[6] is None
    assert repository.daily_entry_count(FRIDAY) == DAILY_ENTRY_LIMIT
    monday = [_enter(repository, symbol, DECISION, f"monday-{symbol}") for symbol in symbols]
    assert monday[5] is not None and monday[6] is None
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT


def test_concurrent_cycles_cannot_store_a_seventh_entry(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'entries.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    load_seed(repository)
    repository.open_paper_session(CASH)
    symbols = _symbols(repository, 12)
    for symbol in symbols:
        _put_daily(repository, symbol, Decimal("99.76"), DECISION)
        proposal = _proposal(symbol, DECISION).model_copy(update={"proposal_id": f"race-{symbol}"})
        repository.insert_proposal(proposal)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _batch(names: list[str]) -> None:
        try:
            barrier.wait(timeout=10)
            local = CoreRepository(factory)
            for symbol in names:
                proposal = local.get_proposal(f"race-{symbol}")
                assert proposal is not None
                queue_entry(local, proposal, DECISION)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=_batch, args=(symbols[:6],)),
        threading.Thread(target=_batch, args=(symbols[6:],)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert repository.daily_entry_count(DECISION) == DAILY_ENTRY_LIMIT


def _symbols(repository: CoreRepository, count: int) -> list[str]:
    names = [item.symbol for item in repository.members_at(DECISION)]
    assert len(names) >= count
    return names[:count]


def _enter(repository: CoreRepository, symbol: str, moment: datetime, name: str):
    _put_daily(repository, symbol, Decimal("99.76"), moment)
    proposal = _proposal(symbol, moment).model_copy(
        update={"proposal_id": name, "entry_price": Decimal("99.76"), "quantity": 5000}
    )
    repository.insert_proposal(proposal)
    return queue_entry(repository, proposal, moment)


def _put_daily(repository: CoreRepository, symbol: str, close: Decimal, end: datetime) -> None:
    repository.upsert_instrument(symbol=symbol, exchange="NSE", trading_symbol=symbol)
    repository.upsert_candles(
        [
            Candle(
                symbol=symbol,
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=close - Decimal("1"),
                high=close + Decimal("1"),
                low=close - Decimal("2"),
                close=close,
                volume=1000,
                start=end - timedelta(hours=6),
                end=end,
            )
        ]
    )


def _legacy_same_day(repository: CoreRepository) -> None:
    proposal = _proposal("RELIANCE", DECISION).model_copy(update={"proposal_id": "legacy-same-day"})
    repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE")
    repository.insert_proposal(proposal)
    repository.insert_order(
        Order(
            order_id="legacy-same-day-order",
            client_order_id="legacy-same-day-order",
            proposal_id=proposal.proposal_id,
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            limit_price=None,
            stop_price=None,
            trading_mode=TradingMode.PAPER,
            status=OrderStatus.CANCELLED,
            created_at=DECISION,
            updated_at=DECISION,
            metadata={"fill_at": "next_open"},
        )
    )


def _schedule():
    from core_paper.charges import ZERODHA_EQUITY_RI

    return ZERODHA_EQUITY_RI
