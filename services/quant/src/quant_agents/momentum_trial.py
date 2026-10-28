"""Forward paper trial of 12-1 momentum across the NSE Liquid-500 (services/quant/docs/momentum-trial.md).

The rule is the one that passed services/quant/docs/whole-market-result.md: the top HOLD (10) by 12-1 momentum at
each month-end close. The book is ₹CAPITAL (₹1,00,000) invested once and never topped up; at every rebalance the whole
book is split equally across the HOLD stocks (services/quant/docs/momentum-rebalance-result.md), traded at the next
open with Zerodha delivery charges and 10 bp slippage, by the backtest engine research.momentum_compound.simulate.
Paper only: no order is ever sent to a broker.

Each evening (after NSE publishes the day's bhavcopy) it:
  1. downloads any missing bhavcopies into DIR/raw (a rolling window from FETCH_FROM);
  2. on the last session of a month, appends that close's full ranking to DIR/decisions.jsonl before the next open
     (the pre-commitment; fills then take the first HOLD that can be bought at that open, as in the backtest);
  3. re-runs the book from START on the data and writes DIR/report.json: equity, holdings, trades, and the
     equal-weight Liquid-500 (gross) and NIFTYBEES over the same months.

    python -m quant_agents.momentum_trial [--once]
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time as clock
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

logger = logging.getLogger("momentum_trial")
IST = ZoneInfo("Asia/Kolkata")
DIR = Path(os.environ.get("MOMENTUM_TRIAL_DIR", "/data/momentum-trial"))
START = date.fromisoformat(os.environ.get("MOMENTUM_TRIAL_START", "2026-10-30"))  # first month-end decision
FETCH_FROM = date(2024, 7, 8)  # enough history for the 252-session look-back; one (UDiFF) file format
RUN_AFTER = time(19, 30)  # NSE publishes the bhavcopy in the early evening
RULE = "mom_12_1"
RANKING_SHOWN = 40
HOLD = int(os.environ.get("MOMENTUM_TRIAL_HOLD", "10"))
CAPITAL = float(os.environ.get("MOMENTUM_TRIAL_CAPITAL", "100000"))
# The same book in the backtest, ₹1 lakh once, equal split every month, 2016-02 to 2026-10 (momentum-compound.md).
BACKTEST = {"period": "2016-02 to 2026-10", "cagr": 0.267, "max_drawdown": 0.39, "benchmark_cagr": 0.140, "niftybees_cagr": 0.123}


def trading_day(day: date) -> bool:
    from quant_agents.global_markets import trading_day as known

    return known(day)


def next_session(day: date) -> date:
    nxt = day + timedelta(days=1)
    while not trading_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def month_end_session(day: date) -> date:
    """The last NSE session of day's month."""
    last = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    while not trading_day(last):
        last -= timedelta(days=1)
    return last


def next_decision(as_of: date) -> date:
    """The next month-end close at which a ranking will be recorded (this month's, or next month's once made)."""
    this = month_end_session(as_of)
    if as_of < this:
        return this
    return month_end_session(this + timedelta(days=7))


def sync(raw: Path, today: date) -> int:
    """Fetch missing files. A 404 on a past non-trading day is recorded; on a trading day it is retried later."""
    from quant_agents.research.bhavcopy import fetch_day

    got = 0
    day = FETCH_FROM
    while day <= today:
        if day.weekday() < 5 and not (raw / f"{day.isoformat()}.zip").exists() and not (raw / f"{day.isoformat()}.none").exists():
            result = fetch_day(day, raw)
            if result:
                got += 1
            elif result is False and (not trading_day(day) or day < today - timedelta(days=5)):
                (raw / f"{day.isoformat()}.none").write_text("404")
            clock.sleep(0.25)
        day += timedelta(days=1)
    return got


def _market(raw: Path):
    from quant_agents.research import bhavcopy
    from quant_agents.research import whole_market as wm

    m = wm.Market(bhavcopy.build(raw))
    last = len(m.d) - 1
    # The newest session is a month-end if the next NSE session falls in a new month (Market can't see tomorrow).
    if last not in m.month_ends and next_session(m.d[last]).month != m.d[last].month and last >= wm.LOOK:
        m.month_ends.append(last)
        m.members[last] = m.universe(last)
    return m, wm


def ranking(m, wm, t: int) -> list[dict[str, object]]:
    cols = m.members[t]
    s = wm.scores(m, RULE, t, cols)
    order = [k for k in np.argsort(-np.nan_to_num(s, nan=-np.inf)) if np.isfinite(s[k])][:RANKING_SHOWN]
    return [{"rank": n + 1, "symbol": str(m.p.symbols[cols[k]]), "score": round(float(s[k]), 4), "close": float(m.p.close[t, cols[k]])} for n, k in enumerate(order)]


def record_decisions(m, wm, now: datetime) -> list[str]:
    """Append each month-end ranking from START on, once. A later recomputation that differs is flagged, not rewritten."""
    path = DIR / "decisions.jsonl"
    logged = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            logged[row["decided_at_close"]] = row
    notes = []
    with path.open("a") as out:
        for t in sorted(m.members):
            day = m.d[t]
            if day < START:
                continue
            ranked = ranking(m, wm, t)
            key = day.isoformat()
            if key not in logged:
                out.write(json.dumps({"decided_at_close": key, "recorded_at": now.isoformat(), "trade_at_open_of": next_session(day).isoformat(), "rule": RULE, "ranking": ranked}) + "\n")
                notes.append(f"decision recorded for {key}")
            elif [r["symbol"] for r in logged[key]["ranking"][:HOLD]] != [r["symbol"] for r in ranked[:HOLD]]:
                notes.append(f"WARNING: ranking for {key} recomputes differently (data revised?)")
    return notes


def report(m, wm, now: datetime, notes: list[str]) -> dict[str, object]:
    start_t = int(np.searchsorted(m.p.days, START.toordinal(), side="right"))  # first session after the decision
    hi = len(m.d) - 1
    base = {"rule": f"12-1 momentum, top {HOLD} of the NSE Liquid-500, monthly", "method": "equal_split_compounding", "capital": CAPITAL, "hold": HOLD,
            "start_decision": START.isoformat(), "as_of_session": m.d[hi].isoformat(), "generated_at": now.isoformat(), "notes": notes, "paper_only": True,
            "next_decision": next_decision(m.d[hi]).isoformat(), "backtest": BACKTEST}
    if start_t > hi:
        decision = next((json.loads(line) for line in (DIR / "decisions.jsonl").read_text().splitlines()[::-1]), None) if (DIR / "decisions.jsonl").exists() else None
        return {**base, "status": "waiting for the first open", "pending_ranking": (decision or {}).get("ranking", [])[:25]}
    from quant_agents.research import momentum_compound as mc

    mc.HOLD, mc.CAPITAL = HOLD, CAPITAL
    sim = mc.simulate(m, start=m.d[start_t])
    marks = sim["marks"]
    ends = [t for t in m.month_ends if start_t <= t <= hi] + ([hi] if hi not in m.month_ends else [])
    values = [CAPITAL] + [marks[t] for t in ends]
    fixed = [(t, 0.0) for t in ends]
    bench = wm.benchmark_months(m, fixed, start_t)
    nifty = wm.asset_months(m, wm.chain_of(m, "NIFTYBEES"), fixed, start_t)
    growth = lambda xs: float(np.prod([1 + x for x in xs]) - 1)  # noqa: E731
    equity = marks[hi]
    holdings = sorted(sim["holdings"], key=lambda h: -h["value"])
    for h in holdings:
        h["return"] = h["value"] / h["cost"] - 1 if h["cost"] else None
    return {
        **base,
        "status": "running",
        "equity": equity,
        "cash": sim["cash_end"],
        "pnl": equity - CAPITAL,
        "return": equity / CAPITAL - 1,
        "benchmark_return": growth(bench),
        "niftybees_return": growth(nifty),
        "charges": sim["charges"],
        "months": [{"month_end": m.d[t].isoformat(), "strategy": values[k + 1] / values[k] - 1, "benchmark": b, "niftybees": n} for k, (t, b, n) in enumerate(zip(ends, bench, nifty))],
        "holdings": holdings,
        "trades": sim["trades"][-60:],
        "pending_buys": sim["pending"],
        "daily_equity": [{"day": m.d[t].isoformat(), "equity": v} for t, v in sorted(marks.items())],
    }


def _plain(value: object) -> object:
    """numpy scalars -> Python numbers; anything else -> str."""
    return value.item() if hasattr(value, "item") else str(value)


def run_once(now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    raw = DIR / "raw"
    DIR.mkdir(parents=True, exist_ok=True)
    got = sync(raw, now.astimezone(IST).date())
    m, wm = _market(raw)
    notes = record_decisions(m, wm, now)
    body = report(m, wm, now, notes)
    tmp = DIR / "report.json.tmp"
    tmp.write_text(json.dumps(body, indent=1, default=_plain))
    tmp.replace(DIR / "report.json")
    logger.info("momentum_trial fetched=%s session=%s status=%s equity=%s notes=%s", got, body["as_of_session"], body["status"], body.get("equity"), notes)
    return body


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "--once" in sys.argv:
        run_once()
        return
    done: date | None = None
    while True:
        local = datetime.now(IST)
        if local.time() >= RUN_AFTER and done != local.date():
            try:
                body = run_once()
                if body["as_of_session"] == local.date().isoformat() or not trading_day(local.date()):
                    done = local.date()  # today's file is in (or there is none): finished for the day
            except Exception:  # noqa: BLE001 - retried in 15 minutes
                logger.exception("momentum_trial run failed")
        clock.sleep(900)


if __name__ == "__main__":
    main()
