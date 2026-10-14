"""Freeze the July 1, 2025 three-symbol acceptance run.

Skips when the research snapshot is not on disk. Does not read the holdout.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from contracts.enums import Timeframe
from core_features.context import load_index_bars
from core_market_data.replay import stream_candles
from core_paper.backtest import run_backtest
from core_paper.costs import CostSchedule

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_CANDLES = ROOT / "snapshots 2" / "nifty50" / "5m" / "candles.jsonl"
START = datetime(2025, 7, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
SYMBOLS = ("RELIANCE", "TCS", "INFY")
SNAPSHOT = "nifty50_5m_20261005"
PAIRS = (
    (Decimal("0"), Decimal("0"), Decimal("-375.10")),
    (Decimal("1"), Decimal("0"), Decimal("-404.70")),
    (Decimal("2"), Decimal("0"), Decimal("-434.30")),
    (Decimal("5"), Decimal("0"), Decimal("-523.10")),
    (Decimal("0"), Decimal("1"), Decimal("-404.88")),
    (Decimal("2"), Decimal("1"), Decimal("-464.08")),
)
QUANTITIES = {"RELIANCE": 66, "TCS": 28, "INFY": 63}


@pytest.mark.skipif(not SNAPSHOT_CANDLES.is_file(), reason="nifty50_5m_20261005 snapshot is not on disk")
def test_july_20250701_ladder_matches_the_recorded_run() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "services" / "quant" / "src"))
    candles, missing, digest = stream_candles(SNAPSHOT, SYMBOLS, START, END)
    index_bars = load_index_bars(Timeframe.M5, END)
    for cost, slip, net in PAIRS:
        report = run_backtest(
            candles,
            symbols=SYMBOLS,
            timeframe="5m",
            start=START,
            end=END,
            snapshot_id=SNAPSHOT,
            candle_sha256=digest,
            initial_cash=Decimal("1000000"),
            schedule=CostSchedule.research(cost, slip),
            missing_candles=missing,
            seed=7,
            index_bars=index_bars,
        )
        assert report["candles_processed"] == 225
        assert report["signals_generated"] == 35
        assert report["orders_generated"] == 3
        assert report["orders_filled"] == 3
        assert report["positions"] == QUANTITIES
        assert Decimal(str(report["performance"]["net_pnl"])) == net
        assert report["live_enabled"] is False
