"""Entry window gates buys only. Settlement and exits keep running. No production database."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from contracts.enums import OrderStatus, Side, TradingMode
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher
from core_paper.backtest import exit_on_bar
from core_paper.cycle import run_paper_cycle
from core_paper.trading_calendar import cash_session_open
from core_worker.paper_schedule import broker_allows_entries, run_scheduled_cycle
from test_execution_policy import CASH, DECISION, _arm, _bar, _sink

UTC = timezone.utc
AFTER_ENTRY = datetime(2026, 10, 13, 5, 30, tzinfo=UTC)
EXPIRY = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)


def test_cash_session_continues_after_the_entry_window() -> None:
    assert cash_session_open(datetime(2026, 10, 13, 4, 0, tzinfo=UTC))
    assert cash_session_open(AFTER_ENTRY)
    assert not cash_session_open(datetime(2026, 10, 13, 10, 0, tzinfo=UTC))
    assert not cash_session_open(datetime(2026, 10, 18, 4, 0, tzinfo=UTC))


def test_closed_window_expires_an_unfilled_entry_and_buys_nothing_more(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)
    created = repository.list_orders()
    assert len(created) == 1
    run_paper_cycle(
        repository,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=EXPIRY,
        enforce_entry_window=True,
        broker_authenticated=True,
    )
    orders = repository.list_orders()
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.EXPIRED_NO_DATA
    assert orders[0].metadata["terminal_reason"] == "expired_no_data"
    assert repository.list_executions() == []


def test_stale_universe_blocks_a_new_buy_and_still_expires(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)
    run_paper_cycle(
        repository,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=EXPIRY,
        enforce_entry_window=True,
        require_universe_fresh=True,
        broker_authenticated=False,
    )
    assert len(repository.list_orders()) == 1
    assert repository.list_orders()[0].status == OrderStatus.EXPIRED_NO_DATA


def test_stop_wins_when_one_later_bar_hits_stop_and_target(repository: CoreRepository) -> None:
    _fill_reliance(repository)
    position = repository.position_for("RELIANCE")
    assert position is not None and position.quantity > 0
    execution = repository.list_executions()[0]
    stop = Decimal(execution.metadata["stop_loss"])
    target = Decimal(execution.metadata["take_profit"])
    breach = _bar(
        datetime(2026, 10, 13, 4, 0, tzinfo=UTC),
        open_=stop,
        low=stop - Decimal("1"),
        symbol="RELIANCE",
    )
    breach = breach.model_copy(update={"high": target + Decimal("1")})
    assert exit_on_bar(Side.BUY, stop, target, breach) == "stop"
    repository.upsert_candles([breach])
    run_paper_cycle(
        repository,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=AFTER_ENTRY,
        enforce_entry_window=True,
    )
    sells = [item for item in repository.list_orders() if item.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].metadata["reason"] == "stop"
    assert sells[0].status == OrderStatus.FILLED
    assert sells[0].quantity == position.quantity
    assert repository.held_quantity("RELIANCE") == 0
    buys = [item for item in repository.list_orders() if item.side == Side.BUY]
    assert len(buys) == 1


def test_a_missed_poll_waits_and_a_later_cycle_exits(repository: CoreRepository) -> None:
    _fill_reliance(repository)
    run_paper_cycle(
        repository,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=AFTER_ENTRY,
        enforce_entry_window=True,
    )
    assert [item for item in repository.list_orders() if item.side == Side.SELL] == []
    execution = repository.list_executions()[0]
    stop = Decimal(execution.metadata["stop_loss"])
    repository.upsert_candles(
        [_bar(datetime(2026, 10, 14, 4, 0, tzinfo=UTC), open_=stop, low=stop - Decimal("1"))]
    )
    restarted = CoreRepository(repository._session_factory)
    run_paper_cycle(
        restarted,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=datetime(2026, 10, 14, 5, 30, tzinfo=UTC),
        enforce_entry_window=True,
    )
    held_before = repository.list_executions()[0].quantity
    sells = [item for item in restarted.list_orders() if item.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].status == OrderStatus.FILLED
    assert sells[0].quantity == held_before
    assert restarted.held_quantity("RELIANCE") == 0


def test_scheduled_cycle_does_not_enter_outside_the_session(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    assert run_scheduled_cycle(
        repository,
        MemoryEventPublisher(),
        mode=TradingMode.PAPER,
        schedule=None,
        now=datetime(2026, 10, 13, 10, 0, tzinfo=UTC),
        broker_authenticated=True,
    ) == 0
    assert repository.list_orders() == []


def test_broker_check_fails_closed() -> None:
    assert broker_allows_entries("http://core-api:8000", "", urlopen=_open) is False

    def _unauthenticated(request, timeout):
        path = request.full_url
        if path.endswith("/api/v1/system/status"):
            return _Body({"trading_mode": "PAPER", "live_enabled": False})
        if path.endswith("/api/v1/zerodha/status"):
            return _Body({"configured": True, "authenticated": False, "live_enabled": False})
        return _Body({"authenticated": True, "credentials_rejected": False, "last_error": None})

    assert broker_allows_entries("http://core-api:8000", "token", urlopen=_unauthenticated) is False

    def _healthy(request, timeout):
        path = request.full_url
        if path.endswith("/api/v1/system/status"):
            return _Body({"trading_mode": "PAPER", "live_enabled": False})
        if path.endswith("/api/v1/zerodha/status"):
            return _Body({"configured": True, "authenticated": True, "live_enabled": False})
        return _Body({"authenticated": True, "credentials_rejected": False, "last_error": None})

    assert broker_allows_entries("http://core-api:8000", "token", urlopen=_healthy) is True


def test_worker_loop_uses_the_guarded_cycle() -> None:
    text = Path("services/core/worker/src/core_worker/__main__.py").read_text()
    guard = Path("services/core/worker/src/core_worker/paper_schedule.py").read_text()
    assert "run_scheduled_cycle" in text
    assert "run_paper_cycle" not in text
    assert "max_new_orders" not in text
    assert "enforce_entry_window=True" in guard
    assert "require_universe_fresh=True" in guard
    assert "require_fresh=True" in guard
    assert "mode=TradingMode.PAPER" in guard


def _fill_reliance(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("440"), low=Decimal("439"))])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=start + timedelta(minutes=5))
    assert repository.list_executions()


def _open(request, timeout):
    raise TimeoutError(timeout)


class _Body:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload
