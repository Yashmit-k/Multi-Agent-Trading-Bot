"""Momentum live, phase 1 (services/quant/docs/momentum-live-plan.md): the owner's Zerodha account, read-only, and the
settings the later phases will use. Nothing in this module places, changes or cancels an order.

Every route needs the Core token. The public proxy forwards them only for a signed-in operator, because the account
and the amount invested are private.
"""

from datetime import datetime, timezone
from typing import Annotated, Any, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from core_db.repository import CoreRepository

SETTING_KEY = "momentum_live"
CHANGE_EVENT = "momentum_live.settings_changed"
DEFAULTS: dict[str, object] = {"amount": 0, "stocks": 10, "mode": "off", "max_order": 25000}
# "live" is accepted only once order placement is built (phase 3 of the plan).
MODES = ("off", "dry_run")
LIMITS = {"amount": (0, 10_000_000), "stocks": (5, 50), "max_order": (1_000, 1_000_000)}


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
    if mode == "live":
        errors["mode"] = "live mode is not built yet; use off or dry_run"
    elif mode not in MODES:
        errors["mode"] = "must be off or dry_run"
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
            "modes": list(MODES),
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

    @app.get("/api/v1/live/account")
    def live_account(_: Annotated[None, Depends(require_user)]) -> dict[str, object]:
        client = app.state.kite_client
        if client is None:
            raise HTTPException(status_code=503, detail="zerodha_not_configured")
        if not logged_in():
            raise HTTPException(status_code=409, detail="zerodha_login_required")
        try:
            body = summarize_account(client.holdings(), client.positions(), client.equity_margins(), client.orders())
        except Exception as exc:
            if type(exc).__name__ == "TokenException":  # kiteconnect's expired or revoked session
                raise HTTPException(status_code=409, detail="zerodha_login_required") from exc
            raise HTTPException(status_code=502, detail="zerodha_unreachable") from exc
        return {**body, "read_at": datetime.now(timezone.utc).isoformat(), "live_enabled": False}
