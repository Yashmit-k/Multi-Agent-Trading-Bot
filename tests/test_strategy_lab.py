"""Strategy-lab backtester: entries, every exit type, partial targets, shorts, sizing, templates and the API."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient

from contracts.enums import Exchange, Timeframe, TradingMode
from contracts.schemas.market import Candle
from core_api.strategy_lab import TEMPLATES, BacktestRequest, StrategyDefinition, leg_charges, portfolio, run_strategy, simulate_symbol
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher
from core_paper.strategy_engine import Bars, Context

UTC = timezone.utc
DAY0 = datetime(2025, 1, 6, 3, 45, tzinfo=UTC)  # Monday 09:15 IST


def _bars(o, h, l, c, *, step=timedelta(days=1), start=datetime(2025, 1, 1, 3, 45, tzinfo=UTC)) -> Bars:  # type: ignore[no-untyped-def]
    n = len(c)
    starts = [start + step * i for i in range(n)]
    ends = [s + (timedelta(hours=6, minutes=15) if step == timedelta(days=1) else step) for s in starts]
    return Bars(starts, ends, *(np.array(x, dtype=float) for x in (o, h, l, c)), np.full(n, 1000.0))


def _flag_strategy(**extra) -> StrategyDefinition:  # type: ignore[no-untyped-def]
    """Entry when the close equals 100 exactly (a controllable trigger); no exit rule unless given."""
    base = {
        "name": "t",
        "entry": {"items": [{"left": {"indicator": "close"}, "op": "==", "right": {"value": 100}}]},
        "stop": {"kind": "percent", "value": 5},
        "targets": [{"kind": "percent", "value": 10, "fraction": 1}],
        "slippage_bps": 0,
    }
    base.update(extra)
    return StrategyDefinition.model_validate(base)


def _run(bars: Bars, strategy: StrategyDefinition):  # type: ignore[no-untyped-def]
    return simulate_symbol("T", Context(bars=bars, timeframe=strategy.timeframe, higher={}, cache={}), strategy, 0)


def test_market_entry_uses_the_live_limit_rule_and_target_exits() -> None:
    # Signal at bar 1 (close 100): limit 100.25. Bar 2 opens at 100.1, below the limit: fills at the open.
    bars = _bars([99, 100, 100.1, 104, 108], [99.5, 100.5, 101, 105, 111], [98.5, 99.5, 99.8, 103, 107], [99, 100, 100.5, 104, 110])
    [trade] = _run(bars, _flag_strategy())
    assert trade.entry_at == bars.end[2] and trade.entry_price == pytest.approx(100.1)
    assert trade.reason == "target" and trade.exit_price == pytest.approx(100.1 * 1.10)  # +10% from the 100.1 fill


def test_a_gap_above_the_live_limit_does_not_fill() -> None:
    bars = _bars([99, 100, 102, 104], [99.5, 100.5, 103, 105], [98.5, 99.5, 101, 103], [99, 100, 102, 104])
    assert _run(bars, _flag_strategy()) == []  # opened 1.75% above the signal close: the +0.25% limit never trades


def test_stop_first_on_ambiguous_bar_and_gap_through() -> None:
    both = _bars([99, 100, 100, 100], [99.5, 100.5, 120, 101], [98.5, 99.5, 80, 99], [99, 100, 100, 100])
    [trade] = _run(both, _flag_strategy())
    assert trade.reason == "stop" and trade.exit_price == pytest.approx(95.0)  # fill-bar touch counts as stopped
    gap = _bars([99, 100, 100, 90], [99.5, 100.5, 100.5, 91], [98.5, 99.5, 99.5, 89], [99, 100, 100.2, 90])
    [trade] = _run(gap, _flag_strategy())
    assert trade.reason == "stop" and trade.exit_price == pytest.approx(90.0)  # gapped through: filled at the open


def test_limit_entry_fills_on_touch_or_not_at_all() -> None:
    strategy = _flag_strategy(entry_order={"type": "limit", "price": {"indicator": "close", "scale": 0.98}, "valid_bars": 2})
    touched = _bars([99, 100, 99, 98, 99], [99.5, 100.5, 99.5, 99, 112], [98.5, 99.5, 97.5, 97, 98], [99, 100, 98.5, 98.5, 111])
    [trade] = _run(touched, strategy)
    assert trade.entry_price == pytest.approx(98.0) and trade.entry_at == touched.end[2]
    never = _bars([99, 100, 101, 102, 103], [99.5, 100.5, 101.5, 102.5, 103.5], [98.5, 99.5, 100.5, 101.5, 102.5], [99, 100, 101, 102, 103])
    assert _run(never, strategy) == []


def test_two_targets_then_breakeven() -> None:
    strategy = _flag_strategy(
        stop={"kind": "percent", "value": 5},
        targets=[{"kind": "r_multiple", "value": 1, "fraction": 0.5}, {"kind": "r_multiple", "value": 2, "fraction": 0.5}],
        breakeven_after_first_target=True,
        sizing={"kind": "notional", "value": 10000},
    )
    # entry 100 at bar 2 open; R = 5 -> TP1 105, TP2 110; bar 3 hits TP1; bar 4 falls back to 100 (breakeven).
    bars = _bars([99, 100, 100, 101, 104], [99.5, 100.5, 101, 106, 104.5], [98.5, 99.5, 99.5, 100.5, 99], [99, 100, 100.5, 104, 99.5])
    [trade] = _run(bars, strategy)
    assert [leg.reason for leg in trade.legs] == ["target", "breakeven"]
    assert trade.legs[0].price == pytest.approx(105) and trade.legs[1].price == pytest.approx(100)
    assert trade.legs[0].quantity + trade.legs[1].quantity == trade.quantity == 100


def test_trailing_stop_and_max_hold_and_exit_rule() -> None:
    trail = _flag_strategy(targets=[], trailing={"kind": "percent", "value": 3})
    bars = _bars([99, 100, 100, 104, 108, 107], [99.5, 100.5, 101, 105, 110, 108], [98.5, 99.5, 99.5, 103, 107, 105], [99, 100, 100.5, 104.5, 109, 105.5])
    [trade] = _run(bars, trail)
    assert trade.reason == "trailing_stop" and trade.exit_price == pytest.approx(110 * 0.97)  # 3% under the best high of earlier bars
    hold = _flag_strategy(targets=[], max_hold_bars=2)
    flat = _bars([99, 100, 100, 100, 100], [99.5, 100.5, 101, 101, 101], [98.5, 99.5, 99.5, 99.5, 99.5], [99, 100, 100.5, 100.4, 100.3])
    [trade] = _run(flat, hold)
    assert trade.reason == "max_hold" and trade.exit_at == flat.end[3]
    rule = _flag_strategy(targets=[], exit={"logic": "any", "items": [{"left": {"indicator": "close"}, "op": "<", "right": {"value": 100.45}}]})
    [trade] = _run(flat, rule)
    assert trade.reason == "exit_rule" and trade.exit_at == flat.end[4]  # rule true at bar 3 close, exits at bar 4 open


def test_intraday_square_off_and_short_side() -> None:
    step = timedelta(minutes=5)
    closes = [99, 100] + [100.0 + 0.01 * i for i in range(76)]
    bars = _bars([c - 0.01 for c in closes], [c + 0.05 for c in closes], [c - 0.05 for c in closes], closes, step=step, start=DAY0)
    long = _flag_strategy(timeframe="5m", targets=[], stop={"kind": "percent", "value": 5}, square_off_intraday=True)
    [trade] = _run(bars, long)
    assert trade.reason == "square_off" and trade.exit_at.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%H:%M") == "15:15"
    short = _flag_strategy(timeframe="5m", direction="short", targets=[{"kind": "percent", "value": 0.05, "fraction": 1}], stop={"kind": "percent", "value": 1}, square_off_intraday=True)
    falling = _bars([99, 100, 100, 99.9], [99.5, 100.5, 100.05, 99.95], [98.5, 99.5, 99.9, 99.8], [99, 100, 99.95, 99.85], step=step, start=DAY0)
    [trade] = _run(falling, short)
    assert trade.direction == "short" and trade.reason == "target" and trade.exit_price < trade.entry_price
    assert trade.net_pnl == pytest.approx((trade.entry_price - trade.exit_price) * trade.quantity - trade.charges)


def test_risk_percent_sizing_and_portfolio_slots() -> None:
    strategy = _flag_strategy(sizing={"kind": "risk_percent", "value": 1, "max_notional": 100000}, initial_cash=500000)
    bars = _bars([99, 100, 100, 100], [99.5, 100.5, 111, 101], [98.5, 99.5, 99.5, 99], [99, 100, 110, 100])
    [trade] = _run(bars, strategy)
    assert trade.quantity == 1000  # Rs 5,000 risk / Rs 5 stop distance, within the Rs 1 lakh cap
    trades = [trade, trade, trade]
    taken, skipped = portfolio(trades, _flag_strategy(max_open_positions=2, initial_cash=1_000_000))
    assert len(taken) == 2 and len(skipped) == 1


def test_charges_cnc_vs_mis() -> None:
    assert leg_charges(20000, 20000, "CNC") > leg_charges(20000, 20000, "MIS") > 0


@pytest.mark.parametrize("template", TEMPLATES, ids=[str(t["name"]) for t in TEMPLATES])
def test_every_template_validates_and_runs(template: dict) -> None:
    strategy = StrategyDefinition.model_validate(template)
    rng = np.random.default_rng(3)

    def loader(symbol, timeframe, start, end):  # type: ignore[no-untyped-def]
        if timeframe == "1d":
            n = 500
            ends = [datetime(2024, 1, 1, 10, 0, tzinfo=UTC) + timedelta(days=i) for i in range(n)]
            close = 100 * np.cumprod(1 + rng.normal(0.0005, 0.015, n))
            starts = [e - timedelta(hours=6, minutes=15) for e in ends]
        else:
            starts = [datetime(2025, 3, 3, 3, 45, tzinfo=UTC) + timedelta(days=d, minutes=5 * k) for d in range(20) for k in range(75)]
            close = 100 * np.cumprod(1 + rng.normal(0, 0.002, len(starts)))
            ends = [s + timedelta(minutes=5) for s in starts]
        open_ = np.concatenate([[close[0]], close[:-1]])
        return Bars(starts, ends, open_, np.maximum(open_, close) * 1.003, np.minimum(open_, close) * 0.997, close, rng.integers(1e4, 1e5, len(close)).astype(float))

    window = BacktestRequest(start=date(2024, 6, 1), end=date(2025, 5, 1)) if strategy.timeframe == "1d" else BacktestRequest(start=date(2025, 3, 5), end=date(2025, 3, 22))
    report = run_strategy(strategy, window, loader, ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"])
    assert report["metrics"]["trades"] >= 0 and report["equity_curve"]
    assert isinstance(report["rules"]["entry"], str)


def _client(repository: CoreRepository) -> TestClient:
    from core_api.app import create_app
    from core_api.settings import Settings

    settings = Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core", internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER)
    return TestClient(create_app(settings, repository, MemoryEventPublisher()))


def _daily_candles(repository: CoreRepository, symbol: str, closes: list[float], first: datetime) -> None:
    instrument = repository.upsert_instrument(symbol=symbol, exchange="NSE", trading_symbol=symbol)
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    candles = []
    for i, price in enumerate(closes):
        end = first + timedelta(days=i)
        candles.append(Candle(symbol=symbol, exchange=Exchange.NSE, timeframe=Timeframe.D1, open=Decimal(str(price)), high=Decimal(str(price + 1)), low=Decimal(str(price - 1)), close=Decimal(str(price)), volume=1000, start=end - timedelta(hours=6, minutes=15), end=end))
    repository.upsert_candles(candles)


def test_api_save_backtest_preview_scan_and_legacy(repository: CoreRepository) -> None:
    closes = [100.0] * 30 + [100 + i for i in range(1, 40)] + [139 - 2 * i for i in range(1, 30)]
    _daily_candles(repository, "TCS", closes, datetime(2025, 3, 1, 10, 0, tzinfo=UTC))
    client = _client(repository)
    auth = {"Authorization": "Bearer core"}
    definition = {
        "name": "cross",
        "symbols": ["TCS"],
        "entry": {"items": [{"left": {"indicator": "ema", "period": 3}, "op": "crosses_above", "right": {"indicator": "ema", "period": 6}}]},
        "exit": {"logic": "any", "items": [{"left": {"indicator": "ema", "period": 3}, "op": "crosses_below", "right": {"indicator": "ema", "period": 6}}]},
        "stop": {"kind": "percent", "value": 10},
        "targets": [],
    }
    saved = client.post("/api/v1/strategies", json={"definition": definition}, headers=auth).json()
    run = client.post(f"/api/v1/strategies/{saved['strategy_id']}/backtest", json={"start": "2025-03-01", "end": "2025-07-01"}, headers=auth)
    assert run.status_code == 200, run.text
    assert run.json()["metrics"]["trades"] >= 1
    preview = client.post("/api/v1/strategies/preview/backtest", json={"start": "2025-03-01", "end": "2025-07-01", "definition": definition}, headers=auth)
    assert preview.status_code == 200 and preview.json()["metrics"]["trades"] == run.json()["metrics"]["trades"]
    assert client.get(f"/api/v1/strategies/{saved['strategy_id']}/scan", headers=auth).json()["scanned"] == 1
    legacy = {**definition, "entry": definition["entry"]["items"], "exit": [], "stop_loss_pct": 5, "take_profit_pct": 10}
    assert client.post("/api/v1/strategies", json={"definition": legacy}, headers=auth).status_code == 200
    catalog = client.get("/api/v1/strategies/catalog", headers=auth).json()
    assert len(catalog["operands"]) >= 60 and len(catalog["templates"]) == len(TEMPLATES)
    assert client.post("/api/v1/strategies", json={"definition": {"name": "x", "entry": {"items": []}}}, headers=auth).status_code == 422
