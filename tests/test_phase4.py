"""Phase 4 paper chain. The clock is the latest stored candle end."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from contracts.enums import AgentName, Exchange, Horizon, OrderStatus, Timeframe, TradingMode
from contracts.events import EventType
from contracts.fixtures import FIXTURE_AS_OF, candles_for, sample_agent_signal
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.market import Candle
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_decision import proposal_id_for
from core_fusion import fuse, select_signals
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_paper import run_paper_cycle

CASH = Decimal("1000000")


def test_confidence_uses_the_same_weights_as_the_signal() -> None:
    as_of = FIXTURE_AS_OF
    technical = _signal(signal_id="sig-technical", signal=0.5, confidence=0.8, timestamp=as_of)
    momentum = _signal(
        signal_id="sig-momentum",
        agent_name=AgentName.MOMENTUM,
        signal=1.0,
        confidence=0.4,
        timestamp=as_of,
    )
    aggregate = fuse(
        [technical, momentum],
        horizon=Horizon.SWING,
        as_of=as_of,
        weights={Horizon.SWING: {"technical": 1.0, "momentum": 3.0}},
    )
    assert aggregate is not None
    assert aggregate.aggregated_signal == 0.4
    assert aggregate.aggregated_confidence == 0.5
    assert aggregate.supporting_signal_ids == ("sig-momentum", "sig-technical")


def test_selection_keeps_the_newest_in_window_signal_per_agent() -> None:
    as_of = FIXTURE_AS_OF
    older = _signal(signal_id="sig-older", timestamp=as_of - timedelta(hours=2), valid_until=as_of + timedelta(hours=1))
    newer = _signal(signal_id="sig-newer", timestamp=as_of - timedelta(hours=1), valid_until=as_of + timedelta(hours=1))
    stale = _signal(signal_id="sig-stale", timestamp=as_of - timedelta(minutes=30), valid_until=as_of - timedelta(minutes=1))
    future = _signal(signal_id="sig-future", timestamp=as_of + timedelta(minutes=1), valid_until=as_of + timedelta(hours=2))
    selected = select_signals([older, newer, stale, future], horizon=Horizon.SWING, as_of=as_of)
    assert [item.signal_id for item in selected] == ["sig-newer"]


def test_paper_cycle_fills_once_and_ignores_late_signals(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    as_of = FIXTURE_AS_OF
    _store(repository, _signal(signal_id="sig-valid", timestamp=as_of - timedelta(hours=2), valid_until=as_of + timedelta(hours=6)))
    _store(
        repository,
        _signal(signal_id="sig-stale", timestamp=as_of - timedelta(hours=1), valid_until=as_of - timedelta(minutes=30)),
    )
    _store(
        repository,
        _signal(signal_id="sig-future", timestamp=as_of + timedelta(hours=1), valid_until=as_of + timedelta(hours=2)),
    )
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    proposals = repository.list_proposals()
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.proposal_id == proposal_id_for("RELIANCE", Horizon.SWING, as_of)
    assert proposal.timestamp == as_of
    assert proposal.timestamp.year == 2024
    assert proposal.supporting_signal_ids == ["sig-valid"]
    assert proposal.aggregated_signal == 0.4
    assert proposal.aggregated_confidence == 0.8
    assert proposal.quantity == 34
    assert proposal.entry_price == Decimal("2927.00")
    assert proposal.stop_loss == Decimal("2868.46")
    assert proposal.take_profit == Decimal("3044.08")
    assert proposal.metadata["stops_monitored"] is True
    looked_up = repository.get_by_symbol("RELIANCE")
    assert looked_up is not None
    assert repository.proposal_instrument_id(proposal.proposal_id) == looked_up.instrument_id
    decision = repository.risk_for_proposal(proposal.proposal_id)
    assert decision is not None
    assert decision.status.value == "APPROVED"
    assert all(check.passed for check in decision.checks)
    orders = repository.list_orders()
    assert len(orders) == 1
    assert orders[0].status == OrderStatus.OPEN
    assert repository.list_executions() == []
    later = as_of + timedelta(days=1)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("2930.00"),
                high=Decimal("2940.00"),
                low=Decimal("2920.00"),
                close=Decimal("2935.00"),
                volume=1000,
                start=later - timedelta(hours=6),
                end=later,
            )
        ]
    )
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    orders = repository.list_orders()
    assert orders[0].status == OrderStatus.FILLED
    assert orders[0].trading_mode == TradingMode.PAPER
    assert repository.order_instrument_id(orders[0].order_id) == looked_up.instrument_id
    fills = repository.list_executions()
    assert len(fills) == 1
    assert fills[0].fees > 0
    assert Decimal(str(fills[0].metadata["gross_price"])) == Decimal("2930.00")
    assert fills[0].price == Decimal("2930.00")
    position = repository.position_for("RELIANCE")
    assert position is not None
    assert position.quantity == 34
    snapshot = repository.latest_snapshot()
    assert snapshot is not None
    assert snapshot.equity < CASH
    event_types = _event_types(publisher)
    assert event_types.count(EventType.ORDER_FILLED.value) == 1
    assert EventType.ORDER_CREATED.value not in event_types
    assert EventType.DECISION_CREATED.value in event_types
    before = len(publisher.events)
    _store(
        repository,
        _signal(
            signal_id="sig-late",
            agent_name=AgentName.MOMENTUM,
            signal=1.0,
            confidence=0.9,
            timestamp=as_of,
            valid_until=as_of + timedelta(hours=6),
        ),
    )
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    assert repository.get_proposal(proposal.proposal_id).supporting_signal_ids == ["sig-valid"]  # type: ignore[union-attr]
    assert repository.execution_count() == 1
    assert len(publisher.events) == before


@pytest.mark.parametrize("mode", [TradingMode.LIVE, TradingMode.BACKTEST, TradingMode.SHADOW])
def test_non_paper_modes_are_rejected(repository: CoreRepository, mode: TradingMode) -> None:
    _prepare_buy(repository)
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=mode, starting_cash=CASH)
    decision = repository.list_risk_decisions()[0]
    assert decision.status.value == "REJECTED"
    assert any(check.name == "mode_is_paper" and not check.passed for check in decision.checks)
    assert repository.list_orders() == []
    assert repository.latest_snapshot() is None
    assert EventType.ORDER_FILLED.value not in _event_types(publisher)
    assert EventType.ORDER_CREATED.value not in _event_types(publisher)


def test_risk_rejects_insufficient_cash(repository: CoreRepository) -> None:
    _prepare_buy(repository)
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=Decimal("1"))
    decision = repository.list_risk_decisions()[0]
    assert decision.status.value == "REJECTED"
    assert any(check.name == "sufficient_cash" and not check.passed for check in decision.checks)
    assert repository.list_orders() == []
    assert repository.cash_balance(Decimal("1")) == Decimal("1")


def test_risk_rejects_notional_cap(repository: CoreRepository) -> None:
    end = FIXTURE_AS_OF + timedelta(days=1)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("150000"),
                high=Decimal("150000"),
                low=Decimal("150000"),
                close=Decimal("150000"),
                volume=1,
                start=end - timedelta(hours=6),
                end=end,
            )
        ]
    )
    _store(repository, _signal(signal_id="sig-expensive", timestamp=end, valid_until=end + timedelta(hours=1)))
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    decision = repository.list_risk_decisions()[0]
    assert decision.status.value == "REJECTED"
    assert any(check.name == "notional_cap" and not check.passed for check in decision.checks)
    assert any(check.name == "sufficient_cash" and check.passed for check in decision.checks)
    assert repository.list_orders() == []


def test_risk_rejects_sell_without_a_long(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    _store(repository, _signal(signal_id="sig-sell", signal=-0.8, confidence=0.9, timestamp=FIXTURE_AS_OF))
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    decision = repository.list_risk_decisions()[0]
    assert decision.status.value == "REJECTED"
    assert any(check.name == "no_short" and not check.passed for check in decision.checks)
    assert repository.held_quantity("RELIANCE") == 0
    assert repository.list_orders() == []
    assert repository.latest_snapshot() is None


def test_paper_routes_and_stop(repository: CoreRepository) -> None:
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
    assert client.get("/api/v1/portfolio").status_code == 401
    assert client.get("/api/v1/portfolio", headers=headers).json()["snapshot"] is None
    assert client.get("/api/v1/performance", headers=headers).status_code == 404
    assert client.get("/api/v1/risk/status", headers=headers).json()["kill_switch"] == "disarmed"
    stopped = client.post("/api/v1/paper/stop", headers=headers)
    assert stopped.json()["running"] is False
    assert stopped.json()["starting_cash"] == "1000000"
    _prepare_buy(repository)
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH)
    assert repository.list_proposals() == []
    client.post("/api/v1/paper/start", headers=headers)
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH)
    assert repository.execution_count() == 0
    assert client.get("/api/v1/orders", headers=headers).json()[0]["status"] == "OPEN"
    later = FIXTURE_AS_OF + timedelta(days=1)
    repository.upsert_candles(
        [
            Candle(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=Decimal("2930.00"),
                high=Decimal("2940.00"),
                low=Decimal("2920.00"),
                close=Decimal("2935.00"),
                volume=1000,
                start=later - timedelta(hours=6),
                end=later,
            )
        ]
    )
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH)
    assert repository.execution_count() == 1
    assert client.get("/api/v1/orders", headers=headers).json()[0]["status"] == "FILLED"
    assert client.get("/api/v1/positions", headers=headers).json()[0]["quantity"] == 34
    assert Decimal(client.get("/api/v1/trades", headers=headers).json()[0]["fees"]) > 0
    proposal_id = repository.list_proposals()[0].proposal_id
    assert client.get(f"/api/v1/decisions/{proposal_id}", headers=headers).status_code == 200
    assert client.get("/api/v1/paper/status", headers=headers).json()["running"] is True


def _prepare_buy(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    _store(repository, _signal(signal_id="sig-valid", timestamp=FIXTURE_AS_OF))


def _store(repository: CoreRepository, signal: AgentSignal) -> None:
    result = ingest_signal(
        repository,
        MemoryEventPublisher(),
        signal,
        mode=TradingMode.BACKTEST,
        now=signal.timestamp,
        replay_as_of=signal.timestamp,
        skew_seconds=5,
    )
    assert result.accepted, result.message


def _signal(**updates: object) -> AgentSignal:
    base = sample_agent_signal("RELIANCE")
    timestamp = updates.get("timestamp", FIXTURE_AS_OF)
    valid_until = updates.get("valid_until", timestamp + timedelta(hours=6))  # type: ignore[operator]
    payload = {
        "horizon": Horizon.SWING,
        "signal": 0.5,
        "confidence": 0.8,
        "timestamp": timestamp,
        "as_of": timestamp,
        "valid_until": valid_until,
    }
    payload.update(updates)
    return base.model_copy(update=payload)


def _event_types(publisher: MemoryEventPublisher) -> list[str]:
    return [json.loads(payload)["event_type"] for _, payload in publisher.events]
