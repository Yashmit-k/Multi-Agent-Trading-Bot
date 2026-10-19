"""User risk settings: bounded parsing, and the cycle obeys the saved values."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from contracts.enums import TradingMode
from core_db.repository import CoreRepository
from core_paper.cycle import load_risk_settings, run_paper_cycle
from core_risk.settings import HARD_MAX_ORDER_NOTIONAL, SettingsError, parse_settings
from test_execution_policy import CASH, DECISION, _arm, _daily, _sink
from test_phase4 import _signal, _store

UTC = timezone.utc


def test_defaults_and_bounds() -> None:
    settings = parse_settings(None)
    assert settings.max_order_notional == Decimal("20000") and settings.daily_entry_limit == 6
    assert parse_settings({"max_order_notional": "50000"}).max_order_notional == Decimal("50000")
    with pytest.raises(SettingsError) as error:
        parse_settings({"max_order_notional": str(HARD_MAX_ORDER_NOTIONAL + 1), "daily_entry_limit": 2.5, "nope": 1})
    assert set(error.value.errors) == {"max_order_notional", "daily_entry_limit", "nope"}
    assert parse_settings({"daily_entry_limit": "abc"}, strict=False).daily_entry_limit == 6  # bad stored value -> default


def _ready(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    _daily(repository, "TCS", Decimal("400"))
    instrument = repository.get_by_symbol("TCS")
    assert instrument is not None
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    _store(repository, _signal(signal_id="sig-tcs", symbol="TCS", timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))


def _cycle(repository: CoreRepository) -> None:
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)


def test_auto_entries_off_blocks_new_orders(repository: CoreRepository) -> None:
    _ready(repository)
    repository.save_setting("risk", {"auto_entries": False}, updated_by="test", now=DECISION)
    assert load_risk_settings(repository).auto_entries is False
    _cycle(repository)
    assert repository.list_orders() == []


def test_zero_daily_limit_blocks_and_brackets_follow_settings(repository: CoreRepository) -> None:
    _ready(repository)
    repository.save_setting("risk", {"daily_entry_limit": 0}, updated_by="test", now=DECISION)
    _cycle(repository)
    assert repository.list_orders() == []


def test_user_brackets_and_cap_reach_the_order(repository: CoreRepository) -> None:
    _ready(repository)
    repository.save_setting("risk", {"stop_loss_pct": "5", "take_profit_pct": "10", "max_order_notional": "5000"}, updated_by="test", now=DECISION)
    _cycle(repository)
    orders = repository.list_orders()
    order = next(o for o in orders if o.metadata.get("reason") == "entry")
    assert order.limit_price * order.quantity <= Decimal("5000")
    reference = Decimal(order.metadata["reference_price"])
    assert Decimal(order.metadata["stop_loss"]) < reference * Decimal("0.96")
    assert Decimal(order.metadata["take_profit"]) > reference * Decimal("1.08")


def _intraday_ready(repository: CoreRepository) -> None:
    from contracts.enums import Exchange, Horizon, Timeframe
    from contracts.schemas.market import Candle

    _ready(repository)
    bar_end = DECISION
    repository.upsert_candles([Candle(symbol="TCS", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("400"), high=Decimal("401"), low=Decimal("399"), close=Decimal("400"), volume=10, start=bar_end - timedelta(minutes=5), end=bar_end)])
    _store(repository, _signal(signal_id="sig-tcs-intraday", symbol="TCS", horizon=Horizon.INTRADAY, timestamp=DECISION, valid_until=DECISION + timedelta(hours=2)))


def _horizons(repository: CoreRepository) -> set[str]:
    return {repository.get_proposal(order.proposal_id).horizon.value for order in repository.list_orders() if order.symbol == "TCS"}  # type: ignore[union-attr]


def test_intraday_entries_are_off_by_default(repository: CoreRepository) -> None:
    _intraday_ready(repository)
    _cycle(repository)
    assert _horizons(repository) == {"SWING"}


def test_intraday_entries_when_enabled(repository: CoreRepository) -> None:
    _intraday_ready(repository)
    repository.save_setting("risk", {"intraday_auto_entries": True}, updated_by="test", now=DECISION)
    _cycle(repository)
    assert "INTRADAY" in _horizons(repository)
