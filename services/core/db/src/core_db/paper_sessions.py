"""Paper-session identity. Legacy rows are never attached to a newly opened session."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from core_db.clock import as_utc

LEGACY_SESSION_ID = hashlib.sha256(b"paper-session:legacy:v1").hexdigest()
LEGACY_ASSESSMENT_AUDIT_ID = hashlib.sha256(b"paper-session:legacy:assessment:v1").hexdigest()
_MONEY = Decimal("0.0001")
_DRAWDOWN = Decimal("0.00000001")


class ActivePaperSessionError(RuntimeError):
    """A second active paper session was refused."""


class MissingPaperSessionError(RuntimeError):
    """A trading write had no active session to charge."""


class AmbiguousPaperSessionError(RuntimeError):
    """More than one session is marked active."""


class ClosedPaperSessionError(RuntimeError):
    """A closed session stays closed."""


@dataclass(frozen=True)
class LegacyAssessment:
    """Whether unassigned paper rows prove one starting cash and one peak.

    ``peak_complete`` is true only when ``runtime_flags.paper.peak_equity`` matches
    the latest snapshot. Any other peak is a lower bound or is left empty, and the
    diagnostics say the historical maximum is incomplete.
    """

    consistent: bool
    starting_cash: Decimal | None
    peak_equity: Decimal | None
    peak_source: str
    peak_complete: bool
    diagnostics: tuple[str, ...]


def payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def reconstructed_starting_cash(
    snapshot_cash: Decimal | None,
    orders: dict[str, dict[str, Any]],
    executions: list[dict[str, Any]],
) -> Decimal | None:
    """Starting cash implied by undoing stored fills from snapshot cash.

    A buy adds ``price * quantity + fees`` back. A sell subtracts ``price * quantity - fees``.
    Slippage is already inside the stored fill price and is not applied again.
    Returns None when the snapshot or a matching order or fee is missing.
    """
    if snapshot_cash is None:
        return None
    cash = snapshot_cash
    for execution in executions:
        order = orders.get(str(execution.get("order_id")))
        if order is None or "fees" not in execution or "price" not in execution or "quantity" not in execution:
            return None
        notional = Decimal(str(execution["price"])) * int(execution["quantity"])
        fees = Decimal(str(execution["fees"]))
        if str(order.get("side")) == "BUY":
            cash += notional + fees
        else:
            cash -= notional - fees
    return cash


def assess_legacy_book(
    *,
    snapshots: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    runtime_peak: Decimal | None,
) -> LegacyAssessment:
    """Check the unassigned book before a legacy session may become active."""
    problems: list[str] = []
    if not snapshots:
        problems.append("no portfolio snapshot exists for the legacy book")
        return _inactive(problems)

    latest = max(snapshots, key=lambda item: (as_utc(item["timestamp"]), str(item.get("snapshot_id"))))
    body = payload_dict(latest.get("payload"))
    snapshot_at = as_utc(latest["timestamp"])
    payload_at = _instant(body.get("timestamp"))
    if payload_at is None:
        problems.append("the latest snapshot payload has no timestamp")
    elif payload_at != snapshot_at:
        problems.append("the latest snapshot payload timestamp disagrees with the snapshot row")

    cash = _money(body.get("cash")) if "cash" in body else None
    equity = _money(body.get("equity")) if "equity" in body else None
    market_value = _money(body.get("market_value")) if "market_value" in body else None
    gross = _money(body.get("gross_exposure")) if "gross_exposure" in body else None
    net = _money(body.get("net_exposure")) if "net_exposure" in body else None
    realized = _money(body.get("realized_pnl")) if "realized_pnl" in body else None
    unrealized = _money(body.get("unrealized_pnl")) if "unrealized_pnl" in body else None
    total_pnl = _money(body.get("total_pnl")) if "total_pnl" in body else None
    drawdown = _drawdown(body.get("drawdown")) if "drawdown" in body else None
    for name, value in (
        ("cash", cash),
        ("equity", equity),
        ("market_value", market_value),
        ("gross_exposure", gross),
        ("net_exposure", net),
        ("realized_pnl", realized),
        ("unrealized_pnl", unrealized),
        ("total_pnl", total_pnl),
        ("drawdown", drawdown),
    ):
        if value is None:
            problems.append(f"the latest snapshot is missing a usable {name}")

    parsed_orders = {str(item["order_id"]): payload_dict(item.get("payload")) for item in orders}
    parsed_fills: list[dict[str, Any]] = []
    for item in executions:
        payload = payload_dict(item.get("payload"))
        order_id = str(item.get("order_id") or "")
        payload_order_id = str(payload.get("order_id") or "")
        if payload_order_id and payload_order_id != order_id:
            problems.append(f"fill {item.get('execution_id')} payload order_id disagrees with the fill row")
        order = parsed_orders.get(order_id)
        if order is None:
            problems.append(f"fill {item.get('execution_id')} has no matching order")
            continue
        price = _money(payload.get("price")) if "price" in payload else None
        quantity = _whole(payload.get("quantity")) if "quantity" in payload else None
        fees = _money(payload.get("fees")) if "fees" in payload else None
        slippage = _money(payload.get("slippage")) if "slippage" in payload else None
        executed_at = _instant(payload.get("executed_at"))
        order_quantity = _whole(order.get("quantity")) if "quantity" in order else None
        side = str(order.get("side") or "")
        fill_symbol = str(payload.get("symbol") or "")
        order_symbol = str(order.get("symbol") or "")
        if price is None or price <= 0:
            problems.append(f"fill {item.get('execution_id')} has no positive price")
        if quantity is None or quantity <= 0:
            problems.append(f"fill {item.get('execution_id')} has no positive quantity")
        if fees is None or fees < 0:
            problems.append(f"fill {item.get('execution_id')} has no non-negative fee")
        if slippage is None or slippage < 0:
            problems.append(f"fill {item.get('execution_id')} has no non-negative slippage")
        if executed_at is None:
            problems.append(f"fill {item.get('execution_id')} has no executed_at")
        elif executed_at > snapshot_at:
            problems.append(f"fill {item.get('execution_id')} is later than the latest snapshot")
        if side not in {"BUY", "SELL"}:
            problems.append(f"order {order_id} side is not BUY or SELL")
        if order_quantity is None or quantity is None or order_quantity != quantity:
            problems.append(f"fill {item.get('execution_id')} quantity does not match its order")
        if not fill_symbol or fill_symbol != order_symbol:
            problems.append(f"fill {item.get('execution_id')} symbol does not match its order")
        if price is not None and quantity is not None and fees is not None and executed_at is not None:
            parsed_fills.append(
                {
                    "order_id": order_id,
                    "price": price,
                    "quantity": quantity,
                    "fees": fees,
                    "executed_at": executed_at,
                    "side": side,
                    "symbol": fill_symbol,
                    "execution_id": str(item.get("execution_id")),
                }
            )

    holdings = _replay_holdings(parsed_fills, problems)
    position_totals = _check_positions(positions, holdings, problems)

    if None not in (cash, equity, market_value, gross, net, realized, unrealized, total_pnl) and position_totals is not None:
        if not _same_money(equity, cash + market_value):
            problems.append("snapshot equity does not equal cash plus market value")
        if not _same_money(market_value, position_totals["market_value"]):
            problems.append("snapshot market value does not equal the open positions")
        if not _same_money(gross, position_totals["gross"]):
            problems.append("snapshot gross exposure does not equal the open positions")
        if not _same_money(net, position_totals["net"]):
            problems.append("snapshot net exposure does not equal the open positions")
        if not _same_money(realized, position_totals["realized"]):
            problems.append("snapshot realized P&L does not equal the open positions")
        if not _same_money(unrealized, position_totals["unrealized"]):
            problems.append("snapshot unrealized P&L does not equal the open positions")
        if not _same_money(total_pnl, realized + unrealized):
            problems.append("snapshot total P&L does not equal realized plus unrealized P&L")
        if cash < 0 or equity <= 0:
            problems.append("snapshot cash or equity is not a usable positive book")

    if problems or cash is None or equity is None or drawdown is None:
        return _inactive(problems or ["legacy starting cash could not be reconstructed as a positive value"])

    order_payloads = {order_id: {"side": parsed_orders[order_id].get("side")} for order_id in parsed_orders}
    fill_payloads = [
        {"order_id": item["order_id"], "price": item["price"], "quantity": item["quantity"], "fees": item["fees"]}
        for item in parsed_fills
    ]
    starting = reconstructed_starting_cash(cash, order_payloads, fill_payloads)
    if starting is None or starting <= 0:
        return _inactive([*problems, "legacy starting cash could not be reconstructed as a positive value"])

    peak, source, complete, peak_notes = _resolve_peak(runtime_peak, equity, drawdown)
    return LegacyAssessment(
        consistent=True,
        starting_cash=starting,
        peak_equity=peak,
        peak_source=source,
        peak_complete=complete,
        diagnostics=peak_notes,
    )


def _inactive(problems: list[str]) -> LegacyAssessment:
    return LegacyAssessment(
        consistent=False,
        starting_cash=None,
        peak_equity=None,
        peak_source="unavailable",
        peak_complete=False,
        diagnostics=tuple(problems),
    )


def _resolve_peak(
    runtime_peak: Decimal | None,
    equity: Decimal,
    drawdown: Decimal,
) -> tuple[Decimal | None, str, bool, tuple[str, ...]]:
    if _peak_matches(runtime_peak, equity, drawdown):
        return runtime_peak, "runtime_flag", True, ()
    notes = [
        "historical peak is incomplete: runtime_flags.paper.peak_equity was missing or did not reproduce the latest snapshot drawdown"
    ]
    if drawdown == 0 and equity > 0:
        notes.append(
            "peak_equity was initialized to the latest snapshot equity because that snapshot records drawdown 0; this is not a stored historical maximum"
        )
        return equity, "snapshot_equity", False, tuple(notes)
    notes.append("peak_equity was left empty because no exact historical maximum is stored")
    return None, "unavailable", False, tuple(notes)


def _peak_matches(runtime_peak: Decimal | None, equity: Decimal, drawdown: Decimal) -> bool:
    if runtime_peak is None or equity <= 0 or runtime_peak <= 0 or runtime_peak < equity:
        return False
    if drawdown < 0 or drawdown > 1:
        return False
    implied = ((runtime_peak - equity) / runtime_peak).quantize(_DRAWDOWN)
    return implied == drawdown.quantize(_DRAWDOWN)


def _replay_holdings(fills: list[dict[str, Any]], problems: list[str]) -> dict[str, dict[str, Any]]:
    holdings: dict[str, dict[str, Any]] = {}
    for fill in sorted(fills, key=lambda item: (item["executed_at"], item["execution_id"])):
        state = holdings.setdefault(fill["symbol"], {"qty": 0, "avg": None, "realized": Decimal("0")})
        quantity = int(fill["quantity"])
        price = fill["price"]
        if fill["side"] == "BUY":
            new_qty = state["qty"] + quantity
            if state["qty"] == 0:
                state["avg"] = price
            elif state["qty"] > 0:
                state["avg"] = ((state["avg"] * state["qty"]) + (price * quantity)) / new_qty
            else:
                problems.append(f"fill {fill['execution_id']} buys against a short holding")
                continue
            state["qty"] = new_qty
        elif fill["side"] == "SELL":
            if state["avg"] is None or state["qty"] < quantity:
                problems.append(f"fill {fill['execution_id']} sells more than the open holding")
                continue
            state["realized"] += (price - state["avg"]) * quantity
            state["qty"] -= quantity
            if state["qty"] == 0:
                state["avg"] = None
    return holdings


def _check_positions(
    positions: list[dict[str, Any]],
    holdings: dict[str, dict[str, Any]],
    problems: list[str],
) -> dict[str, Decimal] | None:
    seen: set[str] = set()
    totals = {
        "market_value": Decimal("0"),
        "gross": Decimal("0"),
        "net": Decimal("0"),
        "realized": Decimal("0"),
        "unrealized": Decimal("0"),
    }
    usable = True
    for item in positions:
        payload = payload_dict(item.get("payload"))
        symbol = str(item.get("symbol") or payload.get("symbol") or "")
        if not symbol or symbol in seen:
            problems.append("a legacy position is missing a unique symbol")
            usable = False
            continue
        seen.add(symbol)
        quantity = _whole(payload.get("quantity")) if "quantity" in payload else None
        average = _money(payload.get("average_price")) if "average_price" in payload else None
        market = _money(payload.get("market_price")) if "market_price" in payload else None
        value = _money(payload.get("market_value")) if "market_value" in payload else None
        realized = _money(payload.get("realized_pnl")) if "realized_pnl" in payload else None
        unrealized = _money(payload.get("unrealized_pnl")) if "unrealized_pnl" in payload else None
        holding = holdings.get(symbol)
        if quantity is None or average is None or market is None or value is None or realized is None or unrealized is None:
            problems.append(f"position {symbol} is missing quantity or valuation fields")
            usable = False
            continue
        if market <= 0 or average <= 0:
            problems.append(f"position {symbol} has a non-positive price")
            usable = False
            continue
        if holding is None or holding["qty"] != quantity or holding["avg"] is None or not _same_money(holding["avg"], average):
            problems.append(f"position {symbol} quantity or average price does not match its fills")
        elif not _same_money(holding["realized"], realized):
            problems.append(f"position {symbol} realized P&L does not match its fills")
        if not _same_money(value, market * quantity):
            problems.append(f"position {symbol} market value does not equal price times quantity")
        if not _same_money(unrealized, (market - average) * quantity):
            problems.append(f"position {symbol} unrealized P&L does not equal its mark")
        totals["market_value"] += value
        totals["gross"] += abs(value)
        totals["net"] += value
        totals["realized"] += realized
        totals["unrealized"] += unrealized
    for symbol, holding in holdings.items():
        if holding["qty"] != 0 and symbol not in seen:
            problems.append(f"fills leave {symbol} open but no position row exists")
            usable = False
        if holding["qty"] == 0 and symbol in seen:
            problems.append(f"position {symbol} is still open after the fills flatten it")
    return totals if usable else None


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite():
        return None
    return number


def _drawdown(value: Any) -> Decimal | None:
    number = _money(value)
    if number is None or number < 0 or number > 1:
        return None
    return number


def _whole(value: Any) -> int | None:
    number = _money(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def _same_money(left: Decimal, right: Decimal) -> bool:
    return left.quantize(_MONEY) == right.quantize(_MONEY)


def _instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)
    if not isinstance(value, str):
        return None
    try:
        return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None
