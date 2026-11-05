"""Momentum live, phase 2: the order planner, the dry-run route and the Telegram notices. Nothing is ever sent."""

import json
import logging
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from core_api.app import create_app
from core_api.live import notices_due
from core_api.live_plan import buy_limit, plan, sell_limit
from core_db.repository import CoreRepository
from core_db.session import create_schema
from test_momentum_live_api import HEADERS, AccountKite, _settings

PROPOSAL = {
    "decided_at_close": "2026-11-30",
    "trade_at_open_of": "2026-12-01",
    "ranking": [{"symbol": s, "close": c} for s, c in [("AAA", 100.0), ("BBB", 250.0), ("CCC", 40.0), ("DDD", 1200.0), ("EEE", 75.0)]],
    "closes": {"AAA": 100.0, "BBB": 250.0, "CCC": 40.0, "DDD": 1200.0, "EEE": 75.0, "OLD": 500.0},
}
SETTINGS = {"amount": 10000, "stocks": 3, "mode": "dry_run", "max_order": 25000}


def _account(cash: float, holdings: list[tuple[str, int]] = ()) -> dict:
    return {"holdings": [{"symbol": s, "quantity": q, "t1_quantity": 0, "close_price": None} for s, q in holdings], "positions": [], "cash": {"available": cash}}


def test_limits_stay_inside_the_band_on_a_tick() -> None:
    assert buy_limit(100.0) == 103.0 and sell_limit(100.0) == 97.0
    assert buy_limit(123.47) <= 123.47 * 1.03 and round(buy_limit(123.47) / 0.05, 6) % 1 == 0
    assert sell_limit(123.47) >= 123.47 * 0.97


def test_a_new_book_buys_the_top_n_within_the_amount() -> None:
    body = plan(PROPOSAL, SETTINGS, _account(50000), {})
    assert body["targets"] == ["AAA", "BBB", "CCC"]
    assert all(o["side"] == "BUY" for o in body["orders"])
    # Worst case at the limit prices never spends past the amount set, though the account holds more cash.
    worst = sum(o["quantity"] * o["limit"] for o in body["orders"]) + body["totals"]["charges"]
    assert worst <= 10000
    assert body["totals"]["spendable"] == 10000
    assert body["assumed_account"] is False


def test_only_ledger_shares_are_sold_and_a_short_account_is_reported() -> None:
    # OLD left the ranking: sold. MINE is in the account but not the ledger: never touched. AAA: ledger 30, account 20.
    account = _account(1000, [("OLD", 4), ("MINE", 50), ("AAA", 20)])
    body = plan(PROPOSAL, SETTINGS, account, {"OLD": 4, "AAA": 30})
    sides = {(o["side"], o["symbol"]) for o in body["orders"]}
    assert ("SELL", "OLD") in sides
    assert not any(o["symbol"] == "MINE" for o in body["orders"])
    assert any("AAA: the ledger has 30 but the account has 20" in w for w in body["warnings"])


def test_buys_shrink_to_fit_the_cash() -> None:
    body = plan(PROPOSAL, {**SETTINGS, "amount": 100000}, _account(3000), {})
    spend = sum(o["quantity"] * o["limit"] for o in body["orders"] if o["side"] == "BUY")
    assert spend + body["totals"]["charges"] <= 3000


def test_big_orders_are_blocked_and_zero_amount_buys_nothing() -> None:
    body = plan(PROPOSAL, {**SETTINGS, "amount": 90000, "max_order": 20000}, _account(90000), {})
    assert any(o["blocked"] for o in body["orders"]) and any("largest single order" in w for w in body["warnings"])
    assert body["totals"]["buy"] == sum(o["value"] for o in body["orders"] if o["side"] == "BUY" and not o["blocked"])
    assert plan(PROPOSAL, {**SETTINGS, "amount": 0}, None, {})["orders"] == []


def test_without_a_login_the_plan_assumes_an_empty_account() -> None:
    body = plan(PROPOSAL, SETTINGS, None, {})
    assert body["assumed_account"] is True and body["cash"] == 10000


def test_plan_route_is_off_by_default_then_logs_each_distinct_dry_run(tmp_path, monkeypatch) -> None:
    (tmp_path / "proposal-2026-10-30.json").write_text(json.dumps({**PROPOSAL, "decided_at_close": "2026-10-30"}))
    (tmp_path / "proposal-2026-11-30.json").write_text(json.dumps(PROPOSAL))
    monkeypatch.setenv("MOMENTUM_LIVE_PROPOSALS", str(tmp_path))
    kite = AccountKite()
    repository = CoreRepository(create_schema("sqlite://"))
    client = TestClient(create_app(_settings(), repository, kite_client=kite))
    assert client.get("/api/v1/live/plan").status_code == 401
    assert client.get("/api/v1/live/plan", headers=HEADERS).json() == {"mode": "off", "sent": False}
    client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"mode": "dry_run", "amount": 10000, "stocks": 5}}).raise_for_status()
    assumed = client.get("/api/v1/live/plan", headers=HEADERS).json()
    assert assumed["decided_at_close"] == "2026-11-30" and assumed["assumed_account"] is True and assumed["sent"] is False
    assert repository.list_system_events(event_type="momentum_live.dry_run") == []  # only real-account dry runs are logged
    client.get("/api/v1/zerodha/callback", params={"request_token": "t"})
    for _ in range(2):
        real = client.get("/api/v1/live/plan", headers=HEADERS).json()
    assert real["assumed_account"] is False
    assert len(repository.list_system_events(event_type="momentum_live.dry_run")) == 1
    assert "place_order" not in kite.calls


def test_notices_once_each_and_none_when_off() -> None:
    evening = datetime(2026, 11, 30, 14, 30, tzinfo=timezone.utc)  # 20:00 IST
    morning = datetime(2026, 12, 1, 3, 20, tzinfo=timezone.utc)  # 08:50 IST
    assert notices_due(evening, PROPOSAL, "off", set(), "https://x") == []
    due = notices_due(evening, PROPOSAL, "dry_run", set(), "https://x")
    assert [k for k, _ in due] == ["decided:2026-11-30"] and "nothing is sent" in due[0][1]
    assert [k for k, _ in notices_due(morning, PROPOSAL, "dry_run", {"decided:2026-11-30"}, "https://x")] == ["morning:2026-12-01"]
    assert notices_due(morning, PROPOSAL, "dry_run", {"decided:2026-11-30", "morning:2026-12-01"}, "https://x") == []
    late = datetime(2026, 12, 2, 3, 20, tzinfo=timezone.utc)
    assert notices_due(late, PROPOSAL, "dry_run", set(), "https://x") == []  # a past rebalance is not announced


def test_the_login_code_never_reaches_the_access_log() -> None:
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "GET", "/api/v1/zerodha/callback?request_token=SECRET123&x=1", "1.1", 200), None)
    for f in logging.getLogger("uvicorn.access").filters:
        f.filter(record)
    assert "SECRET123" not in record.getMessage() and "request_token=[redacted]&x=1" in record.getMessage()


def test_a_new_book_invests_nearly_all_of_the_amount() -> None:
    # Ten stocks priced like the 30 Oct 2026 decision, ₹1,00,000, empty account.
    prices = [536.40, 324.55, 767.45, 1796.10, 3094.80, 6838.00, 4111.60, 955.60, 843.30, 2341.60]
    proposal = {"decided_at_close": "2026-10-30", "trade_at_open_of": "2026-11-02",
                "ranking": [{"symbol": f"S{k}", "close": c} for k, c in enumerate(prices)], "closes": {f"S{k}": c for k, c in enumerate(prices)}}
    body = plan(proposal, {"amount": 100000, "stocks": 10, "mode": "dry_run", "max_order": 25000}, None, {})
    at_limit = sum(o["quantity"] * o["limit"] for o in body["orders"])
    assert 0.97 * 100000 <= at_limit and at_limit + body["totals"]["charges"] <= 100000
    assert len(body["orders"]) == 10


def test_an_empty_account_is_explained() -> None:
    body = plan(PROPOSAL, SETTINGS, _account(0), {})
    assert body["orders"] == []
    assert any("no cash available" in w for w in body["warnings"])
    assert any("Not enough cash" in w for w in plan(PROPOSAL, SETTINGS, _account(20), {})["warnings"])


INSTRUMENTS = {s: {"tick": 0.05, "last_price": 0.0} for s in ("AAA", "BBB", "CCC", "DDD", "EEE", "OLD")}


def test_limits_follow_each_stocks_price_step() -> None:
    body = plan(PROPOSAL, SETTINGS, _account(50000), {}, {**INSTRUMENTS, "AAA": {"tick": 0.10, "last_price": 0.0}, "CCC": {"tick": 0.01, "last_price": 0.0}})
    limits = {o["symbol"]: o["limit"] for o in body["orders"]}
    assert limits["AAA"] == 103.0 and round(limits["AAA"] / 0.10, 6) % 1 == 0
    assert limits["CCC"] == 41.2 and body["ticks"]["CCC"] == 0.01 and body["instruments_checked"] is True
    assert buy_limit(123.47, 0.10) == 127.1 and sell_limit(123.47, 0.10) == 119.8


def test_a_stock_off_the_eq_series_is_replaced_and_a_holding_kept() -> None:
    without_bbb = {k: v for k, v in INSTRUMENTS.items() if k not in ("BBB", "OLD")}
    body = plan(PROPOSAL, SETTINGS, _account(10000, [("OLD", 4)]), {"OLD": 4}, without_bbb)
    assert body["targets"] == ["AAA", "CCC", "DDD"]  # BBB skipped, DDD next in line
    assert not any(o["symbol"] == "OLD" for o in body["orders"])  # cannot be sold today: kept
    assert any("BBB: not trading in the EQ series today" in w for w in body["warnings"])
    assert any("OLD: not trading in the EQ series today, so it is kept" in w for w in body["warnings"])


def test_a_price_jump_like_a_split_is_left_out() -> None:
    split = {**INSTRUMENTS, "AAA": {"tick": 0.05, "last_price": 20.0}}  # 1:5 split: ₹100 became ₹20
    body = plan(PROPOSAL, SETTINGS, _account(10000), {}, split)
    assert "AAA" not in body["targets"] and any("AAA: price ₹20.00 is more than 30%" in w for w in body["warnings"])
    held = plan(PROPOSAL, SETTINGS, {"holdings": [{"symbol": "OLD", "quantity": 4, "t1_quantity": 0, "close_price": 100.0}], "positions": [], "cash": {"available": 1000}},
                {"OLD": 4}, INSTRUMENTS)  # OLD's account price ₹100 against a ₹500 decision close
    assert not any(o["symbol"] == "OLD" for o in held["orders"])


def test_without_the_instrument_list_the_plan_says_so() -> None:
    body = plan(PROPOSAL, SETTINGS, None, {})
    assert body["instruments_checked"] is False and any("instrument list was not available" in w for w in body["warnings"])
