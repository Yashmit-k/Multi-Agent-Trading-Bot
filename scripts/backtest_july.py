"""Three-symbol July 2025 acceptance. Reads snapshots 2 and does not write it."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from contracts.enums import Timeframe
from core_features.context import load_index_bars
from core_market_data.replay import stream_candles
from core_paper.backtest import run_backtest
from core_paper.costs import CostSchedule

ROOT = Path(__file__).resolve().parents[1]
START = datetime(2025, 7, 1, 3, 45, tzinfo=timezone.utc)
END = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
SYMBOLS = ("RELIANCE", "TCS", "INFY")
SNAPSHOT = "nifty50_5m_20261005"
PAIRS = (
    (Decimal("0"), Decimal("0")),
    (Decimal("1"), Decimal("0")),
    (Decimal("2"), Decimal("0")),
    (Decimal("5"), Decimal("0")),
    (Decimal("0"), Decimal("1")),
    (Decimal("2"), Decimal("1")),
)


def main() -> None:
    watched = [
        ROOT / "snapshots 2" / "nifty50" / "5m" / "candles.jsonl",
        ROOT / "snapshots 2" / "nifty50" / "5m" / "manifest.json",
        ROOT / "snapshots 2" / "nifty50" / "1D" / "candles.jsonl",
        ROOT / "snapshots" / "holdout_after_20261005",
    ]
    before = {str(path): (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None for path in watched}
    candles, missing, digest = stream_candles(SNAPSHOT, SYMBOLS, START, END)
    index_bars = load_index_bars(Timeframe.M5, END)
    ladder = []
    for cost, slip in PAIRS:
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
        ladder.append(
            {
                "transaction_cost_bps": str(cost),
                "slippage_bps": str(slip),
                "candles_processed": report["candles_processed"],
                "signals_generated": report["signals_generated"],
                "orders_generated": report["orders_generated"],
                "orders_filled": report["orders_filled"],
                "positions": report["positions"],
                "portfolio_value": report["portfolio_value"],
                "net_pnl": report["performance"]["net_pnl"],
                "sharpe": report["performance"]["sharpe"],
                "periods_per_year": report["performance"]["periods_per_year"],
                "live_enabled": report["live_enabled"],
            }
        )
        print(
            f"cost {cost} slip {slip}: candles {report['candles_processed']} "
            f"signals {report['signals_generated']} orders {report['orders_generated']} "
            f"fills {report['orders_filled']} positions {report['positions']} "
            f"portfolio {report['portfolio_value']}"
        )
    after = {str(path): (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None for path in watched}
    destination = ROOT / "datasets" / "direction" / "backtest-july.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"ladder": ladder, "files_unchanged": before == after}, indent=2), encoding="utf-8")
    print("files_unchanged", before == after)
    print("wrote", destination)


if __name__ == "__main__":
    main()
