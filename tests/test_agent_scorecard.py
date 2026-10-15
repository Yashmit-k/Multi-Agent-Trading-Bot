"""Agent scorecard: forward returns from stored bars only, deduped, no look-ahead."""

from datetime import datetime, timedelta, timezone

from core_api.scorecard import Closes, SignalPoint, forward, score

UTC = timezone.utc
OPEN = datetime(2026, 10, 14, 3, 50, tzinfo=UTC)  # 09:20 IST


def _closes(day0: list[float], day1: list[float] | None = None) -> Closes:
    bars = [(OPEN + timedelta(minutes=5 * i), price) for i, price in enumerate(day0)]
    if day1:
        start = OPEN + timedelta(days=1)
        bars += [(start + timedelta(minutes=5 * i), price) for i, price in enumerate(day1)]
    return Closes(bars)


def _point(signal: float, horizon: str = "INTRADAY", at: datetime = OPEN, agent: str = "momentum", sid: str = "s") -> SignalPoint:
    return SignalPoint(sid, agent, horizon, "TCS", at, signal, abs(signal))


def test_intraday_needs_the_hour_to_have_passed() -> None:
    closes = _closes([100 + i for i in range(20)])
    assert forward(closes, _point(0.5), OPEN + timedelta(minutes=30)) is None
    bucket, ret = forward(closes, _point(0.5), OPEN + timedelta(hours=2))  # type: ignore[misc]
    assert bucket == OPEN and abs(ret - 0.12) < 1e-9  # 100 -> 112 after 12 bars


def test_swing_uses_next_session_close_once_it_is_done() -> None:
    day = [100.0] * 75  # 09:20 .. 15:30
    nxt = [100.0] * 74 + [103.0]
    closes = _closes(day, nxt)
    assert forward(closes, _point(0.4, "SWING"), OPEN + timedelta(days=1, hours=2)) is None
    _, ret = forward(closes, _point(0.4, "SWING"), OPEN + timedelta(days=2))  # type: ignore[misc]
    assert abs(ret - 0.03) < 1e-9


def test_repeats_collapse_and_neutral_is_not_a_hit() -> None:
    closes = {"TCS": _closes([100 + i for i in range(30)])}
    now = OPEN + timedelta(hours=3)
    points = [
        _point(0.5, sid="a"),
        _point(0.6, sid="b"),  # same bar: collapsed
        _point(-0.5, at=OPEN + timedelta(minutes=5), sid="c"),  # wrong way
        _point(0.01, at=OPEN + timedelta(minutes=10), sid="d"),  # neutral
    ]
    [row] = score(points, closes, now, supported={"momentum": 2}, excluded={"news"})
    assert row["published"] == 4 and row["scored"] == 3 and row["neutral"] == 1
    assert row["directional"] == 2 and row["hit_rate"] == 0.5
    assert row["proposals_supported"] == 2 and row["in_fusion"] is True
    assert row["beats_coin_flip"] is False
