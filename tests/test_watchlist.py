"""Watchlist checklist: a steady uptrend scores high, a downtrend low; history is reported."""

from datetime import datetime, timedelta, timezone

import numpy as np

from core_paper.strategy_engine import Bars
from core_api.watchlist import CHECKS, build_watchlist

UTC = timezone.utc


def _bars(closes: np.ndarray) -> Bars:
    ends = [datetime(2024, 1, 1, 10, 0, tzinfo=UTC) + timedelta(days=i) for i in range(len(closes))]
    volume = np.linspace(1000, 2000, len(closes))
    starts = [moment - timedelta(hours=6, minutes=15) for moment in ends]
    return Bars(starts, ends, closes.copy(), closes * 1.005, closes * 0.995, closes, volume)


def test_uptrend_beats_downtrend_and_history_exists() -> None:
    n = 320
    rng = np.random.default_rng(0)
    up = 100 * np.cumprod(1 + 0.002 + rng.normal(0, 0.004, n))
    down = 100 * np.cumprod(1 - 0.003 + rng.normal(0, 0.004, n))
    nifty = 100 * np.cumprod(1 + 0.0005 + rng.normal(0, 0.003, n))
    data = {"UP": _bars(up), "DOWN": _bars(down), "NIFTY50": _bars(nifty)}
    report = build_watchlist(["UP", "DOWN"], data.get, {"UP": 0.3, "DOWN": -0.2}, min_score=7)
    scores = {row["symbol"]: row["score"] for row in report["all"]}
    assert scores["UP"] > scores["DOWN"]
    assert len(report["checks"]) == len(CHECKS) == 10
    assert report["history"]["by_price_score"]
    assert all(row["score"] >= 7 for row in report["watchlist"])
