"""Strategy lab: indicators, conditions, no look-ahead, exits, portfolio pass, and the API."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient

from contracts.enums import Exchange, Timeframe, TradingMode
from contracts.schemas.market import Candle
from core_api.strategy_lab import TEMPLATES, Bars, BacktestRequest, StrategyDefinition, _ema, _rsi, evaluate, run_strategy, simulate_symbol
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher

UTC = timezone.utc
START = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)


def _bars(closes: list[float], *, wiggle: float = 0.5) -> Bars:
    n = len(closes)
    close = np.array(closes, dtype=float)
    return Bars([START + timedelta(days=i) for i in range(n)], close.copy(), close + wiggle, close - wiggle, close, np.full(n, 1000.0))


def _cross(fast: int = 3, slow: int = 6, **extra) -> StrategyDefinition:  # type: ignore[no-untyped-def]
    return StrategyDefinition.model_validate(
        {
            "name": "cross",
            "entry": [{"left": {"indicator": "ema", "period": fast}, "op": "crosses_above", "right": {"indicator": "ema", "period": slow}}],
            "exit": [{"left": {"indicator": "ema", "period": fast}, "op": "crosses_below", "right": {"indicator": "ema", "period": slow}}],
            "stop_loss_pct": None,
            "take_profit_pct": None,
            **extra,
        }
    )


def test_indicators_match_hand_values() -> None:
    values = np.array([1.0, 2, 3, 4, 5])
    assert np.isnan(_ema(values, 3)[1]) and _ema(values, 3)[2] == 2.0 and _ema(values, 3)[3] == 3.0
    assert _rsi(np.array([1.0, 2, 3, 4, 5, 6]), 3)[-1] == 100.0


def test_operand_validation() -> None:
    with pytest.raises(Exception):
        StrategyDefinition.model_validate({"name": "x", "entry": [{"left": {"indicator": "ema"}, "op": ">", "right": {"value": 1}}]})
    for template in TEMPLATES:
        StrategyDefinition.model_validate(template)


def test_entry_fills_on_the_next_open_and_exit_rule_closes() -> None:
    prices = [100.0] * 10 + [100 + 2 * i for i in range(1, 11)] + [120 - 3 * i for i in range(1, 11)]
    bars = _bars(prices)
    strategy = _cross()
    signal = evaluate(bars, strategy.entry, mode="all")
    first = int(np.argmax(signal))
    [trade] = simulate_symbol("TCS", bars, strategy, 0)
    assert trade.entry_at == bars.end[first + 1]  # acted on at the next bar, never the signal bar
    assert trade.entry_price == pytest.approx(bars.open[first + 1] * 1.0005)
    assert trade.reason == "exit_rule"


def test_stop_wins_and_gaps_fill_at_open() -> None:
    prices = [100.0] * 10 + [101, 102, 103, 80, 80, 80]
    bars = _bars(prices)
    strategy = _cross(stop_loss_pct=5.0, take_profit_pct=50.0)
    [trade] = simulate_symbol("TCS", bars, strategy, 0)
    assert trade.reason == "stop"
    assert trade.exit_price == pytest.approx(80 * 0.9995)  # gapped through the stop: filled at the open


def test_portfolio_respects_slots_and_cash() -> None:
    from core_api.strategy_lab import Trade, portfolio

    trades = [Trade(f"S{i}", START, START + timedelta(days=5), 100.0, 101.0, 100, "x", 0.0, 100.0, 5) for i in range(3)]
    taken, skipped = portfolio(trades, _cross(max_open_positions=2, initial_cash=1_000_000))
    assert len(taken) == 2 and len(skipped) == 1


def test_api_save_backtest_and_scan(repository: CoreRepository) -> None:
    from core_api.app import create_app
    from core_api.settings import Settings

    instrument = repository.upsert_instrument(symbol="TCS", exchange="NSE", trading_symbol="TCS")
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    closes = [100.0] * 30 + [100 + i for i in range(1, 40)] + [139 - 2 * i for i in range(1, 30)]
    candles = []
    for i, price in enumerate(closes):
        end = datetime(2025, 3, 1, 10, 0, tzinfo=UTC) + timedelta(days=i)
        candles.append(Candle(symbol="TCS", exchange=Exchange.NSE, timeframe=Timeframe.D1, open=Decimal(str(price)), high=Decimal(str(price + 1)), low=Decimal(str(price - 1)), close=Decimal(str(price)), volume=1000, start=end - timedelta(hours=6, minutes=15), end=end))
    repository.upsert_candles(candles)
    settings = Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core", internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER)
    client = TestClient(create_app(settings, repository, MemoryEventPublisher()))
    auth = {"Authorization": "Bearer core"}
    definition = _cross(symbols=["TCS"]).model_dump(mode="json")
    saved = client.post("/api/v1/strategies", json={"definition": definition}, headers=auth).json()
    run = client.post(f"/api/v1/strategies/{saved['strategy_id']}/backtest", json={"start": "2025-03-01", "end": "2025-07-01"}, headers=auth)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["metrics"]["trades"] >= 1 and body["equity_curve"]
    detail = client.get(f"/api/v1/strategies/{saved['strategy_id']}", headers=auth).json()
    assert len(detail["runs"]) == 1
    assert all(item.get("kind") != "strategy_lab" for item in client.get("/api/v1/backtests", headers=auth).json())
    scan = client.get(f"/api/v1/strategies/{saved['strategy_id']}/scan", headers=auth)
    assert scan.status_code == 200 and scan.json()["scanned"] == 1
    bad = client.post("/api/v1/strategies", json={"definition": {"name": "x", "entry": []}}, headers=auth)
    assert bad.status_code == 422
