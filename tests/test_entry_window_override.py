"""13 October 2026 paper entry extension. Offline SQLite only. No production cycle."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from contracts.enums import OrderStatus, Side, TradingMode
from core_db.repository import DAILY_ENTRY_LIMIT, CoreRepository
from core_paper.charges import ZERODHA_EQUITY_RI, reservation_buy
from core_paper.cycle import CycleRefused, require_entry_window, run_paper_cycle
from core_paper.execute import queue_entry, settle_entries
from core_paper.one_shot import REQUIRED_REVISION, one_shot_blockers, run_authorized_one_shot
from core_paper.trading_calendar import TEST_EXTENSION_END, TEST_EXTENSION_SOURCE, paper_test_entry_window
from test_daily_entry_cap import _enter, _symbols
from test_execution_policy import CASH, DECISION, _bar, _daily, _sink
from test_paper_lifecycle import _fill_reliance
from test_phase4 import _signal, _store

UTC = timezone.utc
BEFORE_OPEN = datetime(2026, 10, 13, 3, 49, 59, tzinfo=UTC)
LATE = datetime(2026, 10, 13, 5, 29, 59, tzinfo=UTC)
ELEVEN = datetime(2026, 10, 13, 5, 30, tzinfo=UTC)
NEXT_CUTOFF = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
NEXT_INSIDE = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
DURING = datetime(2026, 10, 13, 5, 15, tzinfo=UTC)


def test_extension_is_bound_to_one_paper_date() -> None:
    with pytest.raises(CycleRefused):
        require_entry_window(BEFORE_OPEN, mode=TradingMode.PAPER, allow_extension=True)
    require_entry_window(LATE, mode=TradingMode.PAPER, allow_extension=True)
    with pytest.raises(CycleRefused):
        require_entry_window(ELEVEN, mode=TradingMode.PAPER, allow_extension=True)
    with pytest.raises(CycleRefused):
        require_entry_window(NEXT_CUTOFF, mode=TradingMode.PAPER, allow_extension=True)
    require_entry_window(NEXT_INSIDE, mode=TradingMode.PAPER, allow_extension=True)
    with pytest.raises(CycleRefused):
        require_entry_window(DURING, mode=TradingMode.PAPER, allow_extension=False)
    with pytest.raises(CycleRefused):
        require_entry_window(DURING, mode=TradingMode.LIVE, allow_extension=True)
    extended = paper_test_entry_window(LATE)
    assert extended is not None
    assert extended.session_date.isoformat() == "2026-10-13"
    assert extended.entry_end == TEST_EXTENSION_END
    assert paper_test_entry_window(ELEVEN) is None
    assert paper_test_entry_window(NEXT_INSIDE) is None
    assert paper_test_entry_window(datetime(2026, 10, 12, 4, 30, tzinfo=UTC)) is None


def test_extended_order_survives_1030_and_expires_at_1100(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    symbol = _symbols(repository, 1)[0]
    _daily(repository, symbol, Decimal("99.76"))
    proposal = _proposal_for(repository, symbol)
    window = paper_test_entry_window(DURING)
    assert window is not None
    order = queue_entry(repository, proposal, DURING, entry_window=window)
    assert order is not None and order.status == OrderStatus.OPEN
    assert order.metadata["calendar_source"] == TEST_EXTENSION_SOURCE
    assert order.metadata["entry_window_end"].startswith("2026-10-13T05:30:00")
    assert order.limit_price is not None and order.limit_price * order.quantity <= Decimal("20000")
    settle_entries(repository, starting_cash=CASH, now=datetime(2026, 10, 13, 5, 0, tzinfo=UTC))
    assert repository.list_orders()[0].status == OrderStatus.OPEN
    settle_entries(repository, starting_cash=CASH, now=ELEVEN)
    assert repository.list_orders()[0].status == OrderStatus.EXPIRED_NO_DATA


def test_one_new_buy_does_not_block_the_stop_sell(repository: CoreRepository) -> None:
    _fill_reliance(repository)
    for symbol in ("TCS", "INFY"):
        _daily(repository, symbol, Decimal("400"))
        _store(repository, _signal(signal_id=f"sig-{symbol}", symbol=symbol, timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    execution = repository.list_executions()[0]
    stop = Decimal(execution.metadata["stop_loss"])
    repository.upsert_candles([_bar(datetime(2026, 10, 13, 5, 10, tzinfo=UTC), open_=stop, low=stop - Decimal("1"))])
    before = {item.order_id for item in repository.list_orders()}
    run_paper_cycle(
        repository,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=DURING,
        max_new_orders=1,
        allow_test_extension=True,
    )
    created = [item for item in repository.list_orders() if item.order_id not in before]
    buys = [item for item in created if item.side == Side.BUY]
    sells = [item for item in created if item.side == Side.SELL]
    assert len(buys) == 1
    assert buys[0].metadata["calendar_source"] == TEST_EXTENSION_SOURCE
    assert buys[0].limit_price is not None
    notional = buys[0].limit_price * buys[0].quantity
    assert notional <= Decimal("20000")
    assert Decimal(buys[0].metadata["reserved_amount"]) == reservation_buy(notional, ZERODHA_EQUITY_RI)
    assert len(sells) == 1
    assert sells[0].metadata["reason"] == "stop"


def test_daily_cap_still_blocks_the_extended_window(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    symbols = _symbols(repository, 7)
    opened = [_enter(repository, symbol, DURING, f"cap-{symbol}") for symbol in symbols]
    assert opened[5] is not None and opened[6] is None
    assert repository.daily_entry_count(DURING) == DAILY_ENTRY_LIMIT
    run_paper_cycle(
        repository,
        _sink(),
        mode=TradingMode.PAPER,
        starting_cash=CASH,
        now=DURING,
        max_new_orders=1,
        allow_test_extension=True,
    )
    assert repository.daily_entry_count(DURING) == DAILY_ENTRY_LIMIT
    assert sum(1 for item in repository.list_orders() if item.side == Side.BUY and item.metadata.get("policy_version") == "cnc-limit-v1") == DAILY_ENTRY_LIMIT


def test_one_shot_refuses_without_calling_the_cycle(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    reasons = one_shot_blockers(
        mode=TradingMode.LIVE,
        live_enabled=False,
        session_id="other",
        revision="0006_paper_execution",
        broker_authenticated=False,
        daily_count=DAILY_ENTRY_LIMIT,
        now=ELEVEN,
    )
    assert {"mode", "session", "revision", "broker", "daily_entry_cap"} <= set(reasons)
    with pytest.raises(CycleRefused):
        run_authorized_one_shot(
            repository,
            _sink(),
            starting_cash=CASH,
            clock=lambda: ELEVEN,
            live_gates=_open_gates,
        )
    assert repository.list_orders() == []


def test_final_clock_is_the_only_timestamp_the_cycle_receives(monkeypatch) -> None:
    from core_paper import one_shot as one_shot_module

    final = LATE
    seen: dict = {}

    def fake_cycle(*_args, **kwargs):
        seen["now"] = kwargs["now"]
        seen["max_new_orders"] = kwargs["max_new_orders"]
        seen["allow_test_extension"] = kwargs["allow_test_extension"]
        return 0

    monkeypatch.setattr(one_shot_module, "run_paper_cycle", fake_cycle)
    monkeypatch.setattr(one_shot_module, "require_fresh_constituents", lambda _repository, now: seen.setdefault("fresh", now))
    monkeypatch.setattr(one_shot_module, "database_revision", lambda _repository: REQUIRED_REVISION)
    run_authorized_one_shot(
        _ApprovedBook(),
        _sink(),
        starting_cash=CASH,
        clock=lambda: final,
        live_gates=_open_gates,
    )
    assert seen["now"] == final
    assert seen["fresh"] == final
    assert seen["max_new_orders"] == 1
    assert seen["allow_test_extension"] is True


def test_a_closed_or_stale_final_clock_does_not_call_the_cycle(monkeypatch) -> None:
    from core_paper import one_shot as one_shot_module

    calls: list = []
    monkeypatch.setattr(one_shot_module, "run_paper_cycle", lambda *_args, **_kwargs: calls.append(True))
    monkeypatch.setattr(one_shot_module, "require_fresh_constituents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(one_shot_module, "database_revision", lambda _repository: REQUIRED_REVISION)
    with pytest.raises(CycleRefused):
        run_authorized_one_shot(_ApprovedBook(), _sink(), starting_cash=CASH, clock=lambda: ELEVEN, live_gates=_open_gates)
    with pytest.raises(CycleRefused):
        run_authorized_one_shot(_ApprovedBook(), _sink(), starting_cash=CASH, clock=lambda: NEXT_INSIDE, live_gates=_open_gates)

    def stale(_repository, now: datetime) -> None:
        raise CycleRefused(f"stale {now.isoformat()}")

    monkeypatch.setattr(one_shot_module, "require_fresh_constituents", stale)
    with pytest.raises(CycleRefused, match="stale"):
        run_authorized_one_shot(_ApprovedBook(), _sink(), starting_cash=CASH, clock=lambda: LATE, live_gates=_open_gates)
    assert calls == []


def test_worker_does_not_take_the_one_order_extension() -> None:
    worker = Path("services/core/worker/src/core_worker/__main__.py").read_text()
    schedule = Path("services/core/worker/src/core_worker/paper_schedule.py").read_text()
    one_shot = Path("services/core/paper-execution/src/core_paper/one_shot.py").read_text()
    assert "max_new_orders" not in worker
    assert "allow_test_extension" not in worker
    assert "max_new_orders" not in schedule
    assert "max_new_orders=1" in one_shot
    assert "allow_test_extension=True" in one_shot
    assert "c6c7f91fe84f4d48862c4a1b85646f3b" in one_shot
    guard = one_shot.split("def run_authorized_one_shot", 1)[1]
    assert guard.index("moment = (clock or _utc_now)()") < guard.index("require_fresh_constituents")
    assert "now=moment" in guard
    assert "now: datetime" not in guard.split("def database_revision", 1)[0]


def _open_gates() -> dict:
    return {"mode": TradingMode.PAPER, "live_enabled": False, "broker_authenticated": True}


class _ApprovedBook:
    def active_paper_session(self):
        return type("Book", (), {"session_id": "c6c7f91fe84f4d48862c4a1b85646f3b", "starting_cash": CASH})()

    def daily_entry_count(self, _moment: datetime) -> int:
        return 0


def _proposal_for(repository: CoreRepository, symbol: str):
    from test_execution_policy import _proposal

    proposal = _proposal(symbol, DURING).model_copy(update={"proposal_id": f"ext-{symbol}", "entry_price": Decimal("99.76")})
    repository.insert_proposal(proposal)
    return proposal
