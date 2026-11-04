"""Momentum live (services/quant/docs/momentum-live-plan.md): the owner's Zerodha account (read-only), the settings,
the month's planned orders, and the owner's Approve / Skip / Stop of a rebalance.

Orders are placed only by core_api.live_exec, after Approve and only when every gate there passes (the server switch
MOMENTUM_LIVE_ENABLED is off by default). Every route needs the Core token; the public proxy forwards them only for a
signed-in operator, because the account and the amount invested are private.
"""

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from core_api.live_exec import FINAL_PHASES, RUN_EVENT, RUN_KEY, Executor, LiveRefused, check_approval, enabled, new_run, order_digest
from core_db.repository import CoreRepository

SETTING_KEY = "momentum_live"
LEDGER_KEY = "momentum_live_ledger"  # shares the strategy bought itself; written only from real fills (phase 3)
CHANGE_EVENT = "momentum_live.settings_changed"
DRY_RUN_EVENT = "momentum_live.dry_run"
DEFAULTS: dict[str, object] = {"amount": 0, "stocks": 10, "mode": "off", "max_order": 25000}
MODES = ("off", "dry_run")  # plus "live" while the server switch MOMENTUM_LIVE_ENABLED is on


def modes() -> tuple[str, ...]:
    from core_api.live_exec import enabled

    return (*MODES, "live") if enabled() else MODES
LIMITS = {"amount": (0, 10_000_000), "stocks": (5, 50), "max_order": (1_000, 1_000_000)}


def proposals_dir() -> Path:
    # The momentum-trial volume, mounted read-only into Core; the trial writes live/proposal-<close>.json.
    return Path(os.environ.get("MOMENTUM_LIVE_PROPOSALS", "/momentum-trial/momentum-trial/live"))


def latest_proposal(folder: Path | None = None) -> dict | None:
    files = sorted((folder or proposals_dir()).glob("proposal-*.json"))
    return json.loads(files[-1].read_text()) if files else None


def load_ledger(repository: CoreRepository) -> dict[str, int]:
    stored = repository.get_setting(LEDGER_KEY)
    return {str(k): int(v) for k, v in ((stored or {}).get("payload") or {}).items()}


def load_settings(repository: CoreRepository) -> dict[str, object]:
    stored = repository.get_setting(SETTING_KEY)
    return {**DEFAULTS, **(stored["payload"] if stored else {})}


def parse_settings(values: dict[str, Any]) -> tuple[dict[str, object], dict[str, str]]:
    """Merged settings and a field -> error map (empty when valid)."""
    clean: dict[str, object] = {}
    errors: dict[str, str] = {}
    for key, (low, high) in LIMITS.items():
        raw = values.get(key)
        try:
            number = int(str(raw).replace(",", "").strip())
        except ValueError:
            errors[key] = "must be a whole number"
            continue
        if not low <= number <= high:
            errors[key] = f"must be between {low:,} and {high:,}"
            continue
        clean[key] = number
    mode = str(values.get("mode", "")).strip()
    if mode not in modes():
        errors["mode"] = "live needs the server switch MOMENTUM_LIVE_ENABLED=true" if mode == "live" else f"must be one of {', '.join(modes())}"
    else:
        clean["mode"] = mode
    return clean, errors


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def summarize_account(holdings: list[dict], positions: dict, margins: dict, orders: list[dict]) -> dict[str, object]:
    """The parts of Kite's replies the site shows; raw replies are never passed on."""
    held = [
        {
            "symbol": str(row.get("tradingsymbol", "")),
            "exchange": str(row.get("exchange", "")),
            "quantity": int(row.get("quantity") or 0),
            "t1_quantity": int(row.get("t1_quantity") or 0),  # bought on the last session, not yet settled
            "average_price": _number(row.get("average_price")),
            "last_price": _number(row.get("last_price")),
            "close_price": _number(row.get("close_price")),
        }
        for row in holdings
        if int(row.get("quantity") or 0) + int(row.get("t1_quantity") or 0) > 0
    ]
    today = [
        {
            "symbol": str(row.get("tradingsymbol", "")),
            "product": str(row.get("product", "")),
            "quantity": int(row.get("quantity") or 0),
            "average_price": _number(row.get("average_price")),
        }
        for row in (positions.get("net") or [])
        if int(row.get("quantity") or 0) != 0
    ]
    available = margins.get("available") or {}
    order_rows = [
        {
            "order_id": str(row.get("order_id", "")),
            "symbol": str(row.get("tradingsymbol", "")),
            "side": str(row.get("transaction_type", "")),
            "quantity": int(row.get("quantity") or 0),
            "filled_quantity": int(row.get("filled_quantity") or 0),
            "price": _number(row.get("price")),
            "average_price": _number(row.get("average_price")),
            "status": str(row.get("status", "")),
            "tag": row.get("tag"),
            "placed_at": str(row.get("order_timestamp") or ""),
        }
        for row in orders
    ]
    return {
        "holdings": held,
        "positions": today,
        "cash": {"available": _number(available.get("live_balance")), "opening": _number(available.get("opening_balance")), "net": _number(margins.get("net"))},
        "orders": order_rows,
    }


def register(app: FastAPI, repository: CoreRepository, require_user: Callable[..., None], logged_in: Callable[[], bool]) -> None:
    class LiveSettingsBody(BaseModel):
        values: dict[str, Any]
        operator: str = "operator"

    def settings_view() -> dict[str, object]:
        stored = repository.get_setting(SETTING_KEY)
        changes = repository.list_system_events(event_type=CHANGE_EVENT, limit=10)
        return {
            "settings": load_settings(repository),
            "modes": list(modes()),
            "limits": {key: {"min": low, "max": high} for key, (low, high) in LIMITS.items()},
            "updated_at": stored["updated_at"] if stored else None,
            "changes": [{"at": row["recorded_at"].isoformat(), **row["envelope"]} for row in changes],
        }

    @app.get("/api/v1/live/settings")
    def get_live_settings(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return settings_view()

    @app.post("/api/v1/live/settings")
    def save_live_settings(body: LiveSettingsBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        before = load_settings(repository)
        clean, errors = parse_settings({**before, **body.values})
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        now = datetime.now(timezone.utc)
        operator = body.operator[:64] or "operator"
        repository.save_setting(SETTING_KEY, clean, updated_by=operator, now=now)
        changed = {key: {"from": before.get(key), "to": value} for key, value in clean.items() if before.get(key) != value}
        if changed:
            # Append-only record of every change (the plan's audit log).
            repository.insert_system_event(str(uuid4()), CHANGE_EVENT, now, {"by": operator, "changed": changed})
        return settings_view()

    def read_account() -> dict[str, object]:
        client = app.state.kite_client
        try:
            return summarize_account(client.holdings(), client.positions(), client.equity_margins(), client.orders())
        except Exception as exc:
            if type(exc).__name__ == "TokenException":  # kiteconnect's expired or revoked session
                raise HTTPException(status_code=409, detail="zerodha_login_required") from exc
            raise HTTPException(status_code=502, detail="zerodha_unreachable") from exc

    @app.get("/api/v1/live/plan")
    def live_plan(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """The orders this month's rebalance would place. Phase 2: shown only, never sent."""
        from core_api.live_plan import plan

        settings = load_settings(repository)
        if settings["mode"] == "off":
            return {"mode": "off", "sent": False}
        proposal = latest_proposal()
        if proposal is None:
            return {"mode": settings["mode"], "sent": False, "detail": "no_proposal_yet"}
        account = read_account() if app.state.kite_client is not None and logged_in() else None
        body = plan(proposal, settings, account, load_ledger(repository))
        run = load_run()
        body["digest"] = order_digest(body["orders"])
        body["run_phase"] = run["phase"] if run and run.get("decided") == body["decided_at_close"] else None
        if account is not None and body["orders"]:
            # Each distinct dry run is kept once in the append-only log.
            digest = hashlib.sha256(json.dumps([body["orders"], settings], sort_keys=True).encode()).hexdigest()[:16]
            repository.insert_system_event(str(uuid5(NAMESPACE_URL, f"{DRY_RUN_EVENT}:{body['decided_at_close']}:{digest}")), DRY_RUN_EVENT,
                                           datetime.now(timezone.utc), {"settings": settings, "plan": body})
        return {**body, "mode": settings["mode"], "sent": False, "live_switch": enabled()}

    @app.get("/api/v1/live/account")
    def live_account(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        client = app.state.kite_client
        if client is None:
            raise HTTPException(status_code=503, detail="zerodha_not_configured")
        if not logged_in():
            raise HTTPException(status_code=409, detail="zerodha_login_required")
        body = read_account()
        return {**body, "read_at": datetime.now(timezone.utc).isoformat(), "live_enabled": False}

    # ---- Approve / Skip / Stop and the run (core_api.live_exec) ------------------------------------------------

    lock = threading.Lock()  # one step of a run at a time: the background runner and the routes never overlap
    # Swappable in tests: the clock and the pause between orders.
    app.state.momentum_live_clock = lambda: datetime.now(timezone.utc)
    app.state.momentum_live_sleep = time.sleep

    def clock() -> datetime:
        return app.state.momentum_live_clock()

    def load_run() -> dict | None:
        stored = repository.get_setting(RUN_KEY)
        return dict(stored["payload"]) if stored else None

    def executor() -> Executor:
        def save(run: dict) -> None:
            repository.save_setting(RUN_KEY, run, updated_by="momentum_live", now=datetime.now(timezone.utc))

        def log(kind: str, payload: dict) -> None:
            repository.insert_system_event(str(uuid4()), kind, datetime.now(timezone.utc), json.loads(json.dumps(payload, default=str)))

        def update_ledger(ledger: dict[str, int]) -> None:
            repository.save_setting(LEDGER_KEY, ledger, updated_by="momentum_live", now=datetime.now(timezone.utc))

        notify = send_telegram if os.environ.get("TELEGRAM_BOT_TOKEN") else None
        return Executor(app.state.kite_client, save, log, update_ledger, sleep=app.state.momentum_live_sleep, notify=notify)

    def run_view() -> dict[str, object]:
        return {"run": load_run(), "live_switch": enabled()}

    def set_mode_off(operator: str) -> None:
        before = load_settings(repository)
        if before["mode"] != "off":
            now = datetime.now(timezone.utc)
            repository.save_setting(SETTING_KEY, {**before, "mode": "off"}, updated_by=operator, now=now)
            repository.insert_system_event(str(uuid4()), CHANGE_EVENT, now, {"by": operator, "changed": {"mode": {"from": before["mode"], "to": "off"}}})

    class ApproveBody(BaseModel):
        digest: str
        operator: str = "operator"

    class OperatorBody(BaseModel):
        operator: str = "operator"

    @app.get("/api/v1/live/run")
    def live_run(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        return run_view()

    @app.post("/api/v1/live/approve")
    def live_approve(body: ApproveBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """The owner approves exactly the orders shown (body.digest); the sells go out at once."""
        from core_api.live_plan import plan

        if app.state.kite_client is None:
            raise HTTPException(status_code=503, detail="zerodha_not_configured")
        proposal = latest_proposal()
        if proposal is None:
            raise HTTPException(status_code=409, detail="no_proposal_yet")
        with lock:
            settings = load_settings(repository)
            account = read_account() if logged_in() else None
            current = plan(proposal, settings, account, load_ledger(repository))
            now = clock()
            try:
                check_approval(settings=settings, plan=current, digest=body.digest, run=load_run(), now=now, logged_in=account is not None,
                               trading_day=nse_trading_day(now))
            except LiveRefused as exc:
                raise HTTPException(status_code=409, detail=exc.code) from exc
            run = new_run(current, settings, load_ledger(repository), now)
            run["approved_by"] = body.operator[:64] or "operator"
            repository.insert_system_event(str(uuid4()), "momentum_live.approved", now, {"by": run["approved_by"], "decided": run["decided"], "digest": body.digest})
            executor().tick(run, now)
        return run_view()

    @app.post("/api/v1/live/skip")
    def live_skip(body: OperatorBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """No orders this month; the month counts as done."""
        from core_api.live_plan import plan

        proposal = latest_proposal()
        if proposal is None:
            raise HTTPException(status_code=409, detail="no_proposal_yet")
        with lock:
            run = load_run()
            if run is not None and run.get("decided") == proposal["decided_at_close"]:
                raise HTTPException(status_code=409, detail="already_done_this_month")
            settings = load_settings(repository)
            skipped = new_run(plan(proposal, settings, None, load_ledger(repository)), settings, load_ledger(repository), clock(), skipped=True)
            skipped["notes"].append(f"skipped by {body.operator[:64] or 'operator'}")
            repository.save_setting(RUN_KEY, skipped, updated_by="momentum_live", now=clock())
            repository.insert_system_event(str(uuid4()), RUN_EVENT, clock(), json.loads(json.dumps(skipped, default=str)))
        return run_view()

    @app.post("/api/v1/live/stop")
    def live_stop(body: OperatorBody, _: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        """Cancel the strategy's open orders and set Mode to Off. Works even with no run in progress."""
        with lock:
            run = load_run()
            if run is not None and run["phase"] not in FINAL_PHASES and app.state.kite_client is not None:
                executor().stop(run)
            set_mode_off(body.operator[:64] or "operator")
        return run_view()

    def advance() -> None:
        """One step of a run in progress; called by the background runner every few seconds."""
        with lock:
            run = load_run()
            if run is None or run["phase"] in FINAL_PHASES or app.state.kite_client is None:
                return
            if not logged_in():
                note = "Zerodha session ended: log in again on the site to finish the rebalance"
                if note not in run["notes"]:
                    run["notes"].append(note)
                    repository.save_setting(RUN_KEY, run, updated_by="momentum_live", now=clock())
                return
            executor().tick(run, clock())

    app.state.momentum_live_advance = advance


def nse_trading_day(now: datetime) -> bool:
    """False outside the calendar's coverage, so nothing is placed on a day it cannot vouch for."""
    try:
        from core_paper.trading_calendar import session_for

        return session_for((now.astimezone(timezone.utc) + timedelta(hours=5, minutes=30)).date()) is not None
    except Exception:  # noqa: BLE001
        return False


async def run_loop(app: FastAPI, every_seconds: int = 15) -> None:
    import asyncio
    import logging

    log = logging.getLogger("uvicorn.error")
    while True:
        try:
            await asyncio.to_thread(app.state.momentum_live_advance)
        except Exception as exc:  # noqa: BLE001 - logged; the next tick retries from the saved state
            log.warning("momentum_live run step failed: %s: %s", type(exc).__name__, str(exc)[:200])
        await asyncio.sleep(every_seconds)


# ---- Telegram notices: the ranking is fixed (evening) and rebalance morning (08:45 IST) -------------------------

NOTICE_KEY = "momentum_live_notices"
IST_OFFSET_MINUTES = 330


def notices_due(now: datetime, proposal: dict | None, mode: str, sent: set[str], site: str) -> list[tuple[str, str]]:
    """(key, text) of the notices to send now; each key is sent once."""
    if mode == "off" or proposal is None:
        return []
    ist = now.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(minutes=IST_OFFSET_MINUTES)
    decided, trade = proposal["decided_at_close"], proposal["trade_at_open_of"]
    what = "Dry run: the orders are only shown, nothing is sent." if mode == "dry_run" else "Live: nothing is sent until you press Approve."
    out = []
    if ist.date().isoformat() <= trade and f"decided:{decided}" not in sent:
        out.append((f"decided:{decided}", f"StockX momentum: this month's ranking is fixed (close of {decided}). Orders are for the open of {trade}. "
                                          f"That morning, sign in at {site}/settings and log in to Zerodha to see them. {what}"))
    if ist.date().isoformat() == trade and (8, 45) <= (ist.hour, ist.minute) < (10, 30) and f"morning:{trade}" not in sent:
        out.append((f"morning:{trade}", f"StockX momentum: rebalance day. Log in to Zerodha at {site}/settings to see today's orders. {what}"))
    return out


def send_telegram(text: str) -> bool:
    import urllib.request

    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10):
        return True


async def notice_loop(repository: CoreRepository, every_seconds: int = 300) -> None:
    import asyncio
    import logging

    log = logging.getLogger("uvicorn.error")
    site = f"https://{os.environ.get('DOMAIN', '').strip()}" if os.environ.get("DOMAIN") else ""
    while True:
        try:
            stored = repository.get_setting(NOTICE_KEY)
            sent = set(((stored or {}).get("payload") or {}).get("sent", []))
            for key, text in notices_due(datetime.now(timezone.utc), latest_proposal(), str(load_settings(repository)["mode"]), sent, site):
                if await asyncio.to_thread(send_telegram, text):
                    sent.add(key)
                    repository.save_setting(NOTICE_KEY, {"sent": sorted(sent)[-50:]}, updated_by="momentum_live", now=datetime.now(timezone.utc))
                    log.info("momentum_live notice sent: %s", key)
        except Exception as exc:  # noqa: BLE001 - retried on the next tick
            log.warning("momentum_live notice failed: %s", type(exc).__name__)
        await asyncio.sleep(every_seconds)
