"""Explicit new-order cap and database freshness. No worker and no production database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from contracts.enums import Exchange, Timeframe, TradingMode
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_paper.cycle import CycleRefused, require_fresh_constituents, require_ordinary_entry_window, run_paper_cycle
from test_execution_policy import CASH, DECISION, _arm, _daily, _sink
from test_phase4 import _signal, _store

UTC = timezone.utc


def test_unset_cap_is_not_introduced_and_zero_persists_nothing(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    _daily(repository, "TCS", Decimal("400"))
    instrument = repository.get_by_symbol("TCS")
    assert instrument is not None
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    _store(repository, _signal(signal_id="sig-tcs", symbol="TCS", timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False, max_new_orders=0)
    assert repository.list_orders() == []


def test_cap_stops_before_the_next_order_and_leaves_existing_rows(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    _daily(repository, "TCS", Decimal("400"))
    instrument = repository.get_by_symbol("TCS")
    assert instrument is not None
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    _store(repository, _signal(signal_id="sig-tcs", symbol="TCS", timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False, max_new_orders=1)
    first = repository.list_orders()
    assert len(first) == 1
    kept = first[0].order_id
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False, max_new_orders=0)
    again = repository.list_orders()
    assert [item.order_id for item in again] == [kept]
    assert again[0].status == first[0].status


def test_negative_cap_is_refused(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    with pytest.raises(ValueError):
        run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False, max_new_orders=-1)


def test_freshness_uses_stored_bars_and_fails_closed() -> None:
    from core_db.session import create_schema

    repository = CoreRepository(create_schema("sqlite://"))
    moment = datetime(2026, 10, 13, 4, 9, tzinfo=UTC)
    end = datetime(2026, 10, 13, 4, 5, tzinfo=UTC)
    start = end - timedelta(minutes=5)
    for index in range(50):
        symbol = f"S{index:02d}"
        instrument = repository.upsert_instrument(symbol=symbol, exchange="NSE", trading_symbol=symbol)
        repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
        # S00 is two bars behind; the feed check tolerates one bar of lag, not two.
        bar_end = end - timedelta(minutes=10) if symbol == "S00" else end
        repository.upsert_candles([_five(symbol, bar_end - timedelta(minutes=5), bar_end)])
    with pytest.raises(CycleRefused):
        require_fresh_constituents(repository, moment)
    repository.upsert_candles([_five("S00", start - timedelta(minutes=5), start)])  # now one bar behind
    require_fresh_constituents(repository, moment)


def test_ordinary_entry_window_bounds() -> None:
    require_ordinary_entry_window(datetime(2026, 10, 13, 4, 9, tzinfo=UTC))
    with pytest.raises(CycleRefused):
        require_ordinary_entry_window(datetime(2026, 10, 13, 3, 49, tzinfo=UTC))
    with pytest.raises(CycleRefused):
        require_ordinary_entry_window(datetime(2026, 10, 13, 5, 0, tzinfo=UTC))


def _five(symbol: str, start: datetime, end: datetime) -> Candle:
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.M5,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=100,
        start=start,
        end=end,
    )
