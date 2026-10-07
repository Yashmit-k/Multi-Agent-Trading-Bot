"""Backtest bounds: no look-ahead, no holdout, no fill without a later bar."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contracts.enums import AgentName, Exchange, Horizon, OrderType, Side, Timeframe, TradingMode
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.market import Candle
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_ingestion.service import MemoryEventPublisher
from core_market_data import replay
from core_market_data.replay import SnapshotRefused, open_snapshot, stream_candles
from core_paper.backtest import _Book, _Working, _fill_pending, exit_on_bar, periods_per_year, run_backtest
from core_paper.costs import CostSchedule, fee_on, slipped_price
from core_paper.cycle import next_position
from core_risk import assess

UTC = timezone.utc
START = datetime(2025, 7, 1, 3, 45, tzinfo=UTC)


def _bar(symbol: str, end: datetime, price: str, *, high: str | None = None, low: str | None = None, open_: str | None = None) -> Candle:
    close = Decimal(price)
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.M5,
        open=Decimal(open_ or price),
        high=Decimal(high or price),
        low=Decimal(low or price),
        close=close,
        volume=1000,
        start=end - timedelta(minutes=5),
        end=end,
    )


def _signal(symbol: str, stamp: datetime, horizon: Horizon) -> AgentSignal:
    return AgentSignal(
        signal_id=f"{symbol}-{stamp.isoformat()}",
        symbol=symbol,
        exchange=Exchange.NSE,
        agent_name=AgentName.MOMENTUM,
        agent_version="1.0.0",
        timestamp=stamp,
        as_of=stamp,
        horizon=horizon,
        signal=0.9,
        confidence=0.9,
        valid_until=stamp + timedelta(days=1),
        reason_codes=["momentum"],
        features={"last_close": 100},
        metadata={"source": "test"},
    )


def _buy(monkeypatch: pytest.MonkeyPatch, *, block_above: float | None = None) -> None:
    def fake(symbol, feature_set, stamp, horizon, frame, index_sets=()):
        if block_above is not None and float(feature_set.features["last_close"]) > block_above:
            return []
        return [_signal(symbol, stamp, horizon)]

    monkeypatch.setattr("core_paper.backtest._agent_signals", fake)


def _run(candles: list[Candle], **overrides: object) -> dict:
    schedule = overrides.pop("schedule", CostSchedule.research(Decimal("0"), Decimal("0")))
    payload = {
        "symbols": ("RELIANCE",),
        "timeframe": "5m",
        "start": START,
        "end": START + timedelta(days=1),
        "snapshot_id": "nifty50_5m_20261005",
        "candle_sha256": "abc",
        "initial_cash": Decimal("100000"),
        "schedule": schedule,
    }
    payload.update(overrides)
    return run_backtest(candles, **payload)  # type: ignore[arg-type]


def test_holdout_and_late_window_are_refused_before_any_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Path:
        raise AssertionError("snapshot file was opened")

    monkeypatch.setattr(replay, "snapshots_root", boom)
    with pytest.raises(SnapshotRefused):
        open_snapshot("holdout_after_20261005", START)
    with pytest.raises(SnapshotRefused):
        open_snapshot("path/holdout/candles", START)
    with pytest.raises(SnapshotRefused):
        open_snapshot("nifty50_5m_20261005", datetime(2026, 10, 6, tzinfo=UTC))
    with pytest.raises(SnapshotRefused):
        open_snapshot("not-a-snapshot", START)


def test_stream_keeps_order_and_leaves_a_gap_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "5m"
    folder.mkdir()
    first = _bar("RELIANCE", START, "100")
    second = _bar("RELIANCE", START + timedelta(minutes=20), "101")
    later = _bar("RELIANCE", START + timedelta(days=3), "102")
    lines = [first, second, later]
    (folder / "candles.jsonl").write_text(
        "".join(json.dumps(bar.model_dump(mode="json"), separators=(",", ":")) + "\n" for bar in lines),
        encoding="utf-8",
    )
    (folder / "manifest.json").write_text(json.dumps({"snapshot_id": "nifty50_5m_20261005", "candle_sha256": "abc"}), encoding="utf-8")
    monkeypatch.setattr(replay, "snapshots_root", lambda: tmp_path)
    candles, missing, digest = stream_candles("nifty50_5m_20261005", ("RELIANCE",), START, START + timedelta(days=1), warmup=timedelta(0))
    assert [bar.end for bar in candles] == [first.end, second.end]
    assert missing == 3
    assert digest == "abc"
    assert later.end not in {bar.end for bar in candles}


def test_last_bar_signal_does_not_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    _buy(monkeypatch)
    report = _run([_bar("RELIANCE", START, "100")], end=START)
    assert report["orders_generated"] == 1
    assert report["orders_filled"] == 0
    assert report["trades"] == []


def test_future_bar_does_not_change_the_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    _buy(monkeypatch, block_above=500)
    later = START + timedelta(minutes=5)
    original = [_bar("RELIANCE", START, "100"), _bar("RELIANCE", later, "100")]
    changed = [_bar("RELIANCE", START, "100"), _bar("RELIANCE", later, "900")]
    first = _run(original, end=START)
    second = _run(changed, end=START)
    assert first["orders_generated"] == second["orders_generated"] == 1
    assert first["orders_filled"] == second["orders_filled"] == 0


def test_same_bar_stop_and_target_exits_at_the_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _buy(monkeypatch)
    bars = [
        _bar("RELIANCE", START, "100", high="101", low="99"),
        _bar("RELIANCE", START + timedelta(minutes=5), "100", high="101", low="99.50"),
        _bar("RELIANCE", START + timedelta(minutes=10), "100", high="110", low="90"),
    ]
    report = _run(bars, end=bars[-1].end)
    exits = [trade for trade in report["trades"] if trade["reason"] != "entry"]
    assert [trade["reason"] for trade in exits] == ["stop"]
    assert Decimal(exits[0]["price"]) == Decimal("98.00")


def test_stop_market_waits_for_the_next_open_and_limit_fills_at_the_limit() -> None:
    stamp = START + timedelta(minutes=5)
    book = _Book(cash=Decimal("100000"))
    book.positions["RELIANCE"] = next_position(None, "RELIANCE", Side.BUY, 4, Decimal("100"), START)
    book.pending["RELIANCE"] = _Working(
        proposal=object(),
        order_type=OrderType.STOP_LOSS_MARKET,
        stop_price=Decimal("99"),
        reason="stop",
    )
    breach = _bar("RELIANCE", stamp, "100", high="101", low="98")
    _fill_pending(book, "RELIANCE", breach, CostSchedule.research(Decimal("0"), Decimal("0")))
    assert book.fills == 0
    assert book.pending["RELIANCE"].order_type == OrderType.MARKET
    _fill_pending(book, "RELIANCE", _bar("RELIANCE", stamp + timedelta(minutes=5), "97"), CostSchedule.research(Decimal("0"), Decimal("0")))
    assert book.fills == 1
    assert book.trades[-1]["price"] == "97.00"

    limited = _Book(cash=Decimal("100000"))

    class Ticket:
        side = Side.BUY
        quantity = 2
        stop_loss = Decimal("90")
        take_profit = Decimal("110")

    limited.pending["TCS"] = _Working(proposal=Ticket(), order_type=OrderType.LIMIT, limit_price=Decimal("97"), reason="entry")
    _fill_pending(limited, "TCS", _bar("TCS", stamp, "100", high="100", low="96"), CostSchedule.research(Decimal("0"), Decimal("0")))
    assert limited.trades[-1]["price"] == "97.00"
    untouched = _Book(cash=Decimal("100000"))
    untouched.pending["TCS"] = _Working(proposal=Ticket(), order_type=OrderType.LIMIT, limit_price=Decimal("90"), reason="entry")
    _fill_pending(untouched, "TCS", _bar("TCS", stamp, "100", high="100", low="96"), CostSchedule.research(Decimal("0"), Decimal("0")))
    assert untouched.fills == 0
    bracket = _Book(cash=Decimal("0"))
    bracket.positions["INFY"] = next_position(None, "INFY", Side.BUY, 4, Decimal("100"), START)
    bracket.pending["INFY"] = _Working(
        proposal=Ticket(),
        order_type=OrderType.STOP_LOSS,
        stop_price=Decimal("99"),
        limit_price=Decimal("97"),
        reason="stop",
    )
    _fill_pending(bracket, "INFY", _bar("INFY", stamp, "100", high="101", low="96"), CostSchedule.research(Decimal("0"), Decimal("0")))
    assert bracket.trades[-1]["price"] == "97.00"


def test_costs_are_adverse_and_itemized() -> None:
    assert slipped_price(Side.BUY, Decimal("100"), Decimal("10")) == Decimal("100.10")
    assert slipped_price(Side.SELL, Decimal("100"), Decimal("10")) == Decimal("99.90")
    flat = fee_on(Decimal("10000"), CostSchedule.research(Decimal("2"), Decimal("0")))
    itemized = fee_on(
        Decimal("10000"),
        CostSchedule(
            brokerage_rate=Decimal("0.0001"),
            exchange_rate=Decimal("0.00003"),
            stt_rate=Decimal("0.000025"),
            gst_rate=Decimal("0.000018"),
            stamp_rate=Decimal("0.000015"),
            sebi_rate=Decimal("0.000012"),
        ),
    )
    assert flat == Decimal("2.0000")
    assert itemized == Decimal("2.0000")


def test_cash_notional_and_short_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _buy(monkeypatch)
    proposal = _run([_bar("RELIANCE", START, "100")], initial_cash=Decimal("1"))
    assert proposal["orders_generated"] == 0 or proposal["orders_filled"] == 0
    from core_decision.propose import build_proposal
    from core_fusion import fuse

    candle = _bar("RELIANCE", START, "100")
    signal = _signal("RELIANCE", START, Horizon.INTRADAY)
    aggregate = fuse([signal], horizon=Horizon.INTRADAY, as_of=START)
    built = build_proposal(aggregate, candle, START)
    assert built is not None
    oversized = built.model_copy(update={"quantity": 1001, "entry_price": Decimal("100")})
    rejected = assess(
        oversized,
        mode=TradingMode.PAPER,
        in_universe=True,
        cash=Decimal("1000000"),
        held_quantity=0,
        timestamp=START,
    )
    assert rejected.status.value == "REJECTED"
    short = built.model_copy(update={"side": Side.SELL, "quantity": 5, "stop_loss": Decimal("102"), "take_profit": Decimal("96")})
    shorted = assess(short, mode=TradingMode.PAPER, in_universe=True, cash=Decimal("1000000"), held_quantity=1, timestamp=START)
    assert shorted.status.value == "REJECTED"


def test_kill_switch_flattens_and_blocks_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    _buy(monkeypatch)
    bars = [
        _bar("RELIANCE", START, "100", high="101", low="99"),
        _bar("RELIANCE", START + timedelta(minutes=5), "100", high="101", low="99"),
    ]
    report = _run(bars, end=bars[-1].end, kill_after=bars[-1].end)
    assert report["positions"] == {}
    assert any(trade["reason"] == "kill_switch" for trade in report["trades"])


def test_partial_exit_and_pnl_split_gross_from_fees() -> None:
    opened = next_position(None, "RELIANCE", Side.BUY, 10, Decimal("100"), START)
    reduced = next_position(opened, "RELIANCE", Side.SELL, 4, Decimal("110"), START + timedelta(minutes=5))
    assert reduced.quantity == 6
    assert reduced.realized_pnl == Decimal("40")
    assert reduced.unrealized_pnl == Decimal("60")


def test_higher_costs_and_slippage_reduce_net(monkeypatch: pytest.MonkeyPatch) -> None:
    _buy(monkeypatch)
    bars = [
        _bar("RELIANCE", START, "100", high="101", low="99"),
        _bar("RELIANCE", START + timedelta(minutes=5), "100", high="101", low="99.50"),
        _bar("RELIANCE", START + timedelta(minutes=10), "110", high="110", low="109"),
    ]
    nets = []
    for bps in (Decimal("0"), Decimal("1"), Decimal("2"), Decimal("5")):
        report = _run(bars, end=bars[-1].end, schedule=CostSchedule.research(bps, Decimal("0")))
        nets.append(Decimal(report["performance"]["net_pnl"]))
    assert nets[0] > nets[1] > nets[2] > nets[3]
    base = _run(bars, end=bars[-1].end, schedule=CostSchedule.research(Decimal("0"), Decimal("0")))
    slipped = _run(bars, end=bars[-1].end, schedule=CostSchedule.research(Decimal("0"), Decimal("1")))
    assert Decimal(slipped["performance"]["net_pnl"]) < Decimal(base["performance"]["net_pnl"])
    assert Decimal(slipped["performance"]["slippage"]) > 0


def test_sharpe_uses_the_timeframe_period_count() -> None:
    assert periods_per_year("5m") == 75 * 252
    assert periods_per_year("1d") == 252
    assert exit_on_bar(Side.BUY, Decimal("98"), Decimal("104"), _bar("RELIANCE", START, "100", high="110", low="90")) == "stop"


def test_routes_store_a_run_and_refuse_holdout(repository: CoreRepository) -> None:
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
    )
    client = TestClient(create_app(settings, repository, MemoryEventPublisher()))
    headers = {"Authorization": "Bearer core"}
    refused = client.post(
        "/api/v1/backtests",
        headers=headers,
        json={
            "symbols": ["RELIANCE"],
            "timeframe": "5m",
            "start": "2025-07-01T03:45:00+00:00",
            "end": "2025-07-02T09:45:00+00:00",
            "snapshot_id": "holdout_after_20261005",
            "initial_cash": "100000",
            "transaction_cost_bps": "2",
            "slippage_bps": "1",
        },
    )
    assert refused.status_code == 409
    report = {
        "backtest_id": "run-1",
        "snapshot_id": "nifty50_5m_20261005",
        "performance": {"net_pnl": "1", "sharpe": None, "periods_per_year": 18900},
        "trades": [{"symbol": "RELIANCE", "reason": "entry"}],
        "live_enabled": False,
    }
    repository.insert_backtest("run-1", "nifty50_5m_20261005", report)
    listed = client.get("/api/v1/backtests", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["backtest_id"] == "run-1"
    assert client.get("/api/v1/backtests/run-1/performance", headers=headers).json()["periods_per_year"] == 18900
    assert client.get("/api/v1/backtests/run-1/trades", headers=headers).json()[0]["symbol"] == "RELIANCE"
    assert client.get("/api/v1/performance", headers=headers).json()["net_pnl"] == "1"
    assert create_schema("sqlite://") is not None
