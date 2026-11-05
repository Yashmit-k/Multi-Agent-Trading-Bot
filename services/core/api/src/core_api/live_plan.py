"""Momentum live: turn a month-end proposal into an exact order list for the owner's account
(services/quant/docs/momentum-live-plan.md). A pure function: it reads nothing and sends nothing.

The rule is the paper trial's: the top N by 12-1 momentum, the book split equally across them in whole shares, and the
cash left by rounding buying one more share at a time of the holding furthest below its share. Only shares in the
strategy's ledger are ever sold. Orders are limit orders at most BAND away from the decision close, on each stock's
own price step (tick size). With Zerodha's instrument list for the day, a stock is left out (and a holding kept) when
it is not trading in the EQ series that day, or when its price is more than 30% away from the decision close, which
points to a split or bonus the decision close does not reflect.
"""

import math

BAND = 0.03  # limit price at most 3% above (buys) or below (sells) the decision close (momentum-gap-check.md)
TICK = 0.05  # used only when the instrument list is unavailable (dry runs)
JUMP = 0.30  # a price this far from the decision close points to a split or bonus

# Zerodha equity delivery, as in research.mentor_strategies.delivery_charges.
TXN, SEBI, GST, DP = 0.0000307, 10 / 1e7, 0.18, 15.34


def delivery_charges(buy: float, sell: float) -> float:
    exchange = (buy + sell) * TXN
    sebi = (buy + sell) * SEBI
    return (buy + sell) * 0.001 + buy * 0.00015 + exchange + sebi + GST * (exchange + sebi) + (DP if sell else 0.0)


def buy_limit(close: float, tick: float = TICK) -> float:
    return round(math.floor(close * (1 + BAND) / tick + 1e-9) * tick, 2)


def sell_limit(close: float, tick: float = TICK) -> float:
    return round(math.ceil(close * (1 - BAND) / tick - 1e-9) * tick, 2)


def plan(proposal: dict, settings: dict, account: dict | None, ledger: dict[str, int], instruments: dict[str, dict] | None = None) -> dict[str, object]:
    """Orders for one rebalance. account None means not logged in: the plan then assumes an empty account holding the
    amount in cash, and says so. instruments: Zerodha's NSE EQ list for the day, symbol -> {"tick", "last_price"};
    None when unavailable (fine for a dry run; Approve refuses such a plan)."""
    stocks, amount, max_order = int(settings["stocks"]), float(settings["amount"]), float(settings["max_order"])
    warnings: list[str] = []
    if instruments is None:
        warnings.append("Zerodha's instrument list was not available: prices are rounded to ₹0.05 and the EQ series is not checked. Approve needs it.")

    def tick(symbol: str) -> float:
        return float((instruments or {}).get(symbol, {}).get("tick") or TICK)
    assumed = account is None
    account = account or {"holdings": [], "positions": [], "cash": {"available": amount}}
    in_account: dict[str, int] = {}
    last_close: dict[str, float] = {}
    for row in account["holdings"]:
        in_account[row["symbol"]] = in_account.get(row["symbol"], 0) + int(row["quantity"]) + int(row.get("t1_quantity") or 0)
        if row.get("close_price"):
            last_close[row["symbol"]] = float(row["close_price"])
    for row in account.get("positions", []):
        if row.get("product") == "CNC":  # bought today, not yet in holdings
            in_account[row["symbol"]] = in_account.get(row["symbol"], 0) + int(row["quantity"])
    closes = {s: round(c, 2) for s, c in {**last_close, **{str(k): float(v) for k, v in proposal["closes"].items()}}.items()}

    def unfit(symbol: str) -> str | None:
        if instruments is not None and symbol not in instruments:
            return "not trading in the EQ series today"
        ref = float((instruments or {}).get(symbol, {}).get("last_price") or 0.0) or last_close.get(symbol, 0.0)
        close = closes.get(symbol)
        if ref and close and not (1 - JUMP) <= ref / close <= 1 / (1 - JUMP):
            return f"price ₹{ref:,.2f} is more than 30% from the decision close ₹{close:,.2f} (a split or bonus?)"
        return None

    held: dict[str, int] = {}
    for symbol, qty in ledger.items():
        have = min(int(qty), in_account.get(symbol, 0))
        if have < qty:
            warnings.append(f"{symbol}: the ledger has {qty} but the account has {in_account.get(symbol, 0)}; using {have}.")
        if have > 0:
            held[symbol] = have
    untradable = [s for s in held if s not in closes or unfit(s)]
    for symbol in untradable:
        warnings.append(f"{symbol}: {unfit(symbol) if symbol in closes else 'no closing price'}, so it is kept as it is this month.")
    held_value = sum(qty * closes[s] for s, qty in held.items() if s in closes)
    cash = float(account["cash"].get("available") or 0.0)
    book = min(amount, held_value + cash)
    base = {"decided_at_close": proposal["decided_at_close"], "trade_at_open_of": proposal["trade_at_open_of"], "assumed_account": assumed,
            "stocks": stocks, "amount": amount, "cash": cash, "held_value": round(held_value, 2), "book": round(book, 2)}
    if amount <= 0:
        return {**base, "orders": [], "warnings": ["Set the amount for the strategy first."], "per_stock": 0.0, "totals": {}}

    targets = []
    for row in proposal["ranking"]:
        symbol = str(row["symbol"])
        if symbol not in closes or len(targets) >= stocks:
            continue
        reason = unfit(symbol) if symbol not in held else None
        if reason:
            warnings.append(f"{symbol}: {reason}; the next-ranked stock is taken instead.")
            continue
        targets.append(symbol)
    if len(targets) < stocks:
        warnings.append(f"Only {len(targets)} ranked stocks have a price; holding {len(targets)}.")
    per = book / max(len(targets), 1)
    # Shares to buy are sized at their limit price, so the worst case already fits and little cash is left idle;
    # shares already held are valued at the close. A reserve covers the buy charges.
    size = {s: closes[s] if s in held else buy_limit(closes[s], tick(s)) for s in targets}
    budget = book - delivery_charges(max(book - held_value, 0.0), 0.0)
    want = {s: int(per // size[s]) for s in targets}
    left = budget - sum(want[s] * size[s] for s in targets)
    while True:  # leftover fill, as in the paper trial
        room = [s for s in targets if size[s] <= left]
        if not room:
            break
        pick = min(room, key=lambda s: want[s] * size[s] / per)
        want[pick] += 1
        left -= size[pick]

    sells = {s: q for s, q in held.items() if s not in want and s not in untradable}
    sells.update({s: held[s] - want[s] for s in targets if held.get(s, 0) > want[s]})
    buys = {s: want[s] - held.get(s, 0) for s in targets if want[s] > held.get(s, 0)}
    sell_cash = sum(q * sell_limit(closes[s], tick(s)) for s, q in sells.items())
    sell_cost = sum(delivery_charges(0.0, q * sell_limit(closes[s], tick(s))) for s, q in sells.items())

    def buy_cost() -> float:
        value = sum(q * buy_limit(closes[s], tick(s)) for s, q in buys.items())
        return value + delivery_charges(value, 0.0)

    # Worst case (every buy at its limit, every sell at its limit) must fit in the strategy's cash without margin, and
    # never take the strategy past the amount set: only the part of the cash inside the book may be spent.
    spendable = min(cash, max(book - held_value, 0.0))
    while buys and buy_cost() > spendable + sell_cash - sell_cost:
        heavy = max(buys, key=lambda s: (held.get(s, 0) + buys[s]) * closes[s] / per)
        buys[heavy] -= 1
        if buys[heavy] == 0:
            del buys[heavy]

    if not buys and any(s not in held for s in targets):
        if not assumed and cash <= 0 and not sells:
            warnings.append("Your Zerodha account has no cash available, so nothing can be bought. Add funds to see this month's real orders.")
        else:
            warnings.append("Not enough cash for even one share of the stocks to buy.")

    orders = []
    for side, book_side in (("SELL", sells), ("BUY", buys)):
        for symbol, qty in sorted(book_side.items()):
            limit = sell_limit(closes[symbol], tick(symbol)) if side == "SELL" else buy_limit(closes[symbol], tick(symbol))
            value = round(qty * limit, 2)
            order = {"side": side, "symbol": symbol, "quantity": qty, "close": closes[symbol], "limit": limit, "value": value, "blocked": None}
            if value > max_order:
                order["blocked"] = "above the largest single order"
                warnings.append(f"{side} {symbol} for ₹{value:,.0f} is above the largest single order (₹{max_order:,.0f}); it would not be sent.")
            orders.append(order)
    sent = [o for o in orders if not o["blocked"]]
    buy_value = sum(o["value"] for o in sent if o["side"] == "BUY")
    sell_value = sum(o["value"] for o in sent if o["side"] == "SELL")
    charges = delivery_charges(buy_value, 0.0) + sum(delivery_charges(0.0, o["value"]) for o in sent if o["side"] == "SELL")
    return {
        **base,
        "per_stock": round(per, 2),
        "targets": targets,
        "closes": {s: closes[s] for s in [*targets, *held] if s in closes},
        "ticks": {s: tick(s) for s in [*targets, *held]},
        "instruments_checked": instruments is not None,
        "orders": orders,
        "warnings": warnings,
        "totals": {"buy": round(buy_value, 2), "sell": round(sell_value, 2), "charges": round(charges, 2),
                   "spendable": round(spendable, 2)},
    }
