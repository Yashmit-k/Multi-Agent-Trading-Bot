"""Live agent scorecard: does each agent's signal sign predict the stock's next move?

Scored only from stored data, with no look-ahead:
- entry price: close of the latest 5-minute bar ending at or before the signal time;
- INTRADAY exit: close of the 5-minute bar ending at or before entry + 60 minutes, same session;
- SWING exit: close of the last 5-minute bar of the next trading session after the entry bar.
A signal is scored only once its exit bar exists. Repeats are collapsed to one sample per
(agent, horizon, symbol, entry bar) for INTRADAY and per (agent, horizon, symbol, session) for SWING,
because agents re-publish the same view every few minutes. |signal| < NEUTRAL counts as neutral.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NEUTRAL = 0.05
INTRADAY_HOLD = timedelta(minutes=60)


@dataclass(frozen=True)
class SignalPoint:
    signal_id: str
    agent: str
    horizon: str
    symbol: str
    timestamp: datetime
    signal: float
    confidence: float


class Closes:
    """5-minute closes for one symbol, sorted by bar end."""

    def __init__(self, bars: list[tuple[datetime, float]]) -> None:
        bars = sorted(bars)
        self.ends = [end for end, _ in bars]
        self.closes = [close for _, close in bars]
        self.last_by_day: dict[date, int] = {}
        for index, end in enumerate(self.ends):
            self.last_by_day[end.astimezone(IST).date()] = index
        self.days = sorted(self.last_by_day)

    def at_or_before(self, moment: datetime) -> int | None:
        index = bisect.bisect_right(self.ends, moment) - 1
        return index if index >= 0 else None


def forward(closes: Closes, point: SignalPoint, now: datetime) -> tuple[object, float] | None:
    """(dedupe bucket, forward return) or None when the outcome is not known yet."""
    entry = closes.at_or_before(point.timestamp)
    if entry is None:
        return None
    entry_end = closes.ends[entry]
    entry_day = entry_end.astimezone(IST).date()
    if point.horizon == "INTRADAY":
        target = entry_end + INTRADAY_HOLD
        if target > now:
            return None
        exit_index = closes.at_or_before(target)
        if exit_index is None or exit_index <= entry or closes.ends[exit_index].astimezone(IST).date() != entry_day:
            return None
        if target - closes.ends[exit_index] > timedelta(minutes=10):  # the session ended before the hour was up
            return None
        bucket: object = entry_end
    else:
        position = bisect.bisect_right(closes.days, entry_day)
        if position >= len(closes.days):
            return None
        next_day = closes.days[position]
        exit_index = closes.last_by_day[next_day]
        if closes.ends[exit_index].astimezone(IST).hour < 15 or closes.ends[exit_index] > now:
            return None  # next session not finished
        bucket = entry_day
    start, end = closes.closes[entry], closes.closes[exit_index]
    if start <= 0:
        return None
    return bucket, end / start - 1


def _wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 5:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def score(
    points: list[SignalPoint],
    closes: dict[str, Closes],
    now: datetime,
    supported: dict[str, int] | None = None,
    approved: dict[str, int] | None = None,
    excluded: set[str] | None = None,
) -> list[dict[str, object]]:
    samples: dict[tuple[str, str], dict[tuple[str, object], tuple[float, float]]] = defaultdict(dict)
    published: dict[tuple[str, str], int] = defaultdict(int)
    for point in sorted(points, key=lambda item: item.timestamp):
        key = (point.agent, point.horizon)
        published[key] += 1
        series = closes.get(point.symbol)
        if series is None:
            continue
        outcome = forward(series, point, now)
        if outcome is None:
            continue
        bucket, ret = outcome
        samples[key].setdefault((point.symbol, bucket), (point.signal, ret))  # first view in the bucket
    rows: list[dict[str, object]] = []
    for key in sorted(published):
        agent, horizon = key
        values = list(samples[key].values())
        directional = [(s, r) for s, r in values if abs(s) >= NEUTRAL]
        hits = sum(1 for s, r in directional if (s > 0) == (r > 0) and r != 0)
        n = len(directional)
        signed = [math.copysign(1, s) * r for s, r in directional]
        low, high = _wilson(hits, n)
        rows.append(
            {
                "agent": agent,
                "horizon": horizon,
                "published": published[key],
                "scored": len(values),
                "directional": n,
                "neutral": len(values) - n,
                "hit_rate": hits / n if n else None,
                "hit_rate_95": [low, high] if n else None,
                "mean_signed_return_bps": (sum(signed) / n * 10_000) if n else None,
                "information_coefficient": _correlation([s for s, _ in values], [r for _, r in values]),
                "beats_coin_flip": bool(n >= 30 and low > 0.5),
                "proposals_supported": (supported or {}).get(agent, 0) if horizon in ("SWING", "INTRADAY") else 0,
                "approved_supported": (approved or {}).get(agent, 0),
                "in_fusion": agent not in (excluded or set()),
            }
        )
    return rows


def window_start(now: datetime, days: int) -> datetime:
    return (now - timedelta(days=days)).astimezone(timezone.utc)
