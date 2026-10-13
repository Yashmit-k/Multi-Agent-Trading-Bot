"""Synthetic TimesFM-3 score rules. These tests do not download weights or open snapshots."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from quant_agents.research.timesfm3.paths import SnapshotRefused, _refuse_unless_daily_snapshot
from quant_agents.research.timesfm3.scores import (
    MIN_CONTEXT,
    ClosePoint,
    context_is_safe,
    decision_rows,
    flat_mean_net,
    last_close_forecasts,
    net_return,
    score_forecasts,
)

UTC = timezone.utc


def _point(symbol: str, day: int, close: str, *, year: int = 2024) -> ClosePoint:
    end = datetime(year, 1, 1, 10, 0, tzinfo=UTC) + timedelta(days=day - 1)
    return ClosePoint(symbol=symbol, end=end, close=Decimal(close))


def _series(symbol: str = "RELIANCE", days: int = MIN_CONTEXT + 2) -> list[ClosePoint]:
    return [_point(symbol, day, "100") for day in range(1, days + 1)]


def test_unchanged_price_costs_four_bp() -> None:
    assert net_return(Decimal("100"), Decimal("100")) == Decimal("-0.0004")
    assert net_return(Decimal("100"), Decimal("101")) == Decimal("0.01") - Decimal("0.0002") - Decimal("1.01") * Decimal("0.0002")


def test_context_cannot_include_the_label() -> None:
    decision = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    label = decision + timedelta(days=1)
    earlier = decision - timedelta(days=1)
    assert context_is_safe((earlier, decision), decision, label) is True
    assert context_is_safe((earlier, label), decision, label) is False
    assert context_is_safe((decision,), decision, decision) is False


def test_short_history_and_2025_labels_are_not_scored() -> None:
    short = _series(days=MIN_CONTEXT)
    assert decision_rows(short) == ()
    long = _series(days=MIN_CONTEXT + 1)
    assert len(decision_rows(long)) == 1
    crossing = long[:-1] + [_point("RELIANCE", 2, "100", year=2025)]
    assert decision_rows(crossing) == ()


def test_tatamotors_and_non_close_bars_are_excluded() -> None:
    rows = _series(days=MIN_CONTEXT + 1)
    rows.extend(_point("TATAMOTORS", day, "100") for day in range(1, MIN_CONTEXT + 2))
    intraday = ClosePoint(
        symbol="INFY",
        end=datetime(2024, 1, 10, 9, 0, tzinfo=UTC),
        close=Decimal("100"),
    )
    scored = decision_rows([*rows, intraday])
    assert {row.symbol for row in scored} == {"RELIANCE"}


def test_long_forecast_pays_the_realized_net_and_flat_pays_nothing() -> None:
    series = _series(days=MIN_CONTEXT + 1)
    up = series[:-1] + [_point("RELIANCE", MIN_CONTEXT + 1, "110")]
    rows = decision_rows(up)
    won = score_forecasts(rows, [Decimal("101")])
    assert won.hits == 1
    assert won.trade_count == 1
    assert won.mean_net_all == net_return(Decimal("100"), Decimal("110"))
    missed = score_forecasts(rows, [Decimal("99")])
    assert missed.hits == 0
    assert missed.trade_count == 0
    assert missed.mean_net_all == Decimal(0)
    assert flat_mean_net(rows) == Decimal(0)
    last = score_forecasts(rows, last_close_forecasts(rows))
    assert last.trade_count == 0
    assert last.hits == 0
    assert last.mean_net_all == Decimal(0)
    assert last.mean_price_error == Decimal("10")


def test_holdout_and_short_tape_paths_are_refused() -> None:
    with pytest.raises(SnapshotRefused):
        _refuse_unless_daily_snapshot(Path("/tmp/snapshots/holdout_after_20261005/1D/candles.jsonl"))
    with pytest.raises(SnapshotRefused):
        _refuse_unless_daily_snapshot(Path("/tmp/snapshots/nifty50/1D/candles.jsonl"))
    with pytest.raises(SnapshotRefused):
        _refuse_unless_daily_snapshot(Path("/tmp/snapshots 2/nifty50/5m/candles.jsonl"))


def test_package_is_not_imported_by_the_research_package_or_the_worker() -> None:
    root = Path(__file__).resolve().parents[2]
    research_init = (root / "src" / "quant_agents" / "research" / "__init__.py").read_text(encoding="utf-8")
    worker = Path(__file__).resolve().parents[3] / "core" / "worker" / "src" / "core_worker" / "__main__.py"
    assert "timesfm" not in research_init
    assert "timesfm" not in worker.read_text(encoding="utf-8")
    forecast = (root / "src" / "quant_agents" / "research" / "timesfm3" / "forecast.py").read_text(encoding="utf-8")
    assert "from timesfm3.mlx import TimesFM3Forecaster" not in forecast.split("def median_forecasts", 1)[0]
