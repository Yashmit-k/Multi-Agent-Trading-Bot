"""Applying a Strategy-lab strategy to paper trading: confirmation, replacing agent entries, managed exits."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import OrderStatus, Side, TradingMode
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher
from core_paper.cycle import run_paper_cycle
from core_paper.strategy_live import active_strategy
from test_execution_policy import CASH, DECISION, _arm, _bar, _daily

UTC = timezone.utc
SESSION = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)  # 09:20 IST, the entry window after DECISION

STRATEGY = {
    "name": "close above 300",
    "timeframe": "1d",
    "symbols": ["TCS"],
    "entry": {"items": [{"left": {"indicator": "close"}, "op": ">", "right": {"value": 300}}]},
    "stop": {"kind": "percent", "value": 5},
    "targets": [{"kind": "r_multiple", "value": 1, "fraction": 0.5}, {"kind": "r_multiple", "value": 2, "fraction": 0.5}],
    "breakeven_after_first_target": True,
    "sizing": {"kind": "notional", "value": 20000},
}


def _client(repository: CoreRepository) -> TestClient:
    from core_api.app import create_app
    from core_api.settings import Settings

    settings = Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core", internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER)
    return TestClient(create_app(settings, repository, MemoryEventPublisher()))


AUTH = {"Authorization": "Bearer core"}


def _ready(repository: CoreRepository) -> TestClient:
    _arm(repository, Decimal("442"))  # RELIANCE has an agent BUY signal
    _daily(repository, "TCS", Decimal("400"))  # daily close 400 at DECISION: the strategy's rule fires
    _history(repository, "TCS", days=30)
    for symbol in ("TCS", "RELIANCE"):
        instrument = repository.get_by_symbol(symbol)
        assert instrument is not None
        repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    return _client(repository)


def _history(repository: CoreRepository, symbol: str, *, days: int) -> None:
    """Earlier daily bars so the strategy has history to evaluate on."""
    from contracts.enums import Exchange, Timeframe
    from contracts.schemas.market import Candle

    candles = []
    for k in range(1, days + 1):
        end = DECISION - timedelta(days=k)
        candles.append(Candle(symbol=symbol, exchange=Exchange.NSE, timeframe=Timeframe.D1, open=Decimal("390"), high=Decimal("395"), low=Decimal("385"), close=Decimal("390"), volume=1000, start=end - timedelta(hours=6, minutes=15), end=end))
    repository.upsert_candles(candles)


def _cycle(repository: CoreRepository, now: datetime) -> None:
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH, now=now, enforce_entry_window=False)


def test_apply_needs_confirmation_and_a_live_compatible_strategy(repository: CoreRepository) -> None:
    client = _ready(repository)
    saved = client.post("/api/v1/strategies", json={"definition": STRATEGY}, headers=AUTH).json()
    assert client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={}, headers=AUTH).status_code == 422
    no_stop = client.post("/api/v1/strategies", json={"definition": {**STRATEGY, "stop": {"kind": "none"}, "targets": [{"kind": "percent", "value": 4}]}}, headers=AUTH).json()
    refused = client.post(f"/api/v1/strategies/{no_stop['strategy_id']}/apply", json={"confirm": True}, headers=AUTH)
    assert refused.status_code == 422 and "needs a stop" in str(refused.json())
    applied = client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={"confirm": True, "operator": "tester"}, headers=AUTH).json()
    assert applied["active"]["name"] == "close above 300" and applied["active"]["applied_by"] == "tester"
    # The applied copy is frozen: editing the saved strategy does not change what trades.
    client.post("/api/v1/strategies", json={"strategy_id": saved["strategy_id"], "definition": {**STRATEGY, "name": "edited"}}, headers=AUTH)
    assert client.get("/api/v1/strategies/active", headers=AUTH).json()["active"]["name"] == "close above 300"
    assert client.post("/api/v1/strategies/active/stop", json={"confirm": True}, headers=AUTH).json() == {"active": None}
    assert active_strategy(repository) is None


def test_applied_strategy_replaces_agent_entries_and_manages_its_exits(repository: CoreRepository) -> None:
    client = _ready(repository)
    saved = client.post("/api/v1/strategies", json={"definition": STRATEGY}, headers=AUTH).json()
    client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={"confirm": True}, headers=AUTH)
    _cycle(repository, DECISION + timedelta(hours=1))
    orders = repository.list_orders()
    assert {order.symbol for order in orders} == {"TCS"}  # the agents' RELIANCE BUY is not placed
    [entry_order] = orders
    proposal = repository.get_proposal(entry_order.proposal_id)
    assert proposal is not None and proposal.strategy_id == f"user:{saved['strategy_id']}"
    plan = proposal.metadata["plan"]
    stop, tp1, tp2 = plan["stop"], plan["targets"][0]["price"], plan["targets"][1]["price"]
    assert stop == 380 and tp1 == 420 and tp2 == 440  # entry 400, 5% stop, 1R and 2R
    _cycle(repository, DECISION + timedelta(hours=1))
    assert len(repository.list_orders()) == 1  # the same bar's signal is handled once

    # Next session: fill at the open, then TP1 (partial sell), then back to entry (breakeven on the rest).
    repository.upsert_candles([_bar(SESSION, open_=Decimal("400"), low=Decimal("399"), symbol="TCS")])
    _cycle(repository, SESSION + timedelta(minutes=5))
    position = repository.position_for("TCS")
    assert position is not None and position.quantity == entry_order.quantity
    filled = position.quantity
    tp_bar = SESSION + timedelta(minutes=5)
    repository.upsert_candles([_bar(tp_bar, open_=Decimal("410"), low=Decimal("409"), symbol="TCS").model_copy(update={"high": Decimal("421"), "close": Decimal("418")})])
    _cycle(repository, tp_bar + timedelta(minutes=5))
    sells = [order for order in repository.list_orders() if order.side == Side.SELL]
    assert [order.metadata["reason"] for order in sells] == ["strategy_target_1"]
    assert sells[0].quantity == filled // 2
    _cycle(repository, tp_bar + timedelta(minutes=5, seconds=30))  # settle the partial sell
    assert repository.position_for("TCS").quantity == filled - filled // 2  # type: ignore[union-attr]
    back = tp_bar + timedelta(minutes=5)
    repository.upsert_candles([_bar(back, open_=Decimal("405"), low=Decimal("399.5"), symbol="TCS")])
    _cycle(repository, back + timedelta(minutes=5))
    sells = sorted((order for order in repository.list_orders() if order.side == Side.SELL), key=lambda order: order.created_at)
    reasons = [order.metadata["reason"] for order in sells]
    assert reasons == ["strategy_target_1", "strategy_breakeven"]
    final = sells[-1]
    assert Decimal(str(final.metadata["level_price"])) == Decimal("400")  # breakeven, not the original 380 stop
    assert all(order.status != OrderStatus.REJECTED for order in repository.list_orders())


def test_intraday_limit_entries_expire_after_valid_bars(repository: CoreRepository) -> None:
    from contracts.enums import Exchange, Timeframe
    from contracts.schemas.market import Candle
    from core_paper.strategy_live import expire_strategy_orders

    client = _ready(repository)
    bars = []
    for k in range(40):  # 5-minute history ending at the 09:20 bar of the next session
        end = SESSION - timedelta(minutes=5 * (39 - k))
        bars.append(Candle(symbol="TCS", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("400"), high=Decimal("401"), low=Decimal("399"), close=Decimal("400"), volume=100, start=end - timedelta(minutes=5), end=end))
    repository.upsert_candles(bars)
    intraday = {
        **STRATEGY,
        "timeframe": "5m",
        "entry": {"items": [{"left": {"indicator": "close"}, "op": ">", "right": {"value": 300}}]},
        "entry_order": {"type": "limit", "price": {"indicator": "close", "scale": 0.99}, "valid_bars": 2},
        "square_off_intraday": True,
    }
    saved = client.post("/api/v1/strategies", json={"definition": intraday}, headers=AUTH).json()
    assert client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={"confirm": True}, headers=AUTH).status_code == 200
    _cycle(repository, SESSION + timedelta(minutes=1))
    [order] = [item for item in repository.list_orders() if item.symbol == "TCS"]
    assert order.status == OrderStatus.OPEN and order.limit_price == Decimal("396.00")  # 1% below the close: a retest
    assert expire_strategy_orders(repository, SESSION + timedelta(minutes=9)) == 0  # still within 2 bars
    assert expire_strategy_orders(repository, SESSION + timedelta(minutes=11)) == 1
    assert repository.list_orders()[0].status == OrderStatus.CANCELLED


def _apply(repository: CoreRepository, mode: str) -> TestClient:
    client = _ready(repository)
    repository.save_setting("risk", {"strategy_mode": mode}, updated_by="test", now=DECISION)
    saved = client.post("/api/v1/strategies", json={"definition": STRATEGY}, headers=AUTH).json()
    client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={"confirm": True}, headers=AUTH)
    return client


def _tcs_view(repository: CoreRepository, score: float) -> None:
    from test_phase4 import _signal, _store

    _store(repository, _signal(signal_id="sig-tcs-view", symbol="TCS", signal=score, timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))


def test_alongside_mode_lets_the_strategy_and_the_agents_both_trade(repository: CoreRepository) -> None:
    _apply(repository, "alongside")
    _cycle(repository, DECISION + timedelta(hours=1))
    assert {order.symbol for order in repository.list_orders() if order.side == Side.BUY} == {"TCS", "RELIANCE"}


def test_agents_agree_mode_blocks_a_strategy_entry_the_agents_are_bearish_on(repository: CoreRepository) -> None:
    _apply(repository, "agents_agree")
    _tcs_view(repository, -0.6)
    _cycle(repository, DECISION + timedelta(hours=1))
    assert repository.list_orders() == []  # TCS blocked by the agents; RELIANCE agent BUY not placed either


def test_agents_agree_mode_trades_when_the_agents_are_not_bearish(repository: CoreRepository) -> None:
    _apply(repository, "agents_agree")
    _tcs_view(repository, 0.4)
    _cycle(repository, DECISION + timedelta(hours=1))
    [order] = repository.list_orders()
    assert order.symbol == "TCS"
    proposal = repository.get_proposal(order.proposal_id)
    assert proposal.metadata["strategy_mode"] == "agents_agree" and proposal.metadata["agents_fused_signal"] > 0


def test_agents_agree_mode_sends_the_entry_to_the_portfolio_manager(repository: CoreRepository) -> None:
    from contracts.schemas.review import ProposalReview

    _apply(repository, "agents_agree")
    _tcs_view(repository, 0.4)
    now = DECISION + timedelta(hours=1)
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH, now=now, enforce_entry_window=False, manager_review=True)
    assert repository.list_orders() == []  # waiting for the manager
    [row] = repository.list_reviews()
    assert row["proposal_id"].startswith("strategy-")
    repository.complete_review(
        ProposalReview(review_id=row["review_id"], kind="pipeline", proposal_id=row["proposal_id"], symbol="TCS", verdict="VETO", size_fraction=0.0,
                       critique="The strategy's breakout fights a risk-off market.", reviewer="test", steps=2, timestamp=now),
        now,
    )
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH, now=now + timedelta(seconds=30), enforce_entry_window=False, manager_review=True)
    decision = repository.risk_for_proposal(row["proposal_id"])
    assert decision is not None and decision.status.value == "REJECTED"
    assert repository.list_orders() == []


def test_strategy_mode_setting_is_validated(repository: CoreRepository) -> None:
    from core_risk.settings import SettingsError, parse_settings

    assert parse_settings({"strategy_mode": "alongside"}).strategy_mode == "alongside"
    try:
        parse_settings({"strategy_mode": "yolo"})
    except SettingsError as exc:
        assert "strategy_mode" in exc.errors
    else:
        raise AssertionError("bad mode accepted")


def test_a_daily_signal_from_friday_is_still_fresh_on_monday_morning() -> None:
    from core_paper.strategy_engine import StrategyDefinition
    from core_paper.strategy_live import _fresh, last_closed_session

    definition = StrategyDefinition.model_validate(STRATEGY)
    friday_close = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    monday_morning = datetime(2026, 10, 12, 3, 55, tzinfo=UTC)  # 09:25 IST
    assert last_closed_session(monday_morning).isoformat() == "2026-10-09"
    assert _fresh(definition, friday_close, monday_morning)
    assert not _fresh(definition, friday_close - timedelta(days=1), monday_morning)  # Thursday's bar is stale


def test_the_strategys_own_position_limit_is_enforced_live(repository: CoreRepository) -> None:
    client = _ready(repository)
    _daily(repository, "RELIANCE", Decimal("442"))
    _history(repository, "RELIANCE", days=30)
    both = {**STRATEGY, "symbols": ["TCS", "RELIANCE"], "max_open_positions": 1}
    saved = client.post("/api/v1/strategies", json={"definition": both}, headers=AUTH).json()
    client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={"confirm": True}, headers=AUTH)
    _cycle(repository, DECISION + timedelta(hours=1))
    strategy_buys = [o for o in repository.list_orders() if o.side == Side.BUY and repository.get_proposal(o.proposal_id).metadata.get("source") == "strategy"]
    assert len(strategy_buys) == 1


def test_add_on_lifecycle_live(repository: CoreRepository) -> None:
    from contracts.enums import Exchange, Timeframe
    from contracts.schemas.market import Candle
    from core_paper.strategy_live import entry_plan

    client = _ready(repository)
    repository.save_setting("risk", {"min_reward_risk": "0.5"}, updated_by="test", now=DECISION)
    with_add = {
        **STRATEGY,
        "targets": [{"kind": "percent", "value": 5, "fraction": 1}],
        "breakeven_after_first_target": False,
        "add_on": {"when": {"items": [{"left": {"indicator": "close"}, "op": "<", "right": {"value": 390}}]}, "notional": 20000,
                   "target": {"kind": "percent", "value": 10}},
    }
    saved = client.post("/api/v1/strategies", json={"definition": with_add}, headers=AUTH).json()
    assert client.post(f"/api/v1/strategies/{saved['strategy_id']}/apply", json={"confirm": True}, headers=AUTH).status_code == 200
    _cycle(repository, DECISION + timedelta(hours=1))  # entry order on Monday's close (400)
    repository.upsert_candles([_bar(SESSION, open_=Decimal("400"), low=Decimal("399"), symbol="TCS")])
    _cycle(repository, SESSION + timedelta(minutes=5))
    first = repository.position_for("TCS")
    assert first is not None and first.quantity > 0
    initial = first.quantity
    # Tuesday closes at 385: the add-on rule fires; it fills Wednesday morning at 385
    tuesday_close = DECISION + timedelta(days=1)
    repository.upsert_candles([Candle(symbol="TCS", exchange=Exchange.NSE, timeframe=Timeframe.D1, open=Decimal("399"), high=Decimal("400"), low=Decimal("384"),
                                      close=Decimal("385"), volume=1000, start=tuesday_close - timedelta(hours=6, minutes=15), end=tuesday_close)])
    repository.upsert_candles([_bar(tuesday_close - timedelta(minutes=5), open_=Decimal("385"), low=Decimal("384.5"), symbol="TCS")])
    _cycle(repository, tuesday_close + timedelta(hours=1))
    add_orders = [o for o in repository.list_orders() if o.side == Side.BUY and repository.get_proposal(o.proposal_id).metadata.get("add_on")]
    assert len(add_orders) == 1
    assert add_orders[0].quantity >= 50
    wednesday = SESSION + timedelta(days=1)
    repository.upsert_candles([_bar(wednesday, open_=Decimal("385"), low=Decimal("384.5"), symbol="TCS")])
    _cycle(repository, wednesday + timedelta(minutes=5))
    position = repository.position_for("TCS")
    assert position.quantity == initial + add_orders[0].quantity
    execution, proposal = entry_plan(repository, "TCS")
    assert execution.quantity == initial and not proposal.metadata.get("add_on")  # the entry is still the first buy
    # The stop is now 5% below the average (~392.4 -> ~372.8), not 5% below 400 (380): a dip to 378 does not stop it out
    dip = wednesday + timedelta(minutes=5)
    repository.upsert_candles([_bar(dip, open_=Decimal("380"), low=Decimal("378"), symbol="TCS")])
    _cycle(repository, dip + timedelta(minutes=5))
    assert [o for o in repository.list_orders() if o.side == Side.SELL] == []
    # Target 1 (+5% on 400 = 420) sells only the initial shares; the added ones wait for their own target (+10% = 440)
    up = dip + timedelta(minutes=5)
    repository.upsert_candles([Candle(symbol="TCS", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("415"), high=Decimal("421"), low=Decimal("414"),
                                      close=Decimal("420"), volume=100, start=up, end=up + timedelta(minutes=5))])
    _cycle(repository, up + timedelta(minutes=5))
    [sell] = [o for o in repository.list_orders() if o.side == Side.SELL]
    assert sell.metadata["reason"] == "strategy_target_1" and sell.quantity == initial


def test_preflight_warns_about_settings_that_will_block_entries(repository: CoreRepository) -> None:
    client = _ready(repository)
    tight = {**STRATEGY, "stop": {"kind": "percent", "value": 10}, "targets": [{"kind": "percent", "value": 5, "fraction": 1}], "breakeven_after_first_target": False,
             "max_open_positions": 25}
    saved = client.post("/api/v1/strategies", json={"definition": tight}, headers=AUTH).json()
    body = client.get(f"/api/v1/strategies/{saved['strategy_id']}/preflight", headers=AUTH).json()
    text = " ".join(body["warnings"])
    assert body["problems"] == []
    assert "every entry will be rejected" in text and "open positions in total" in text and "mode:" in text
    no_stop = client.post("/api/v1/strategies", json={"definition": {**tight, "stop": {"kind": "none"}}}, headers=AUTH).json()
    assert client.get(f"/api/v1/strategies/{no_stop['strategy_id']}/preflight", headers=AUTH).json()["problems"]
