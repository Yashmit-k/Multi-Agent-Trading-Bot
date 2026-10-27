"""Global markets agent: the pre-registered timing rules, the fit, and the observe-only signal."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from contracts.enums import AgentName, Horizon
from quant_agents import global_markets as gm


def _days(n: int, start: date = date(2023, 1, 2)) -> list[date]:
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def test_close_input_uses_only_bars_before_the_session() -> None:
    bars = [(date(2026, 10, 22), 100.0, 100.0), (date(2026, 10, 23), 100.0, 102.0), (date(2026, 10, 26), 102.0, 999.0)]
    # Session 26 Oct (Monday), previous session 23 Oct: latest US close before the 26th is the 23rd's, vs the 22nd's.
    assert gm.input_value(bars, "close", date(2026, 10, 26), date(2026, 10, 23)) == pytest.approx(0.02)
    # No new bar since the previous Indian session (a foreign holiday): 0.
    assert gm.input_value(bars[:2], "close", date(2026, 10, 27), date(2026, 10, 26)) == 0.0


def test_asia_input_is_the_gap_not_the_close() -> None:
    bars = [(date(2026, 10, 23), 100.0, 100.0), (date(2026, 10, 26), 101.0, 50.0)]
    assert gm.input_value(bars, "asia_gap", date(2026, 10, 26), date(2026, 10, 23)) == pytest.approx(0.01)
    assert gm.input_value(bars, "asia_gap", date(2026, 10, 27), date(2026, 10, 26)) == 0.0


def _synthetic(n: int) -> tuple[dict[str, gm.Bars], date]:
    """Asia gaps alternate up and down; NIFTY's gap follows the Asia gap. Other inputs are flat."""
    days = _days(n + 1)
    asia, nifty = [], []
    level, n_close = 100.0, 100.0
    for i, day in enumerate(days):
        move = 0.01 * ((i * 7919) % 13 - 6) / 6
        asia.append((day, level * (1 + move), level * (1 + move)))
        level *= 1 + move
        n_open = n_close * (1 + 0.5 * move)
        nifty.append((day, n_open, n_open))
        n_close = n_open
    bars = {name: [(d, 100.0, 100.0) for d in days] for name in gm.INPUTS}
    for name in gm.ASIA:
        bars[name] = asia
    bars["nifty"] = nifty
    return bars, days[-1]


def test_outlook_points_the_way_of_asia_and_ignores_today_nifty() -> None:
    bars, today = _synthetic(2 * gm.WINDOW + 10)
    view = gm.outlook(bars, today)
    asia_today = view["inputs"]["asia"]["move_pct"]
    assert view["fit"]["correlation"] > 0.9
    assert (view["expected_gap_pct"] > 0) == (asia_today > 0)
    changed = dict(bars)
    changed["nifty"] = bars["nifty"][:-1] + [(today, 1.0, 1.0)]  # today's NIFTY bar must not matter
    assert gm.outlook(changed, today)["expected_gap_pct"] == view["expected_gap_pct"]


def test_outlook_needs_two_windows_of_history() -> None:
    bars, today = _synthetic(gm.WINDOW)
    with pytest.raises(gm.InsufficientHistory):
        gm.outlook(bars, today)


def test_signal_is_market_level_and_observe_only() -> None:
    bars, today = _synthetic(2 * gm.WINDOW + 10)
    now = datetime.combine(today, time(8, 45), gm.IST)
    signal = gm.build_signal(gm.outlook(bars, today), now, time(8, 45))
    assert signal.agent_name is AgentName.GLOBAL_MARKETS
    assert signal.symbol == "NIFTY50" and signal.horizon is Horizon.INTRADAY
    assert signal.metadata["observe_only"] is True
    assert "global.observe_only" in signal.reason_codes
    assert signal.valid_until == datetime.combine(today, time(15, 30), gm.IST).astimezone(timezone.utc)
    assert signal.signal_id == f"global-markets-{today.isoformat()}-0845"


def test_due_slot_runs_each_slot_once_and_only_on_trading_days() -> None:
    day = date(2026, 10, 27)
    at = lambda h, m: datetime.combine(day, time(h, m), gm.IST)  # noqa: E731
    trading = lambda d: d.weekday() < 5  # noqa: E731
    assert gm.due_slot(at(8, 30), set(), trading) is None
    assert gm.due_slot(at(8, 50), set(), trading) == time(8, 45)
    assert gm.due_slot(at(8, 50), {(day, time(8, 45))}, trading) is None
    assert gm.due_slot(at(9, 30), {(day, time(8, 45))}, trading) == time(9, 10)
    assert gm.due_slot(at(15, 40), set(), trading) is None
    assert gm.due_slot(at(9, 30), set(), lambda d: False) is None
