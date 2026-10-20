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


# --- reliability weights for fusion ---------------------------------------------------------------

DESIGN_EFFECT = 5.0  # grades on the same bar across 50 stocks are not independent: discount the sample size
UNPROVEN_WEIGHT = 0.5
MIN_EFFECTIVE = 30.0


def compute(repository, now: datetime, days: int, *, excluded: set[str] | None = None, versions: dict[str, str] | None = None) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """The scorecard over the last `days`. With `versions`, only signals from each agent's current version count."""
    from contracts.enums import Timeframe

    start = window_start(now, days)
    points: list[SignalPoint] = []
    for row in repository.signal_points_since(start, with_version=versions is not None):
        signal_id, agent, horizon, symbol, stamp, signal, confidence = row[:7]
        if versions is not None and agent in versions and (len(row) < 8 or row[7] != versions[agent]):
            continue
        try:
            moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        points.append(SignalPoint(signal_id, agent, horizon, symbol, moment, float(signal), float(confidence)))
    closes = {symbol: Closes(bars) for symbol, bars in repository.closes_since(Timeframe.M5, start - timedelta(days=1)).items()}
    owner = {point.signal_id: point.agent for point in points}
    supported: dict[str, int] = {}
    approved: dict[str, int] = {}
    for ids, ok in repository.proposal_support_since(start):
        for agent in {owner[item] for item in ids if item in owner}:
            supported[agent] = supported.get(agent, 0) + 1
            if ok:
                approved[agent] = approved.get(agent, 0) + 1
    return {
        "as_of": now.isoformat(),
        "window_days": days,
        "method": {
            "intraday": "sign of signal vs 5m close 60 min later, same session",
            "swing": "sign of signal vs close at the end of the next trading session",
            "dedupe": "one sample per agent, horizon, symbol and entry bar (intraday) or session (swing)",
            "neutral_below": NEUTRAL,
        },
        "agents": score(points, closes, now, supported, approved, excluded),
    }


def reliability_weight(row: dict) -> tuple[float, str]:
    """Fusion weight from a scorecard row: 0 if proven worse than a coin flip, 0.5 if unproven, 1.0-1.5 if proven better."""
    n = int(row.get("directional") or 0)
    rate = row.get("hit_rate")
    if rate is None or n / DESIGN_EFFECT < MIN_EFFECTIVE:
        return UNPROVEN_WEIGHT, "unproven"
    effective = n / DESIGN_EFFECT
    low, high = _wilson(int(round(rate * effective)), int(round(effective)))
    if high < 0.5:
        return 0.0, "worse_than_coin_flip"
    if low > 0.5:
        return min(1.5, 1.0 + (low - 0.5) * 10), "better_than_coin_flip"
    return UNPROVEN_WEIGHT, "unproven"
