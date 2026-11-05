"""Momentum live, phase 3 (services/quant/docs/momentum-live-plan.md): place one approved rebalance on Zerodha.

A run goes: sells first; then buys sized to the cash Zerodha shows; then one leftover round with the cash the fills
freed; anything still open at the deadline is cancelled; the strategy's ledger is updated from the actual fills.

Nothing is sent unless every gate passes: the server switch MOMENTUM_LIVE_ENABLED=true (off by default, set only by
the owner), Mode = Live, a fresh Zerodha login, the owner pressing Approve on exactly the orders shown, 09:15-15:00 IST
on an NSE trading day on or after the trade day, with Zerodha's instrument list for the day (price steps, EQ series), and at most one run per month-end decision. Each order is an NSE delivery (CNC)
limit order, no larger than the "largest single order" setting, in a stock of that month's ranking (buys) or the
ledger (sells); buys never exceed the approved budget. Orders go out at most one a second, and every run state is
saved after each order, so a restart picks up the run (and adopts an order placed just before a crash) instead of
placing it twice.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from core_api.live_plan import TICK, buy_limit, delivery_charges

RUN_KEY = "momentum_live_run"
RUN_EVENT = "momentum_live.run"
ORDER_EVENT = "momentum_live.order"
ENABLED_ENV = "MOMENTUM_LIVE_ENABLED"
TERMINAL = {"COMPLETE", "CANCELLED", "REJECTED", "ERROR"}
FINAL_PHASES = {"done", "stopped", "skipped"}
SELL_WAIT = timedelta(minutes=15)  # buys start once the sells are done, or after this long
IST = timedelta(hours=5, minutes=30)


class LiveRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "").strip().lower() == "true"


def ist(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(tzinfo=None) + IST


def order_digest(orders: list[dict]) -> str:
    """What the owner approves: every order that would be sent, exactly."""
    sent = sorted((o["side"], o["symbol"], int(o["quantity"]), float(o["limit"])) for o in orders if not o.get("blocked"))
    return hashlib.sha256(json.dumps(sent).encode()).hexdigest()[:20]


def check_approval(*, settings: dict, plan: dict, digest: str, run: dict | None, now: datetime, logged_in: bool, trading_day: bool) -> None:
    if not enabled():
        raise LiveRefused("server_switch_off")
    if settings.get("mode") != "live":
        raise LiveRefused("mode_not_live")
    if not logged_in or plan.get("assumed_account", True):
        raise LiveRefused("zerodha_login_required")
    if run is not None and run.get("decided") == plan["decided_at_close"]:
        raise LiveRefused("already_done_this_month")
    local = ist(now)
    # From 09:15: an order sent in the 09:00-09:08 pre-open can be rejected for a stock outside the call auction.
    if local.date().isoformat() < plan["trade_at_open_of"] or not trading_day or not ((9, 15) <= (local.hour, local.minute) < (15, 0)):
        raise LiveRefused("outside_trading_window")
    if not plan.get("instruments_checked"):
        raise LiveRefused("instrument_list_unavailable")
    if not [o for o in plan["orders"] if not o.get("blocked")]:
        raise LiveRefused("nothing_to_do")
    if order_digest(plan["orders"]) != digest:
        raise LiveRefused("plan_changed_reload")


def new_run(plan: dict, settings: dict, ledger: dict[str, int], now: datetime, *, skipped: bool = False) -> dict[str, Any]:
    local = ist(now)
    deadline_local = max(local.replace(hour=10, minute=30, second=0, microsecond=0), local + timedelta(minutes=60))
    deadline_local = min(deadline_local, local.replace(hour=15, minute=15, second=0, microsecond=0))
    orders = [
        {"key": f"main:{o['side']}:{o['symbol']}", "round": "main", "side": o["side"], "symbol": o["symbol"], "quantity": int(o["quantity"]),
         "limit": float(o["limit"]), "order_id": None, "status": "PENDING", "filled": 0, "average_price": None}
        for o in plan["orders"] if not o.get("blocked")
    ]
    closes = {s: float(c) for s, c in plan.get("closes", {}).items()}
    return {
        "decided": plan["decided_at_close"], "trade": plan["trade_at_open_of"], "tag": "mom" + plan["decided_at_close"].replace("-", "")[2:],
        "approved_at": now.isoformat(), "deadline": (deadline_local - IST).replace(tzinfo=timezone.utc).isoformat(),
        "phase": "skipped" if skipped else "selling", "budget": float(plan["totals"].get("spendable", 0.0)) if not skipped else 0.0,
        "max_order": float(settings["max_order"]), "targets": list(plan.get("targets", [])), "per_stock": float(plan.get("per_stock", 0.0)),
        "closes": closes, "ticks": {str(k): float(v) for k, v in plan.get("ticks", {}).items()}, "ledger_before": dict(ledger), "orders": [] if skipped else orders, "notes": [], "ledger_applied": skipped,
    }


class Executor:
    """Advances a run one step at a time. kite is the wrapper in core_market_data.kite_client (or a fake in tests)."""

    def __init__(self, kite: Any, save: Callable[[dict], None], log: Callable[[str, dict], None], update_ledger: Callable[[dict[str, int]], None], *,
                 sleep: Callable[[float], None] = time.sleep, notify: Callable[[str], Any] | None = None) -> None:
        self.kite, self.save, self.log, self.update_ledger, self.sleep, self.notify = kite, save, log, update_ledger, sleep, notify

    # ---- bookkeeping ----------------------------------------------------------------------------------------

    def refresh(self, run: dict) -> None:
        """Statuses and fills from Zerodha's order book; adopt an order placed just before a crash."""
        book = [row for row in self.kite.orders() if row.get("tag") == run["tag"]]
        by_id = {str(row["order_id"]): row for row in book}
        claimed = {o["order_id"] for o in run["orders"] if o["order_id"]}
        for o in run["orders"]:
            if o["order_id"] is None and o["status"] == "PLACING":
                twin = next((r for r in book if str(r["order_id"]) not in claimed and r.get("tradingsymbol") == o["symbol"]
                             and r.get("transaction_type") == o["side"] and int(r.get("quantity") or 0) == o["quantity"]), None)
                if twin is not None:
                    o["order_id"] = str(twin["order_id"])
                    claimed.add(o["order_id"])
                    run["notes"].append(f"adopted order {o['order_id']} for {o['side']} {o['symbol']} after a restart")
                else:
                    o["status"] = "PENDING"  # never reached Zerodha: place it again
            row = by_id.get(o["order_id"]) if o["order_id"] else None
            if row is not None:
                o["status"] = str(row.get("status", o["status"]))
                o["filled"] = int(row.get("filled_quantity") or 0)
                o["average_price"] = float(row["average_price"]) if row.get("average_price") else o["average_price"]

    def _gate(self, run: dict, o: dict) -> str | None:
        if not enabled():
            return "server switch off"
        if o["side"] == "BUY" and o["symbol"] not in run["targets"]:
            return "not in this month's ranking"
        if o["side"] == "SELL" and o["quantity"] > int(run["ledger_before"].get(o["symbol"], 0)) - self._sold(run, o["symbol"], exclude=o):
            return "more than the strategy holds"
        if o["quantity"] * o["limit"] > run["max_order"]:
            return "above the largest single order"
        if o["side"] == "BUY" and self._committed_buys(run, exclude=o) + o["quantity"] * o["limit"] > run["budget"] + self._sale_cash(run) + 1e-6:
            return "over the approved budget"
        return None

    @staticmethod
    def _sold(run: dict, symbol: str, exclude: dict | None = None) -> int:
        return sum(o["quantity"] if o["status"] not in TERMINAL else o["filled"] for o in run["orders"]
                   if o["side"] == "SELL" and o["symbol"] == symbol and o is not exclude and o["status"] != "PENDING")

    @staticmethod
    def _sale_cash(run: dict) -> float:
        return sum(o["filled"] * (o["average_price"] or o["limit"]) for o in run["orders"] if o["side"] == "SELL")

    @staticmethod
    def _committed_buys(run: dict, exclude: dict | None = None) -> float:
        """Money spent or still blocked by buys: filled at their price, open ones at their limit."""
        total = 0.0
        for o in run["orders"]:
            if o["side"] != "BUY" or o is exclude or o["status"] == "PENDING":
                continue
            total += o["filled"] * (o["average_price"] or o["limit"])
            if o["status"] not in TERMINAL:
                total += (o["quantity"] - o["filled"]) * o["limit"]
        return total

    def place(self, run: dict, o: dict) -> None:
        refused = self._gate(run, o)
        if refused:
            o["status"] = "ERROR"
            run["notes"].append(f"{o['side']} {o['symbol']} not sent: {refused}")
            self.save(run)
            return
        o["status"] = "PLACING"
        self.save(run)  # saved first: a crash after Zerodha accepts it is caught by refresh()'s adoption
        try:
            o["order_id"] = self.kite.place_limit_order(symbol=o["symbol"], side=o["side"], quantity=o["quantity"], price=o["limit"], tag=run["tag"])
            o["status"] = "OPEN"
        except Exception as exc:  # noqa: BLE001 - a rejected order is recorded, never retried blindly
            o["status"] = "ERROR"
            run["notes"].append(f"{o['side']} {o['symbol']} failed: {type(exc).__name__}: {str(exc)[:120]}")
        self.save(run)
        self.log(ORDER_EVENT, {"run": run["decided"], **o})
        self.sleep(1.0)  # at most one order a second

    def _cash(self) -> float:
        available = (self.kite.equity_margins().get("available") or {})
        return float(available.get("live_balance") or 0.0)

    # ---- the run --------------------------------------------------------------------------------------------

    def tick(self, run: dict, now: datetime) -> dict:
        if run["phase"] in FINAL_PHASES:
            return run
        self.refresh(run)
        if now >= datetime.fromisoformat(run["deadline"]) and run["phase"] != "closing":
            run["phase"] = "closing"
            run["notes"].append("deadline reached: cancelling what is still open")
        phase = run["phase"]
        mine = lambda side, rnd="main": [o for o in run["orders"] if o["side"] == side and o["round"] == rnd]  # noqa: E731
        if phase == "selling":
            for o in mine("SELL"):
                if o["status"] == "PENDING":
                    self.place(run, o)
            self.refresh(run)
            if all(o["status"] in TERMINAL for o in mine("SELL")) or now >= datetime.fromisoformat(run["approved_at"]) + SELL_WAIT:
                run["phase"] = "buying"
        elif phase == "buying":
            self._fit_buys_to_cash(run)
            for o in mine("BUY"):
                if o["status"] == "PENDING":
                    self.place(run, o)
            run["phase"] = "buying_wait"
        elif phase == "buying_wait":
            if all(o["status"] in TERMINAL for o in mine("BUY")) and all(o["status"] in TERMINAL for o in mine("SELL")):
                self._leftover_round(run)
                run["phase"] = "leftover_wait"
        elif phase == "leftover_wait":
            if all(o["status"] in TERMINAL for o in run["orders"]):
                self._finish(run, "done")
        elif phase == "closing":
            self._cancel_open(run)
            self.refresh(run)
            if all(o["status"] in TERMINAL for o in run["orders"]):
                self._finish(run, "done")
        self.save(run)
        return run

    def _fit_buys_to_cash(self, run: dict) -> None:
        pending = [o for o in run["orders"] if o["side"] == "BUY" and o["status"] == "PENDING"]
        allowed = min(self._cash(), run["budget"] + self._sale_cash(run))
        def cost() -> float:
            value = sum(o["quantity"] * o["limit"] for o in pending)
            return value + delivery_charges(value, 0.0)
        while pending and cost() > allowed:
            heavy = max(pending, key=lambda o: o["quantity"] * o["limit"])
            heavy["quantity"] -= 1
            if heavy["quantity"] == 0:
                heavy["status"] = "ERROR"
                run["notes"].append(f"BUY {heavy['symbol']} dropped: not enough cash")
                pending.remove(heavy)
        if pending and any(o["quantity"] for o in pending):
            run["notes"].append(f"buys sized to ₹{allowed:,.0f} of cash")

    def held_after(self, run: dict) -> dict[str, int]:
        held = dict(run["ledger_before"])
        for o in run["orders"]:
            held[o["symbol"]] = held.get(o["symbol"], 0) + (o["filled"] if o["side"] == "BUY" else -o["filled"])
        return {s: q for s, q in held.items() if q > 0}

    def _leftover_round(self, run: dict) -> None:
        """The cash the fills freed (buys filled below their limits) buys one more share at a time of the most
        underweight target, as in the paper trial; one round only."""
        spent = sum(o["filled"] * (o["average_price"] or o["limit"]) for o in run["orders"] if o["side"] == "BUY")
        left = min(self._cash(), run["budget"] + self._sale_cash(run) - spent - delivery_charges(spent, 0.0)) - 50
        held = self.held_after(run)
        targets = [s for s in run["targets"] if s in run["closes"] and s in held]  # only stocks the main round bought or kept
        value = {s: held.get(s, 0) * run["closes"][s] for s in targets}
        extra: dict[str, int] = {}
        while True:
            fits = [s for s in targets if buy_limit(run["closes"][s], run["ticks"].get(s, TICK)) * 1.0013 <= left]
            if not fits:
                break
            s = min(fits, key=lambda k: value[k])
            extra[s] = extra.get(s, 0) + 1
            value[s] += run["closes"][s]
            left -= buy_limit(run["closes"][s], run["ticks"].get(s, TICK)) * 1.0013
        for s, qty in sorted(extra.items()):
            o = {"key": f"leftover:BUY:{s}", "round": "leftover", "side": "BUY", "symbol": s, "quantity": qty, "limit": buy_limit(run["closes"][s], run["ticks"].get(s, TICK)),
                 "order_id": None, "status": "PENDING", "filled": 0, "average_price": None}
            run["orders"].append(o)
            self.place(run, o)

    def _cancel_open(self, run: dict) -> None:
        for o in run["orders"]:
            if o["order_id"] and o["status"] not in TERMINAL:
                try:
                    self.kite.cancel_order(o["order_id"])
                except Exception as exc:  # noqa: BLE001 - it may have just filled; refresh() will tell
                    run["notes"].append(f"cancel {o['symbol']} failed: {type(exc).__name__}")
            elif o["status"] == "PENDING":
                o["status"] = "CANCELLED"

    def _finish(self, run: dict, phase: str) -> None:
        run["phase"] = phase
        if not run["ledger_applied"]:
            self.update_ledger(apply_fills_to_ledger(run, run["ledger_before"]))
            run["ledger_applied"] = True
        bought = sum(o["filled"] * (o["average_price"] or 0) for o in run["orders"] if o["side"] == "BUY")
        sold = sum(o["filled"] * (o["average_price"] or 0) for o in run["orders"] if o["side"] == "SELL")
        unfilled = [f"{o['side']} {o['symbol']}" for o in run["orders"] if o["filled"] < o["quantity"]]
        run["summary"] = {"bought": round(bought, 2), "sold": round(sold, 2), "unfilled": unfilled}
        self.log(RUN_EVENT, run)
        if self.notify:
            text = f"StockX momentum: rebalance {phase}. Bought ₹{bought:,.0f}, sold ₹{sold:,.0f}."
            self.notify(text + (f" Not filled: {', '.join(unfilled)}." if unfilled else " Everything filled."))

    def stop(self, run: dict) -> dict:
        """The Stop button: cancel the strategy's open orders; the fills so far still count."""
        if run["phase"] in FINAL_PHASES:
            return run
        self.refresh(run)
        self._cancel_open(run)
        self.refresh(run)
        run["notes"].append("stopped by the owner")
        self._finish(run, "stopped")
        self.save(run)
        return run


def apply_fills_to_ledger(run: dict, ledger: dict[str, int]) -> dict[str, int]:
    """The ledger after a finished run, from the fills only. Applied once (run["ledger_applied"])."""
    held = dict(ledger)
    for o in run["orders"]:
        held[o["symbol"]] = held.get(o["symbol"], 0) + (o["filled"] if o["side"] == "BUY" else -o["filled"])
    return {s: q for s, q in held.items() if q > 0}
