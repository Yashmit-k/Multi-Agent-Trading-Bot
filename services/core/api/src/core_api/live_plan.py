"""Momentum live: turn a month-end proposal into an exact order list for the owner's account
(services/quant/docs/momentum-live-plan.md). A pure function: it reads nothing and sends nothing.

The rule is the paper trial's: the top N by 12-1 momentum, the book split equally across them in whole shares, and the
cash left by rounding buying one more share at a time of the holding furthest below its share. The book is the
strategy's own: the shares in its ledger plus its own cash (the money put in, plus what its sales brought, minus what
its buys cost), so it grows and shrinks like the paper trial's and never touches other money in the account. Only
ledger shares are ever sold. Orders are limit orders at most BAND (or the stock's daily price band, if narrower) away
from the decision close, on the stock's own price step. A stock not trading in the EQ series that day, or whose price
is more than 30% from the decision close (a split or bonus), is left out, and such a holding is left exactly as it is.
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


def buy_limit(close: float, tick: float = TICK, band: float = BAND) -> float:
    return round(math.floor(close * (1 + min(band, BAND)) / tick + 1e-9) * tick, 2)


def sell_limit(close: float, tick: float = TICK, band: float = BAND) -> float:
    return round(math.ceil(close * (1 - min(band, BAND)) / tick - 1e-9) * tick, 2)


def empty_book(amount: float) -> dict:
    """The strategy before its first trade: all of the amount in cash."""
    return {"shares": {}, "cash": float(amount), "contributed": float(amount), "ref": {}}


SPLIT_RATIO_TOLERANCE = 0.25


def plan(proposal: dict, settings: dict, account: dict | None, book: dict, instruments: dict[str, dict] | None = None, today: str | None = None) -> dict[str, object]:
    """Orders for one rebalance.

    book: the strategy's own book, {"shares": {symbol: qty}, "cash": rupees, "ref": {symbol: price when last traded}}.
    A plain {symbol: qty} is read as shares with all of the amount as cash (tests, and before the first trade).
    account None means not logged in: the plan then assumes the account holds exactly the strategy's book, and says so.
    instruments: Zerodha's NSE EQ list for the day, symbol -> {"tick", "last_price"}; None when unavailable (fine for a
    dry run; Approve refuses such a plan). today: the IST date, to warn when approving after the trade day."""
    stocks, amount, max_order = int(settings["stocks"]), float(settings["amount"]), float(settings["max_order"])
    if "shares" not in book:
        book = {**empty_book(amount), "shares": dict(book)}
    shares = {str(k): int(v) for k, v in book["shares"].items()}
    strategy_cash = float(book.get("cash", amount))
    ref = {str(k): float(v) for k, v in (book.get("ref") or {}).items()}
    bands = {str(k): float(v) for k, v in (proposal.get("bands") or {}).items() if v}
    warnings: list[str] = []
    if instruments is None:
        warnings.append("Zerodha's instrument list was not available: prices are rounded to ₹0.05 and the EQ series is not checked. Approve needs it.")
    if today and today > proposal["trade_at_open_of"]:
        warnings.append(f"This is after the trade day ({proposal['trade_at_open_of']}): the limits still come from the close of {proposal['decided_at_close']}, so more orders may miss.")

    def tick(symbol: str) -> float:
        return float((instruments or {}).get(symbol, {}).get("tick") or TICK)

    def band(symbol: str) -> float:
        return bands.get(symbol, BAND * 100) / 100

    def blim(symbol: str) -> float:
        return buy_limit(closes[symbol], tick(symbol), band(symbol))

    def slim(symbol: str) -> float:
        return sell_limit(closes[symbol], tick(symbol), band(symbol))

    assumed = account is None
    account = account or {"holdings": [{"symbol": s, "quantity": q, "t1_quantity": 0, "close_price": None} for s, q in shares.items()],
                          "positions": [], "cash": {"available": max(strategy_cash, 0.0)}}
    in_account: dict[str, int] = {}
    last_close: dict[str, float] = {}
    for row in account["holdings"]:
        in_account[row["symbol"]] = in_account.get(row["symbol"], 0) + int(row["quantity"]) + int(row.get("t1_quantity") or 0)
        if row.get("close_price"):
            last_close[row["symbol"]] = float(row["close_price"])
    for row in account.get("positions", []):
        if row.get("product") == "CNC":  # bought or sold today, not yet in holdings
            in_account[row["symbol"]] = in_account.get(row["symbol"], 0) + int(row["quantity"])
    closes = {s: round(c, 2) for s, c in {**last_close, **{str(k): float(v) for k, v in proposal["closes"].items()}}.items()}

    def unfit(symbol: str) -> str | None:
        if instruments is not None and symbol not in instruments:
            return "not trading in the EQ series today"
        ref_price = float((instruments or {}).get(symbol, {}).get("last_price") or 0.0) or last_close.get(symbol, 0.0)
        close = closes.get(symbol)
        if ref_price and close and not (1 - JUMP) <= ref_price / close <= 1 / (1 - JUMP):
            return f"price ₹{ref_price:,.2f} is more than 30% from the decision close ₹{close:,.2f} (a split or bonus?)"
        return None

    held: dict[str, int] = {}
    ledger_used = dict(shares)
    for symbol, qty in shares.items():
        have = in_account.get(symbol, 0)
        if have > qty > 0:
            ratio = have / qty
            moved = ref.get(symbol, 0.0) / closes[symbol] if closes.get(symbol) else 0.0
            if ratio >= 1.4 and abs(moved - ratio) / ratio <= SPLIT_RATIO_TOLERANCE:
                warnings.append(f"{symbol}: {qty} shares became {have} and the price fell in step (a split or bonus); the ledger now counts {have}.")
                qty = ledger_used[symbol] = have
            else:
                warnings.append(f"{symbol}: the account has {have}, more than the strategy's {qty}; the extra {have - qty} are not the strategy's and are left alone.")
        use = min(qty, have)
        if use < qty:
            warnings.append(f"{symbol}: the ledger has {qty} but the account has {have}; using {use}.")
        if use > 0:
            held[symbol] = use
    untradable = [s for s in held if s not in closes or unfit(s)]
    for symbol in untradable:
        warnings.append(f"{symbol}: {unfit(symbol) if symbol in closes else 'no closing price'}, so it is kept as it is this month.")
    held_value = sum(qty * closes[s] for s, qty in held.items() if s in closes)
    cash_info = account["cash"]
    account_cash = float(cash_info["net"] if cash_info.get("net") is not None else cash_info.get("available") or 0.0)
    book_value = max(held_value + strategy_cash, 0.0)
    spendable = max(min(account_cash, strategy_cash), 0.0)
    base = {"decided_at_close": proposal["decided_at_close"], "trade_at_open_of": proposal["trade_at_open_of"], "assumed_account": assumed,
            "stocks": stocks, "amount": amount, "strategy_cash": round(strategy_cash, 2), "cash": account_cash, "held_value": round(held_value, 2),
            "book": round(book_value, 2), "ledger_used": ledger_used, "instruments_checked": instruments is not None}
    if book_value <= 0:
        return {**base, "orders": [], "warnings": [*warnings, "Set the amount for the strategy first."], "per_stock": 0.0, "totals": {}, "targets": [], "closes": {}, "ticks": {}, "bands": {}}
    if not assumed and account_cash < strategy_cash:
        warnings.append(f"Zerodha shows ₹{account_cash:,.0f} of cash, less than the strategy's ₹{strategy_cash:,.0f}: buys are limited to ₹{max(account_cash, 0):,.0f}.")

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
    per = book_value / max(len(targets), 1)
    # Shares to buy are sized at their limit price, so the worst case already fits and little cash is left idle;
    # shares already held are valued at the close. A reserve covers the buy charges. A holding left as it is
    # (untradable) keeps exactly its shares.
    fixed = {s for s in targets if s in untradable}
    size = {s: closes[s] if s in held else blim(s) for s in targets}
    budget = book_value - delivery_charges(max(strategy_cash, 0.0), 0.0)
    want = {s: held[s] if s in fixed else int(per // size[s]) for s in targets}
    left = budget - sum(want[s] * size[s] for s in targets)
    while True:  # leftover fill, as in the paper trial
        room = [s for s in targets if size[s] <= left and s not in fixed]
        if not room:
            break
        pick = min(room, key=lambda s: want[s] * size[s] / per)
        want[pick] += 1
        left -= size[pick]

    sells = {s: q for s, q in held.items() if s not in want and s not in untradable}
    sells.update({s: held[s] - want[s] for s in targets if held.get(s, 0) > want[s] and s not in untradable})
    buys = {s: want[s] - held.get(s, 0) for s in targets if want[s] > held.get(s, 0) and s not in untradable}
    blocked_sells = {s for s, q in sells.items() if q * slim(s) > max_order}
    sell_cash = sum(q * slim(s) for s, q in sells.items() if s not in blocked_sells)
    sell_cost = sum(delivery_charges(0.0, q * slim(s)) for s, q in sells.items() if s not in blocked_sells)

    def buy_cost() -> float:
        value = sum(q * blim(s) for s, q in buys.items())
        return value + delivery_charges(value, 0.0)

    # Worst case (every buy at its limit, every sell at its limit) must fit in the strategy's own cash, without margin
    # and without other money in the account.
    while buys and buy_cost() > spendable + sell_cash - sell_cost:
        heavy = max(buys, key=lambda s: (held.get(s, 0) + buys[s]) * closes[s] / per)
        buys[heavy] -= 1
        if buys[heavy] == 0:
            del buys[heavy]

    if not buys and any(s not in held for s in targets):
        if not assumed and account_cash <= 0 and not sells:
            warnings.append("Your Zerodha account has no cash available, so nothing can be bought. Add funds to see this month's real orders.")
        else:
            warnings.append("Not enough cash for even one share of the stocks to buy.")

    orders = []
    for side, book_side in (("SELL", sells), ("BUY", buys)):
        for symbol, qty in sorted(book_side.items()):
            limit = slim(symbol) if side == "SELL" else blim(symbol)
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
        "bands": {s: band(s) for s in [*targets, *held]},
        "orders": orders,
        "warnings": warnings,
        "totals": {"buy": round(buy_value, 2), "sell": round(sell_value, 2), "charges": round(charges, 2),
                   "spendable": round(spendable, 2)},
    }
