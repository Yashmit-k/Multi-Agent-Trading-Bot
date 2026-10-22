"""Watchlist: every NIFTY 50 stock scored on a checklist of conditions often read as bullish.

Each check is a plain yes/no on stored daily bars (and the agents' latest views). The score is
how many checks pass. This is a screen, not a forecast: the checklist has not been validated as
an edge, and the page shows how past high-score days actually did (`history`), so the user can see
that for themselves.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Callable

import numpy as np

from core_paper.strategy_engine import IST, Bars, _atr, _ema, _rsi, _sma, raw_indicator

CHECKS: list[tuple[str, str]] = [
    ("trend_200", "Close above its 200-day SMA (long-term uptrend)"),
    ("ema_stack", "20-day EMA above 50-day EMA (medium-term uptrend)"),
    ("momentum_20", "20-day return beats NIFTY 50's"),
    ("rsi_zone", "RSI(14) between 50 and 70 (strong, not overbought)"),
    ("macd_up", "MACD line above its signal line"),
    ("volume_up", "5-day average volume above the 20-day average"),
    ("near_high", "Within 5% of its 60-day high"),
    ("calm", "ATR(14) under 3% of price (risk is moderate)"),
    ("agents_bullish", "Agents' latest swing view is positive"),
    ("market_up", "NIFTY 50 above its 50-day EMA (supportive market)"),
]
FORWARD_SESSIONS = 10


def _series(bars: Bars) -> dict[str, np.ndarray]:
    close = bars.close
    macd = _ema(close, 12) - _ema(close, 26)
    signal = np.full(len(close), np.nan)
    valid = ~np.isnan(macd)
    if valid.sum() >= 9:
        first = int(np.argmax(valid))
        signal[first:] = _ema(macd[first:], 9)
    ret20 = np.full(len(close), np.nan)
    ret20[20:] = close[20:] / close[:-20] - 1
    return {
        "sma200": _sma(close, 200),
        "ema20": _ema(close, 20),
        "ema50": _ema(close, 50),
        "rsi": _rsi(close, 14),
        "macd": macd,
        "signal": signal,
        "vol5": _sma(bars.volume.astype(float), 5),
        "vol20": _sma(bars.volume.astype(float), 20),
        "high60": raw_indicator(bars, "highest", 60, None, None, False, {}),
        "atr_pct": _atr(bars, 14) / close * 100,
        "ret20": ret20,
    }


def _passes(s: dict[str, np.ndarray], close: np.ndarray, k: int, nifty_ret20: float | None, agents: float | None, market_up: bool | None) -> dict[str, bool | None]:
    def ok(value) -> bool | None:  # type: ignore[no-untyped-def]
        return None if value is None or (isinstance(value, float) and math.isnan(value)) else bool(value)

    def defined(*values: float) -> bool:
        return not any(math.isnan(v) for v in values)

    c = float(close[k])
    return {
        "trend_200": ok(c > s["sma200"][k]) if defined(s["sma200"][k]) else None,
        "ema_stack": ok(s["ema20"][k] > s["ema50"][k]) if defined(s["ema20"][k], s["ema50"][k]) else None,
        "momentum_20": (ok(s["ret20"][k] > nifty_ret20) if nifty_ret20 is not None and defined(s["ret20"][k]) else None),
        "rsi_zone": ok(50 <= s["rsi"][k] <= 70) if defined(s["rsi"][k]) else None,
        "macd_up": ok(s["macd"][k] > s["signal"][k]) if defined(s["macd"][k], s["signal"][k]) else None,
        "volume_up": ok(s["vol5"][k] > s["vol20"][k]) if defined(s["vol5"][k], s["vol20"][k]) else None,
        "near_high": ok(c >= 0.95 * s["high60"][k]) if defined(s["high60"][k]) else None,
        "calm": ok(s["atr_pct"][k] < 3) if defined(s["atr_pct"][k]) else None,
        "agents_bullish": None if agents is None else agents > 0,
        "market_up": market_up,
    }


def build_watchlist(
    symbols: list[str],
    load_daily: Callable[[str], Bars | None],
    agent_view: dict[str, float],
    min_score: int = 7,
) -> dict[str, object]:
    nifty = load_daily("NIFTY50")
    nifty_ret: dict[date, float] = {}
    nifty_up: dict[date, bool] = {}
    if nifty is not None and len(nifty.close) > 60:
        ema50 = _ema(nifty.close, 50)
        for k, moment in enumerate(nifty.end):
            day = moment.astimezone(IST).date()
            if k >= 20:
                nifty_ret[day] = float(nifty.close[k] / nifty.close[k - 20] - 1)
            if not math.isnan(ema50[k]):
                nifty_up[day] = bool(nifty.close[k] > ema50[k])
    rows = []
    history: dict[int, list[float]] = {}
    for symbol in symbols:
        bars = load_daily(symbol)
        if bars is None or len(bars.close) < 60:
            continue
        s = _series(bars)
        last = len(bars.close) - 1
        day = bars.end[last].astimezone(IST).date()
        passes = _passes(s, bars.close, last, nifty_ret.get(day), agent_view.get(symbol), nifty_up.get(day))
        known = [v for v in passes.values() if v is not None]
        score = sum(1 for v in known if v)
        rows.append(
            {
                "symbol": symbol,
                "as_of": day.isoformat(),
                "close": round(float(bars.close[last]), 2),
                "score": score,
                "checks_known": len(known),
                "checks": passes,
                "rsi": None if math.isnan(s["rsi"][last]) else round(float(s["rsi"][last]), 1),
                "return_20d": None if math.isnan(s["ret20"][last]) else round(float(s["ret20"][last]) * 100, 2),
                "atr_pct": None if math.isnan(s["atr_pct"][last]) else round(float(s["atr_pct"][last]), 2),
                "agent_view": agent_view.get(symbol),
            }
        )
        # History of the eight price checks (agents' views are not stored that far back): score vs the next 10 sessions.
        for k in range(200, last - FORWARD_SESSIONS + 1):
            past_day = bars.end[k].astimezone(IST).date()
            past = _passes(s, bars.close, k, nifty_ret.get(past_day), None, nifty_up.get(past_day))
            price_checks = [v for key, v in past.items() if key != "agents_bullish" and v is not None]
            if len(price_checks) < 8:
                continue
            forward = float(bars.close[k + FORWARD_SESSIONS] / bars.close[k] - 1)
            history.setdefault(sum(1 for v in price_checks if v), []).append(forward)
    rows.sort(key=lambda row: (-int(row["score"]), -(row["return_20d"] or 0)))
    table = [
        {
            "price_score": score,
            "samples": len(values),
            "mean_forward_return_pct": round(float(np.mean(values)) * 100, 2),
            "share_positive": round(float(np.mean([v > 0 for v in values])), 3),
        }
        for score, values in sorted(history.items())
    ]
    return {
        "as_of": datetime.now(IST).isoformat(),
        "checks": [{"key": key, "label": label} for key, label in CHECKS],
        "min_score": min_score,
        "watchlist": [row for row in rows if int(row["score"]) >= min_score],
        "all": rows,
        "history": {"forward_sessions": FORWARD_SESSIONS, "by_price_score": table},
    }
