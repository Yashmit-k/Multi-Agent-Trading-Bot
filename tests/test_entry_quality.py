"""Fewer, better trades: a stricter bar for agent buys, strongest first, and exits by the holding's own horizon."""

from datetime import timedelta
from decimal import Decimal

from contracts.enums import Exchange, Horizon, Side, Timeframe, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for, sample_agent_signal
from contracts.schemas.market import Candle
from contracts.schemas.position import Position
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_paper import run_paper_cycle
from core_paper.cycle import holding_horizon

CASH = Decimal("1000000")


def _signal(repository: CoreRepository, symbol: str, score: float, *, horizon: Horizon = Horizon.SWING, at=FIXTURE_AS_OF, sid: str | None = None) -> None:
    signal = sample_agent_signal(symbol).model_copy(
        update={"signal_id": sid or f"sig-{symbol}-{horizon.value}-{score}", "horizon": horizon, "signal": score, "confidence": 0.8,
                "timestamp": at, "as_of": at, "valid_until": at + timedelta(hours=6)}
    )
    ingest_signal(repository, MemoryEventPublisher(), signal, mode=TradingMode.BACKTEST, now=at, replay_as_of=at, skew_seconds=5)


def _cycle(repository: CoreRepository, now=FIXTURE_AS_OF) -> None:
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH, now=now, enforce_entry_window=False)


def _buys(repository: CoreRepository) -> list[str]:
    return sorted(order.symbol for order in repository.list_orders() if order.side == Side.BUY)


def test_a_weak_agent_buy_is_not_taken_but_a_strong_one_is(repository: CoreRepository) -> None:
    for symbol in ("RELIANCE", "TCS"):
        repository.upsert_candles(list(candles_for(symbol)))
    repository.open_paper_session(CASH)
    _signal(repository, "RELIANCE", 0.3)  # fused 0.3 < 0.35
    _signal(repository, "TCS", 0.6)
    _cycle(repository)
    assert _buys(repository) == ["TCS"]


def test_the_entry_bar_is_a_setting(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    repository.open_paper_session(CASH)
    repository.save_setting("risk", {"min_entry_signal": "0.25"}, updated_by="test", now=FIXTURE_AS_OF)
    _signal(repository, "RELIANCE", 0.3)
    _cycle(repository)
    assert _buys(repository) == ["RELIANCE"]


def test_the_strongest_candidates_take_the_daily_entry_slots(repository: CoreRepository) -> None:
    for symbol in ("HDFCBANK", "INFY", "RELIANCE", "TCS"):
        repository.upsert_candles(list(candles_for(symbol)))
    repository.open_paper_session(CASH)
    repository.save_setting("risk", {"daily_entry_limit": 2}, updated_by="test", now=FIXTURE_AS_OF)
    for symbol, score in (("HDFCBANK", 0.5), ("INFY", 0.9), ("RELIANCE", 0.4), ("TCS", 0.8)):
        _signal(repository, symbol, score)
    _cycle(repository)
    assert _buys(repository) == ["INFY", "TCS"]  # not HDFCBANK, the first alphabetically


def test_an_intraday_signal_does_not_sell_a_swing_holding(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    repository.open_paper_session(CASH)
    repository.save_position(Position(symbol="RELIANCE", quantity=7, average_price=Decimal("2900"), market_price=Decimal("2900"),
                                      market_value=Decimal("20300"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"),
                                      opened_at=FIXTURE_AS_OF, updated_at=FIXTURE_AS_OF))
    assert holding_horizon(repository, "RELIANCE") == Horizon.SWING  # no agent entry on record: treated as delivery
    bar_end = FIXTURE_AS_OF
    repository.upsert_candles([Candle(symbol="RELIANCE", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("2900"), high=Decimal("2905"),
                                      low=Decimal("2890"), close=Decimal("2895"), volume=1000, start=bar_end - timedelta(minutes=5), end=bar_end)])
    _signal(repository, "RELIANCE", -0.9, horizon=Horizon.INTRADAY)
    _cycle(repository)
    assert [order for order in repository.list_orders() if order.side == Side.SELL] == []
    _signal(repository, "RELIANCE", -0.9, horizon=Horizon.SWING)
    _cycle(repository)
    sells = [order for order in repository.list_orders() if order.side == Side.SELL]
    assert len(sells) == 1 and sells[0].metadata["reason"] == "signal"
