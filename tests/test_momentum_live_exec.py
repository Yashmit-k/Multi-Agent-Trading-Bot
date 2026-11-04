"""Momentum live, phase 3: placing an approved rebalance, tested only against a fake Zerodha."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from core_api import live as live_module
from core_api.app import create_app
from core_api.live_exec import ENABLED_ENV, Executor, LiveRefused, check_approval, new_run, order_digest
from core_db.repository import CoreRepository
from core_db.session import create_schema
from test_momentum_live_api import HEADERS, _settings

UTC = timezone.utc
TRADE_MORNING = datetime(2026, 12, 1, 3, 35, tzinfo=UTC)  # 09:05 IST on the trade day


class FakeBroker:
    """An order book. behaviour per symbol: 'fill' (complete 0.5% under the limit), 'partial' (half, then open),
    'never' (stays open), 'reject'. Fills happen on the next look at the order book."""

    def __init__(self, cash: float, holdings: dict[str, int] | None = None, behaviour: dict[str, str] | None = None) -> None:
        self.cash = cash
        self.holding = dict(holdings or {})
        self.behaviour = behaviour or {}
        self.book: list[dict] = []
        self.placed: list[dict] = []
        self.cancelled: list[str] = []

    # account (read-only)
    def holdings(self) -> list[dict]:
        return [{"tradingsymbol": s, "quantity": q, "t1_quantity": 0, "close_price": None} for s, q in self.holding.items() if q > 0]

    def positions(self) -> dict:
        return {"net": []}

    def equity_margins(self) -> dict:
        return {"net": self.cash, "available": {"live_balance": self.cash}}

    def orders(self) -> list[dict]:
        for row in self.book:
            if row["status"] == "OPEN" and not row.get("_seen"):
                row["_seen"] = True
                how = self.behaviour.get(row["tradingsymbol"], "fill")
                if how == "never":
                    continue
                qty = row["quantity"] if how == "fill" else row["quantity"] // 2
                price = row["price"] * (0.995 if row["transaction_type"] == "BUY" else 1.005)
                row.update(filled_quantity=qty, average_price=price, status="COMPLETE" if qty == row["quantity"] else "OPEN")
                sign = 1 if row["transaction_type"] == "BUY" else -1
                self.cash -= sign * qty * price
                self.holding[row["tradingsymbol"]] = self.holding.get(row["tradingsymbol"], 0) + sign * qty
        return [{k: v for k, v in row.items() if not k.startswith("_")} for row in self.book]

    def place_limit_order(self, *, symbol: str, side: str, quantity: int, price: float, tag: str) -> str:
        if self.behaviour.get(symbol) == "reject":
            raise RuntimeError("InputException: insufficient funds")
        order_id = str(1000 + len(self.book))
        row = {"order_id": order_id, "tradingsymbol": symbol, "transaction_type": side, "quantity": quantity, "price": price, "tag": tag,
               "status": "OPEN", "filled_quantity": 0, "average_price": 0.0}
        self.book.append(row)
        self.placed.append({"symbol": symbol, "side": side, "quantity": quantity, "price": price})
        return order_id

    def cancel_order(self, order_id: str) -> None:
        self.cancelled.append(order_id)
        for row in self.book:
            if row["order_id"] == order_id and row["status"] == "OPEN":
                row["status"] = "CANCELLED"


PLAN = {
    "decided_at_close": "2026-11-30",
    "trade_at_open_of": "2026-12-01",
    "assumed_account": False,
    "targets": ["AAA", "BBB", "CCC"],
    "closes": {"AAA": 100.0, "BBB": 250.0, "CCC": 40.0, "OLD": 500.0},
    "per_stock": 3300.0,
    "orders": [
        {"side": "SELL", "symbol": "OLD", "quantity": 4, "limit": 485.0, "blocked": None},
        {"side": "BUY", "symbol": "AAA", "quantity": 32, "limit": 103.0, "blocked": None},
        {"side": "BUY", "symbol": "BBB", "quantity": 12, "limit": 257.5, "blocked": None},
        {"side": "BUY", "symbol": "CCC", "quantity": 80, "limit": 41.2, "blocked": None},
    ],
    "totals": {"spendable": 8000.0},
}
SETTINGS = {"amount": 10000, "stocks": 3, "mode": "live", "max_order": 25000}


@pytest.fixture
def switch_on(monkeypatch):
    monkeypatch.setenv(ENABLED_ENV, "true")


def _executor(broker, sleeps=None, ledger_out=None, events=None, notes=None):
    saved = {}
    return Executor(
        broker,
        save=lambda run: saved.update(run=json.loads(json.dumps(run))),
        log=lambda kind, payload: (events if events is not None else []).append(kind),
        update_ledger=lambda ledger: (ledger_out if ledger_out is not None else {}).update(ledger=ledger),
        sleep=lambda s: (sleeps if sleeps is not None else []).append(s),
        notify=lambda text: (notes if notes is not None else []).append(text),
    ), saved


def _run_to_end(executor, run, start=TRADE_MORNING, steps=12):
    now = start
    for _ in range(steps):
        executor.tick(run, now)
        if run["phase"] in ("done", "stopped"):
            break
        now += timedelta(minutes=1)
    return run


# ---- the gates ------------------------------------------------------------------------------------------------


def _check(**changes):
    args = {"settings": SETTINGS, "plan": PLAN, "digest": order_digest(PLAN["orders"]), "run": None, "now": TRADE_MORNING, "logged_in": True, "trading_day": True}
    args.update(changes)
    check_approval(**args)


def test_every_gate_refuses_on_its_own(switch_on, monkeypatch) -> None:
    _check()  # all gates pass
    cases = {
        "mode_not_live": {"settings": {**SETTINGS, "mode": "dry_run"}},
        "zerodha_login_required": {"logged_in": False},
        "already_done_this_month": {"run": {"decided": "2026-11-30"}},
        "outside_trading_window": {"now": datetime(2026, 12, 1, 3, 25, tzinfo=UTC)},  # 08:55 IST
        "plan_changed_reload": {"digest": "something-else"},
        "nothing_to_do": {"plan": {**PLAN, "orders": [{**PLAN["orders"][0], "blocked": "above"}]}},
    }
    for code, change in cases.items():
        with pytest.raises(LiveRefused) as refused:
            _check(**change)
        assert refused.value.code == code
    with pytest.raises(LiveRefused, match="outside_trading_window"):
        _check(trading_day=False)
    with pytest.raises(LiveRefused, match="outside_trading_window"):
        _check(now=datetime(2026, 11, 30, 5, 0, tzinfo=UTC))  # the decision day itself, before the trade day
    monkeypatch.setenv(ENABLED_ENV, "false")
    with pytest.raises(LiveRefused, match="server_switch_off"):
        _check()


# ---- a run ------------------------------------------------------------------------------------------------------


def test_a_run_sells_first_then_buys_then_fills_the_leftover_and_updates_the_ledger(switch_on) -> None:
    broker = FakeBroker(cash=8000.0, holdings={"OLD": 4, "MINE": 50})
    ledger, events, notes, sleeps = {}, [], [], []
    executor, saved = _executor(broker, sleeps, ledger, events, notes)
    run = new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING)
    executor.tick(run, TRADE_MORNING)
    assert [p["side"] for p in broker.placed] == ["SELL"]  # buys wait for the sells
    _run_to_end(executor, run)
    sides = [(p["side"], p["symbol"]) for p in broker.placed]
    assert sides[:4] == [("SELL", "OLD"), ("BUY", "AAA"), ("BUY", "BBB"), ("BUY", "CCC")]
    assert any(p.get("symbol") for p in broker.placed[4:])  # the leftover round bought more with the cash the fills freed
    assert run["phase"] == "done" and run["ledger_applied"]
    assert "OLD" not in ledger["ledger"] and ledger["ledger"]["AAA"] >= 32 and "MINE" not in ledger["ledger"]
    assert broker.holding["MINE"] == 50  # never touched
    assert sleeps and all(s == 1.0 for s in sleeps) and len(sleeps) == len(broker.placed)
    assert "momentum_live.run" in events and notes and "Everything filled" in notes[0]
    bought = sum(p["quantity"] * p["price"] for p in broker.placed if p["side"] == "BUY")
    assert bought <= 8000.0 + 4 * 485.0  # never past the approved budget plus the sale money
    assert saved["run"]["phase"] == "done"


def test_unfilled_orders_are_cancelled_at_the_deadline_and_partial_fills_count(switch_on) -> None:
    broker = FakeBroker(cash=8000.0, holdings={"OLD": 4}, behaviour={"BBB": "never", "CCC": "partial"})
    ledger, notes = {}, []
    executor, _ = _executor(broker, ledger_out=ledger, notes=notes)
    run = new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING)
    _run_to_end(executor, run, steps=5)
    assert run["phase"] == "buying_wait"  # BBB and CCC still open
    late = datetime.fromisoformat(run["deadline"]) + timedelta(seconds=1)
    executor.tick(run, late)
    executor.tick(run, late + timedelta(minutes=1))
    assert run["phase"] == "done" and len(broker.cancelled) == 2
    assert ledger["ledger"].get("BBB") is None and ledger["ledger"]["CCC"] == 40
    assert "Not filled: BUY BBB, BUY CCC" in notes[0]


def test_buys_shrink_to_the_cash_zerodha_shows(switch_on) -> None:
    broker = FakeBroker(cash=3000.0, holdings={"OLD": 4}, behaviour={"OLD": "never"})
    executor, _ = _executor(broker)
    run = new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING)
    executor.tick(run, TRADE_MORNING)
    executor.tick(run, TRADE_MORNING + timedelta(minutes=16))  # sell still open after 15 minutes: buys go ahead
    executor.tick(run, TRADE_MORNING + timedelta(minutes=17))
    spend = sum(p["quantity"] * p["price"] for p in broker.placed if p["side"] == "BUY")
    assert 0 < spend <= 3000.0


def test_a_rejected_order_is_recorded_not_retried(switch_on) -> None:
    broker = FakeBroker(cash=8000.0, holdings={"OLD": 4}, behaviour={"AAA": "reject"})
    executor, _ = _executor(broker)
    run = _run_to_end(executor, new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING))
    assert not any(p["symbol"] == "AAA" for p in broker.placed)
    assert any("BUY AAA failed: RuntimeError" in n for n in run["notes"]) and run["phase"] == "done"


def test_guards_refuse_overselling_off_switch_and_oversized_orders(switch_on, monkeypatch) -> None:
    broker = FakeBroker(cash=8000.0, holdings={"OLD": 10})
    executor, _ = _executor(broker)
    run = new_run(PLAN, SETTINGS, {"OLD": 2}, TRADE_MORNING)  # the ledger only owns 2 of OLD
    executor.tick(run, TRADE_MORNING)
    assert broker.placed == [] and "more than the strategy holds" in run["notes"][0]
    big = new_run({**PLAN, "decided_at_close": "2026-12-31"}, {**SETTINGS, "max_order": 1000}, {"OLD": 4}, TRADE_MORNING)
    executor.tick(big, TRADE_MORNING)
    assert broker.placed == [] and "above the largest single order" in big["notes"][0]
    monkeypatch.setenv(ENABLED_ENV, "false")
    off = new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING)
    executor.tick(off, TRADE_MORNING)
    assert broker.placed == [] and "server switch off" in off["notes"][0]


def test_an_order_placed_just_before_a_crash_is_adopted_not_placed_twice(switch_on) -> None:
    broker = FakeBroker(cash=8000.0, holdings={"OLD": 4})
    executor, _ = _executor(broker)
    run = new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING)
    broker.place_limit_order(symbol="OLD", side="SELL", quantity=4, price=485.0, tag=run["tag"])  # reached Zerodha...
    run["orders"][0]["status"] = "PLACING"  # ...but the process died before saving the order id
    executor.tick(run, TRADE_MORNING)
    assert len([p for p in broker.placed if p["symbol"] == "OLD"]) == 1
    assert run["orders"][0]["order_id"] == "1000" and any("adopted order 1000" in n for n in run["notes"])


def test_stop_cancels_open_orders_and_keeps_the_fills(switch_on) -> None:
    broker = FakeBroker(cash=8000.0, holdings={"OLD": 4}, behaviour={"OLD": "partial"})
    ledger = {}
    executor, _ = _executor(broker, ledger_out=ledger)
    run = new_run(PLAN, SETTINGS, {"OLD": 4}, TRADE_MORNING)
    executor.tick(run, TRADE_MORNING)
    executor.stop(run)
    assert run["phase"] == "stopped" and broker.cancelled == ["1000"]
    assert ledger["ledger"] == {"OLD": 2}  # half was sold before the stop


# ---- the routes -------------------------------------------------------------------------------------------------


class RouteBroker(FakeBroker):
    def login_url(self) -> str:
        return "https://kite.zerodha.com/connect/login?api_key=test"

    def generate_session(self, request_token: str) -> dict:
        return {"access_token": "access-token"}

    def use_access_token(self, token: str) -> None:
        pass


def _client(tmp_path, monkeypatch, broker):
    proposal = {"decided_at_close": "2026-11-30", "trade_at_open_of": "2026-12-01",
                "ranking": [{"symbol": s, "close": c} for s, c in [("AAA", 100.0), ("BBB", 250.0), ("CCC", 40.0), ("DDD", 400.0), ("EEE", 75.0)]],
                "closes": {"AAA": 100.0, "BBB": 250.0, "CCC": 40.0, "DDD": 400.0, "EEE": 75.0}}
    (tmp_path / "proposal-2026-11-30.json").write_text(json.dumps(proposal))
    monkeypatch.setenv("MOMENTUM_LIVE_PROPOSALS", str(tmp_path))
    monkeypatch.setattr(live_module, "nse_trading_day", lambda now: True)
    repository = CoreRepository(create_schema("sqlite://"))
    app = create_app(_settings(), repository, kite_client=broker)
    app.state.momentum_live_clock = lambda: TRADE_MORNING
    app.state.momentum_live_sleep = lambda s: None
    client = TestClient(app)
    client.get("/api/v1/zerodha/callback", params={"request_token": "t"})
    return client, app, repository


def test_live_mode_needs_the_server_switch(tmp_path, monkeypatch) -> None:
    client, _, _ = _client(tmp_path, monkeypatch, RouteBroker(cash=20000.0))
    refused = client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"mode": "live"}})
    assert refused.status_code == 422 and "MOMENTUM_LIVE_ENABLED" in refused.json()["detail"]["errors"]["mode"]
    assert client.get("/api/v1/live/settings", headers=HEADERS).json()["modes"] == ["off", "dry_run"]
    monkeypatch.setenv(ENABLED_ENV, "true")
    assert client.get("/api/v1/live/settings", headers=HEADERS).json()["modes"] == ["off", "dry_run", "live"]


def test_approve_places_exactly_the_orders_shown_once(tmp_path, monkeypatch, switch_on) -> None:
    broker = RouteBroker(cash=20000.0)
    client, app, repository = _client(tmp_path, monkeypatch, broker)
    client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"mode": "live", "amount": 10000, "stocks": 5}}).raise_for_status()
    plan = client.get("/api/v1/live/plan", headers=HEADERS).json()
    assert plan["live_switch"] is True and plan["run_phase"] is None and broker.placed == []
    stale = client.post("/api/v1/live/approve", headers=HEADERS, json={"digest": "old"})
    assert stale.status_code == 409 and stale.json()["detail"] == "plan_changed_reload" and broker.placed == []
    approved = client.post("/api/v1/live/approve", headers=HEADERS, json={"digest": plan["digest"]})
    assert approved.status_code == 200 and approved.json()["run"]["phase"] in ("selling", "buying")
    for _ in range(8):
        app.state.momentum_live_advance()
    run = client.get("/api/v1/live/run", headers=HEADERS).json()["run"]
    assert run["phase"] == "done"
    main_buys = sorted((p["symbol"], p["quantity"]) for p in broker.placed[:5])
    assert main_buys == sorted((o["symbol"], o["quantity"]) for o in plan["orders"])
    again = client.post("/api/v1/live/approve", headers=HEADERS, json={"digest": plan["digest"]})
    assert again.status_code == 409 and again.json()["detail"] == "already_done_this_month"
    assert repository.get_setting("momentum_live_ledger")["payload"]


def test_skip_and_stop(tmp_path, monkeypatch, switch_on) -> None:
    broker = RouteBroker(cash=20000.0)
    client, _, _ = _client(tmp_path, monkeypatch, broker)
    client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"mode": "live", "amount": 10000, "stocks": 5}}).raise_for_status()
    assert client.post("/api/v1/live/skip", headers=HEADERS, json={}).json()["run"]["phase"] == "skipped"
    plan = client.get("/api/v1/live/plan", headers=HEADERS).json()
    assert plan["run_phase"] == "skipped"
    assert client.post("/api/v1/live/approve", headers=HEADERS, json={"digest": plan["digest"]}).json()["detail"] == "already_done_this_month"
    client.post("/api/v1/live/stop", headers=HEADERS, json={})
    assert client.get("/api/v1/live/settings", headers=HEADERS).json()["settings"]["mode"] == "off"
    assert broker.placed == []
